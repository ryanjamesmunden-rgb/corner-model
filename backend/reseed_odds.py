"""Regenerate placeholder bookmaker odds against the CURRENT real-data model.
No API calls — just realigns demo odds so edges look realistic. Run once."""
import asyncio
import os
import random
from pathlib import Path
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient
from server import expected_lambdas, poisson_ge, fair_odds, TOTAL_LINES

load_dotenv(Path(__file__).parent / ".env")
client = AsyncIOMotorClient(os.environ["MONGO_URL"])
db = client[os.environ["DB_NAME"]]


async def main():
    fixtures = await db.fixtures.find({}, {"_id": 0}).to_list(5000)
    teams = {t["team_id"]: t for t in await db.teams.find({}, {"_id": 0}).to_list(5000)}
    updated = 0
    for fx in fixtures:
        existing = await db.odds.find_one({"fixture_id": fx["fixture_id"]}, {"_id": 0})
        if not existing:
            continue  # only realign fixtures that already have demo odds
        h, a = teams.get(fx["home_team_id"]), teams.get(fx["away_team_id"])
        if not h or not a:
            continue
        lambdas = expected_lambdas(h, a)
        rng = random.Random(fx["fixture_id"] + "-reseed")
        odds = {}
        for line in TOTAL_LINES:
            p = poisson_ge(int(line) + 1, lambdas["total"])
            fo = fair_odds(p)
            if fo:
                odds[f"total_over_{line}"] = round(fo * rng.uniform(0.92, 1.16), 2)
        await db.odds.update_one({"fixture_id": fx["fixture_id"]}, {"$set": {"odds": odds}})
        updated += 1
    print(f"Realigned demo odds for {updated} fixtures")


if __name__ == "__main__":
    asyncio.run(main())
