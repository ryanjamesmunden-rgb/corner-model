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
    for f in recent:
        fid = f["fixture"]["id"]
        hid = f["teams"]["home"]["id"]
        aid = f["teams"]["away"]["id"]
        hname = f["teams"]["home"]["name"]
        aname = f["teams"]["away"]["name"]
        fdate = f["fixture"]["date"]
        try:
            st = await af_get(hc, "/fixtures/statistics", {"fixture": fid})
        except Exception as e:
            print(f"  stat {fid} err {e}"); continue
        corners = {}
        for t in st:
            c = next((s["value"] for s in t["statistics"] if s["type"] == "Corner Kicks"), None)
            corners[t["team"]["id"]] = c if isinstance(c, int) else 0
        if hid not in corners or aid not in corners:
            continue
        hc_, ac_ = corners.get(hid, 0), corners.get(aid, 0)
        league_corners += [hc_, ac_]
        if hid in samples:
            samples[hid].append({"home": True, "corners_for": hc_, "corners_against": ac_, "date": fdate, "opponent": aname})
        if aid in samples:
            samples[aid].append({"home": False, "corners_for": ac_, "corners_against": hc_, "date": fdate, "opponent": hname})

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
            "fixture_id": str(uuid.uuid4()), "league_id": my_lid, "round": "Upcoming",
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

    await db.leagues.update_one({"league_id": my_lid},
                                {"$set": {"league_id": my_lid, "name": meta["name"],
                                          "country": meta["country"], "data_source": "real",
                                          "season": season,
                                          "synced_at": datetime.now(timezone.utc).isoformat()}},
                                upsert=True)
    print(f"[{my_lid}] DONE teams={len(team_docs)} fixtures={len(fixture_docs)} odds={len(odds_docs)}")


async def main():
    targets = sys.argv[1:] if len(sys.argv) > 1 else list(LEAGUE_META.keys())
    async with httpx.AsyncClient() as hc:
        for lid in targets:
            try:
                await sync_league(hc, lid)
            except Exception as e:
                print(f"[{lid}] FAILED: {e}")


if __name__ == "__main__":
    asyncio.run(main())
