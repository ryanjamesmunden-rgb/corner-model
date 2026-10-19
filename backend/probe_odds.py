"""Can we fetch CORNER prices automatically, on the key we already pay for?

THE QUESTION, ASKED PROPERLY. "Other sites do it so it must be possible" is true and does
not say whether it is possible HERE — the answer depends on one thing nobody has checked:
whether API-Football's odds feed carries corner markets for the competitions this app
syncs, and from which bookmakers. Everything else about automating prices is downstream of
that, so this probes it rather than anybody building on a guess.

EVERY PRICE ON THIS SITE IS TYPED IN BY HAND TODAY. db.odds holds one document per
fixture with a `source` of "manual" or "demo", and the value features deliberately trust
only "manual", because seed_team_odds writes `fair_odds * uniform(0.90, 1.15)` and an EV
computed against that is the model finding value in its own noise. So this is not a
nice-to-have: the pricing page is the thing every value feature waits on.

WHAT THIS PRINTS, IN THREE PARTS:

  1. EVERY BET TYPE THE PROVIDER OFFERS, with the corner ones called out. /odds/bets is a
     flat catalogue and costs one call. If no corner market is listed at all, nothing
     downstream matters and the answer is no.
  2. FOR REAL UPCOMING FIXTURES WE ALREADY HOLD, which bookmakers actually price those
     markets and at what. A market existing in the catalogue and a market being quoted on
     Tuesday's game in the Eerste Divisie are very different claims — top-flight coverage
     says nothing about League Two.
  3. A COVERAGE COUNT PER COMPETITION, because that is the number that decides whether
     this replaces hand-entry or merely supplements it. 90% of the Premier League and 5%
     of everything else would mean the board still waits on a human for most rows.

SPENDS API CREDITS: one /odds/bets call plus one /odds call per sampled fixture. Cheap,
and much cheaper than building a fetch path for a market the feed does not carry.

WHAT THIS DELIBERATELY DOES NOT DO: scrape bookmaker websites. It is against their terms,
it breaks whenever they ship a layout change, and a price that silently goes stale or
wrong is worse here than no price — the value board ranks on the gap between the model and
that number, so a bad one does not look like missing data, it looks like an edge.

Run: python probe_odds.py                   (the default sample)
     python probe_odds.py --league eng-pl
     python probe_odds.py --fixtures 6
"""
import asyncio
import os
import sys
from collections import Counter, defaultdict
from pathlib import Path

import httpx
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

from sync_real import af_get

ROOT = Path(__file__).parent
load_dotenv(ROOT / ".env")
db = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]

#: Fixtures sampled when no league is named. Spread across competitions rather than taken
#: off the front, because the front of the list is whichever league synced most recently
#: and coverage is the thing being measured.
DEFAULT_FIXTURES = 8

#: A bet whose name contains any of these is a corner market as far as this probe cares.
CORNER_WORDS = ("corner",)

BAR = "-" * 78


def is_corner(name):
    low = str(name or "").lower()
    return any(w in low for w in CORNER_WORDS)


async def catalogue(hc):
    """Every bet type the provider will quote, and the corner ones among them."""
    bets = await af_get(hc, "/odds/bets", {})
    rows = [{"id": b.get("id"), "name": b.get("name")} for b in bets]
    corner = [b for b in rows if is_corner(b["name"])]
    print(f"{BAR}\n1. THE CATALOGUE — every market the feed offers\n{BAR}")
    print(f"  {len(rows)} bet types listed; {len(corner)} mention corners\n")
    if not corner:
        print("  NO CORNER MARKET IN THE CATALOGUE AT ALL.")
        print("  That is a provider limit and nothing in this app can work around it.")
        print("  Automatic corner prices would need a different feed — see the note at")
        print("  the top of this file about why scraping is not the answer.")
        return []
    for b in corner:
        print(f"    id={b['id']:<5} {b['name']}")
    return corner


async def sample_fixtures(league_id, limit):
    """Upcoming fixtures we already hold, spread across competitions.

    OURS, NOT THE PROVIDER'S WHOLE LIST, because the question is whether the games on THIS
    board can be priced. A fixture the app does not store is not a gap this would fill.
    """
    q = {} if not league_id or league_id == "all" else {"league_id": league_id}
    docs = await db.fixtures.find(q, {"_id": 0}).sort("date", 1).to_list(3000)
    if not docs:
        return []
    by_league = defaultdict(list)
    for d in docs:
        by_league[d.get("league_id")].append(d)
    out, leagues = [], sorted(by_league)
    # Round-robin so a sample of eight is eight competitions where possible rather than
    # eight fixtures from whichever league happens to be first.
    i = 0
    while len(out) < limit and any(by_league[l] for l in leagues):
        lg = leagues[i % len(leagues)]
        if by_league[lg]:
            out.append(by_league[lg].pop(0))
        i += 1
    return out[:limit]


