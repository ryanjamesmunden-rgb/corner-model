"""Fetch corner prices for upcoming fixtures and store them, so the board stops waiting
on somebody typing them in.

WHAT THIS REPLACES. Every price on the site is hand-entered: db.odds holds one document
per fixture stamped `source: "manual"`, and the value features trust only that stamp
because the seeders write `fair_odds * uniform(0.90, 1.15)`. So the pricing page is the
bottleneck every value feature waits on, and scanning a whole matchday by hand is the job
nobody has time for.

WHAT IT COSTS, SAID PLAINLY, because this is the reason it is not simply run over
everything twice a day: ONE API CALL PER FIXTURE. The board carries roughly 300 fixtures
a week and a price is only useful if it is refreshed, so fetching everything repeatedly is
the expensive way to do this. `--days` and `--leagues` narrow it, `--limit` caps it, and
the default is deliberately small. Check the printed call count before widening it.

WHERE IT WRITES, AND WHY NOT INTO db.odds. Feed prices go to their own collection,
db.odds_feed. db.odds is one document per fixture with a single `source` flag that
set_odds merges dicts into — so writing here would either overwrite a price a human chose
or be overwritten by one, and that one flag could never say which key came from where.
Separate collections mean a manual price always wins, a feed price ages on its own clock,
and neither can quietly become the other. See odds_feed.merge_prices.

WHAT IT STORES. Only the three markets this app can actually price: the match total and
each side's own corners, on .5 lines only. Half-time markets and Asian integer lines are
refused on purpose and odds_feed.py says why at length — both would put a confident EV
figure on the board against the wrong event.

Run: python fetch_odds.py                      (next 2 days, capped)
     python fetch_odds.py --days 3 --limit 60
     python fetch_odds.py --leagues eng-ch eng-l1
     python fetch_odds.py --dry-run            (what it WOULD fetch, no calls, no writes)
"""
import argparse
import asyncio
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

from odds_feed import SOURCE, feed_doc, first_entry
from sync_real import af_get

ROOT = Path(__file__).parent
load_dotenv(ROOT / ".env")

#: ONE DAY, BECAUSE THE MARKETS DO NOT EXIST BEFORE THEN. Measured: a window pass over
#: 62 fixtures spanning seven days came back `priced: 2, unpriced: 60` with no errors —
#: the books simply had not opened a corner market yet. The two that priced kicked off
#: that evening. Série B settles it as timing rather than coverage: its fixtures priced
#: fine when sampled on the day and returned nothing when asked about four days ahead.
#:
#: So a wider window does not buy earlier prices, it buys empty answers at one API call
#: each. Sixty of them, in the run that produced this comment.
DEFAULT_DAYS = 1
DEFAULT_LIMIT = 40

#: A price older than this is a memory of a price. The board should age it out rather than
#: rank on it; this is the same reasoning as set_odds stamping `updated_at`.
STALE_HOURS = 12


def _now():
    return datetime.now(timezone.utc)


async def upcoming(db, days: int, leagues, limit: int):
    """Fixtures that have not kicked off yet, soonest first.

    SOONEST FIRST BECAUSE THE BUDGET IS FINITE. If the limit cuts the list, the fixtures
    that get priced should be the ones about to be bet, not whichever the database
    happened to return."""
    now = _now()
    q = {"date": {"$gte": now.isoformat(),
                  "$lte": (now + timedelta(days=days)).isoformat()}}
    if leagues:
        q["league_id"] = {"$in": list(leagues)}
    rows = await db.fixtures.find(q, {"_id": 0}).sort("date", 1).to_list(limit * 3)
    out = []
    for fx in rows:
        api_fid = fx.get("api_fixture_id") or str(fx.get("fixture_id", "")).split("-")[-1]
        if not str(api_fid).isdigit():
            continue
        out.append((fx, int(api_fid)))
        if len(out) >= limit:
            break
    return out


async def fetch_one(hc, db, fx, api_fid, write=True):
    """One fixture: one API call, one upsert. Returns a short result line."""
    entry = first_entry(await af_get(hc, "/odds", {"fixture": api_fid}))
    if entry is None:
        return {"fixture_id": fx["fixture_id"], "priced": 0, "books": 0,
                "note": "no bookmaker quotes this fixture yet"}
    doc = feed_doc(fx["fixture_id"], api_fid, entry, _now().isoformat())
    if write:
        await db.odds_feed.update_one({"fixture_id": doc["fixture_id"]},
                                      {"$set": doc}, upsert=True)
    return {"fixture_id": fx["fixture_id"], "priced": len(doc["odds"]),
            "books": len(doc["bookmakers"]), "skipped": doc["skipped_total"],
            "keys": sorted(doc["odds"])}


