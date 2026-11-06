"""Turning the provider's corner odds into the market keys this app prices.

WHAT THE PROBE ESTABLISHED (probe_odds, run 6 Nov 2026, 8 of 8 sampled fixtures priced
across A-League, Austria Bundesliga, Championship, Jupiler Pro League, Liga Profesional,
Superliga, Série A and Série B — so not a top-flight-only feed): the provider carries 35
corner markets, quoted by Bet365, Pinnacle, 1xBet, Betano, Marathonbet, William Hill and
Betfair, 5 to 7 books per fixture.

ONLY THREE OF THOSE 35 ARE USABLE HERE, and the reason is the whole point of this file.

  Corners Over Under        -> total_over_N     match total
  Home Corners Over/Under   -> home_over_N      the home side's own corners
  Away Corners Over/Under   -> away_over_N      the away side's own corners

EVERY FIRST- AND SECOND-HALF CORNER MARKET IS REFUSED, and they are refused even though
the feed quotes them on every fixture sampled. There is no half-split corner DATA — the
provider's statistics endpoint returns one full-match number and `?half=1` returns it
again, byte-identical (probe_corner_halves, issue #260). So the model cannot produce a
fair price for "Total Corners (1st Half)", and storing a book price for a line we cannot
price would put a number on the value board with nothing to compare it against. An EV
column computed from a missing fair price is not a smaller edge, it is a fabricated one.

INTEGER LINES ARE REFUSED TOO, and this one is easy to miss because the price looks
normal. The feed quotes both "Over 10.5" and "Over 10" on the same market. "Over 10.5"
means 11 or more, which is exactly nb_ge(11, lam). "Over 10" is an Asian line: exactly ten
corners is a PUSH and the stake comes back. Its fair price is therefore not 1/P(X>=11) —
it is conditional on the game not landing on ten — and pricing it as though it were would
overstate the edge on every single one. build_markets has no push handling, so the honest
move is to take the .5 lines and record the rest as skipped with the reason attached.

WHY BEST PRICE RATHER THAN A NAMED BOOK. A backer wants the highest number available, so
the best of the quoted prices is the one an EV calculation should use, and the book that
offered it travels with it so the row can say where to go. Taking Bet365's price when
Pinnacle is a tick better would understate the edge and send the reader to the wrong place.

Pure functions, no database and no HTTP, so the mapping is testable without either.
"""
import re
from typing import Dict, List, Optional, Tuple

#: Provider market name -> the group in this app's market keys. Anything absent is refused.
MARKET_GROUP = {
    "Corners Over Under": "total",
    "Home Corners Over/Under": "home",
    "Away Corners Over/Under": "away",
}

#: Markets the feed offers that this app must NOT store, with the reason, so a future
#: reader does not "fix" the omission. Keyed by provider name.
REFUSED = {
    "Total Corners (1st Half)": "no half-split corner data exists (issue #260)",
    "Total Corners (2nd Half)": "no half-split corner data exists (issue #260)",
    "Home Total Corners (1st Half)": "no half-split corner data exists (issue #260)",
    "Home Total Corners (2nd Half)": "no half-split corner data exists (issue #260)",
    "Away Total Corners (1st Half)": "no half-split corner data exists (issue #260)",
    "Away Total Corners (2nd Half)": "no half-split corner data exists (issue #260)",
    "Corners Asian Handicap": "handicap, not a line this model prices",
    "Corners 1x2": "which side wins the corner count — not a total",
    "Corners Race To": "first to N, a different event",
    "Corners. Odd/Even": "not a line this model prices",
    "Corners. Total (Range)": "banded, not an over/under",
    "Multicorners": "combined across fixtures",
}

#: The source stamp. Deliberately NOT "manual": the value board treats manual as "a human
#: chose this number", and the seeders write fair_odds * uniform(0.90, 1.15), so an EV
#: against anything auto-generated must be distinguishable. See set_odds in server.py.
SOURCE = "api"

_OVER_HALF = re.compile(r"^over\s+(\d+)\.5$", re.I)
_OVER_INT = re.compile(r"^over\s+(\d+)$", re.I)


def parse_line(label: str) -> Tuple[Optional[int], Optional[str]]:
    """"Over 4.5" -> (4, None). Anything else -> (None, why not).

    The returned integer is the N in this app's `{group}_over_{N}` key, which prices
    P(X >= N+1) — the same event as the feed's "Over N.5"."""
    s = str(label or "").strip()
    m = _OVER_HALF.match(s)
    if m:
        return int(m.group(1)), None
    if _OVER_INT.match(s):
        return None, "integer line — exactly N is a push, which this model cannot price"
    if s.lower().startswith("under"):
        return None, "under side — the board prices overs"
    return None, f"unrecognised line {s!r}"


