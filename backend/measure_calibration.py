"""Offline: when the model says 77%, does it happen 77% of the time?

This is the question the chase board's published record raised and could not answer on
its own. As of 2026-09-21 the Daily 2 ledger read **23 of 44 settled, 52.3%**, while the
fair prices printed on the card (1.29, 1.36, 1.42) imply 77.5%, 73.5% and 70.4%. The 95%
Wilson interval on 23/44 is 37.5%-67.0%, so every one of those implied rates sits above
the TOP of the interval. Either the model is overconfident or 44 games is a coincidence,
and nothing in the ledger can separate those two.

WHAT THIS MEASURES: the residual.

    residual = actual hit rate - the model's own predicted probability

Zero means calibrated. Negative means the model claims more than it delivers.

THE TRAP THIS IS BUILT AROUND, and it is the whole reason the ledger cannot be read at
face value: the Daily 2 selects the HIGHEST model probability of the day. That is not a
random sample of the model's opinions, it is the extreme tail of them. Lambda is
ESTIMATED from a 10-game window, so it carries error in both directions; sorting by
probability and taking the top two preferentially picks the spots where that error
happened to run high. This is the winner's curse, and it produces a negative residual at
the top of the list EVEN IF THE MODEL IS UNBIASED ON AVERAGE. So a bad ledger does not by
itself convict the model, and a calibrated model overall does not acquit the selection.

Which is why there are two views, and why the second one is the one that decides:

  1. THE LEDGER. Every settled auto pick, scored against the `model_prob` that was
     FROZEN INTO THE PICK BEFORE KICK-OFF by _snapshot_daily_picks. Recomputing the
     probability afterwards would be look-ahead bias and would make the whole exercise
     worthless, so this reads the stored number and nothing else. It is the real
     published record. It is also small, so it is reported with a Wilson interval and
     is not asked to carry a conclusion on its own.

  2. THE REPLAY. The same model, walk-forward over every cached fixture, via
     measure_chase_board.build_spots — thousands of rows instead of dozens. Scored
     three ways, and the three together are the diagnosis:

       all spots        the model's calibration with no selection at all
       quality bar      the spots the Daily 2 was allowed to choose between
       top 2 per day    what the Daily 2 actually chose

     If ALL THREE are near zero, the ledger is noise and 44 games is simply too few.
     If ALL THREE are equally negative, the model is overconfident everywhere and the
     fix is the model — dispersion, most likely (see the note in measure_chase_board:
     NB_R is fixed at 11 for every team in every league).
     If ONLY the top-2 row is negative, the model is fine and the SELECTION is what
     bleeds — sorting on an estimated quantity is picking estimation error, and the fix
     is to stop sorting by probability, not to retune anything.

     That last case is the one nobody looks for, and it is the most likely of the three.

ALSO SPLIT BY LINE (3+, 4+, 5+, 6+). If the gap is uniform across lines it is a level
error and has a shape a single parameter can fix. If it widens with the line, it is the
tail of the distribution that is wrong, which is a dispersion problem and r=11 is the
suspect.

WHAT THIS IS NOT: it is not a search for an edge. Nothing here ranks anything or claims
to beat a price. It asks one question — is the printed number honest — and the only
actions it can justify are recalibrating the model or changing what the Daily 2 selects
on. See DAILY_PICK_RULE in server.py, and measure_chase_board.py for the ranking search
that already ran and failed.

Run: python measure_calibration.py
     python measure_calibration.py --league eng-pl
     python measure_calibration.py --skip-replay     (ledger only, instant)
"""
import asyncio
import math
import os
import sys
from collections import defaultdict
from pathlib import Path

from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

ROOT = Path(__file__).parent
load_dotenv(ROOT / ".env")
db = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]

# Bands over PREDICTED probability, in percent. Chosen to straddle the prices actually
# printed on the card: 1.42 -> 70.4, 1.36 -> 73.5, 1.29 -> 77.5.
BAND_EDGES = (65.0, 72.5, 80.0, 87.5)
MIN_BUCKET = 30          # below this a bucket is printed but marked as noise
Z = 1.96                 # 95%

