"""Was the projection any good? Graded against what the games actually produced.

WHY THIS EXISTS. The projections board says a game will have 10.4 corners. Nothing
anywhere said whether games it called 10.4 went on to produce ten, or eight, or thirteen —
so the number could be read as confident or as decoration and there was no way to tell
which. A projection nobody scores is a horoscope with decimals.

THE QUESTION IT IS BUILT TO ANSWER is not "what is the mean absolute error", which is a
modelling number and settles no bets. It is the one a person stands to act on: WHEN THE
MODEL PROJECTS A GAME QUIET, DOES THAT GAME GO UNDER. Both ends matter and they are not
symmetrical — the quiet end is the one the board was extended to show, because an under is
bet on the games a filtered board can never surface.

BIAS BEFORE ACCURACY. A model that is wrong by two corners in both directions is noisy and
still usable; a model wrong by one corner in the SAME direction every time poisons every
over bet placed off it while looking twice as accurate. So the signed error is reported
first and the absolute error second.

FULL-MATCH CORNERS ONLY. The synced match records carry `corners_for` and
`corners_against` and no half split — see probe_corner_halves.py, which exists to find out
whether one is obtainable. First-half lines cannot be graded here, and pretending
otherwise by halving a full-match number would invent a record rather than keep one.
"""
from typing import List, Optional

# The lines a corner market is actually priced around. Graded as stated rather than
# rounded to the projection, because a projection of 9.9 and a line of 9.5 are a bet and
# the whole point is whether that bet won.
LINES = (8.5, 9.5, 10.5, 11.5)

# Bands over the PROJECTION, not over the outcome. Grouping by outcome would answer "when
# a game had few corners, what had we said" — which reads well and is useless, because the
# outcome is not known when the bet is placed. These are the groups a reader can actually
# find themselves in beforehand.
BANDS = (
    ("quiet", None, 8.5),
    ("below par", 8.5, 9.5),
    ("middling", 9.5, 10.5),
    ("busy", 10.5, 11.5),
    ("very busy", 11.5, None),
)


def band_for(projection: Optional[float]) -> str:
    """Which band a projection falls in. Unknown projections are their own answer."""
    if projection is None:
        return "unknown"
    for name, lo, hi in BANDS:
        if (lo is None or projection >= lo) and (hi is None or projection < hi):
            return name
    return "unknown"


def settle_line(total: Optional[int], line: float) -> Optional[str]:
    """Did this match go over or under one line?

    None when the game has not settled. A half-line cannot push, which is why every line
    here is a half — a whole-number line would need a third answer and a stake returned,
    and reporting that as a win or a loss would misstate the record in one direction.
    """
    if total is None:
        return None
    return "over" if total > line else "under"


def grade(entry: dict, total: Optional[int]) -> dict:
    """One snapshotted fixture, with its outcome attached.

    `error` is SIGNED and actual-minus-projected, so a positive number means the game had
    more corners than the model said. Kept in that direction everywhere rather than
    flipped per-caller, because a sign convention that varies by function is a bug waiting
    for somebody to average two of them together.
    """
    projection = entry.get("lambda_total")
    out = {
        **entry,
        "actual_total": total,
        "band": band_for(projection),
        "settled": total is not None,
        "error": None,
        "abs_error": None,
        "lines": {},
    }
    if total is None or projection is None:
        return out
    out["error"] = round(total - projection, 2)
    out["abs_error"] = round(abs(total - projection), 2)
    # What the projection SAID about each line, and what the game did. Stored as a pair so
    # a caller cannot accidentally score the outcome against itself.
    out["lines"] = {
        str(line): {
            "called": "over" if projection > line else "under",
            "landed": settle_line(total, line),
        }
        for line in LINES
    }
    return out


def _rate(hits: int, of: int) -> Optional[float]:
    """A percentage, or None when there is nothing to divide by.

    NOT ZERO. A band with no settled games in it is not a band that never wins, and
    printing 0% for one is the kind of number somebody quotes back at you.
    """
    return round(100 * hits / of, 1) if of else None


