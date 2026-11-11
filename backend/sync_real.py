"""One-off / on-demand real data sync from API-Football into the app's schema.
Run: python sync_real.py            (all leagues)
     python sync_real.py eng-pl     (one league)
Requires an active API-Football plan with current-season access (Pro+).
"""
import os
import sys
import asyncio
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path
import httpx
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient


import cups
from leagues_meta import CUP_META, LEAGUE_META
ROOT = Path(__file__).parent
load_dotenv(ROOT / ".env")

KEY = os.environ["API_FOOTBALL_KEY"]
BASE = "https://v3.football.api-sports.io"
HEADERS = {"x-apisports-key": KEY}

client = AsyncIOMotorClient(os.environ["MONGO_URL"])
db = client[os.environ["DB_NAME"]]

# my league_id -> API-Football metadata lives in leagues_meta.py, so server.py can share
# the same list — see the note there about the two copies silently disagreeing.
#
# Fixtures per league whose statistics we pull. This is what decides HISTORY DEPTH:
# a 20-team league plays 10 fixtures a round, so 120 fixtures was only ~12 rounds and
# every team topped out at ~12-13 games no matter how long the season had run. 250
# covers roughly 12-13 rounds beyond that — about 25 games a team, comfortably past the
# 20 that team.real_matches keeps.
#
# WHY 250 AND NOT MORE: only UNCACHED fixtures cost a call (see the fixture_stats lookup
# below), so the one-off spend of raising this is (new cap - what is already cached) per
# league. From the old 120 that is ~130 calls a league, ~3.5k across 27 leagues — which
# fits inside a day's quota on API-Football's Pro plan. At 400 it was ~7.6k, which would
# have run the quota dry mid-sync and left the job half done.
#
# Past results never change and fixture_stats is cached permanently, so this is a one-off
# spend, not a recurring one, and a run that stops early RESUMES rather than repeats.
# Raise it with the STATS_CAP env var once the first pass has settled — no deploy needed.
STATS_CAP = int(os.environ.get("STATS_CAP", "250"))
# Upcoming fixtures stored per league. These come out of the /fixtures call the sync
# already makes, so a bigger number costs NOTHING extra in API calls — and the old
# value of 10 was silently capping every downstream "next N days" view: a league
# playing a weekend round plus a midweek round could not fit inside it.
#
# 40 was about four rounds — roughly a fortnight for a league playing midweek, which was
# fine while the board could not look past 14 days. It now looks a month ahead, and 40
# would have quietly truncated that window the same way 10 truncated the old one: the
# later fixtures simply would not be in the database to find. A 20-team league plays 10
# a round, so 80 covers a month even with two rounds a week.
UPCOMING_FIXTURES = 80

# WHICH STATUSES COUNT AS "NOT YET PLAYED", and the one that was missing.
#
# This filter used to be the literal tuple ("NS", "TBD") written out twice — once in the
# league sync and once in the cup sync. Both were blind to PST, which is the status a
# postponed fixture carries, and the consequence is not that a postponed game shows the
# wrong date: it is that the game DISAPPEARS. The sync replaces a league's upcoming
# fixtures with what it fetched, so the moment a match was postponed it stopped matching
# here and was deleted, and nothing downstream could report a fixture that was not there.
#
# Found on Kristiansund v Vålerenga, postponed from Saturday 7 November 2026 after an
# illness outbreak and rescheduled to the Monday. The fixture was not in the database at
# all, so it could not be projected, could not be priced, and did not appear on any board
# — and there was no error anywhere, because deleting a fixture the provider no longer
# lists as NS is the correct behaviour for a fixture that has actually been cancelled.
#
# A POSTPONED MATCH IS ONLY UPCOMING ONCE IT HAS A NEW DATE, which is what separates the
# two things PST means. Rescheduled: the provider moves the date forward and the fixture
# is an ordinary upcoming game that happens to have been moved. Postponed indefinitely:
# the date stays on the round it was meant to be played in, which is now in the past.
# Storing the second kind would put a game that is not going to be played onto the board,
# so PST is admitted on the DATE rather than on the status alone.
#
# NOTHING ELSE JOINS THIS LIST. SUSP and INT are matches already in progress, so part of
# their corner count has been taken and pricing them from zero would be wrong. ABD, CANC,
# AWD and WO are over, however they ended. Each of those is correctly deleted today.
#
# THIS COSTS NO API CALLS. Every fixture here came out of the single /fixtures?league&
# season response the sync already makes, so admitting more of them is free.
UPCOMING_STATUSES = ("NS", "TBD")


def fixture_dt(f):
    """The kick-off as an aware UTC datetime, or None if it cannot be read.

    The provider sends "2026-11-09T19:00:00+00:00", but a missing or malformed date has
    to be survivable: this runs over every fixture of every league and one bad row must
    not end a sync.
    """
    raw = ((f or {}).get("fixture") or {}).get("date")
    if not isinstance(raw, str) or not raw:
        return None
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt


def is_upcoming(f, now=None) -> bool:
    """Has this fixture not been played yet, and is it going to be?

    NS and TBD pass on the status alone, exactly as before — a past NS is the provider
    lagging behind a game that has kicked off, and every reader downstream already
    filters on the date. PST passes only with a kick-off in the FUTURE, because that is
    what distinguishes a match that has been moved from one that has merely been called
    off; see UPCOMING_STATUSES above.
    """
    short = (((f or {}).get("fixture") or {}).get("status") or {}).get("short")
    if short in UPCOMING_STATUSES:
        return True
    if short != "PST":
        return False
    dt = fixture_dt(f)
    return dt is not None and dt > (now or datetime.now(timezone.utc))


