"""Cheap backfill: set the real `round` on already-stored upcoming fixtures.
Only calls /fixtures (one per league) — no statistics calls."""
import os
import asyncio
import httpx
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient
from pathlib import Path

from sync_real import LEAGUE_META, _round_label, af_get, current_season

ROOT = Path(__file__).parent
load_dotenv(ROOT / ".env")
db = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]


async def main():
    async with httpx.AsyncClient() as hc:
        for lid, meta in LEAGUE_META.items():
            api = meta["api"]
            try:
                season = await current_season(hc, api)
                resp = await af_get(hc, "/fixtures", {"league": api, "season": season})
            except Exception as e:
                print(f"[{lid}] fixtures fetch failed: {e}")
                continue
            round_by_pair = {}
            for f in resp:
                hid = f["teams"]["home"]["id"]
                aid = f["teams"]["away"]["id"]
                round_by_pair[(f"{lid}-{hid}", f"{lid}-{aid}")] = _round_label(f["league"].get("round"))
            updated = 0
            fixtures = await db.fixtures.find({"league_id": lid}, {"_id": 0}).to_list(500)
            for fx in fixtures:
                rnd = round_by_pair.get((fx["home_team_id"], fx["away_team_id"]))
                if rnd:
                    await db.fixtures.update_one({"fixture_id": fx["fixture_id"]}, {"$set": {"round": rnd}})
                    updated += 1
            print(f"[{lid}] updated {updated}/{len(fixtures)} fixtures with round")


if __name__ == "__main__":
    asyncio.run(main())
