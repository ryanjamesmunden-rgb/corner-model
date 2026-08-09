"""Cheap backfill: populate goals + first-half goals onto existing fixture_stats
cache docs. One /fixtures call per league (no statistics calls)."""
import os
import asyncio
import httpx
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient
from pathlib import Path

from sync_real import LEAGUE_META, af_get, current_season

ROOT = Path(__file__).parent
load_dotenv(ROOT / ".env")
db = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]


async def main():
    total = 0
    async with httpx.AsyncClient() as hc:
        for lid, meta in LEAGUE_META.items():
            api = meta["api"]
            ids = [c["_id"] async for c in db.fixture_stats.find({"league_id": lid}, {"_id": 1})]
            if not ids:
                continue
            want = set(ids)
            updated = 0
            for season in (await current_season(hc, api), (await current_season(hc, api)) - 1):
                try:
                    resp = await af_get(hc, "/fixtures", {"league": api, "season": season})
                except Exception as e:
                    print(f"[{lid}] {season} fetch failed: {e}"); continue
                for f in resp:
                    fid = f["fixture"]["id"]
                    if fid not in want:
                        continue
                    g = f.get("goals") or {}
                    hth = ((f.get("score") or {}).get("halftime") or {})
                    await db.fixture_stats.update_one({"_id": fid}, {"$set": {
                        "home_goals": g.get("home") or 0, "away_goals": g.get("away") or 0,
                        "home_fh_goals": hth.get("home") or 0, "away_fh_goals": hth.get("away") or 0}})
                    updated += 1
                    want.discard(fid)
            total += updated
            print(f"[{lid}] goals backfilled on {updated} fixtures")
    print(f"done — {total} fixtures updated")


if __name__ == "__main__":
    asyncio.run(main())