# A GAME CAN FINISH THREE WAYS AND ONLY ONE OF THEM IS "FT".
#
# The league syncs filter on `status == "FT"` and that is correct for a league, where
# nothing goes to extra time. It is wrong for a cup: an EFL Trophy tie level after ninety
# minutes is settled on penalties, and the provider marks those AET and PEN. Filtering FT
# alone would drop exactly the ties that went the distance — a biased hole in the record
# rather than a random one, since a drawn game is a different game from a decided one.
#
# The corner statistics for an AET fixture cover the whole match, which is also what the
# corner lines were priced on, so no adjustment belongs here.
FINISHED_STATUSES = ("FT", "AET", "PEN")

# HOW LONG A PLAYED FIXTURE STAYS ON THE SITE.
#
# Rebuilt from the provider's own fixture list on every sync, so nothing accumulates and
# there is no pruning job to forget: a game simply stops being re-inserted once it falls
# outside the window. That also means the window can be changed by editing this number,
# with the next sync applying it in both directions.
PLAYED_KEEP_DAYS = 30

# Cup statistics cost ONE CALL PER FIXTURE and league statistics cost nothing — the league
# syncs already fetch and permanently cache them to build team history, while sync_cup
# fetches none at all. So this caps the cup path only. Newest first, because a results page
# is read from the top and the most recent round is the one anyone is looking for.
PLAYED_STATS_CAP = 40


def is_recently_played(f, now=None, days=PLAYED_KEEP_DAYS) -> bool:
    """Has this fixture been played, and recently enough to still be worth showing?

    Both halves matter. Without the status test an abandoned or postponed game would be
    kept as a result; without the date test the window would be the whole season, which
    is a different feature and a much larger one.
    """
    short = (((f or {}).get("fixture") or {}).get("status") or {}).get("short")
    if short not in FINISHED_STATUSES:
        return False
    dt = fixture_dt(f)
    if dt is None:
        return False
    cutoff = (now or datetime.now(timezone.utc)) - timedelta(days=days)
    return dt >= cutoff


def _as_int(v):
    """An integer stat, or None. Bools are refused: isinstance(True, int) is True, and a
    True sneaking into a corner count would render as 1 corner and settle as a 1+ hit."""
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        return None
    return int(v)


def result_fields(f, stats=None) -> dict:
    """The outcome half of a played fixture: how it finished, the score, the corners.

    `stats` is a db.fixture_stats document — keyed by the PROVIDER's fixture id, not ours
    — or None when no statistics call has been made for this game yet.

    CORNERS ARE None AND NEVER ZERO WHEN THEY ARE UNKNOWN. A 0-0 corner count is a real
    result, and "nobody has fetched this yet" is not; a results page that prints 0 for the
    second is wrong in the most believable way available to it. `corners_known` is carried
    so a reader does not have to infer the difference from a blank.
    """
    fx = (f or {}).get("fixture") or {}
    g = (f or {}).get("goals") or {}
    s = stats or {}
    hc, ac = _as_int(s.get("home_corners")), _as_int(s.get("away_corners"))
    total = hc + ac if hc is not None and ac is not None else None
    return {
        "status": "played",
        # FT, AET or PEN — whether a tie was decided inside ninety minutes is a fact about
        # the game that a corner count cannot show and a reader will want.
        "finished_as": (fx.get("status") or {}).get("short"),
        "home_goals": _as_int(g.get("home")), "away_goals": _as_int(g.get("away")),
        "home_corners": hc, "away_corners": ac, "total_corners": total,
        "corners_known": total is not None,
    }


# Shot-volume stats pulled out of /fixtures/statistics alongside corners. The provider
# labels these inconsistently across leagues (and "Dangerous Attacks" is only present
# where the coverage includes it), so each feature matches on a set of normalised
# aliases. A stat the provider did NOT report is stored as None, never 0 — a blank
# must not read as "zero blocked shots" when this data is later fitted on.
STAT_TYPES = {
    "shots": ("total shots", "shots total"),
    "shots_on_target": ("shots on goal", "shots on target"),
    "blocked_shots": ("blocked shots", "shots blocked"),
    "dangerous_attacks": ("dangerous attacks", "attacks dangerous"),
    # Cards ride along in the SAME statistics block, so these cost nothing extra on any
    # fixture the sync was already fetching. They are counts only — the MINUTE of a
    # sending-off comes from /fixtures/events via backfill_goal_events.py, which prefers
    # its own numbers where it has run.
    "red_cards": ("red cards", "cards red"),
    "yellow_cards": ("yellow cards", "cards yellow"),
    # Fouls, for the same reason and the same price. Reds are far too rare to estimate a
    # team rate from — 1 in 9 games is a 2%-44% interval — but fouls happen twenty-odd
    # times a match, so a team's foul rate against the league's is the DENSE version of
    # "this side is likely to get carded".
    "fouls": ("fouls", "total fouls", "fouls committed"),
}


def _feature_sample(own: dict, opp: dict) -> dict:
    """Feature keys for one side of one fixture, as stored on team.real_matches.

    `shots_*` are coerced to ints because the live v2 lambda already consumes them and
    must not start seeing None; the new features keep None so an uncovered fixture stays
    distinguishable from a genuine zero."""
    out = {}
    for f in STAT_TYPES:
        mine, theirs = own.get(f), opp.get(f)
        if f == "shots":
            mine, theirs = mine or 0, theirs or 0
        out[f"{f}_for"], out[f"{f}_against"] = mine, theirs
    return out


