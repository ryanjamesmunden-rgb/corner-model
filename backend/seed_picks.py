"""Seed the curated 'Corner Model 2.0 Picks' board. Idempotent: re-running keeps
already-settled results (only inserts new picks)."""
import os
import asyncio
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient
from pathlib import Path

ROOT = Path(__file__).parent
load_dotenv(ROOT / ".env")
db = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]

LEAGUE_NAME_TO_ID = {
    "Eredivisie": "ned-ere", "Eerste Divisie": "ned-ed", "League One": "eng-l1",
    "League Two": "eng-l2", "Championship": "eng-ch", "Ligue 1": "fra-l1",
    "Premier League": "eng-pl",
}

# (date, round, league, home, away, picked_team, line)
PICKS = [
    ("2026-08-09", 8, "Eredivisie", "Groningen", "Utrecht", "Utrecht", 5),
    ("2026-08-09", 8, "Eredivisie", "PEC Zwolle", "Ajax", "PEC Zwolle", 4),
    ("2026-08-09", 8, "Eredivisie", "Sparta Rotterdam", "Feyenoord", "Feyenoord", 5),
    ("2026-08-10", 9, "Eerste Divisie", "Jong AZ", "FC Eindhoven", "Jong AZ", 5),
    ("2026-08-14", 13, "Eredivisie", "Telstar", "Sparta Rotterdam", "Sparta Rotterdam", 5),
    ("2026-08-15", 14, "League One", "Plymouth", "Stockport County", "Plymouth", 5),
    ("2026-08-15", 14, "League Two", "Accrington ST", "Colchester", "Colchester", 5),
    ("2026-08-15", 14, "Championship", "Norwich", "West Brom", "Norwich", 5),
    ("2026-08-15", 14, "League One", "Reading", "Luton", "Luton", 5),
    ("2026-08-15", 14, "League Two", "Chesterfield", "Fleetwood Town", "Chesterfield", 5),
    ("2026-08-15", 14, "League Two", "Crawley Town", "Crewe", "Crewe", 5),
    ("2026-08-15", 14, "Championship", "Bristol City", "Millwall", "Millwall", 6),
    ("2026-08-15", 14, "League One", "Blackpool", "Wycombe", "Wycombe", 6),
    ("2026-08-15", 14, "Championship", "Stoke City", "Swansea", "Stoke City", 6),
    ("2026-08-16", 15, "Championship", "Watford", "Southampton", "Watford", 5),
    ("2026-08-22", 21, "Ligue 1", "Lens", "Auxerre", "Lens", 6),
    ("2026-08-23", 22, "Ligue 1", "Paris Saint Germain", "Rennes", "Paris Saint Germain", 5),
    ("2026-08-23", 22, "Premier League", "Manchester City", "Bournemouth", "Manchester City", 6),
]


async def main():
    for date, rnd, league, home, away, team, line in PICKS:
        pid = f"{date}|{home}|{away}|{team}|{line}"
        await db.picks.update_one(
            {"_id": pid},
            {"$set": {"date": date, "round": rnd, "league_name": league,
                      "league_id": LEAGUE_NAME_TO_ID.get(league), "home": home, "away": away,
                      "team": team, "line": line, "market": f"{line}+ team corners"},
             "$setOnInsert": {"status": "pending", "result_corners": None,
                              "api_fixture_id": None, "kickoff": None, "settled_at": None}},
            upsert=True)
    print(f"seeded {len(PICKS)} picks; total in db = {await db.picks.count_documents({})}")


if __name__ == "__main__":
    asyncio.run(main())
