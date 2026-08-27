"""Probe leagues before trusting them: is the id the competition you think it is, does
it expose Corner Kicks + shots, and are there enough games?

SPENDS A FEW API CREDITS — about 6 calls per league (one /leagues, one or two /fixtures,
four /fixtures/statistics). Cheap, and much cheaper than syncing a league for 250
fixtures only to find it has no corner data.

The identity check is the point. League ids are easy to get wrong from memory — Norway's
second TIER is called "1. divisjon" while "2. divisjon" is the third tier — so this
prints the provider's OWN name and country next to the one we assumed, and says MISMATCH
when they disagree.

Run: python probe_leagues.py                  (leagues not yet proven / the defaults)
     python probe_leagues.py nor-d1 nor-d2    (by our league key)
     python probe_leagues.py --id 104 105     (by raw API-Football id)
"""
import asyncio
import os
import sys
from pathlib import Path

import httpx
from dotenv import load_dotenv

from leagues_meta import LEAGUE_META

ROOT = Path(__file__).parent
load_dotenv(ROOT / ".env")
KEY = os.environ["API_FOOTBALL_KEY"]
BASE = "https://v3.football.api-sports.io"
H = {"x-apisports-key": KEY}

# Probed by default: the leagues most recently added, which are the ones whose ids and
# stat coverage have not yet been confirmed against live data.
DEFAULT_KEYS = ["nor-d1", "nor-d2"]


async def af(hc, path, params):
    for _ in range(5):
        r = await hc.get(f"{BASE}{path}", params=params, headers=H, timeout=30.0)
        if r.status_code == 429:
            await asyncio.sleep(12)
            continue
        r.raise_for_status()
        d = r.json()
        if isinstance(d.get("errors"), dict) and d["errors"].get("rateLimit"):
            await asyncio.sleep(12)
            continue
        await asyncio.sleep(0.2)
        return d["response"]
    return []


async def identify(hc, api):
    """What the PROVIDER calls this id — the check that the id is the right competition."""
    resp = await af(hc, "/leagues", {"id": api})
    if not resp:
        return None
    lg, seasons = resp[0]["league"], resp[0]["seasons"]
    season = next((s["year"] for s in seasons if s.get("current")), None) \
        or max((s["year"] for s in seasons), default=2025)
    return {"name": lg.get("name"), "type": lg.get("type"),
            "country": (resp[0].get("country") or {}).get("name"), "season": season}


async def probe(hc, lid, meta):
    api = meta["api"]
    ident = await identify(hc, api)
    if not ident:
        print(f"{lid:8} api={api:<4} NOT FOUND — the provider has no league with this id")
        return
    assumed = f"{meta['country']} / {meta['name']}"
    actual = f"{ident['country']} / {ident['name']}"
    match = (ident["country"] or "").lower() == meta["country"].lower()
    print(f"{lid:8} api={api:<4} provider says: {actual}  ({ident['type']}, season {ident['season']})")
    if not match:
        print(f"{'':8} !! MISMATCH — we call it {assumed}. Fix leagues_meta.py before syncing.")

    season = ident["season"]
    fx = await af(hc, "/fixtures", {"league": api, "season": season})
    ft = [f for f in fx if f["fixture"]["status"]["short"] == "FT"]
    used = season
    if len(ft) < 40:
        prev = await af(hc, "/fixtures", {"league": api, "season": season - 1})
        pft = [f for f in prev if f["fixture"]["status"]["short"] == "FT"]
        if len(pft) > len(ft):
            ft, used = pft, season - 1
    ft.sort(key=lambda f: f["fixture"]["date"])

    # do the last few finished games actually carry the stats the model needs?
    corner_ok = shots_ok = blocked_ok = 0
    sample = ft[-4:]
    for f in sample:
        st = await af(hc, "/fixtures/statistics", {"fixture": f["fixture"]["id"]})
        types = {s["type"] for t in st for s in t["statistics"]}
        corner_ok += "Corner Kicks" in types
        shots_ok += "Total Shots" in types
        blocked_ok += "Blocked Shots" in types

    teams = {tid for f in ft for tid in (f["teams"]["home"]["id"], f["teams"]["away"]["id"])}
    per_team = (2 * len(ft) / len(teams)) if teams else 0
    ns = [f for f in fx if f["fixture"]["status"]["short"] in ("NS", "TBD")]
    n = len(sample)
    verdict = "QUALIFY" if (corner_ok >= 3 and per_team >= 10 and match) else "SKIP"
    print(f"{'':8} season={used} FT={len(ft):3} games/team~{per_team:4.1f} upcoming={len(ns):3} "
          f"corners={corner_ok}/{n} shots={shots_ok}/{n} blocked={blocked_ok}/{n}  => {verdict}")
    if verdict == "SKIP":
        why = []
        if not match:
            why.append("id points at another country")
        if corner_ok < 3:
            why.append("no corner data — the whole model needs it")
        if per_team < 10:
            why.append(f"only ~{per_team:.0f} games a team, too thin to price")
        print(f"{'':8} reason: {'; '.join(why)}")
    if verdict == "QUALIFY" and blocked_ok < 3:
        print(f"{'':8} note: blocked shots are thin here, so v3 will fall back to the v2 "
              f"shots intent for these teams")


async def main():
    args = sys.argv[1:]
    if "--id" in args:
        ids = [int(a) for a in args[args.index("--id") + 1:] if a.isdigit()]
        targets = {f"api-{i}": {"api": i, "name": "?", "country": "?"} for i in ids}
    else:
        keys = [a for a in args if not a.startswith("--")] or DEFAULT_KEYS
        unknown = [k for k in keys if k not in LEAGUE_META]
        if unknown:
            raise SystemExit(f"unknown league key(s): {unknown}\nknown: {sorted(LEAGUE_META)}")
        targets = {k: LEAGUE_META[k] for k in keys}

    print(f"probing {len(targets)} league(s) — about {len(targets) * 6} API calls\n")
    async with httpx.AsyncClient() as hc:
        for lid, meta in targets.items():
            try:
                await probe(hc, lid, meta)
            except Exception as e:
                print(f"{lid:8} ERROR {e}")
            print()


if __name__ == "__main__":
    asyncio.run(main())