# The Daily 2's quality bar, restated here so the replay can apply the SAME filter the
# live selection applies. Kept in sync with DAILY_MIN_VENUE_GAMES / DAILY_MIN_CONSISTENCY
# in server.py — if those move, move these, or the replay stops describing production.
BAR_MIN_OF = 4
BAR_MIN_RATE = 0.8
TOP_N = 2

WON_STATES = {"won", "half_won"}
LOST_STATES = {"lost", "half_lost"}


# --------------------------------------------------------------------------
# Pure — no I/O, so every line below this can be tested without a database
# --------------------------------------------------------------------------

def wilson(hits: int, n: int, z: float = Z):
    """95% interval on a hit rate, in percent. Wilson rather than normal-approximation
    because n here is often under 50 and a rate near 1.0, which is exactly where the
    textbook interval runs past 100% and stops meaning anything."""
    if n <= 0:
        return (0.0, 100.0)
    p = hits / n
    denom = 1 + z * z / n
    centre = p + z * z / (2 * n)
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return (max(0.0, (centre - half) / denom) * 100, min(1.0, (centre + half) / denom) * 100)


def hit_of(pick: dict):
    """Did the thing the probability described actually happen? 1 / 0 / None.

    Read from the RESULT rather than the status where possible. A team line stored as
    "X+" is Over (X - 0.5) and cannot push, so the two agree — but the result is the
    primitive and the status is a derived label, and a settlement bug would show up here
    as a disagreement rather than being silently inherited. A void has no answer at all
    and must be dropped, not counted as a loss."""
    line, corners = pick.get("line"), pick.get("result_corners")
    if line is not None and isinstance(corners, (int, float)) and not isinstance(corners, bool):
        return 1 if corners >= line else 0
    status = (pick.get("status") or "").lower()
    if status in WON_STATES:
        return 1
    if status in LOST_STATES:
        return 0
    return None


def predicted_of(pick: dict):
    """The probability AS IT STOOD BEFORE KICK-OFF, in percent, or None.

    `model_prob` is frozen into the pick by _snapshot_daily_picks. `model_odds` is the
    same number expressed as a price and is used only as a fallback for older picks
    written before model_prob was stored. Nothing here recomputes anything: a
    recomputed probability has seen the result and would make the residual meaningless."""
    p = pick.get("model_prob")
    if isinstance(p, (int, float)) and not isinstance(p, bool) and 0 < p <= 100:
        return float(p)
    odds = pick.get("model_odds")
    if isinstance(odds, (int, float)) and not isinstance(odds, bool) and odds >= 1.0:
        return 100.0 / odds
    return None


def ledger_rows(picks):
    """Settled auto picks reduced to (predicted, hit, line). Ungradeable rows are
    dropped and counted, never defaulted — a pick with no stored probability cannot
    contribute to a calibration check, and pretending otherwise is how a record starts
    flattering itself."""
    rows, dropped = [], defaultdict(int)
    for p in picks:
        hit = hit_of(p)
        if hit is None:
            dropped["not settled or void"] += 1
            continue
        pred = predicted_of(p)
        if pred is None:
            dropped["no stored probability"] += 1
            continue
        rows.append({"prob": pred, "hit": hit, "line": p.get("line"),
                     "date": p.get("date"), "team": p.get("team"),
                     "selected_by": p.get("selected_by")})
    return rows, dict(dropped)


def _label(lo: float, hi=None) -> str:
    # %g, not %.0f: an edge of 72.5 printed as "72" labels a band with a number no row
    # in it can have, and the table stops being checkable against the card's prices.
    if hi is None:
        return f"{lo:g}%+"
    return f"{lo:g}-{hi:g}%" if lo else f"<{hi:g}%"


def band_of(prob: float) -> str:
    """Which predicted-probability band a row falls in."""
    lo = 0.0
    for edge in BAND_EDGES:
        if prob < edge:
            return _label(lo, edge)
        lo = edge
    return _label(lo)


def band_keys():
    keys, lo = [], 0.0
    for edge in BAND_EDGES:
        keys.append(_label(lo, edge))
        lo = edge
    return keys + [_label(lo)]


