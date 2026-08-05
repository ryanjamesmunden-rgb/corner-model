"""Probe candidate leagues: do they expose Corner Kicks + shots stats, and enough games?"""
import os
import asyncio
import httpx
from dotenv import load_dotenv
from pathlib import Path

ROOT = Path(__file__).parent
load_dotenv(ROOT / ".env")
KEY = os.environ["API_FOOTBALL_KEY"]
BASE = "https://v3.football.api-sports.io"
H = {"x-apisports-key": KEY}

CANDIDATES = {
    "ger-bl":  {"api": 78,  "name": "Bundesliga",        "country": "Germany"},
    "ger-bl2": {"api": 79,  "name": "2. Bundesliga",     "country": "Germany"},
    "por-pl":  {"api": 94,  "name": "Primeira Liga",     "country": "Portugal"},
    "bel-pl":  {"api": 144, "name": "Jupiler Pro League","country": "Belgium"},
    "sco-pl":  {"api": 179, "name": "Premiership",       "country": "Scotland"},
    "tur-sl":  {"api": 203, "name": "Super Lig",         "country": "Turkey"},
    "usa-ml":  {"api": 253, "name": "Major League Soccer","country": "USA"},
    "den-sl":  {"api": 119, "name": "Superliga",         "country": "Denmark"},
    "sui-sl":  {"api": 207, "name": "Super League",      "country": "Switzerland"},
    "aut-bl":  {"api": 218, "name": "Bundesliga",        "country": "Austria"},
    "gre-sl":  {"api": 197, "name": "Super League",      "country": "Greece"},
    "jpn-j1":  {"api": 98,  "name": "J1 League",         "country": "Japan"},
    "arg-lp":  {"api": 128, "name": "Liga Profesional",  "country": "Argentina"},
}


async def af(hc, path, params):
    for _ in range(5):
        r = await hc.get(f"{BASE}{path}", params=params, headers=H, timeout=30.0)
        if r.status_code == 429:
            await asyncio.sleep(12); continue
        r.raise_for_status()
        d = r.json()
        if isinstance(d.get("errors"), dict) and d["errors"].get("rateLimit"):
            await asyncio.sleep(12); continue
        await asyncio.sleep(0.2)
        return d["response"]
    return []


async def current_season(hc, api):
    resp = await af(hc, "/leagues", {"id": api})
    seasons = resp[0]["seasons"] if resp else []
    return next((s["year"] for s in seasons if s.get("current")), None) or max((s["year"] for s in seasons), default=2025)


async def probe(hc, lid, meta):
    api = meta["api"]
    season = await current_season(hc, api)
    fx = await af(hc, "/fixtures", {"league": api, "season": season})
    ft = [f for f in fx if f["fixture"]["status"]["short"] == "FT"]
    used = season
    if len(ft) < 40:
        prev = await af(hc, "/fixtures", {"league": api, "season": season - 1})
        pft = [f for f in prev if f["fixture"]["status"]["short"] == "FT"]
        if len(pft) > len(ft):
            ft = pft; used = season - 1
    ft.sort(key=lambda f: f["fixture"]["date"])
    # check corner + shot stat presence on last few FT
    corner_ok = shots_ok = 0
    sample = ft[-4:]
    for f in sample:
        st = await af(hc, "/fixtures/statistics", {"fixture": f["fixture"]["id"]})
        types = set()
        for t in st:
            for s in t["statistics"]:
                types.add(s["type"])
        if "Corner Kicks" in types:
            corner_ok += 1
        if "Total Shots" in types:
            shots_ok += 1
    # games per team estimate
    teams = set()
    for f in ft:
        teams.add(f["teams"]["home"]["id"]); teams.add(f["teams"]["away"]["id"])
    games_per_team = (2 * len(ft) / len(teams)) if teams else 0
    ns = [f for f in fx if f["fixture"]["status"]["short"] in ("NS", "TBD")]
    print(f"{lid:8} {meta['country']:12} {meta['name']:22} season={used} FT={len(ft):3} g/team~{games_per_team:4.1f} "
          f"corner={corner_ok}/{len(sample)} shots={shots_ok}/{len(sample)} upcoming={len(ns)} "
          f"=> {'QUALIFY' if corner_ok>=3 and games_per_team>=10 else 'skip'}")


async def main():
    async with httpx.AsyncClient() as hc:
        for lid, meta in CANDIDATES.items():
            try:
                await probe(hc, lid, meta)
            except Exception as e:
                print(f"{lid:8} ERROR {e}")


if __name__ == "__main__":
    asyncio.run(main())