def _norm_stat(name) -> str:
    return str(name or "").strip().lower().replace("_", " ").replace("-", " ")


def _stat_int(value):
    """API-Football values arrive as ints, numeric strings, "45%" or null."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        v = value.strip().rstrip("%")
        if v.lstrip("-").isdigit():
            return int(v)
    return None


def parse_team_stats(statistics) -> dict:
    """One team's statistics block -> {feature: int|None} for every STAT_TYPES entry."""
    by_type = {_norm_stat(s.get("type")): s.get("value") for s in (statistics or [])}
    out = {}
    for feature, aliases in STAT_TYPES.items():
        val = None
        for alias in aliases:
            if alias in by_type:
                val = _stat_int(by_type[alias])
                if val is not None:
                    break
        out[feature] = val
    out["corners"] = _stat_int(by_type.get("corner kicks"))
    return out


async def af_get(hc, path, params=None, retries=6):
    for attempt in range(retries):
        r = await hc.get(f"{BASE}{path}", params=params or {}, headers=HEADERS, timeout=30.0)
        if r.status_code == 429:
            await asyncio.sleep(15)
            continue
        r.raise_for_status()
        data = r.json()
        errs = data.get("errors")
        if isinstance(errs, dict) and errs.get("rateLimit"):
            await asyncio.sleep(15)
            continue
        if errs:
            raise RuntimeError(f"{path} -> {errs}")
        await asyncio.sleep(0.25)
        return data["response"]
    raise RuntimeError(f"{path} -> rate limited after {retries} retries")


def season_from(entry):
    """The current season year out of a /leagues entry, newest as a fallback."""
    seasons = (entry or {}).get("seasons") or []
    cur = next((s["year"] for s in seasons if s.get("current")), None)
    return cur or max((s["year"] for s in seasons),
                      default=int(os.environ.get("API_FOOTBALL_SEASON", "2024")))


async def league_entry(hc, api_id):
    """The provider's own record of one competition. One call, two uses: the season to
    sync, and — for a cup — the name to check the id against before writing anything."""
    resp = await af_get(hc, "/leagues", {"id": api_id})
    return resp[0] if resp else None


async def current_season(hc, api_id):
    return season_from(await league_entry(hc, api_id))


def _round_label(raw):
    if not raw:
        return None
    raw = str(raw).strip()
    import re
    m = re.match(r"^Regular Season\s*-\s*(\d+)$", raw)
    if m:
        return f"Round {m.group(1)}"
    return raw


def _synth_matches(mean_for, mean_ag, n, rng):
    out = []
    for i in range(n):
        is_home = i % 2 == 0
        mf = mean_for * (1.12 if is_home else 0.9)
        ma = mean_ag * (0.9 if is_home else 1.12)
        out.append({"home": is_home,
                    "corners_for": max(0, int(round(rng.gauss(mf, 1.6)))),
                    "corners_against": max(0, int(round(rng.gauss(ma, 1.6))))})
    return out