#: How close to kick-off a capture counts as the closing price. The real closing line is
#: the last price before the off; this is the last price we can reliably reach.
CLOSING_MINUTES = 90


async def kicking_off_soon(db, minutes: int, limit: int):
    """Fixtures inside the closing window that have not kicked off yet."""
    now = _now()
    q = {"date": {"$gte": now.isoformat(),
                  "$lte": (now + timedelta(minutes=minutes)).isoformat()}}
    rows = await db.fixtures.find(q, {"_id": 0}).sort("date", 1).to_list(limit * 3)
    out = []
    for fx in rows:
        api_fid = fx.get("api_fixture_id") or str(fx.get("fixture_id", "")).split("-")[-1]
        if not str(api_fid).isdigit():
            continue
        out.append((fx, int(api_fid)))
        if len(out) >= limit:
            break
    return out


async def fetch_closing(db, minutes: int = CLOSING_MINUTES, limit: int = DEFAULT_LIMIT,
                        write: bool = True) -> dict:
    """Capture the last price before kick-off, so CLV can be computed at all.

    THIS CANNOT BE DONE AFTER THE GAME, which is the fact that shapes the whole design.
    The provider's /odds endpoint serves PRE-MATCH markets; once a fixture is played
    there is nothing left to ask for. So a closing price is not something to backfill
    later — it is something that is either captured in the hour before the off or lost for
    that fixture for good. That is why this is a separate scheduled pass rather than part
    of the twice-daily sync: the sync runs at 07:00 and 19:00, and a 15:00 kick-off is not
    near either.

    WHY IT IS WORTH A SCHEDULED JOB OF ITS OWN. A hundred settled bets cannot separate a
    5% edge from noise, but the closing price is a second opinion on every one of them,
    win or lose. It is the only evidence available that does not need hundreds of games.

    IT OVERWRITES NOTHING IT SHOULD NOT. Each capture is stamped with how many minutes
    before kick-off it was taken, and a later capture replaces an earlier one only when it
    is CLOSER to the off — so a job that runs twice in the window keeps the better
    reading, and a re-run after kick-off cannot overwrite a good capture with an empty one.
    """
    todo = await kicking_off_soon(db, minutes, limit)
    out = {"fixtures": len(todo), "calls": 0, "captured": 0, "unpriced": 0,
           "errors": 0, "kept_earlier": 0}
    if not todo:
        return out
    now = _now()
    async with httpx.AsyncClient() as hc:
        for fx, api_fid in todo:
            # Before the call, for the reason fetch_window's loop explains: a charged
            # call that is not counted is worse than one counted twice.
            out["calls"] += 1
            try:
                entry = first_entry(await af_get(hc, "/odds", {"fixture": api_fid}))
                if entry is None:
                    out["unpriced"] += 1
                    continue
                doc = feed_doc(fx["fixture_id"], api_fid, entry, now.isoformat())
                if not doc["odds"]:
                    out["unpriced"] += 1
                    continue
                try:
                    ko = datetime.fromisoformat((fx.get("date") or "").replace("Z", "+00:00"))
                    if ko.tzinfo is None:
                        ko = ko.replace(tzinfo=timezone.utc)
                    before = round((ko - now).total_seconds() / 60, 1)
                except Exception:
                    before = None
                doc["minutes_before_kickoff"] = before
                doc["captured_at"] = now.isoformat()
                doc["kickoff"] = fx.get("date")
                if write:
                    prev = await db.odds_closing.find_one(
                        {"fixture_id": doc["fixture_id"]},
                        {"_id": 0, "minutes_before_kickoff": 1})
                    old = (prev or {}).get("minutes_before_kickoff")
                    # Closer to the off wins. A capture with no readable clock never
                    # displaces one that has it.
                    if prev is not None and (before is None or
                                             (old is not None and old <= before)):
                        out["kept_earlier"] += 1
                        continue
                    await db.odds_closing.update_one({"fixture_id": doc["fixture_id"]},
                                                     {"$set": doc}, upsert=True)
                out["captured"] += 1
            except Exception as e:
                out["errors"] += 1
                out.setdefault("last_error", f"{type(e).__name__}: {e}"[:200])
    return out


