"""Every price that was stored on a game, graded after it was played.

WHY THIS EXISTS. The site could tell you what it thought BEFORE a game and what the board
claimed after it, but not what every PRICE on that game did. A fixture vanished from the
boards at kick-off and its twenty-odd stored lines went with it — so "which of the edges we
found actually landed, and at what price" was unanswerable, and the weekly question behind
it ("what is this model getting wrong") had nothing to read.

Two things come out of that, and they are the same join done twice:

  1. REVIEW. A played fixture plus the prices stored against it, each line settled, so the
     week can be read back: what the model liked, what the book offered, what happened.
  2. LAST TIME. For a line being offered NOW, the previous time that same team had that
     same line priced — did it land, and at what price. A 4+ at 1.24 that landed last week
     is a different proposition from one that has been missed three games running, and the
     board has always shown the model's number with no memory attached.

THE MARKET KEY IS THE UNIT, not the bet slip. db.odds and db.odds_feed store prices under
keys like `home_over_4.5`, `total_under_9.5`, `both_over_3.5`, and every one of them is a
claim that can be settled from two numbers: the home corner count and the away one. So the
grading here is a function of the key and nothing else — no team lookup, no venue
inference, no second settlement implementation to drift from the first.

SETTLEMENT IS settlement.grade_line AND NOT A COPY OF IT. Whole lines push, half lines
cannot, and that rule already lives in one place with tests around it. This file maps a key
onto (value, line, direction) and hands those three to it.
"""
import re
from typing import Dict, Iterable, List, Optional, Tuple

from settlement import HALF_LOST, HALF_WON, LOST, VOID, WON, grade_line, pick_profit

#: `home_over_4.5`, `total_under_9.5`, `both_over_3.5`.
_KEY = re.compile(r"^(home|away|total|both)_(over|under)_(\d+(?:\.\d+)?)$")

#: settlement's OWN vocabulary, imported rather than restated. Declaring these here as
#: literals is how a module ends up grading "push" while grade_line returns "void" — the
#: comparisons quietly stop matching and every push reads as neither a win nor a loss.
#: Quarter lines can also half-win, which is why these five exist and not three.
WIN, LOSS = WON, LOST
OUTCOMES = (WON, HALF_WON, VOID, HALF_LOST, LOST)


def parse_key(key: str) -> Optional[Tuple[str, str, float]]:
    """`home_over_4.5` -> ("home", "over", 4.5). Anything else -> None.

    Refusing rather than guessing: a key this cannot read is a market this cannot settle,
    and a review that silently skipped it would under-report the week rather than say so.
    """
    m = _KEY.match(str(key or "").strip())
    if not m:
        return None
    return m.group(1), m.group(2), float(m.group(3))


def value_for(group: str, home_corners: Optional[int], away_corners: Optional[int]
              ) -> Optional[float]:
    """The number this group's line is settled against.

    `both` is the WEAKER SIDE, and that is the whole definition of the market: "both teams
    4+" is won only if the side that won fewer corners still reached four, so the minimum
    is the figure the line is struck against. Taking the total, or either side on its own,
    grades a different bet.
    """
    if home_corners is None or away_corners is None:
        return None
    if group == "home":
        return float(home_corners)
    if group == "away":
        return float(away_corners)
    if group == "total":
        return float(home_corners + away_corners)
    if group == "both":
        return float(min(home_corners, away_corners))
    return None


def settle_key(key: str, home_corners: Optional[int], away_corners: Optional[int]
               ) -> Optional[dict]:
    """One stored market key against a finished game.

    Returns `{"result", "value", "line", "direction", "group"}`, or None when the key is
    unreadable or the corner counts are not known. None is not a loss — a game whose
    statistics were never fetched has no result, and counting it as one would be the
    cheapest way to make a record look worse or better than it is.
    """
    parsed = parse_key(key)
    if not parsed:
        return None
    group, direction, line = parsed
    value = value_for(group, home_corners, away_corners)
    if value is None:
        return None
    return {"group": group, "direction": direction, "line": line,
            "value": value, "result": grade_line(value, line, direction)}