async def sync_league(hc, my_lid):
    meta = LEAGUE_META[my_lid]
    api_id = meta["api"]
    season = await current_season(hc, api_id)
    print(f"[{my_lid}] api={api_id} season={season}")

    teams_resp = await af_get(hc, "/teams", {"league": api_id, "season": season})
    team_names = {t["team"]["id"]: t["team"]["name"] for t in teams_resp}

    fixtures = await af_get(hc, "/fixtures", {"league": api_id, "season": season})
    ft = [f for f in fixtures if f["fixture"]["status"]["short"] == "FT"]
    ns = [f for f in fixtures if is_upcoming(f)]
    # Top up from last season whenever this one has not yet produced enough finished
    # matches to fill the pool. The old trigger was `< 40`, which only ever fired in the
    # opening weeks of a season — a league 12 rounds in had 120 games, cleared the bar,
    # and every team was still stuck on ~12 matches of history.
    if len(ft) < STATS_CAP:
        try:
            prev = await af_get(hc, "/fixtures", {"league": api_id, "season": season - 1})
            ft += [f for f in prev if f["fixture"]["status"]["short"] == "FT"]
        except Exception as e:
            print(f"[{my_lid}] prev season fetch skipped: {e}")
    ft.sort(key=lambda f: f["fixture"]["date"])
    ns.sort(key=lambda f: f["fixture"]["date"])
    print(f"[{my_lid}] teams={len(team_names)} FT(pool)={len(ft)} upcoming={len(ns)}")

    # gather real corner samples from most recent FT fixtures (include prev-season team ids)
    all_team_ids = set(team_names.keys())
    for f in ft:
        all_team_ids.add(f["teams"]["home"]["id"])
        all_team_ids.add(f["teams"]["away"]["id"])
    samples = {tid: [] for tid in all_team_ids}
    league_corners = []
    recent = ft[-STATS_CAP:] if len(ft) > STATS_CAP else ft
    recent_ids = [f["fixture"]["id"] for f in recent]
    # PERSISTENT CACHE: past results never change — only fetch fixtures we haven't seen before
    cached = {}
    async for c in db.fixture_stats.find({"_id": {"$in": recent_ids}}):
        cached[c["_id"]] = c
    fetched = 0
    coverage = {f: 0 for f in STAT_TYPES}
    coverage["fixtures"] = 0
    for f in recent:
        fid = f["fixture"]["id"]
        hid = f["teams"]["home"]["id"]
        aid = f["teams"]["away"]["id"]
        hname = f["teams"]["home"]["name"]
        aname = f["teams"]["away"]["name"]
        fdate = f["fixture"]["date"]
        # goals come free from the fixture object (no extra API call)
        g = f.get("goals") or {}
        hth = ((f.get("score") or {}).get("halftime") or {})
        hg, ag = (g.get("home") or 0), (g.get("away") or 0)
        hfg, afg = (hth.get("home") or 0), (hth.get("away") or 0)
        # WHICH SEASON THIS GAME BELONGS TO, taken from the fixture rather than inferred.
        #
        # THE POOL MIXES SEASONS BY DESIGN. When the current season has produced fewer than
        # STATS_CAP finished games, the block above tops up from `season - 1` — which is what
        # gives a team twenty games of history in August instead of three. That is the right
        # trade, and it was invisible: nothing downstream could tell a game played six weeks
        # ago from one played last April, so "won 5+ in 7 of 10" could be 5 of 7 this season
        # and two from a side that has since changed manager, formation and half its squad.
        #
        # The provider labels every fixture with its own season, so this is its answer and not
        # a guess from the date — which would need a different cutoff for every league, since
        # Brazil, Japan and MLS run on the calendar year and Europe does not.
        fseason = (f.get("league") or {}).get("season")
        c = cached.get(fid)
        if c:
            hc_, ac_, hs_, as_ = c["home_corners"], c["away_corners"], c["home_shots"], c["away_shots"]
            # shot-volume features can't be self-healed from the fixture object — they need a
            # statistics call, so older cache docs read None here until backfill_shots.py runs
            home_feat = {f: c.get(f"home_{f}") for f in STAT_TYPES}
            away_feat = {f: c.get(f"away_{f}") for f in STAT_TYPES}
            # self-heal: backfill goals onto older cache docs that predate goal capture
            if c.get("home_goals") is None:
                await db.fixture_stats.update_one({"_id": fid}, {"$set": {
                    "home_goals": hg, "away_goals": ag, "home_fh_goals": hfg, "away_fh_goals": afg}})
        else:
            try:
                st = await af_get(hc, "/fixtures/statistics", {"fixture": fid})
            except Exception as e:
                print(f"  stat {fid} err {e}"); continue
            per_team = {t["team"]["id"]: parse_team_stats(t.get("statistics")) for t in st}
            if hid not in per_team or aid not in per_team:
                continue
            home_feat, away_feat = per_team[hid], per_team[aid]
            if home_feat["corners"] is None or away_feat["corners"] is None:
                continue
            hc_, ac_ = home_feat["corners"], away_feat["corners"]
            hs_, as_ = home_feat["shots"] or 0, away_feat["shots"] or 0
            fetched += 1
            for feat in STAT_TYPES:
                coverage[feat] += sum(1 for side in (home_feat, away_feat) if side[feat] is not None)
            coverage["fixtures"] += 1
            await db.fixture_stats.update_one({"_id": fid}, {"$set": {
                "_id": fid, "league_id": my_lid, "date": fdate, "season": fseason,
                "home_id": hid, "away_id": aid,
                "home_corners": hc_, "away_corners": ac_,
                "home_shots": hs_, "away_shots": as_,
                **{f"home_{f}": home_feat[f] for f in STAT_TYPES},
                **{f"away_{f}": away_feat[f] for f in STAT_TYPES},
                "features_at": datetime.now(timezone.utc).isoformat(),
                "home_goals": hg, "away_goals": ag,
                "home_fh_goals": hfg, "away_fh_goals": afg}}, upsert=True)
        league_corners += [hc_, ac_]
        if hid in samples:
            samples[hid].append({"home": True, "corners_for": hc_, "corners_against": ac_, "shots_for": hs_,
                                 "goals_for": hg, "goals_against": ag, "fh_goals_for": hfg,
                                 "fh_goals_against": afg, "date": fdate, "season": fseason,
                                 "opponent": aname, **_feature_sample(home_feat, away_feat)})
        if aid in samples:
            samples[aid].append({"home": False, "corners_for": ac_, "corners_against": hc_, "shots_for": as_,
                                 "goals_for": ag, "goals_against": hg, "fh_goals_for": afg,
                                 "fh_goals_against": hfg, "date": fdate, "season": fseason,
                                 "opponent": hname, **_feature_sample(away_feat, home_feat)})
    print(f"[{my_lid}] stats cache_hit={len(cached)} api_fetched={fetched}")
    if coverage["fixtures"]:
        cov = " ".join(f"{f}={coverage[f]}/{coverage['fixtures'] * 2}" for f in STAT_TYPES)
        print(f"[{my_lid}] feature coverage (team-sides on newly fetched fixtures): {cov}")

    league_avg = (sum(league_corners) / len(league_corners)) if league_corners else 5.0
    print(f"[{my_lid}] league avg corners/team/game = {league_avg:.2f}")

    # build & upsert teams: model uses REAL matches (synthetic only as fallback for sparse teams)
    await db.teams.delete_many({"league_id": my_lid})
    team_docs = []
    for tid, name in team_names.items():
        rng = random.Random(f"{my_lid}-{tid}")
        real = sorted(samples.get(tid, []), key=lambda m: m["date"])[-20:]  # chronological, newest last
        m_for = (sum(x["corners_for"] for x in real) / len(real)) if real else league_avg
        m_ag = (sum(x["corners_against"] for x in real) / len(real)) if real else league_avg
        if len(real) >= 5:
            matches = list(real)  # real data only -> accurate probabilities
        else:
            matches = _synth_matches(m_for, m_ag, max(0, 8 - len(real)), rng) + list(real)
        team_docs.append({
            "team_id": f"{my_lid}-{tid}", "api_team_id": tid, "league_id": my_lid,
            "name": name, "matches": matches, "real_matches": real, "real_samples": len(real),
        })
    if team_docs:
        await db.teams.insert_many(team_docs)

    # build fixtures: real upcoming NS if available, else pair recent teams
    await db.fixtures.delete_many({"league_id": my_lid})
    fixture_docs = []
    upcoming = ns[:UPCOMING_FIXTURES]
    if not upcoming and ft:
        # fallback: synthesize an upcoming round from real team pairings
        ids = list(team_names.keys())
        rng = random.Random(my_lid)
        rng.shuffle(ids)
        now = datetime.now(timezone.utc)
        for i in range(0, len(ids) - 1, 2):
            upcoming.append({"fixture": {"id": f"{my_lid}-gen-{i}",
                                         "date": (now.replace(microsecond=0)).isoformat()},
                             "teams": {"home": {"id": ids[i], "name": team_names[ids[i]]},
                                       "away": {"id": ids[i + 1], "name": team_names[ids[i + 1]]}}})
    for f in upcoming:
        hid, aid = f["teams"]["home"]["id"], f["teams"]["away"]["id"]
        fixture_docs.append({
            # DERIVED FROM THE PROVIDER'S ID, not a fresh uuid4 per run.
            #
            # This block deletes every fixture in the league and re-inserts it, so a
            # random id meant the SAME real match got a different fixture_id every
            # twelve hours. Everything keyed to a fixture — the odds someone typed in,
            # their starred games — pointed at a row that no longer existed by the next
            # sync, and silently matched nothing. The value board joins odds to fixtures
            # on this id, which is why it kept coming up empty however many prices went
            # in.
            #
            # api_fixture_id was already being stored two lines down; it just was not
            # being used as the key. Same shape as the team ids below.
            "fixture_id": f"{my_lid}-{f['fixture']['id']}", "league_id": my_lid,
            # real API-Football id (synthesized fallback fixtures get a string id,
            # which settlement treats as unsettleable rather than guessing)
            "api_fixture_id": f["fixture"]["id"],
            "round": _round_label((f.get("league") or {}).get("round")) or "Upcoming",
            "home_team_id": f"{my_lid}-{hid}", "away_team_id": f"{my_lid}-{aid}",
            "home_name": f["teams"]["home"]["name"], "away_name": f["teams"]["away"]["name"],
            "date": f["fixture"]["date"], "status": "upcoming",
        })
    if fixture_docs:
        await db.fixtures.insert_many(fixture_docs)

    # PLAYED FIXTURES, KEPT SO THE SITE CAN SHOW WHAT HAPPENED.
    #
    # A SEPARATE COLLECTION, and that is the whole design — the same reasoning that keeps
    # db.odds_feed out of db.odds. Twenty-two call sites read db.fixtures and only five of
    # them test `status`, so a played row added there would be picked up as the "next
    # fixture" by the one that sorts ascending on date, handed a projection by the boards
    # that walk every row, and counted in the league yardsticks. Kept apart, a results
    # view cannot leak into a board that means "what is on".
    #
    # FREE FOR A LEAGUE. The stats loop above has already fetched and permanently cached
    # every recent finished game's corners to build team history, so this re-reads the
    # cache rather than the provider. A fixture inside the window that the loop never
    # reached — it keeps only the last STATS_CAP — comes back with corners None and says
    # so through `corners_known`, instead of being dropped or shown as 0-0.
    played_docs = []
    in_window = [f for f in ft if is_recently_played(f)]
    if in_window:
        pstats = {}
        async for c in db.fixture_stats.find(
                {"_id": {"$in": [f["fixture"]["id"] for f in in_window]}}):
            pstats[c["_id"]] = c
        for f in in_window:
            hid, aid = f["teams"]["home"]["id"], f["teams"]["away"]["id"]
            played_docs.append({
                # Same derivation as the upcoming row, so a fixture keeps its id across
                # the moment it is played and anything keyed to it still resolves.
                "fixture_id": f"{my_lid}-{f['fixture']['id']}", "league_id": my_lid,
                "api_fixture_id": f["fixture"]["id"],
                "round": _round_label((f.get("league") or {}).get("round")) or "",
                "home_team_id": f"{my_lid}-{hid}", "away_team_id": f"{my_lid}-{aid}",
                "home_name": f["teams"]["home"]["name"],
                "away_name": f["teams"]["away"]["name"],
                "date": f["fixture"]["date"],
                **result_fields(f, pstats.get(f["fixture"]["id"])),
            })
    # Rebuilt, not appended: the delete is what enforces the retention window, because a
    # game outside it is simply not in `played_docs` to be re-inserted.
    await db.fixtures_played.delete_many({"league_id": my_lid})
    if played_docs:
        await db.fixtures_played.insert_many(played_docs)
    known = sum(1 for d in played_docs if d["corners_known"])
    print(f"[{my_lid}] played kept={len(played_docs)} with corners={known}")

    # THE ODDS DELETE IS GONE, and removing it is not optional now.
    #
    # It existed to clear fabricated prices: the sync used to synthesise bookmaker odds —
    # the model's own fair price times a random 0.9-1.18 — so every EV computed from one
    # was that multiplier minus one, dressed up as an edge. The generator was deleted
    # long ago and this line was what swept up what it had left behind.
    #
    # It was harmless only because the ids above were random: it deleted odds for
    # fixture_ids invented microseconds earlier, so it always matched nothing. Now that
    # the ids are stable it would match everything — and the only thing writing to this
    # collection today is a person typing a price in. Leaving it would have turned a
    # no-op into "every sync wipes the odds you entered", which is a worse bug than the
    # one above.

    all_shots = [m.get("shots_for", 0) for t in team_docs for m in (t.get("real_matches") or [])]
    avg_shots = round(sum(all_shots) / len(all_shots), 2) if all_shots else None
    # league blocked-shots average drives the v3 intent term; None where the backfill
    # hasn't reached this league, which makes its teams price off shots intent instead
    all_blocked = [m["blocked_shots_for"] for t in team_docs for m in (t.get("real_matches") or [])
                   if m.get("blocked_shots_for") is not None]
    avg_blocked = round(sum(all_blocked) / len(all_blocked), 2) if all_blocked else None
    await db.leagues.update_one({"league_id": my_lid},
                                {"$set": {"league_id": my_lid, "name": meta["name"],
                                          "country": meta["country"], "data_source": "real",
                                          "tier": meta.get("tier"),
                                          "season": season, "avg_shots": avg_shots,
                                          "avg_blocked": avg_blocked,
                                          "synced_at": datetime.now(timezone.utc).isoformat()}},
                                upsert=True)
    # `odds_docs` used to be built here by the synthetic-odds generator. That generator was
    # deleted (see the note where the odds wipe used to be) but this line kept referencing it,
    # so the last statement of every league sync was a NameError — caught by main()'s
    # per-league handler and recorded as an error AFTER all the writes had landed. Latent
    # rather than fatal today only because the leagues are failing earlier than this.
    print(f"[{my_lid}] DONE teams={len(team_docs)} fixtures={len(fixture_docs)}")
    return {"teams": len(team_docs), "fixtures": len(fixture_docs),
            # The results half, reported for the same reason the fixture count is: a
            # store that quietly stays empty is indistinguishable from one that is
            # working, and the report is where that gets noticed. No `stat_calls` here —
            # the league path spends nothing, because the stats loop above has already
            # fetched and cached everything it reads.
            "played": len(played_docs), "played_with_corners": known,
            "cache_hit": len(cached), "api_fetched": fetched, "feature_coverage": coverage}