def summarise(rows):
    """n, what was promised, what happened, and whether the promise is inside the
    interval the sample can actually support."""
    n = len(rows)
    if not n:
        return None
    hits = sum(r["hit"] for r in rows)
    predicted = sum(r["prob"] for r in rows) / n
    actual = hits / n * 100
    lo, hi = wilson(hits, n)
    return {"n": n, "hits": hits, "predicted": predicted, "actual": actual,
            "residual": actual - predicted, "lo": lo, "hi": hi,
            "covers": lo <= predicted <= hi}


def group(rows, key):
    out = defaultdict(list)
    for r in rows:
        out[key(r)].append(r)
    return out


def qualifying(spots, min_of=BAR_MIN_OF, min_rate=BAR_MIN_RATE):
    """The spots the Daily 2 was ALLOWED to choose between — the quality bar only, with
    no ordering applied. The gap between this and `top_per_day` below is entirely the
    cost of sorting on probability."""
    return [s for s in spots
            if (s.get("consistency_of") or 0) >= min_of
            and (s.get("consistency") or 0) >= min_rate]


def top_per_day(spots, top_n=TOP_N, key="prob"):
    """What the Daily 2 actually picks: the highest model probability of each day."""
    picked = []
    for _, rows in group(spots, lambda r: r["date"]).items():
        picked += sorted(rows, key=lambda r: r[key], reverse=True)[:top_n]
    return picked


def verdict(all_s, bar_s, top_s, tolerance=2.0):
    """Turn three residuals into the one sentence that says what to do next.

    The three cases are laid out in the module docstring; this only decides which of
    them the numbers are in, and it refuses to decide when the sample is too thin."""
    if not all_s or not top_s:
        return "not enough replayed spots to say anything"
    if top_s["n"] < MIN_BUCKET:
        return (f"only {top_s['n']} replayed picks — too few to separate the model from "
                f"the selection")
    base = all_s["residual"]
    sel = top_s["residual"]
    bar = bar_s["residual"] if bar_s else base
    if abs(base) <= tolerance and abs(sel) <= tolerance:
        return ("CALIBRATED, AND THE SELECTION COSTS NOTHING. The published 52.3% is then "
                "a small-sample result, not evidence of anything. Nothing to fix; the "
                "ledger needs more games, not a retune.")
    if abs(base) > tolerance and abs(sel - base) <= tolerance:
        return (f"THE MODEL IS OFF EVERYWHERE ({base:+.1f} with no selection at all). "
                f"The selection adds {sel - base:+.1f} on top, which is nothing. Fix the "
                f"model — read the by-line table: uniform means a level error, widening "
                f"with the line means dispersion, and NB_R is fixed at 11 for every team.")
    if abs(base) <= tolerance and sel < base - tolerance:
        return (f"THE MODEL IS FINE ({base:+.1f}) AND THE SELECTION BLEEDS ({sel:+.1f}, "
                f"{sel - bar:+.1f} of it from the sort alone). Sorting on an estimated "
                f"probability picks estimation error. The fix is what the Daily 2 selects "
                f"on, not the model — do not retune anything on this.")
    return (f"MIXED: {base:+.1f} unselected, {bar:+.1f} past the bar, {sel:+.1f} selected. "
            f"Both the model and the sort are contributing; read the tables before acting.")


# --------------------------------------------------------------------------
# Printing
# --------------------------------------------------------------------------

HEAD = (f"  {'bucket':>12} {'n':>6} {'promised':>9} {'actual':>8} {'residual':>9} "
        f"{'95% interval':>16}  ")


def print_row(tag, s):
    flag = "" if s["covers"] else "  <- promise outside the interval"
    thin = "  (thin)" if s["n"] < MIN_BUCKET else ""
    print(f"  {tag:>12} {s['n']:6} {s['predicted']:8.1f}% {s['actual']:7.1f}% "
          f"{s['residual']:+9.1f} {s['lo']:7.1f}-{s['hi']:.1f}%{flag}{thin}")


def print_table(title, buckets, order=None):
    print(f"\n{title}")
    print(HEAD)
    keys = order or sorted(buckets)
    for k in keys:
        rows = buckets.get(k)
        if not rows:
            continue
        s = summarise(rows)
        if s:
            print_row(str(k), s)


# --------------------------------------------------------------------------
# I/O
# --------------------------------------------------------------------------

