"""One-off / on-demand real data sync from API-Football into the app's schema.
Run: python sync_real.py            (all leagues)
     python sync_real.py eng-pl     (one league)
Requires an active API-Football plan with current-season access (Pro+).
"""
import os
import sys
import asyncio
import random
from datetime import datetime, timezone
from pathlib import Path
import httpx
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient


from leagues_meta import LEAGUE_META
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


async def current_season(hc, api_id):
    resp = await af_get(hc, "/leagues", {"id": api_id})
    seasons = resp[0]["seasons"] if resp else []
    cur = next((s["year"] for s in seasons if s.get("current")), None)
    return cur or max((s["year"] for s in seasons), default=int(os.environ.get("API_FOOTBALL_SEASON", "2024")))


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
    ns = [f for f in fixtures if f["fixture"]["status"]["short"] in ("NS", "TBD")]
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
                "_id": fid, "league_id": my_lid, "date": fdate,
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
                                 "fh_goals_against": afg, "date": fdate,
                                 "opponent": aname, **_feature_sample(home_feat, away_feat)})
        if aid in samples:
            samples[aid].append({"home": False, "corners_for": ac_, "corners_against": hc_, "shots_for": as_,
                                 "goals_for": ag, "goals_against": hg, "fh_goals_for": afg,
                                 "fh_goals_against": hfg, "date": fdate,
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
    import uuid
    for f in upcoming:
        hid, aid = f["teams"]["home"]["id"], f["teams"]["away"]["id"]
        fixture_docs.append({
            "fixture_id": str(uuid.uuid4()), "league_id": my_lid,
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

    # Clear any stored odds for these fixtures.
    #
    # This used to SYNTHESISE bookmaker odds — the model's own fair price multiplied by a
    # random 0.9-1.18 — "so scanner has content". They looked real, auto-filled the odds
    # boxes, and every EV and value tier computed from them was therefore noise: EV came
    # out as that random multiplier minus one. Fabricated prices are worse than none, so
    # the generation is gone and the delete stays, which clears the ones already stored.
    # Odds now only ever come from a person entering them.
    await db.odds.delete_many({"fixture_id": {"$in": [f["fixture_id"] for f in fixture_docs]}})

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
                                          "season": season, "avg_shots": avg_shots,
                                          "avg_blocked": avg_blocked,
                                          "synced_at": datetime.now(timezone.utc).isoformat()}},
                                upsert=True)
    # `odds_docs` used to be built here by the synthetic-odds generator. That generator was
    # deleted (see the note above db.odds.delete_many) but this line kept referencing it,
    # so the last statement of every league sync was a NameError — caught by main()'s
    # per-league handler and recorded as an error AFTER all the writes had landed. Latent
    # rather than fatal today only because the leagues are failing earlier than this.
    print(f"[{my_lid}] DONE teams={len(team_docs)} fixtures={len(fixture_docs)}")
    return {"teams": len(team_docs), "fixtures": len(fixture_docs),
            "cache_hit": len(cached), "api_fetched": fetched, "feature_coverage": coverage}


async def main():
    import uuid as _uuid
    trigger = os.environ.get("SYNC_TRIGGER", "manual")
    targets = [a for a in sys.argv[1:] if not a.startswith("--")] or list(LEAGUE_META.keys())
    run_id = str(_uuid.uuid4())
    await db.sync_runs.insert_one({
        "_id": run_id, "trigger": trigger, "started_at": datetime.now(timezone.utc).isoformat(),
        "finished_at": None, "status": "running", "targets": targets, "leagues": []})
    results = []
    async with httpx.AsyncClient() as hc:
        for lid in targets:
            try:
                counts = await sync_league(hc, lid)
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
    # settle any Corner Model 2.0 picks whose games have finished
    try:
        from settle_picks import settle as settle_picks
        async with httpx.AsyncClient() as hc:
            await settle_picks(hc)
    except Exception as e:
        print(f"pick settlement skipped: {e}")


if __name__ == "__main__":
    asyncio.run(main())