def cup_fixture_docs(cup_id, upcoming, by_api, min_games=cups.CUP_MIN_GAMES,
                     status="upcoming"):
    """Provider fixtures -> our fixture documents, with each side resolved to its DOMESTIC
    team row. Pure, so the resolution rules are testable without a database or an API key.

    Returns (documents, {reason: count}) — the counts are printed, because "the round had
    thirty-two ties and we stored eleven" is a sentence somebody will need explained, and
    the alternative is a silently short board.

    NO TEAMS ARE CREATED HERE, and that is the entire point of the cup path. The documents
    below reference `eng-pl-42`, not `ucl-42`, so every streak, average and projection on a
    cup game is computed from the side's full domestic season.
    """
    from collections import Counter
    docs, skipped = [], Counter()
    for f in upcoming:
        hid, aid = f["teams"]["home"]["id"], f["teams"]["away"]["id"]
        home, away, reason = cups.resolve_tie(hid, aid, by_api, min_games)
        if reason:
            skipped[reason] += 1
            continue
        docs.append({
            # Same shape and same derivation as a league fixture — see the long note in
            # sync_league about why these are NOT uuid4.
            "fixture_id": f"{cup_id}-{f['fixture']['id']}", "league_id": cup_id,
            "api_fixture_id": f["fixture"]["id"],
            "round": (_round_label((f.get("league") or {}).get("round"))
                      or ("Upcoming" if status == "upcoming" else "")),
            "home_team_id": home["team_id"], "away_team_id": away["team_id"],
            "home_name": f["teams"]["home"]["name"], "away_name": f["teams"]["away"]["name"],
            "date": f["fixture"]["date"],
            # SAME RESOLUTION RULES FOR A PLAYED TIE AS AN UPCOMING ONE, which is why
            # `status` is a parameter rather than this function being copied. Both sides
            # still have to resolve to a domestic team row: a result stored against a
            # side the app does not know is a row no page can label and no claim can
            # settle against, so "both sides or neither" holds after the whistle too.
            "status": status,
            # STORED ON THE ROW so every reader downstream can see what it is holding
            # without re-deriving it from two team lookups. `cross_league` is what the
            # transfer caveat hangs off, and it is FALSE for an all-English tie in
            # Europe — the caveat is about the two sides, not the competition.
            "cup": True, "cross_league": cups.cross_league(home, away),
            "home_league_id": home["league_id"], "away_league_id": away["league_id"],
        })
    return docs, dict(skipped)