async def ledger_view(league_id=None):
    q = {"auto": True}
    if league_id and league_id != "all":
        q["league_id"] = league_id
    picks = await db.picks.find(q, {"_id": 0}).to_list(20000)
    rows, dropped = ledger_rows(picks)
    print(f"\n{'=' * 78}\nTHE LEDGER — what was actually published")
    print(f"{'=' * 78}")
    print(f"auto picks on file: {len(picks)}   gradeable: {len(rows)}")
    for reason, n in sorted(dropped.items()):
        print(f"  dropped {n}: {reason}")
    if not rows:
        print("nothing settled with a stored probability — no calibration to check yet")
        return None
    overall = summarise(rows)
    print(f"\n  {overall['hits']} of {overall['n']} settled · {overall['actual']:.1f}%")
    print_table("by predicted probability", group(rows, lambda r: band_of(r["prob"])),
                order=band_keys())
    print_table("by line", group(rows, lambda r: f"{r['line']}+"))
    print_table("overall", {"all picks": rows})
    if not overall["covers"]:
        print(f"\n  The model promised {overall['predicted']:.1f}% and the sample supports "
              f"{overall['lo']:.1f}-{overall['hi']:.1f}%.\n  That is a real disagreement, "
              f"not rounding — but see the replay below before blaming the model:\n  these "
              f"picks are the top of the model's own confidence and are biased by selection.")
    else:
        print(f"\n  The promise ({overall['predicted']:.1f}%) sits inside what {overall['n']} "
              f"games can support ({overall['lo']:.1f}-{overall['hi']:.1f}%).\n  The record is "
              f"not evidence of a calibration problem. It is not evidence against one either.")
    return overall


async def replay_view(league_id=None, top_n=TOP_N):
    from measure_chase_board import build_spots

    spots, matches = await build_spots(league_id)
    print(f"\n{'=' * 78}\nTHE REPLAY — the same model over every cached fixture")
    print(f"{'=' * 78}")
    if not matches:
        print("no cached fixtures — run sync_real.py first")
        return None, None, None
    if not spots:
        print("no spot had enough history to price — nothing to measure")
        return None, None, None
    print(f"fixtures={len(matches)}  league={league_id or 'all'}  spots priced={len(spots)}")
    print(f"date range: {matches[0]['date'][:10]} -> {matches[-1]['date'][:10]}")

    bar = qualifying(spots)
    top = top_per_day(bar, top_n)
    all_s, bar_s, top_s = summarise(spots), summarise(bar), summarise(top)

    print("\nthe same model, three levels of selection")
    print(HEAD)
    for tag, s in (("all spots", all_s), ("quality bar", bar_s),
                   (f"top {top_n}/day", top_s)):
        if s:
            print_row(tag, s)
    print("\n  (the drop from `all spots` to `top N/day` is the cost of selection, not of"
          "\n   the model. The model's own error is the `all spots` row.)")

    print_table("all spots, by predicted probability",
                group(spots, lambda r: band_of(r["prob"])), order=band_keys())
    print_table("all spots, by line", group(spots, lambda r: f"{r['line']}+"))
    if top:
        print_table(f"top {top_n}/day, by line", group(top, lambda r: f"{r['line']}+"))
    return all_s, bar_s, top_s


async def run(league_id=None, top_n=TOP_N, skip_replay=False):
    print("CALIBRATION — does the printed probability happen as often as it claims?")
    await ledger_view(league_id)
    if skip_replay:
        print("\n(replay skipped — the ledger alone cannot separate an overconfident model "
              "from\n an unlucky 44 games. Re-run without --skip-replay for the answer.)")
        return
    all_s, bar_s, top_s = await replay_view(league_id, top_n)
    print(f"\n{'=' * 78}\nVERDICT\n{'=' * 78}")
    print(f"  {verdict(all_s, bar_s, top_s)}")


def main():
    args = sys.argv[1:]

    def opt(flag, default=None, cast=str):
        return cast(args[args.index(flag) + 1]) if flag in args else default

    asyncio.run(run(league_id=opt("--league"), top_n=opt("--top", TOP_N, int),
                    skip_replay="--skip-replay" in args))


if __name__ == "__main__":
    main()
