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

#: The lines this app actually prices, mirroring TEAM_LINES and TOTAL_LINES in server.py.
#: A FEED LINE OUTSIDE THESE IS REFUSED, for the same reason the half-time markets are:
#: build_markets never creates a key for it, so there would be no fair price to compare a
#: stored book price against, and an EV column with no fair value behind it is not a
#: smaller edge but an invented one. The feed quotes "Over 14.5" totals and "Over 1.5"
#: team lines that fall outside both.
TEAM_FEED_LINES = frozenset({2.5, 3.5, 4.5, 5.5, 6.5, 7.5, 8.5, 9.5})
TOTAL_FEED_LINES = frozenset({6.5, 7.5, 8.5, 9.5, 10.5, 11.5, 12.5, 13.5})
GROUP_LINES = {"home": TEAM_FEED_LINES, "away": TEAM_FEED_LINES,
               "total": TOTAL_FEED_LINES}

_OVER_HALF = re.compile(r"^over\s+(\d+)\.5$", re.I)
_OVER_INT = re.compile(r"^over\s+(\d+)$", re.I)


def parse_line(label: str) -> Tuple[Optional[float], Optional[str]]:
    """"Over 4.5" -> (4.5, None). Anything else -> (None, why not).

    THE .5 IS KEPT BECAUSE THE KEY KEEPS IT. server.py's TEAM_LINES and TOTAL_LINES are
    lists of floats, so build_markets writes `home_over_4.5` — not `home_over_4` — and
    that spelling is what every reader of db.odds looks up. Returning the integer 4 here
    produced keys in the right shape for a key nothing queries: the prices would have
    stored cleanly, merged cleanly, and silently never matched a market. A mapping that
    fails by doing nothing is worse than one that throws.

    The key prices P(X >= int(line) + 1), which is the same event the feed means by
    "Over N.5"."""
    s = str(label or "").strip()
    m = _OVER_HALF.match(s)
    if m:
        return float(m.group(1)) + 0.5, None
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
                if line not in GROUP_LINES[group]:
                    skipped.append({"market": name, "book": book,
                                    "line": str(val.get("value")),
                                    "why": f"line {line} is outside the ladder this model "
                                           f"prices, so there is no fair price for it"})
                    continue
                price = _price(val.get("odd"))
                if price is None:
                    skipped.append({"market": name, "book": book,
                                    "line": str(val.get("value")),
                                    "why": f"unusable price {val.get('odd')!r}"})
                    continue
                # SPELLED EXACTLY AS build_markets SPELLS IT — "home_over_4.5". See
                # parse_line: a key with the .5 dropped matches nothing and fails silently.
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


def market_key(subject: str, is_home, line, direction: str = "over") -> Tuple[Optional[str], Optional[str]]:
    """A claim as it was posted -> the market key its price lives under, or why not.

    THE CLAIM AND THE KEY COUNT DIFFERENTLY, which is the whole reason this is a function
    and not an f-string at each call site. A post says "5+ corners"; the key for that bet
    is `home_over_4.5`, because build_markets spells its lines as the .5 the bet is struck
    on. Subtracting the 0.5 in one place and forgetting it in another is how a price gets
    compared against the wrong line.

    UNDERS COME BACK REFUSED, and honestly. build_markets only ever creates `_over_` keys,
    and this module refuses the feed's under side, so no fetched price exists for an under
    at all — answering with a key that nothing will ever hold would turn "we cannot
    measure this" into "this had no closing price", which are different facts.
    """
    if str(direction or "over").lower() != "over":
        return None, "unders have no fetched price — the feed's under side is not stored"
    n = None
    try:
        n = float(line)
    except (TypeError, ValueError):
        return None, f"unusable line {line!r}"
    group = "total" if str(subject or "team").lower() == "match" else \
        ("home" if is_home else "away" if is_home is False else None)
    if group is None:
        return None, "which side's corners this was about was never recorded"
    # "5+" is the bet; 4.5 is the line it is struck on.
    return f"{group}_over_{n - 0.5}", None


def clv_percent(taken, closing) -> Optional[float]:
    """How much better than the closing price you got, as a percentage of the odds.

    WHY CLV IS WORTH MORE THAN THE RESULT ON A SMALL SAMPLE. A hundred settled bets is
    not enough football to tell a 5% edge from noise, but the price the market closed at
    is a second opinion on every single one of them — available whether the bet won or
    lost. Beating the close repeatedly is the one piece of evidence that does not need
    hundreds of games to mean something.

    POSITIVE MEANS YOU TOOK THE BETTER PRICE. (2.10 taken, 2.00 close) is +5.0%.

    None rather than 0 when either price is missing or unusable, for the same reason
    settlement.pick_profit answers None for a win at an unknown price: an unmeasured CLV
    and a CLV of zero are different facts, and averaging the first as the second drags
    every summary towards nothing.
    """
    t, c = _price(taken), _price(closing)
    if t is None or c is None:
        return None
    return round((t / c - 1.0) * 100, 2)


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