async def sync_cup(hc, cup_id):
    """A cup: fixtures only, sides resolved to the teams the league syncs already built.

    ORDER OF OPERATIONS MATTERS. Everything is fetched and resolved BEFORE the existing
    fixtures are deleted, so a failed request or a wrong id leaves the previous round
    standing rather than emptying the competition and then falling over.
    """
    meta = CUP_META[cup_id]
    api_id = meta["api"]

    # THE IDENTITY CHECK, BEFORE ANY WRITE. See cups.verify_identity — this repo has a scar
    # from an api id added from memory, and the only thing that caught it was a human
    # remembering to run the probe. This runs every time.
    entry = await league_entry(hc, api_id)
    complaint = cups.verify_identity(entry, meta)
    if complaint:
        raise RuntimeError(complaint)
    season = season_from(entry)
    print(f"[{cup_id}] api={api_id} season={season} "
          f"({(entry.get('league') or {}).get('name')})")

    fixtures = await af_get(hc, "/fixtures", {"league": api_id, "season": season})
    ns = sorted((f for f in fixtures if is_upcoming(f)),
                key=lambda f: f["fixture"]["date"])

    teams = await db.teams.find({}, {"_id": 0, "team_id": 1, "api_team_id": 1,
                                     "league_id": 1, "name": 1,
                                     "real_samples": 1}).to_list(5000)
    by_api = cups.index_by_api_id(teams)
    # THE CAP GOES ON WHAT IS KEPT, NOT ON WHAT IS CONSIDERED, and with three European
    # competitions that difference is the feature working or not.
    #
    # Capping the fetched list first spends the allowance on ties that will be thrown
    # away. The Conference League's league phase is 36 teams and over a hundred fixtures,
    # a large share of them involving sides from leagues this app does not sync — so 80
    # taken off the front by date could resolve to a dozen stored games while perfectly
    # usable ties two matchdays later, still well inside the board's month-long horizon,
    # were never looked at. It would present as "the Conference League barely has any
    # games on", which is indistinguishable from the competition being quiet.
    #
    # Resolving first costs NOTHING: every fixture came from the single /fixtures response
    # already fetched, and resolution is a dictionary lookup.
    docs, skipped = cup_fixture_docs(cup_id, ns, by_api)
    docs = docs[:UPCOMING_FIXTURES]
    print(f"[{cup_id}] upcoming={len(ns)} stored={len(docs)} skipped={skipped or '{}'}")

    await db.fixtures.delete_many({"league_id": cup_id})
    if docs:
        await db.fixtures.insert_many([dict(d) for d in docs])

    # PLAYED TIES, AND THE ONE PLACE IN THIS FEATURE THAT SPENDS CREDITS.
    #
    # A league sync fetches every recent finished game's statistics anyway, to build team
    # history, so the league path above reads a cache. A cup sync builds no team data and
    # fetches no statistics at all, so each uncached tie costs one /fixtures/statistics
    # call. They are cached permanently afterwards, keyed by the provider's fixture id, so
    # this is one call per tie EVER rather than per sync — a round of fourteen costs
    # fourteen once and nothing on every run after.
    #
    # Newest first and capped: a results view is read from the top, and the cap is what
    # stops a first run on a competition with a long season turning into a backfill
    # nobody asked for.
    recent_played = sorted((f for f in fixtures if is_recently_played(f)),
                           key=lambda f: f["fixture"]["date"], reverse=True)
    pdocs, pskip = cup_fixture_docs(cup_id, recent_played[:PLAYED_STATS_CAP], by_api,
                                    status="played")
    raw = {f["fixture"]["id"]: f for f in recent_played}
    out, stat_calls = [], 0
    for d in pdocs:
        fid = d["api_fixture_id"]
        f = raw.get(fid)
        if f is None:                      # cannot happen; a missing raw row is not a result
            continue
        cached_stat = await db.fixture_stats.find_one({"_id": fid})
        if cached_stat is None:
            try:
                st = await af_get(hc, "/fixtures/statistics", {"fixture": fid})
            except Exception as e:
                print(f"  [{cup_id}] stat {fid} err {e}")
                st = []
            per = {t["team"]["id"]: parse_team_stats(t.get("statistics")) for t in st}
            hid, aid = f["teams"]["home"]["id"], f["teams"]["away"]["id"]
            hf, af_ = per.get(hid), per.get(aid)
            if hf and af_ and hf.get("corners") is not None and af_.get("corners") is not None:
                stat_calls += 1
                g = f.get("goals") or {}
                hth = ((f.get("score") or {}).get("halftime") or {})
                cached_stat = {
                    "_id": fid, "league_id": cup_id, "date": f["fixture"]["date"],
                    "season": (f.get("league") or {}).get("season"),
                    "home_id": hid, "away_id": aid,
                    "home_corners": hf["corners"], "away_corners": af_["corners"],
                    "home_shots": hf.get("shots") or 0, "away_shots": af_.get("shots") or 0,
                    "home_goals": g.get("home") or 0, "away_goals": g.get("away") or 0,
                    "home_fh_goals": hth.get("home") or 0,
                    "away_fh_goals": hth.get("away") or 0,
                    **{f"home_{k}": hf.get(k) for k in STAT_TYPES},
                    **{f"away_{k}": af_.get(k) for k in STAT_TYPES},
                }
                # THE SAME CACHE THE LEAGUE SYNCS USE, deliberately. It is keyed by the
                # provider's fixture id with no competition in the key, so a tie fetched
                # here is never fetched again by anything.
                await db.fixture_stats.update_one({"_id": fid}, {"$set": cached_stat},
                                                  upsert=True)
        out.append({**d, **result_fields(f, cached_stat)})
    await db.fixtures_played.delete_many({"league_id": cup_id})
    if out:
        await db.fixtures_played.insert_many([dict(d) for d in out])
    known = sum(1 for d in out if d["corners_known"])
    print(f"[{cup_id}] played kept={len(out)} with corners={known} "
          f"stat_calls={stat_calls} skipped={pskip or '{}'}")

    # A LEAGUE DOCUMENT WITH NO SHOT AVERAGES ON IT, on purpose. It exists so the cup has a
    # name to display and so boot cleanup recognises it; `avg_shots` and `avg_blocked` stay
    # absent because a cup has no teams to compute them from, and server.py reads those
    # references off each SIDE's league instead. Writing a number here would be the
    # hardcoded-default bug in a different hiding place.
    await db.leagues.update_one({"league_id": cup_id}, {"$set": {
        "league_id": cup_id, "name": meta["name"], "country": meta["country"],
        "data_source": "cup", "is_cup": True, "teams_from": "domestic",
        "season": season, "synced_at": datetime.now(timezone.utc).isoformat()}}, upsert=True)
    print(f"[{cup_id}] DONE fixtures={len(docs)}")
    return {"teams": 0, "fixtures": len(docs), "skipped": skipped,
            "played": len(out), "played_with_corners": known,
            "stat_calls": stat_calls}


