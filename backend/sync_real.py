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

from server import expected_lambdas, poisson_ge, fair_odds, TOTAL_LINES

ROOT = Path(__file__).parent
load_dotenv(ROOT / ".env")

KEY = os.environ["API_FOOTBALL_KEY"]
BASE = "https://v3.football.api-sports.io"
HEADERS = {"x-apisports-key": KEY}

client = AsyncIOMotorClient(os.environ["MONGO_URL"])
db = client[os.environ["DB_NAME"]]

# my league_id -> API-Football metadata
LEAGUE_META = {
    "eng-pl":  {"api": 39,  "name": "Premier League",  "country": "England"},
    "eng-ch":  {"api": 40,  "name": "Championship",     "country": "England"},
    "eng-l1":  {"api": 41,  "name": "League One",       "country": "England"},
    "eng-l2":  {"api": 42,  "name": "League Two",       "country": "England"},
    "eng-nl":  {"api": 43,  "name": "National League",  "country": "England"},
    "aus-al":  {"api": 188, "name": "A-League",         "country": "Australia"},
    "nor-el":  {"api": 103, "name": "Eliteserien",      "country": "Norway"},
    "ned-ere": {"api": 88,  "name": "Eredivisie",       "country": "Netherlands"},
    "ned-ed":  {"api": 89,  "name": "Eerste Divisie",   "country": "Netherlands"},
    "bra-sa":  {"api": 71,  "name": "Série A",          "country": "Brazil"},
    "bra-sb":  {"api": 72,  "name": "Série B",          "country": "Brazil"},
    "ita-sa":  {"api": 135, "name": "Serie A",          "country": "Italy"},
    "fra-l1":  {"api": 61,  "name": "Ligue 1",          "country": "France"},
    "esp-ll":  {"api": 140, "name": "La Liga",          "country": "Spain"},
    "ger-bl":  {"api": 78,  "name": "Bundesliga",       "country": "Germany"},
    "ger-bl2": {"api": 79,  "name": "2. Bundesliga",    "country": "Germany"},
    "por-pl":  {"api": 94,  "name": "Primeira Liga",    "country": "Portugal"},
    "bel-pl":  {"api": 144, "name": "Jupiler Pro League","country": "Belgium"},
    "sco-pl":  {"api": 179, "name": "Premiership",      "country": "Scotland"},
    "tur-sl":  {"api": 203, "name": "Süper Lig",        "country": "Turkey"},
    "usa-ml":  {"api": 253, "name": "MLS",              "country": "USA"},
    "den-sl":  {"api": 119, "name": "Superliga",        "country": "Denmark"},
    "sui-sl":  {"api": 207, "name": "Super League",     "country": "Switzerland"},
    "aut-bl":  {"api": 218, "name": "Bundesliga",       "country": "Austria"},
    "gre-sl":  {"api": 197, "name": "Super League",     "country": "Greece"},
    "jpn-j1":  {"api": 98,  "name": "J1 League",        "country": "Japan"},
    "arg-lp":  {"api": 128, "name": "Liga Profesional", "country": "Argentina"},
}
STATS_CAP = 120  # max per-fixture statistics calls per league


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
    # if the current season has too few finished matches, pull last season for corner form
    if len(ft) < 40:
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
            # self-heal: backfill goals onto older cache docs that predate goal capture
            if c.get("home_goals") is None:
                await db.fixture_stats.update_one({"_id": fid}, {"$set": {
                    "home_goals": hg, "away_goals": ag, "home_fh_goals": hfg, "away_fh_goals": afg}})
        else:
            try:
                st = await af_get(hc, "/fixtures/statistics", {"fixture": fid})
            except Exception as e:
                print(f"  stat {fid} err {e}"); continue
            corners = {}
            shots = {}
            for t in st:
                cc = next((s["value"] for s in t["statistics"] if s["type"] == "Corner Kicks"), None)
                corners[t["team"]["id"]] = cc if isinstance(cc, int) else 0
                sh = next((s["value"] for s in t["statistics"] if s["type"] == "Total Shots"), None)
                shots[t["team"]["id"]] = sh if isinstance(sh, int) else 0
            if hid not in corners or aid not in corners:
                continue
            hc_, ac_ = corners.get(hid, 0), corners.get(aid, 0)
            hs_, as_ = shots.get(hid, 0), shots.get(aid, 0)
            fetched += 1
            await db.fixture_stats.update_one({"_id": fid}, {"$set": {
                "_id": fid, "league_id": my_lid, "date": fdate,
                "home_id": hid, "away_id": aid,
                "home_corners": hc_, "away_corners": ac_,
                "home_shots": hs_, "away_shots": as_,
                "home_goals": hg, "away_goals": ag,
                "home_fh_goals": hfg, "away_fh_goals": afg}}, upsert=True)
        league_corners += [hc_, ac_]
        if hid in samples:
            samples[hid].append({"home": True, "corners_for": hc_, "corners_against": ac_, "shots_for": hs_,
                                 "goals_for": hg, "goals_against": ag, "fh_goals_for": hfg, "date": fdate, "opponent": aname})
        if aid in samples:
            samples[aid].append({"home": False, "corners_for": ac_, "corners_against": hc_, "shots_for": as_,
                                 "goals_for": ag, "goals_against": hg, "fh_goals_for": afg, "date": fdate, "opponent": hname})
    print(f"[{my_lid}] stats cache_hit={len(cached)} api_fetched={fetched}")

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
    upcoming = ns[:10]
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
            "round": _round_label((f.get("league") or {}).get("round")) or "Upcoming",
            "home_team_id": f"{my_lid}-{hid}", "away_team_id": f"{my_lid}-{aid}",
            "home_name": f["teams"]["home"]["name"], "away_name": f["teams"]["away"]["name"],
            "date": f["fixture"]["date"], "status": "upcoming",
        })
    if fixture_docs:
        await db.fixtures.insert_many(fixture_docs)

    # seed bookmaker odds for ~70% of fixtures so scanner has content
    await db.odds.delete_many({"fixture_id": {"$in": [f["fixture_id"] for f in fixture_docs]}})
    tmap = {t["team_id"]: t for t in team_docs}
    odds_docs = []
    for fx in fixture_docs:
        rng = random.Random(fx["fixture_id"])
        if rng.random() > 0.7:
            continue
        lambdas = expected_lambdas(tmap[fx["home_team_id"]], tmap[fx["away_team_id"]])
        odds = {}
        for line in TOTAL_LINES:
            p = poisson_ge(int(line) + 1, lambdas["total"])
            fo = fair_odds(p)
            if fo:
                odds[f"total_over_{line}"] = round(fo * rng.uniform(0.9, 1.18), 2)
        odds_docs.append({"fixture_id": fx["fixture_id"], "odds": odds})
    if odds_docs:
        await db.odds.insert_many(odds_docs)

    all_shots = [m.get("shots_for", 0) for t in team_docs for m in (t.get("real_matches") or [])]
    avg_shots = round(sum(all_shots) / len(all_shots), 2) if all_shots else None
    await db.leagues.update_one({"league_id": my_lid},
                                {"$set": {"league_id": my_lid, "name": meta["name"],
                                          "country": meta["country"], "data_source": "real",
                                          "season": season, "avg_shots": avg_shots,
                                          "synced_at": datetime.now(timezone.utc).isoformat()}},
                                upsert=True)
    print(f"[{my_lid}] DONE teams={len(team_docs)} fixtures={len(fixture_docs)} odds={len(odds_docs)}")
    return {"teams": len(team_docs), "fixtures": len(fixture_docs),
            "cache_hit": len(cached), "api_fetched": fetched}


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
