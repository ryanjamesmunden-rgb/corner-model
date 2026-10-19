"""What would have happened one line lower — and two lines lower, and one higher.

THE QUESTION THIS ANSWERS, asked after a good weekend: "how many corner lines won, or
would have won if we backed the line below what was recommended?"

It is a better question than it looks, and the reason is that it is NOT free information.
Dropping a line raises the hit rate by construction — 4+ lands at least as often as 5+,
always, in every sample, however bad the model is. So "we would have won more at one line
lower" is not evidence of anything on its own. The number that matters is the MARGIN:

    margin  =  corners actually won  -  the line we recommended

A board whose winners mostly clear by 4, 5 and 6 was recommending lines far below what the
games delivered, and the honest reading is that it was too timid. A board whose winners
mostly scrape home by 0 or 1 was priced about right, and dropping a line would buy a
handful of extra wins at a much worse price. Those two boards produce the SAME "one line
lower would have won more" headline and call for opposite changes, which is why this
reports the whole distribution rather than one counterfactual count.

AND IT CUTS BOTH WAYS. The same table reports one line HIGHER, because a board clearing by
5 and 6 is leaving money on the table and the only way to see that is to ask.

NO PRICES, AND THAT IS A REAL LIMIT STATED UP FRONT. A line lower is a shorter price, and
this module counts outcomes, not returns. "11 more would have landed at 4+" is true and
says nothing about whether 4+ was worth backing — that needs the odds for each rung, which
the ledger holds for only some rows. Where a price IS stored the script reports units
beside the counts; where it is not, it reports counts and says so. A counterfactual hit
rate quoted as though it were profit is the single easiest way to talk yourself into
backing shorter and shorter lines.

PURE, SO THE TESTS RUN. No database, no server import — the same split calibration.py
took, for the same reason: the one environment where this most needs checking is the one
where importing server dies on a pydantic-core panic.

THE SETTLE RULE IS DUPLICATED HERE ON PURPOSE, and line_ladder.py cross-checks it against
server.settle_streak_leg over a grid on every run. Importing the real one would drag the
whole app in and cost this module its tests; copying it without a check would let the two
drift silently, and a drifted settle rule produces a confident, wrong record.
"""
from collections import Counter, defaultdict

WIN, VOID, LOSS = "win", "void", "loss"

#: Offsets from the recommended line that the ladder reports, in display order.
#: Negative is an EASIER line (fewer corners needed for an over).
RUNGS = (1, 0, -1, -2)


def settle_at(value, line, direction="over"):
    """Settle one played game against one line. Mirrors server.settle_streak_leg.

    Exact-line results VOID on unders — a stake back, neither a win nor a loss — which is
    why every rate below divides by won+lost rather than by the row count.
    """
    if value is None or line is None:
        return None
    if direction == "under":
        if value < line:
            return WIN
        return VOID if value == line else LOSS
    return WIN if value >= line else LOSS


def shifted(line, offset, direction="over", floor=1):
    """The line `offset` rungs away, in the direction that makes an over EASIER.

    An over at a LOWER line is easier; an under at a HIGHER line is easier. So the offset
    is applied with the sign that means the same thing for both, and a reader comparing
    "one line easier" across the two is comparing like with like.

    `floor` keeps an over from sliding to 0+, which every game on earth clears and which
    would put a meaningless 100% row at the bottom of the table.
    """
    if line is None:
        return None
    shift = -offset if direction == "under" else offset
    return max(floor, line + shift)


def margin_of(row):
    """How far the result cleared the recommended line. Negative means it missed.

    Signed so that POSITIVE IS ALWAYS GOOD for the bet that was made, on both directions:
    an over wanting 5 that got 9 cleared by 4, and an under wanting below 5 that got 1
    also cleared by 4.
    """
    value, line = row.get("value"), row.get("line")
    if value is None or line is None:
        return None
    return (line - value) if row.get("direction") == "under" else (value - line)


def tally(rows, key="result"):
    """Counts and a rate that refuses to exist without a denominator."""
    won = sum(1 for r in rows if r.get(key) == WIN)
    lost = sum(1 for r in rows if r.get(key) == LOSS)
    void = sum(1 for r in rows if r.get(key) == VOID)
    settled = won + lost
    return {"rows": len(rows), "won": won, "lost": lost, "void": void,
            "settled": settled, "pending": len(rows) - settled - void,
            "rate": round(100.0 * won / settled, 1) if settled else None}


def graded(rows):
    """Only the rows with a real result behind them.

    A pending row cannot be re-settled at another line either, so it has to be excluded
    from EVERY rung or the denominators move between them and the comparison is void.
    """
    return [r for r in rows if r.get("value") is not None and r.get("line") is not None]


def ladder(rows, rungs=RUNGS, floor=1):
    """Every rung, settled over the same set of games.

    SAME GAMES AT EVERY RUNG. That is the whole validity of the comparison: if one rung
    quietly dropped the rows it could not settle, a lower line would look better partly
    because it was being scored on an easier subset.
    """
    pool = graded(rows)
    out = []
    for offset in rungs:
        settled = []
        for r in pool:
            line = shifted(r["line"], offset, r.get("direction", "over"), floor)
            settled.append({**r, "line_at": line,
                            "result": settle_at(r["value"], line,
                                                r.get("direction", "over"))})
        out.append({"offset": offset, **tally(settled),
                    # How many rows this rung moved, and which way. "11 more landed" is
                    # the number that gets quoted, so it is computed here rather than
                    # left to a reader subtracting two percentages.
                    "rows_at": settled})
    base = next((r for r in out if r["offset"] == 0), None)
    for r in out:
        r["gained"] = (r["won"] - base["won"]) if base else None
    return out


