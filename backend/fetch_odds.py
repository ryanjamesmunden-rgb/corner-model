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

from odds_feed import SOURCE, feed_doc
from sync_real import af_get

ROOT = Path(__file__).parent
load_dotenv(ROOT / ".env")

#: Small on purpose — see the cost note above. Raise it deliberately, not by default.
DEFAULT_DAYS = 2
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
    resp = await af_get(hc, "/odds", {"fixture": api_fid})
    entries = resp.get("response") or []
    if not entries:
        return {"fixture_id": fx["fixture_id"], "priced": 0, "books": 0,
                "note": "no bookmaker quotes this fixture yet"}
    doc = feed_doc(fx["fixture_id"], api_fid, entries[0], _now().isoformat())
    if write:
        await db.odds_feed.update_one({"fixture_id": doc["fixture_id"]},
                                      {"$set": doc}, upsert=True)
    return {"fixture_id": fx["fixture_id"], "priced": len(doc["odds"]),
            "books": len(doc["bookmakers"]), "skipped": doc["skipped_total"],
            "keys": sorted(doc["odds"])}


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=DEFAULT_DAYS)
    ap.add_argument("--limit", type=int, default=DEFAULT_LIMIT)
    ap.add_argument("--leagues", nargs="*", default=None)
    ap.add_argument("--dry-run", action="store_true",
                    help="list what would be fetched; no API calls and no writes")
    a = ap.parse_args()

    db = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
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
