"""Add manually-tracked, already-settled Corner Model 2.0 picks (user-supplied results).
These carry their own result (no fixture/API resolution). Idempotent by _id."""
import os
import asyncio
from datetime import datetime, timezone
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient
from pathlib import Path

ROOT = Path(__file__).parent
load_dotenv(ROOT / ".env")
db = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]

# (team, line, odds, actual_corners, league_name)
MANUAL = [
    ("Fredrikstad", 5, None, 6, "Eliteserien"),
    ("Emmen", 5, None, 0, "Eerste Divisie"),
    ("Dordrecht", 5, None, 8, "Eerste Divisie"),
    ("Almere City", 5, None, 5, "Eerste Divisie"),
    ("NEC Nijmegen", 6, 1.40, 13, "Eredivisie"),
    ("PSV Eindhoven", 8, 1.73, 9, "Eredivisie"),
    ("Feyenoord", 6, 1.73, 10, "Eredivisie"),
]


async def main():
    for team, line, odds, corners, league in MANUAL:
        status = "won" if corners >= line else "lost"
        pid = f"manual|{team}|{line}|{corners}"
        await db.picks.update_one(
            {"_id": pid},
            {"$set": {"team": team, "line": line, "market": f"{line}+ team corners",
                      "odds": odds, "league_name": league, "source": "manual",
                      "date": None, "home": None, "away": None, "league_id": None,
                      "kickoff": None, "api_fixture_id": None,
                      "result_corners": corners, "status": status,
                      "settled_at": datetime.now(timezone.utc).isoformat()}},
            upsert=True)
    print(f"seeded {len(MANUAL)} manual picks; total picks = {await db.picks.count_documents({})}")


if __name__ == "__main__":
    asyncio.run(main())