async def probe_fixture(hc, fx, corner_ids):
    """Which bookmakers quote a corner market on this fixture, and at what.

    THE FIXTURE ID IS THE PROVIDER'S, NOT OURS. db.fixtures keys on a derived id (see
    sync_real) and the odds endpoint wants API-Football's own, which is the numeric part.
    A mismatch here would report "no odds" for every fixture on the board and look exactly
    like the feed not carrying corners.
    """
    api_fid = fx.get("api_fixture_id") or str(fx.get("fixture_id", "")).split("-")[-1]
    if not str(api_fid).isdigit():
        return {"fixture": fx, "error": f"no provider fixture id (got {api_fid!r})"}
    resp = await af_get(hc, "/odds", {"fixture": int(api_fid)})
    if not resp:
        return {"fixture": fx, "books": [], "markets": {}}
    books, markets = [], defaultdict(list)
    for entry in resp:
        for bm in entry.get("bookmakers") or []:
            name = bm.get("name")
            hit = False
            for bet in bm.get("bets") or []:
                if not (is_corner(bet.get("name")) or bet.get("id") in corner_ids):
                    continue
                hit = True
                vals = [(v.get("value"), v.get("odd")) for v in (bet.get("values") or [])]
                markets[bet.get("name")].append({"book": name, "values": vals})
            if hit:
                books.append(name)
    return {"fixture": fx, "books": sorted(set(books)), "markets": dict(markets)}


async def run(league_id=None, fixtures=DEFAULT_FIXTURES):
    async with httpx.AsyncClient() as hc:
        corner = await catalogue(hc)
        corner_ids = {b["id"] for b in corner}
        if not corner:
            return

        fxs = await sample_fixtures(league_id, fixtures)
        print(f"\n{BAR}\n2. REAL FIXTURES ON THIS BOARD — who is quoting them\n{BAR}")
        if not fxs:
            print("  No upcoming fixtures stored. Run a sync before reading anything into")
            print("  this — an empty board and an unquoted one look identical here.")
            return

        leagues = {l["league_id"]: l.get("name", l["league_id"])
                   for l in await db.leagues.find({}, {"_id": 0}).to_list(500)}
        per_league = defaultdict(lambda: {"n": 0, "priced": 0})
        market_count = Counter()
        for fx in fxs:
            res = await probe_fixture(hc, fx, corner_ids)
            lg = leagues.get(fx.get("league_id"), fx.get("league_id"))
            slot = per_league[lg]
            slot["n"] += 1
            label = (f"{fx.get('home_name', '?')} v {fx.get('away_name', '?')}"
                     f"  ({lg}, {str(fx.get('date'))[:10]})")
            if res.get("error"):
                print(f"\n  {label}\n    SKIPPED — {res['error']}")
                continue
            if not res["books"]:
                print(f"\n  {label}\n    no corner market quoted by any bookmaker")
                continue
            slot["priced"] += 1
            print(f"\n  {label}\n    {len(res['books'])} bookmaker(s): "
                  f"{', '.join(res['books'][:6])}")
            for mname, entries in sorted(res["markets"].items()):
                market_count[mname] += 1
                first = entries[0]
                shown = ", ".join(f"{v}={o}" for v, o in first["values"][:4])
                print(f"      {mname}: {first['book']} -> {shown}")

        print(f"\n{BAR}\n3. COVERAGE — the number that decides whether this replaces "
              f"typing\n{BAR}")
        print(f"  {'competition':<28} {'sampled':>8} {'priced':>7}")
        for lg in sorted(per_league):
            s = per_league[lg]
            print(f"  {lg[:28]:<28} {s['n']:8} {s['priced']:7}")
        total_n = sum(s["n"] for s in per_league.values())
        total_p = sum(s["priced"] for s in per_league.values())
        print(f"\n  {total_p} of {total_n} sampled fixtures carry a corner price.")
        if market_count:
            print("\n  markets seen, most common first:")
            for mname, n in market_count.most_common():
                print(f"    {n:3}x  {mname}")
        print("\n  READ THE PER-COMPETITION SPLIT, NOT THE TOTAL. A feed that covers the")
        print("  Premier League and nothing below it would leave the board still waiting")
        print("  on a human for most rows, which is the same position as today for every")
        print("  league that actually needs the help.")
        print("\n  AND IF THIS DOES WORK: an auto-fetched price must NOT be stamped")
        print("  source=\"manual\". The value board trusts that flag to mean a human chose")
        print("  the number; a feed deserves its own source so the two can be told apart")
        print("  and so a stale fetch can be aged out separately.")


def main():
    args = sys.argv[1:]

    def opt(flag, default=None, cast=str):
        return cast(args[args.index(flag) + 1]) if flag in args else default

    asyncio.run(run(league_id=opt("--league"),
                    fixtures=opt("--fixtures", DEFAULT_FIXTURES, int)))


if __name__ == "__main__":
    main()