async def fetch_window(db, days: int = DEFAULT_DAYS, limit: int = DEFAULT_LIMIT,
                       leagues=None) -> dict:
    """Price the next `days` of fixtures. The entry point the sync calls.

    ONE API CALL PER FIXTURE, and the returned `calls` says how many were made, because
    this is the only step in the sync that spends per-fixture rather than per-league.
    Whoever turns it on should be able to read the bill off the run record.

    A FAILURE HERE IS NEVER THE SYNC'S FAILURE. Form, fixtures and results are the data
    the whole site is built on; a price is a convenience on top of it. So every fixture is
    caught individually and the summary reports `errors` rather than raising — a provider
    hiccup on the odds endpoint must not mark a successful form sync as failed.
    """
    todo = await upcoming(db, days, leagues, limit)
    out = {"fixtures": len(todo), "calls": 0, "priced": 0, "unpriced": 0, "errors": 0,
           "lines": 0, "capped": len(todo) >= limit}
    if not todo:
        return out
    async with httpx.AsyncClient() as hc:
        for fx, fid in todo:
            # COUNTED BEFORE THE CALL, NOT AFTER IT SUCCEEDS. It was the other way round
            # and sixty calls went out against a mapping bug while this reported `calls:
            # 0` — so the run read as free as well as empty, and the one number that was
            # supposed to make the cost visible hid it instead. A call that is made is a
            # call that is charged, whatever happens to the answer, and over-counting a
            # request that never left is the safe direction for a bill.
            out["calls"] += 1
            try:
                r = await fetch_one(hc, db, fx, fid)
            except Exception as e:
                out["errors"] += 1
                out.setdefault("last_error", f"{type(e).__name__}: {e}"[:200])
                continue
            if r["priced"]:
                out["priced"] += 1
                out["lines"] += r["priced"]
            else:
                out["unpriced"] += 1
    return out


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=DEFAULT_DAYS)
    ap.add_argument("--limit", type=int, default=DEFAULT_LIMIT)
    ap.add_argument("--leagues", nargs="*", default=None)
    ap.add_argument("--dry-run", action="store_true",
                    help="list what would be fetched; no API calls and no writes")
    ap.add_argument("--closing", action="store_true",
                    help="capture the last price before kick-off (db.odds_closing) "
                         "instead of pricing the days ahead")
    ap.add_argument("--minutes", type=int, default=CLOSING_MINUTES,
                    help="how close to kick-off counts as closing (with --closing)")
    a = ap.parse_args()

    db = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]

    if a.closing:
        todo = await kicking_off_soon(db, a.minutes, a.limit)
        print(f"fixtures kicking off within {a.minutes}m: {len(todo)}")
        print(f"this run will make {0 if a.dry_run else len(todo)} API call(s)\n")
        for fx, _fid in todo:
            print(f"  {fx['date'][:16]}  {fx.get('home_name')} v {fx.get('away_name')}")
        if a.dry_run:
            return
        got = await fetch_closing(db, a.minutes, a.limit)
        print(f"\ncaptured {got['captured']}/{got['fixtures']}; {got['unpriced']} had no "
              f"lines, {got['kept_earlier']} already had a closer reading, "
              f"{got['errors']} error(s)")
        print("A closing price CANNOT be fetched after the game — the provider serves "
              "pre-match markets only. Run this on a schedule or it is lost per fixture.")
        return

    todo = await upcoming(db, a.days, a.leagues, a.limit)

    print(f"fixtures in the next {a.days}d with a provider id: {len(todo)}"
          f"{' (capped at --limit)' if len(todo) >= a.limit else ''}")
    print(f"this run will make {0 if a.dry_run else len(todo)} API call(s)\n")
    if a.dry_run:
        for fx, fid in todo:
            print(f"  would fetch {fx['date'][:16]}  {fx.get('home_name')} v "
                  f"{fx.get('away_name')}  ({fx.get('league_id')})")
        return

    priced = unpriced = 0
    async with httpx.AsyncClient() as hc:
        for fx, fid in todo:
            try:
                r = await fetch_one(hc, db, fx, fid)
            except Exception as e:                       # one bad fixture is not the run
                print(f"  !! {fx['fixture_id']}: {type(e).__name__}: {e}")
                continue
            if r["priced"]:
                priced += 1
                print(f"  {fx.get('home_name','?')[:20]:<20} v "
                      f"{fx.get('away_name','?')[:20]:<20} "
                      f"{r['priced']:>2} line(s) from {r['books']} book(s)  "
                      f"{','.join(r['keys'][:6])}")
            else:
                unpriced += 1
                print(f"  {fx.get('home_name','?')[:20]:<20} v "
                      f"{fx.get('away_name','?')[:20]:<20}  -- {r.get('note','no lines')}")

    print(f"\nstored prices for {priced}/{len(todo)} fixtures; {unpriced} had none")
    print(f"written to db.odds_feed with source={SOURCE!r}; db.odds (manual) untouched")


if __name__ == "__main__":
    asyncio.run(main())