def margins(rows):
    """The distribution of how far the winners cleared, and the losers missed.

    THE ANSWER THE LADDER CANNOT GIVE. A lower line always wins more; only this says
    whether the lines were set too low to begin with. A pile-up at +4 and above means the
    board was being timid.
    """
    counts = Counter()
    for r in graded(rows):
        m = margin_of(r)
        if m is not None:
            counts[m] += 1
    if not counts:
        return None
    cleared = [m for m in counts.elements() if m >= 0]
    missed = [m for m in counts.elements() if m < 0]
    return {
        "counts": dict(sorted(counts.items())),
        "n": sum(counts.values()),
        "cleared": len(cleared),
        "missed": len(missed),
        "mean_cleared": round(sum(cleared) / len(cleared), 2) if cleared else None,
        "mean_missed": round(sum(missed) / len(missed), 2) if missed else None,
        # Winners that cleared by 3 or more. The board could have asked for more corners
        # on every one of these and still won.
        "comfortable": sum(n for m, n in counts.items() if m >= 3),
        # Losers that missed by exactly one. The nearly-rows, which is where a reader's
        # memory of a weekend tends to sit.
        "by_one": counts.get(-1, 0),
    }


def by_line(rows, rungs=RUNGS, floor=1):
    """The same ladder, split by the line that was recommended.

    A board can be timid at 4+ and about right at 7+, and a pooled table shows neither —
    the same reason calibration.py splits by line as well as by band.
    """
    groups = defaultdict(list)
    for r in graded(rows):
        groups[r["line"]].append(r)
    out = []
    for line in sorted(groups):
        rung_rows = ladder(groups[line], rungs, floor)
        out.append({"line": line, "n": len(groups[line]),
                    "margins": margins(groups[line]),
                    "rungs": [{k: v for k, v in r.items() if k != "rows_at"}
                              for r in rung_rows]})
    return out


# ---------------------------------------------------------------------------
# Match totals
# ---------------------------------------------------------------------------
#
# WHY THIS IS IN THE SAME FILE. The weekend that prompted it had Barnsley v Cambridge on
# the board from BOTH sides and the game finished 11-11 on corners — 22 in a match, with
# two team lines landing and no total line recommended because the board does not offer
# one. That is the gap, and it is measurable rather than anecdotal: take every graded
# fixture, add the two sides' counts, and ask what a total line would have done.
#
# A SINGLE 22-CORNER GAME IS NOT A CASE FOR A FEATURE. It is a case for counting, which is
# what these two functions do.

def fixture_totals(rows):
    """One row per FIXTURE, with both sides' corner counts where both are known.

    Keyed on the fixture where there is an id and on the pair of names and the date where
    there is not — snapshot rows and hand-posted angles carry different fields, and a
    fixture recognised under two keys would be counted twice.
    """
    seen = {}
    for r in graded(rows):
        if r.get("subject") not in (None, "team", "conceded"):
            continue
        fid = r.get("fixture_id")
        team, opp = r.get("name") or "", r.get("opponent") or ""
        date = str(r.get("played_at") or r.get("kickoff") or "")[:10]
        key = f"f:{fid}" if fid else "p:" + "|".join(sorted([team, opp]) + [date])
        slot = seen.setdefault(key, {"key": key, "date": date, "sides": {},
                                     "lines": [], "names": set()})
        slot["names"].update([team, opp])
        # `conceded` rows measure the OPPONENT's corners, so they fill the other slot.
        # Reading one as the subject team's count would invent a total.
        who = opp if r.get("subject") == "conceded" else team
        if who:
            slot["sides"][who] = r["value"]
        slot["lines"].append({"team": team, "line": r["line"],
                              "direction": r.get("direction", "over"),
                              "subject": r.get("subject") or "team",
                              "value": r["value"], "margin": margin_of(r)})
    out = []
    for slot in seen.values():
        sides = slot["sides"]
        both = len(sides) >= 2
        out.append({
            "key": slot["key"], "date": slot["date"],
            "teams": sorted(slot["names"] - {""}),
            "sides": sides,
            "lines": slot["lines"],
            # BOTH SIDES OR NOTHING. One side's count plus a guess at the other is not a
            # match total, and a total line settled against half a game would be wrong
            # about half the time in a way nothing downstream could detect.
            "total": sum(sides.values()) if both else None,
            "both_sides_known": both,
            # The fixtures that were on the board from BOTH ends — the shape the weekend
            # threw up, and the one a total line is most obviously for.
            "both_on_board": len({ln["team"] for ln in slot["lines"] if ln["team"]}) >= 2,
        })
    out.sort(key=lambda r: (-(r["total"] or 0), r["date"]))
    return out


def total_ladder(totals, lines=range(7, 25)):
    """What each match-total line would have done over the fixtures with both sides known.

    NOT A RECOMMENDATION AND NOT A BACKTEST. It is the hit rate a flat "over N total
    corners" would have shown on exactly the games the board already picked for other
    reasons — which is a biased sample by construction, because those games were chosen
    for having two corner-winning sides in them. That bias is the point when the question
    is "would a total line have landed on the games we were already on", and it would be
    fatal if anyone read these as league-wide odds. They are not.
    """
    pool = [t for t in totals if t.get("total") is not None]
    if not pool:
        return []
    out = []
    for line in lines:
        won = sum(1 for t in pool if t["total"] >= line)
        out.append({"line": line, "n": len(pool), "won": won,
                    "lost": len(pool) - won,
                    "rate": round(100.0 * won / len(pool), 1)})
    return out
