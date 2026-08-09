"""Seed placeholder bookmaker odds for TEAM-corner markets (home/away over lines)
so the Value Finder's default 'Team Corners (chase)' view has content. No API calls —
demo odds derived from the v2 model's fair odds. Merges into existing odds docs."""
import asyncio
import os
import random
from pathlib import Path
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient
from server import expected_lambdas, nb_ge, fair_odds, TEAM_LINES, REF_SHOTS

load_dotenv(Path(__file__).parent / ".env")
client = AsyncIOMotorClient(os.environ["MONGO_URL"])
db = client[os.environ["DB_NAME"]]


async def main():
    fixtures = await db.fixtures.find({}, {"_id": 0}).to_list(5000)
    teams = {t["team_id"]: t for t in await db.teams.find({}, {"_id": 0}).to_list(5000)}
    leagues = {l["league_id"]: l for l in await db.leagues.find({}, {"_id": 0}).to_list(200)}
    updated = 0
    for fx in fixtures:
        h, a = teams.get(fx["home_team_id"]), teams.get(fx["away_team_id"])
        if not h or not a:
            continue
        ls = leagues.get(fx["league_id"], {}).get("avg_shots") or REF_SHOTS
        lambdas = expected_lambdas(h, a, ls)
        rng = random.Random(fx["fixture_id"] + "-team")
        existing = await db.odds.find_one({"fixture_id": fx["fixture_id"]}, {"_id": 0})
        odds = dict(existing.get("odds", {})) if existing else {}
        for group in ("home", "away"):
            lam = lambdas[group]
            for line in TEAM_LINES:
                p = nb_ge(int(line) + 1, lam)
                fo = fair_odds(p)
                if fo and 1.2 <= fo <= 15:  # skip implausible extremes
                    odds[f"{group}_over_{line}"] = round(fo * rng.uniform(0.90, 1.15), 2)
        await db.odds.update_one({"fixture_id": fx["fixture_id"]}, {"$set": {"odds": odds}}, upsert=True)
        updated += 1
    print(f"Seeded team-corner demo odds for {updated} fixtures")


if __name__ == "__main__":
    asyncio.run(main())