def line_record(rows: List[dict], line: float) -> dict:
    """How often the projection's side of one line was the winning side.

    THIS IS THE NUMBER THAT MATTERS and it is deliberately not "how close was the
    projection". Betting a line is a binary question, and a model can be several corners
    out on average while still landing on the right side of 9.5 four times in five.
    """
    key = str(line)
    settled = [r for r in rows if r.get("lines", {}).get(key, {}).get("landed")]
    hits = sum(1 for r in settled
               if r["lines"][key]["called"] == r["lines"][key]["landed"])
    overs = [r for r in settled if r["lines"][key]["called"] == "over"]
    unders = [r for r in settled if r["lines"][key]["called"] == "under"]
    return {
        "line": line,
        "settled": len(settled),
        "hits": hits,
        "rate": _rate(hits, len(settled)),
        # SPLIT BY SIDE, because one good side can carry a mediocre overall number and
        # the reader is about to bet one side or the other, not the average of them.
        "over": {"called": len(overs),
                 "hits": sum(1 for r in overs if r["lines"][key]["landed"] == "over"),
                 "rate": _rate(sum(1 for r in overs if r["lines"][key]["landed"] == "over"),
                               len(overs))},
        "under": {"called": len(unders),
                  "hits": sum(1 for r in unders if r["lines"][key]["landed"] == "under"),
                  "rate": _rate(sum(1 for r in unders if r["lines"][key]["landed"] == "under"),
                                len(unders))},
    }


def band_record(rows: List[dict], name: str) -> dict:
    """What games in one projection band actually did.

    `under_9_5` and `over_10_5` ride along because they are the two questions the board is
    read for — the quiet end for unders, the busy end for overs — and computing them from
    the raw rows in a browser would be a second implementation of settle_line.
    """
    band = [r for r in rows if r.get("band") == name]
    settled = [r for r in band if r.get("settled")]
    totals = [r["actual_total"] for r in settled]
    projections = [r["lambda_total"] for r in settled if r.get("lambda_total") is not None]
    errors = [r["error"] for r in settled if r.get("error") is not None]
    return {
        "band": name,
        "games": len(band),
        "settled": len(settled),
        "avg_projected": round(sum(projections) / len(projections), 2) if projections else None,
        "avg_actual": round(sum(totals) / len(totals), 2) if totals else None,
        # Signed, actual minus projected. Positive means the model is projecting LOW here.
        "bias": round(sum(errors) / len(errors), 2) if errors else None,
        "under_9_5": _rate(sum(1 for t in totals if t < 9.5), len(totals)),
        "over_10_5": _rate(sum(1 for t in totals if t > 10.5), len(totals)),
    }


def summarise(rows: List[dict]) -> dict:
    """The whole record: overall accuracy, per band, per line.

    PENDING GAMES ARE COUNTED AND PUBLISHED rather than filtered out. A record that shows
    only what has settled is one dropped fixture away from being a record of the games
    that happened to be convenient, and the same discipline the streak record keeps.
    """
    settled = [r for r in rows if r.get("settled")]
    errors = [r["error"] for r in settled if r.get("error") is not None]
    abs_errors = [r["abs_error"] for r in settled if r.get("abs_error") is not None]
    return {
        "games": len(rows),
        "settled": len(settled),
        "pending": len(rows) - len(settled),
        # BIAS FIRST. A model wrong by one corner in the same direction every time poisons
        # every over bet placed off it while reading as more accurate than one that is
        # wrong by two in both directions.
        "bias": round(sum(errors) / len(errors), 2) if errors else None,
        "mean_abs_error": round(sum(abs_errors) / len(abs_errors), 2) if abs_errors else None,
        "bands": [band_record(rows, name) for name, _lo, _hi in BANDS],
        "lines": [line_record(rows, line) for line in LINES],
    }