def _price(v) -> Optional[float]:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    # A price at or below evens on a corner over is not impossible, but 1.0 and below is
    # a feed artefact — the probe saw "Over 1 = 1.00" on 3-way markets.
    return f if 1.01 <= f <= 1000.0 else None


def extract(entry: dict) -> dict:
    """One /odds response entry -> the prices this app can use, plus what was refused.

    `taken` maps market key -> {"price", "book", "quotes"}: the BEST price quoted, who
    quoted it, and how many books were seen for that key. `skipped` records every
    market/line that was not stored and why, because a silent omission here looks
    identical to a fixture nobody prices."""
    taken: Dict[str, dict] = {}
    skipped: List[dict] = []
    books: set = set()

    for bm in (entry.get("bookmakers") or []):
        book = str(bm.get("name") or "").strip() or "?"
        books.add(book)
        for bet in (bm.get("bets") or []):
            name = str(bet.get("name") or "").strip()
            group = MARKET_GROUP.get(name)
            if group is None:
                why = REFUSED.get(name)
                if why:
                    skipped.append({"market": name, "book": book, "why": why})
                continue
            for val in (bet.get("values") or []):
                line, why = parse_line(val.get("value"))
                if line is None:
                    skipped.append({"market": name, "book": book,
                                    "line": str(val.get("value")), "why": why})
                    continue
                price = _price(val.get("odd"))
                if price is None:
                    skipped.append({"market": name, "book": book,
                                    "line": str(val.get("value")),
                                    "why": f"unusable price {val.get('odd')!r}"})
                    continue
                key = f"{group}_over_{line}"
                cur = taken.get(key)
                if cur is None:
                    taken[key] = {"price": price, "book": book, "quotes": 1}
                else:
                    cur["quotes"] += 1
                    # BEST price wins: the backer takes the highest number available.
                    if price > cur["price"]:
                        cur["price"], cur["book"] = price, book

    return {"taken": taken, "skipped": skipped, "books": sorted(books)}


def feed_doc(fixture_id: str, api_fixture_id, entry: dict, fetched_at: str) -> dict:
    """The document stored per fixture in db.odds_feed.

    A SEPARATE COLLECTION FROM db.odds ON PURPOSE. db.odds holds ONE document per fixture
    with one `source` flag and set_odds merges dicts into it, so writing feed prices there
    would either overwrite a price a human typed or be overwritten by one, and the single
    flag could not say which of the two any given key came from. Keeping them apart means
    a manual price always wins, a feed price is always aged on its own clock, and neither
    can quietly become the other."""
    got = extract(entry)
    return {
        "fixture_id": fixture_id,
        "api_fixture_id": api_fixture_id,
        "source": SOURCE,
        "fetched_at": fetched_at,
        "odds": {k: v["price"] for k, v in got["taken"].items()},
        "books": {k: v["book"] for k, v in got["taken"].items()},
        "quotes": {k: v["quotes"] for k, v in got["taken"].items()},
        "bookmakers": got["books"],
        # Capped: a fixture quoted by seven books refuses the same twelve markets seven
        # times over, and the reasons repeat. Enough to diagnose, not a second copy of
        # the payload.
        "skipped": got["skipped"][:40],
        "skipped_total": len(got["skipped"]),
    }


def merge_prices(manual: Dict[str, float], feed: Dict[str, float]) -> Dict[str, dict]:
    """Prices for one fixture, each labelled with where it came from.

    MANUAL ALWAYS WINS. A human typing a price has seen the market and chosen that
    number; a feed price is the best of whatever was quoted when the fetch ran. Where
    both exist the human's stands and the feed's is kept beside it, so a board can show
    that a better price is available elsewhere without silently switching to it."""
    out: Dict[str, dict] = {}
    for k, v in (feed or {}).items():
        p = _price(v)
        if p is not None:
            out[k] = {"price": p, "source": SOURCE}
    for k, v in (manual or {}).items():
        p = _price(v)
        if p is None:
            continue
        alt = out.get(k, {}).get("price")
        out[k] = {"price": p, "source": "manual"}
        if alt is not None:
            out[k]["feed_price"] = alt
            out[k]["feed_better"] = alt > p
    return out
