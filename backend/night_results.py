"""Offline: the corner counts from the games that have just been played.

THE SITE CANNOT ANSWER THIS, and that is the complaint it exists for. Every board here
is computed from the CURRENT team records and looks forward, so the moment a fixture
kicks off it drops out of everything — the row is gone, and with it any way to ask what
the game actually produced. The numbers are in db.fixture_stats the whole time; nothing
reads them back.

So this prints finished fixtures in a recent window with the corners each side won, the
match total, and the half-time score where it was filed. No model, no lines, no grading:
it is the result sheet a board cannot give you, and what you settle your own bets
against.

Deliberately NOT a record of anything claimed. Grading a pick needs the claim frozen
before kick-off — that is what the snapshot endpoints are for — and a results list that
started quietly settling things would be the survivorship trap all over again, in a file
whose name says it only reports scores.

Reads db.fixture_stats, db.teams and db.leagues. Writes nothing.
"""
import asyncio
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

ROOT = Path(__file__).parent
load_dotenv(ROOT / ".env")
db = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]

LON = ZoneInfo("Europe/London")
DAYS = 2


def london(stamp):
    """Kick-offs are stored in UTC; a reader in England reads them in London time, and
    the clocks move mid-season. The zone does that rather than a flat offset."""
    try:
        dt = datetime.fromisoformat((stamp or "").replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(LON)
    except Exception:
        return None


async def run(days=DAYS, league_id=None):
    since = (datetime.now(timezone.utc) - timedelta(days=days)).date().isoformat()
    q = {"date": {"$gte": since}}
    if league_id and league_id != "all":
        q["league_id"] = league_id
    matches = await db.fixture_stats.find(q, {"_id": 0}).to_list(4000)
    matches = [m for m in matches
               if m.get("home_corners") is not None and m.get("away_corners") is not None]
    matches.sort(key=lambda m: (m.get("date") or "", m.get("league_id") or ""))

    names = {t["team_id"]: t["name"] for t in
             await db.teams.find({}, {"_id": 0, "team_id": 1, "name": 1}).to_list(4000)}
    leagues = {l["league_id"]: l["name"] for l in
               await db.leagues.find({}, {"_id": 0}).to_list(200)}

    if not matches:
        print(f"No finished fixtures with corner data since {since}.")
        return

    print(f"CORNERS IN THE LAST {days} DAYS — {len(matches)} finished fixtures\n")
    day = None
    for m in matches:
        dt = london(m.get("date"))
        key = dt.strftime("%A %d %B") if dt else (m.get("date") or "?")[:10]
        if key != day:
            day = key
            print(f"\n{key}")
            print(f"  {'time':<6} {'competition':<22} {'fixture':<46} "
                  f"{'corners':>9}  {'total':>5}")
        home = names.get(m.get("home_id"), f"#{m.get('home_id')}")
        away = names.get(m.get("away_id"), f"#{m.get('away_id')}")
        hc, ac = m["home_corners"], m["away_corners"]
        print(f"  {dt.strftime('%H:%M') if dt else '--:--':<6} "
              f"{leagues.get(m.get('league_id'), '?')[:22]:<22} "
              f"{(home + ' v ' + away)[:46]:<46} "
              f"{str(hc) + '-' + str(ac):>9}  {hc + ac:>5}")

    totals = [m["home_corners"] + m["away_corners"] for m in matches]
    print(f"\n{len(matches)} fixtures, {sum(totals)} corners, "
          f"{sum(totals)/len(totals):.1f} a game.")
    print(f"Highest {max(totals)}, lowest {min(totals)}. "
          f"{sum(1 for t in totals if t >= 10)} games reached 10+, "
          f"{sum(1 for t in totals if t < 8)} finished under 8.")


def main():
    args = sys.argv[1:]

    def opt(flag, default=None, cast=str):
        return cast(args[args.index(flag) + 1]) if flag in args else default

    asyncio.run(run(days=opt("--days", DAYS, int), league_id=opt("--league")))


if __name__ == "__main__":
    main()