async def main():
    import uuid as _uuid
    trigger = os.environ.get("SYNC_TRIGGER", "manual")
    # CUPS LAST, and it is not cosmetic: a cup resolves its sides out of db.teams, so it
    # has to run after the leagues that populate them. On the very first sync of a fresh
    # database the other order would store no cup fixtures at all and look like the cup
    # had no games on.
    targets = ([a for a in sys.argv[1:] if not a.startswith("--")]
               or list(LEAGUE_META.keys()) + list(CUP_META.keys()))
    run_id = str(_uuid.uuid4())
    await db.sync_runs.insert_one({
        "_id": run_id, "trigger": trigger, "started_at": datetime.now(timezone.utc).isoformat(),
        "finished_at": None, "status": "running", "targets": targets, "leagues": []})
    results = []
    async with httpx.AsyncClient() as hc:
        for lid in targets:
            try:
                counts = await (sync_cup(hc, lid) if lid in CUP_META
                                else sync_league(hc, lid))
                entry = {"league_id": lid, "status": "ok", **(counts or {})}
            except Exception as e:
                entry = {"league_id": lid, "status": "error", "error": str(e)[:300]}
                print(f"[{lid}] FAILED: {e}")
            results.append(entry)
            await db.sync_runs.update_one({"_id": run_id}, {"$set": {"leagues": results}})
    errors = [r for r in results if r["status"] == "error"]
    status = "success" if not errors else ("failed" if len(errors) == len(results) else "partial")
    await db.sync_runs.update_one({"_id": run_id}, {"$set": {
        "finished_at": datetime.now(timezone.utc).isoformat(), "status": status,
        "error_count": len(errors)}})
    # retain only the most recent 30 run records
    old = await db.sync_runs.find({}, {"_id": 1}).sort("started_at", -1).skip(30).to_list(1000)
    if old:
        await db.sync_runs.delete_many({"_id": {"$in": [o["_id"] for o in old]}})
    # Prices whose fixture this sync has just replaced. Fixtures are deleted and
    # re-inserted per league, so an id that changes shape (as they did once) strands
    # every price stored against the old one. Left alone they accumulate for ever and
    # crowd the real prices out of the value board's read — so they go every run.
    try:
        from server import purge_orphan_odds
        gone = await purge_orphan_odds(db)
        if gone:
            print(f"removed {gone} orphaned odds documents")
    except Exception as e:
        print(f"orphan odds purge skipped: {e}")

    # settle any Corner Model 2.0 picks whose games have finished
    try:
        from settle_picks import settle as settle_picks
        async with httpx.AsyncClient() as hc:
            await settle_picks(hc)
    except Exception as e:
        print(f"pick settlement skipped: {e}")

    # CORNER PRICES — OFF UNLESS SWITCHED ON, and the flag is the point.
    #
    # Every other step in this sync costs calls PER LEAGUE. This one costs one call PER
    # FIXTURE, so enabling it silently on deploy would quietly change the shape of the
    # subscription bill on a run nobody asked for. FETCH_ODDS=1 is the owner saying yes,
    # and the printed call count is so the cost stays visible afterwards rather than
    # becoming a line on an invoice.
    #
    # It runs LAST for the same reason the two steps above do: a price is a convenience
    # on top of the data, and nothing here may put the form sync at risk.
    if os.environ.get("FETCH_ODDS", "").strip().lower() in ("1", "true", "yes", "on"):
        try:
            from fetch_odds import fetch_window
            got = await fetch_window(db)
            print(f"odds: {got['calls']} API call(s), priced {got['priced']}/"
                  f"{got['fixtures']} fixtures, {got['lines']} line(s), "
                  f"{got['errors']} error(s)")
            await db.sync_runs.update_one({"_id": run_id}, {"$set": {"odds": got}})
        except Exception as e:
            # Recorded, not raised. A provider hiccup on the odds endpoint must not mark a
            # successful form sync as failed — that was the symptom that sent somebody
            # looking for a broken sync when the sync was fine.
            print(f"odds fetch failed (data sync unaffected): {e}")
    else:
        print("odds: not enabled — set FETCH_ODDS=1 to fetch prices "
              "(one API call per fixture, ~40 per run by default)")


if __name__ == "__main__":
    asyncio.run(main())
