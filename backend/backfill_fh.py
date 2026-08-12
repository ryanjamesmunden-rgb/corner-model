"""Backfill fh_goals_for/against (+ goals_for/against) onto team.real_matches from
the fixture_stats cache. DB-only, no API calls. Matches on api_team_id + date (day).

fh_goals_against is what makes a team's HALF-TIME state derivable (was it behind at
the break?), which the corners-by-state splits need."""
import asyncio
import os
from pathlib import Path
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

load_dotenv(Path(__file__).parent / ".env")
db = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]


async def main():
    # lookup: (api_team_id, YYYY-MM-DD) -> {fh, goals_for, goals_against}
    lut = {}
    async for c in db.fixture_stats.find({}, {"_id": 0}):
        d = (c.get("date") or "")[:10]
        if not d:
            continue
        hid, aid = c.get("home_id"), c.get("away_id")
        hg, ag = c.get("home_goals"), c.get("away_goals")
        hfg, afg = c.get("home_fh_goals"), c.get("away_fh_goals")
        if hid is not None:
            lut[(hid, d)] = {"fh": hfg or 0, "fha": afg or 0, "gf": hg or 0, "ga": ag or 0}
        if aid is not None:
            lut[(aid, d)] = {"fh": afg or 0, "fha": hfg or 0, "gf": ag or 0, "ga": hg or 0}

    teams = 0
    updated_matches = 0
    async for t in db.teams.find({}, {"real_matches": 1, "api_team_id": 1}):
        aid = t.get("api_team_id")
        rms = t.get("real_matches") or []
        if aid is None or not rms:
            continue
        changed = False
        for m in rms:
            key = (aid, (m.get("date") or "")[:10])
            hit = lut.get(key)
            if hit:
                m["fh_goals_for"] = hit["fh"]
                m["fh_goals_against"] = hit["fha"]
                m["goals_for"] = hit["gf"]
                m["goals_against"] = hit["ga"]
                updated_matches += 1
                changed = True
        if changed:
            await db.teams.update_one({"_id": t["_id"]}, {"$set": {"real_matches": rms}})
            teams += 1
    print(f"backfilled fh (for+against)/goals onto {updated_matches} matches "
          f"across {teams} teams")


if __name__ == "__main__":
    asyncio.run(main())