def review_fixture(played: dict, odds: Dict[str, float],
                   model: Optional[Dict[str, dict]] = None) -> dict:
    """A played fixture and every price that was stored against it, settled.

    `odds` is `{market_key: price}` as the stores hold it. `model` is optional and maps the
    same keys to the model's own row — `{"prob", "fair_odds", "ev"}` — so the review can
    say whether the edges the board PUBLISHED are the ones that landed, which is the
    question a weekly read is actually asking.

    Every line comes back, winners and losers alike. A review that listed only the winners
    would be the same mistake as a tipster's results page.
    """
    hc, ac = played.get("home_corners"), played.get("away_corners")
    rows = []
    for key, price in sorted((odds or {}).items()):
        got = settle_key(key, hc, ac)
        if not got:
            continue
        m = (model or {}).get(key) or {}
        ev = m.get("ev")
        rows.append({
            "key": key, **got,
            "book_odds": price,
            "prob": m.get("prob"), "fair_odds": m.get("fair_odds"), "ev": ev,
            # AT A FLAT STAKE, because that is how this site's record is kept and a
            # review in different units from the record cannot be compared with it.
            "profit": pick_profit(got["result"], price),
        })
    landed = [r for r in rows if r["result"] == WIN]
    evplus = [r for r in rows if isinstance(r.get("ev"), (int, float)) and r["ev"] > 0]
    return {
        "fixture_id": played.get("fixture_id"),
        "date": played.get("date"),
        "league_id": played.get("league_id"),
        "home_name": played.get("home_name"), "away_name": played.get("away_name"),
        "home_corners": hc, "away_corners": ac,
        "total_corners": played.get("total_corners"),
        "corners_known": bool(played.get("corners_known")),
        "lines": rows,
        "priced": len(rows),
        "landed": len(landed),
        # THE EDGES THE BOARD ACTUALLY OFFERED, settled on their own. The whole-ladder
        # figure above includes lines nobody would have backed, so a review that reported
        # only it would say nothing about whether the model's opinion was worth anything.
        "ev_plus": len(evplus),
        "ev_plus_landed": sum(1 for r in evplus if r["result"] == WIN),
        "ev_plus_profit": _sum_profit(evplus),
        "profit": _sum_profit(rows),
    }


def _sum_profit(rows: Iterable[dict]) -> Optional[float]:
    """Flat-stake profit, or None when a winner's price is unknown.

    A win at an unknown price has no computable return — see pick_profit — so a total that
    quietly treated it as zero would understate a winning week.
    """
    rows = list(rows)
    vals = [r.get("profit") for r in rows]
    if any(v is None for v in vals):
        return None
    return round(sum(vals), 4)


def best_landed(reviews: Iterable[dict], limit: int = 20,
                min_ev: float = 0.0) -> List[dict]:
    """The biggest edges that actually came in, across a set of reviewed fixtures.

    RANKED BY EV, NOT BY PRICE, because the question is "was the model right where it was
    most confident it disagreed with the book" and not "what was the longest winner".
    """
    out = []
    for rv in reviews or []:
        for line in rv.get("lines") or []:
            ev = line.get("ev")
            if line.get("result") != WIN or not isinstance(ev, (int, float)):
                continue
            if ev <= min_ev:
                continue
            out.append({**line, "fixture_id": rv.get("fixture_id"),
                        "date": rv.get("date"),
                        "home_name": rv.get("home_name"),
                        "away_name": rv.get("away_name")})
    out.sort(key=lambda r: -(r.get("ev") or 0))
    return out[:max(1, limit)]


def tally(reviews: Iterable[dict]) -> dict:
    """The week in four numbers, plus the one that matters.

    `ev_plus_*` is the honest scoreboard: every stored line includes rungs nobody would
    back, so the hit rate across all of them describes the ladder, not the model.
    """
    rows = list(reviews or [])
    graded = [r for r in rows if r.get("corners_known")]
    lines = [ln for r in graded for ln in (r.get("lines") or [])]
    evplus = [ln for ln in lines
              if isinstance(ln.get("ev"), (int, float)) and ln["ev"] > 0]
    settled = [ln for ln in evplus if ln["result"] in (WIN, LOSS)]
    return {
        "fixtures": len(rows),
        "graded": len(graded),
        "awaiting_corners": len(rows) - len(graded),
        "lines": len(lines),
        "landed": sum(1 for ln in lines if ln["result"] == WIN),
        "ev_plus": len(evplus),
        "ev_plus_landed": sum(1 for ln in evplus if ln["result"] == WIN),
        "ev_plus_settled": len(settled),
        "ev_plus_rate": (round(100.0 * sum(1 for ln in settled if ln["result"] == WIN)
                               / len(settled), 1) if settled else None),
        "ev_plus_profit": _sum_profit(evplus),
    }


def last_time(key: str, history: Iterable[dict]) -> Optional[dict]:
    """The previous time this exact market was priced on this team, and how it went.

    `history` is that team's played fixtures, NEWEST FIRST, each carrying its own stored
    odds under `odds` — see the endpoint, which does the fetching.

    THE SAME KEY, NOT A SIMILAR ONE. `home_over_4.5` and `away_over_4.5` are two different
    bets and a team is not always at home; the caller resolves the venue and asks for the
    key it means. What comes back is the last game where that key had BOTH a price and a
    corner count, because "it landed" with no price attached answers half the question.
    """
    for game in history or []:
        price = (game.get("odds") or {}).get(key)
        if not price:
            continue
        got = settle_key(key, game.get("home_corners"), game.get("away_corners"))
        if not got:
            continue
        return {
            "fixture_id": game.get("fixture_id"), "date": game.get("date"),
            "home_name": game.get("home_name"), "away_name": game.get("away_name"),
            "key": key, "book_odds": price, **got,
            "profit": pick_profit(got["result"], price),
        }
    return None
