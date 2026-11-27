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
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

from game_state import match_winner

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

_SIDE_HALF = re.compile(r"^(over|under)\s+(\d+)\.5$", re.I)
_SIDE_INT = re.compile(r"^(over|under)\s+(\d+)$", re.I)


def parse_line(label: str) -> Tuple[Optional[float], Optional[str], Optional[str]]:
    """"Over 4.5" -> (4.5, "over", None). "Under 9.5" -> (9.5, "under", None).

    THE .5 IS KEPT BECAUSE THE KEY KEEPS IT. server.py's TEAM_LINES and TOTAL_LINES are
    lists of floats, so build_markets writes `home_over_4.5` — not `home_over_4` — and
    that spelling is what every reader of db.odds looks up. Returning the integer 4 here
    produced keys in the right shape for a key nothing queries: the prices would have
    stored cleanly, merged cleanly, and silently never matched a market. A mapping that
    fails by doing nothing is worse than one that throws.

    THE UNDER SIDE IS NOW KEPT, and it was never a question of the feed. Every over/under
    bet in the response carries both halves; this function discarded one of them because
    build_markets only ever made `_over_` keys, so an under price had nothing to be
    compared against. markets.build_extra_markets prices `{group}_under_{line}` from the
    same distribution — Under 9.5 is exactly 1 - P(X >= 10) — so the price now has a fair
    price to sit beside, at no extra request and no extra API credit.

    An over key prices P(X >= int(line) + 1); an under key prices P(X <= int(line)). The
    integer lines stay refused on both sides, for the push reason in the header."""
    s = str(label or "").strip()
    m = _SIDE_HALF.match(s)
    if m:
        return float(m.group(2)) + 0.5, m.group(1).lower(), None
    m = _SIDE_INT.match(s)
    if m:
        return None, None, "integer line — exactly N is a push, which this model cannot price"
    return None, None, f"unrecognised line {s!r}"


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

    `taken` maps market key -> {"price", "book", "quotes", "prices"}: the BEST price
    quoted, who quoted it, how many books were seen for that key, and EVERY book's price
    for it. `skipped` records every market/line that was not stored and why, because a
    silent omission here looks identical to a fixture nobody prices.

    WHY `prices` EXISTS. The response already carries all five to seven books and this
    function was discarding them the moment one was beaten, which cost nothing to keep and
    left two questions unanswerable afterwards: how far clear the best price actually is
    (a 2.30 against 2.28 and 2.25 is a market, a 2.30 against 1.95 and 1.90 is an outlier
    worth distrusting), and whether a price exists at a book the reader actually holds.
    Keeping them is free — no second request, no extra API call."""
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
                line, direction, why = parse_line(val.get("value"))
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
                # SPELLED EXACTLY AS build_markets SPELLS IT — "home_over_4.5" and now
                # "home_under_4.5". See parse_line: a key with the .5 dropped matches
                # nothing and fails silently.
                key = f"{group}_{direction}_{line}"
                cur = taken.get(key)
                if cur is None:
                    taken[key] = {"price": price, "book": book, "quotes": 1,
                                  "prices": {book: price}}
                else:
                    cur["quotes"] += 1
                    # ONE ENTRY PER BOOK, ITS BEST. A bookmaker can quote the same market
                    # twice in one response — the probe saw both "Over 10.5" and "Over 10"
                    # fold onto the same key — and a dict keyed by book collapses that the
                    # same way the headline price does, rather than listing a book twice
                    # at two prices as though they were two books.
                    if price > cur["prices"].get(book, 0):
                        cur["prices"][book] = price
                    # BEST price wins: the backer takes the highest number available.
                    if price > cur["price"]:
                        cur["price"], cur["book"] = price, book

    return {"taken": taken, "skipped": skipped, "books": sorted(books)}


def first_entry(resp):
    """The one /odds entry out of whatever sync_real.af_get handed back.

    THE BUG THIS IS NAMED AFTER. af_get ends `return data["response"]` — it unwraps the
    provider's envelope and returns the LIST. The first version of the fetcher did
    `resp.get("response")`, which is what the raw API returns, and every call raised
    AttributeError: 'list' object has no attribute 'get'.

    It cost sixty real API calls to find out, and nothing was stored for any of them.
    Worse, it was invisible from outside: the fetcher reported `calls: 0` because the
    counter only incremented after a fixture parsed, so the run looked free as well as
    empty. A mapping bug that spends money and reports nothing is the exact failure the
    call count exists to make impossible.

    So the shape is handled here, in one tested place, and BOTH forms are accepted: the
    list af_get returns, and the envelope the provider sends, in case anything ever calls
    this with a raw response. Guessing between them at the call site is what went wrong.
    """
    if isinstance(resp, dict):
        resp = resp.get("response") or []
    if not isinstance(resp, list) or not resp:
        return None
    first = resp[0]
    return first if isinstance(first, dict) else None


def feed_doc(fixture_id: str, api_fixture_id, entry: dict, fetched_at: str,
             kickoff: Optional[str] = None) -> dict:
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
        # WHEN THE GAME IS, stored beside the price so its age can be judged against the
        # thing that makes a price go off: how close kick-off is. See allowed_age_hours.
        # Without it every reader would need the fixture document to decide whether a
        # price may be shown, which is a join on the hot path of every board. A document
        # written before this carries no `kickoff` and falls back to the flat twelve-hour
        # rule, so nothing needs migrating.
        "kickoff": kickoff,
        "odds": {k: v["price"] for k, v in got["taken"].items()},
        "books": {k: v["book"] for k, v in got["taken"].items()},
        "quotes": {k: v["quotes"] for k, v in got["taken"].items()},
        # EVERY BOOK'S PRICE, market by market. `odds` and `books` stay exactly as they
        # were — the best price and who quoted it — because everything downstream reads
        # them and a shape change there would be a migration. This rides alongside, so an
        # older document simply has no `quoted` and every reader has to cope with that
        # anyway.
        "quoted": {k: dict(sorted(v["prices"].items(), key=lambda kv: -kv[1]))
                   for k, v in got["taken"].items()},
        "bookmakers": got["books"],
        # Capped: a fixture quoted by seven books refuses the same twelve markets seven
        # times over, and the reasons repeat. Enough to diagnose, not a second copy of
        # the payload.
        "skipped": got["skipped"][:40],
        "skipped_total": len(got["skipped"]),
        # WHO THE MARKET THINKS WINS, read out of the same response at no extra cost:
        # /odds returns every market, so the Match Winner prices were already arriving and
        # being dropped. Consensus no-margin probabilities, not best prices — see
        # game_state.match_winner. None when no book quoted all three outcomes.
        "match_odds": match_winner(entry),
    }


def market_key(subject: str, is_home, line, direction: str = "over") -> Tuple[Optional[str], Optional[str]]:
    """A claim as it was posted -> the market key its price lives under, or why not.

    THE CLAIM AND THE KEY COUNT DIFFERENTLY, which is the whole reason this is a function
    and not an f-string at each call site. A post says "5+ corners"; the key for that bet
    is `home_over_4.5`, because build_markets spells its lines as the .5 the bet is struck
    on. Subtracting the 0.5 in one place and forgetting it in another is how a price gets
    compared against the wrong line.

    BOTH SIDES NOW HAVE KEYS. The under side used to come back refused because nothing
    stored it; markets.build_extra_markets prices `{group}_under_{line}` and extract keeps
    the feed's under half, so an under claim resolves to a real key with a real price.
    """
    want = str(direction or "over").lower()
    if want not in ("over", "under"):
        return None, f"unknown direction {direction!r}"
    n = None
    try:
        n = float(line)
    except (TypeError, ValueError):
        return None, f"unusable line {line!r}"
    group = "total" if str(subject or "team").lower() == "match" else \
        ("home" if is_home else "away" if is_home is False else None)
    if group is None:
        return None, "which side's corners this was about was never recorded"
    # "5+" is the bet; 4.5 is the line it is struck on, so an over claim shifts by half.
    #
    # AN UNDER CLAIM DOES NOT, and its line keeps the spelling the projection already
    # uses. _streak_projection reads `f"{group}_under_{line}"` with the INTEGER line and
    # prices it with a push on exactly that number ("under 10" voids on ten) — a different
    # event from the feed's "Under 9.5", which cannot push. Writing 10 as "10.0" here
    # would produce a key nothing holds and nothing ever would: the lookup would fail
    # silently, which is the failure this function's header is about.
    if want == "under":
        line = int(n) if float(n).is_integer() else n
    else:
        line = n - 0.5
    return f"{group}_{want}_{line}", None


#: The tightest a price is ever allowed to be, and the loosest.
#:
#: Twelve hours is the old flat rule and stays as the FLOOR, because inside a day of
#: kick-off team news moves a corner market and a price from before it is a memory. Three
#: days is the CEILING: past that a quote has had a full week of nothing happen to it.
PRICE_MIN_AGE_HOURS = 12
PRICE_MAX_AGE_HOURS = 72


def allowed_age_hours(hours_to_kickoff: Optional[float]) -> float:
    """How old a fetched price may be, given how far off the game is.

    WHY THIS IS NOT ONE NUMBER. A flat twelve-hour rule and the fetcher's "never re-ask a
    fixture that has a price" are individually reasonable and together make a weekend
    unbettable: books post Saturday corner markets on the Monday or Tuesday, the ahead
    pass picks them up then and never looks again, and by Wednesday every one of those
    prices is older than twelve hours and the board shows nothing. Measured on a real
    weekend: 239 fixtures the fetcher reported as already priced, 0 of Sunday's 59 showing
    a price on the board.

    Discarding them is the wrong half to fix. A price quoted on Monday for Saturday IS the
    market for that game — nothing has happened to the teams yet, no fresher quote exists,
    and the alternative on screen is a blank. What a reader needs is the price plus its
    age, not silence.

    So the tolerance scales with the distance to kick-off and tightens as it closes:
    roughly `hours_to_kickoff`, floored at twelve hours and capped at three days. A game
    five days out shows a three-day-old quote; one 36 hours out wants something from the
    last 36; inside half a day it is back to the original twelve-hour rule, which is when
    lineups and team news actually move a corner line.

    Unknown distance falls back to the floor — the behaviour before this existed — because
    a price that cannot be aged against anything must not be given extra rope.
    """
    if hours_to_kickoff is None:
        return float(PRICE_MIN_AGE_HOURS)
    return float(max(PRICE_MIN_AGE_HOURS, min(PRICE_MAX_AGE_HOURS, hours_to_kickoff)))


def price_is_stale(fetched_at, kickoff=None, now=None) -> bool:
    """True when a fetched price is too old to rank on, or carries no readable clock.

    ONE FUNCTION FOR THE BOARD AND THE FETCHER, and that is the point of it rather than a
    tidiness. The two used to decide separately: the board dropped anything over twelve
    hours old, the fetcher skipped any fixture that had a price at all, so a fixture could
    be "already priced" and "too old to show" at the same time, for ever, with nothing
    able to report the contradiction. Whatever this returns, both now agree: a price the
    board will not show is a price the fetcher treats as due.

    No clock means it cannot be aged, which means it cannot be shown to be current — so it
    is stale rather than waved through.
    """
    got, when = _as_dt(fetched_at), _as_dt(kickoff)
    if got is None:
        return True
    now = now or datetime.now(timezone.utc)
    age_h = (now - got).total_seconds() / 3600.0
    to_kick = ((when - now).total_seconds() / 3600.0) if when is not None else None
    # A game already under way or played is judged on the floor: there is no "distance" to
    # scale by, and a closing price is captured by its own pass.
    if to_kick is not None and to_kick < 0:
        to_kick = None
    return age_h > allowed_age_hours(to_kick)


def _as_dt(value):
    """An ISO timestamp as an aware datetime, or None. Never raises on stored junk."""
    try:
        dt = datetime.fromisoformat(str(value or "").replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt


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
