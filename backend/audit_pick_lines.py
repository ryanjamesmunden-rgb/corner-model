"""Offline: was the model's LAMBDA right for the picks it actually published?

WHERE THIS SITS. Three things are already settled and this does not re-open them:

  * The model is calibrated. measure_calibration replayed 11,590 spots: residual +0.1.
  * The grading is sound. audit_settlement checked all 44 settled picks against the
    fixture's own corner count, by team id. Zero disagreed, zero regraded.
  * The stored line and the stored probability agree with each other. _chase_board
    computes `line = max(3, round(lam) - 1)` and then `p = nb_ge(line, lam)` from that
    same lam, so a mismatched pair is not possible at write time.

WHAT IS LEFT. The 3+ picks went 6 of 15 (40.0%) against a promised 75.3%. The replay's
own top-2 3+ bucket — same selection, near-identical promise — went 75.9% over 365 rows:

    ledger, top-2 3+     15    promised 75.3%    actual 40.0%
    replay, top-2 3+    365    promised 75.0%    actual 75.9%

Same rule, same stated confidence, opposite outcome. Under the replay's own 75.9% the
ledger's 6 of 15 has p = 0.0007. That is either a genuinely unlucky fifteen games, or the
LIVE board's lambda differs from the replayed one in a way the replay cannot see.

HOW THIS TESTS IT — by inverting the probability instead of trusting it.

    implied lambda  =  the lam for which nb_ge(line, lam) equals the stored model_prob

nb_ge is monotonic in lam, so that inversion is exact and needs nothing but the two
numbers frozen onto the pick before kick-off. It recovers the model's own estimate of how
many corners it expected. Then compare it with what the team ACTUALLY won, which
settlement stored as `result_corners`:

    gap  =  implied lambda  -  actual corners

Averaged over a bucket, that gap IS the lambda error, in corners, with no model
re-running and no look-ahead. A calibrated model has a gap near zero. A 3+ bucket
promising 75.3% needs lambda around 4.0; if those teams were really winning 2.5, the
lambda was a corner and a half too high and the probability was never achievable.

WHY THAT IS THE USEFUL NUMBER. A residual in percentage points says the answer was wrong.
A gap in corners says by how much and in which direction, in the units the model actually
estimates — which is the difference between "recalibrate something" and a specific,
checkable claim about the inputs.

TWO SPLITS THAT WOULD EACH NAME A CAUSE:

  by line     a gap concentrated at 3+ means the max(3, ...) FLOOR is the problem. That
              floor fires for low-lambda teams, where round(lam) - 1 would be 2 or less,
              and it puts the line AT the mean rather than one below it. Those spots are
              not the same bet as the rest of the board and the board does not say so.
  by venue    a gap on away picks only is a venue-split problem, and measure_chase_board
              has a scar exactly there: `venue_delta` looked like a +9.1 edge until lambda
              was built venue-split the way production builds it, and then it vanished.

ALSO CHECKED: that `line == max(3, round(implied_lambda) - 1)` still holds. It must, by
construction — so if it ever fails, something rewrote a pick after it was priced and
every conclusion above is void. It is here as a tripwire, not as a hypothesis.

NO WRITES, NO API CALLS. It reads db.picks and nothing else.

Run: python audit_pick_lines.py
     python audit_pick_lines.py --league eng-pl
"""
import asyncio
import os
import sys
from collections import defaultdict
from pathlib import Path

from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

from server import NB_R, nb_ge

ROOT = Path(__file__).parent
load_dotenv(ROOT / ".env")
db = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]

LAM_LO, LAM_HI = 0.05, 30.0     # the bracket the inversion searches
LAM_STEPS = 60                  # bisection depth; 60 halvings is far past float precision
MIN_BUCKET = 10


# --------------------------------------------------------------------------
# Pure
# --------------------------------------------------------------------------

def implied_lambda(line, prob_pct, r=NB_R):
    """The lam for which nb_ge(line, lam) == prob. None when the pair is unusable.

    Bisection rather than a formula: nb_ge sums the pmf and has no closed-form inverse,
    but it is strictly increasing in lam, so bisection is exact to float precision and
    cannot land on the wrong root."""
    if line is None or prob_pct is None:
        return None
    try:
        line = int(line)
        p = float(prob_pct) / 100.0
    except (TypeError, ValueError):
        return None
    if not (0.0 < p < 1.0) or line < 0:
        return None
    lo, hi = LAM_LO, LAM_HI
    # A probability outside what the bracket can produce would otherwise return a
    # silently clamped endpoint, which reads as a real estimate.
    if nb_ge(line, lo, r) > p or nb_ge(line, hi, r) < p:
        return None
    for _ in range(LAM_STEPS):
        mid = (lo + hi) / 2
        if nb_ge(line, mid, r) < p:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def line_for(lam):
    """The board's own rule, restated: line = max(3, round(lam) - 1)."""
    return max(3, round(lam) - 1)


def row_for(pick):
    """One pick reduced to what the gap needs. None when it cannot contribute."""
    line, prob = pick.get("line"), pick.get("model_prob")
    corners = pick.get("result_corners")
    if not isinstance(corners, (int, float)) or isinstance(corners, bool):
        return None
    lam = implied_lambda(line, prob)
    if lam is None:
        return None
    return {"line": int(line), "prob": float(prob), "lam": lam,
            "corners": float(corners), "gap": lam - float(corners),
            "hit": 1 if corners >= line else 0,
            "rule_ok": line_for(lam) == int(line),
            "venue": pick.get("venue"), "league_id": pick.get("league_id"),
            "team": pick.get("team"), "date": pick.get("date")}


def summarise(rows):
    n = len(rows)
    if not n:
        return None
    return {"n": n,
            "prob": sum(r["prob"] for r in rows) / n,
            "lam": sum(r["lam"] for r in rows) / n,
            "corners": sum(r["corners"] for r in rows) / n,
            "gap": sum(r["gap"] for r in rows) / n,
            "actual": sum(r["hit"] for r in rows) / n * 100,
            "broken": sum(1 for r in rows if not r["rule_ok"])}


def group(rows, key):
    out = defaultdict(list)
    for r in rows:
        out[key(r)].append(r)
    return out


def verdict(by_line, overall, tolerance=0.5):
    """What the gap points at. Only ever names a cause the split actually supports."""
    if not overall:
        return "nothing gradeable — no conclusion"
    low = by_line.get(3)
    rest = [r for line, rows in by_line.items() if line != 3 for r in rows]
    low_s, rest_s = summarise(low or []), summarise(rest)
    if abs(overall["gap"]) <= tolerance:
        return (f"Lambda is RIGHT on average ({overall['gap']:+.2f} corners). The 3+ result "
                f"is then an unlucky {low_s['n'] if low_s else 0} games, not a broken "
                f"estimate — and nothing here justifies changing the model.")
    if low_s and rest_s and low_s["gap"] > rest_s["gap"] + tolerance:
        return (f"THE GAP IS AT THE 3+ LINE: {low_s['gap']:+.2f} corners there against "
                f"{rest_s['gap']:+.2f} elsewhere. That is the max(3, ...) FLOOR — it fires "
                f"for low-lambda teams, putting the line AT the mean instead of one below "
                f"it, so a 3+ pick is not the same bet as the rest of the board. Fix the "
                f"floor or stop publishing spots that hit it; do not retune lambda on this.")
    return (f"Lambda runs {overall['gap']:+.2f} corners high ACROSS THE BOARD, not just at "
            f"3+. That is an input problem, not the line rule — read the venue split below "
            f"before touching anything.")


# --------------------------------------------------------------------------
# Printing
# --------------------------------------------------------------------------

HEAD = (f"  {'bucket':>10} {'n':>5} {'promised':>9} {'implied λ':>10} {'actual':>8} "
        f"{'gap':>8} {'hit %':>7}")


def print_table(title, buckets, order=None):
    print(f"\n{title}")
    print(HEAD)
    for k in (order or sorted(buckets, key=lambda x: (x is None, x))):
        s = summarise(buckets.get(k) or [])
        if not s:
            continue
        thin = "  (thin)" if s["n"] < MIN_BUCKET else ""
        print(f"  {str(k):>10} {s['n']:5} {s['prob']:8.1f}% {s['lam']:10.2f} "
              f"{s['corners']:8.2f} {s['gap']:+8.2f} {s['actual']:6.1f}%{thin}")


async def run(league_id=None):
    q = {"auto": True, "status": {"$in": ["won", "lost", "half_won", "half_lost"]}}
    if league_id and league_id != "all":
        q["league_id"] = league_id
    picks = await db.picks.find(q, {"_id": 0}).to_list(20000)

    print("PICK LINE AUDIT — was the model's lambda right for the picks it published?")
    print("(reads only; no API calls)\n")
    rows = [r for r in (row_for(p) for p in picks) if r]
    print(f"settled picks: {len(picks)}   usable: {len(rows)}")
    if not rows:
        print("nothing with both a stored probability and a result — no gap to measure")
        return

    overall = summarise(rows)
    print(f"\n  promised {overall['prob']:.1f}%  ->  implied λ {overall['lam']:.2f} corners")
    print(f"  actually won {overall['corners']:.2f} corners  ->  gap {overall['gap']:+.2f}")
    print("  (gap = what the model expected minus what happened, in corners.")
    print("   Positive means lambda was too high and the price was never achievable.)")

    broken = [r for r in rows if not r["rule_ok"]]
    if broken:
        print(f"\n  !! {len(broken)} pick(s) violate line == max(3, round(λ) - 1), which is "
              f"impossible\n  !! at write time. Something rewrote them after pricing — every "
              f"number here is void\n  !! until that is explained.")
        for r in broken[:10]:
            print(f"      {r['date']}  {r['team']} {r['line']}+  implied λ {r['lam']:.2f} "
                  f"-> rule says {line_for(r['lam'])}+")

    by_line = group(rows, lambda r: r["line"])
    print_table("by line", by_line)
    print_table("by venue", group(rows, lambda r: r["venue"] or "?"))
    leagues = group(rows, lambda r: r["league_id"] or "?")
    if len(leagues) > 1:
        print_table("by league", leagues)

    print(f"\n{'=' * 78}\nVERDICT\n{'=' * 78}")
    print(f"  {verdict(by_line, overall)}")


def main():
    args = sys.argv[1:]

    def opt(flag, default=None, cast=str):
        return cast(args[args.index(flag) + 1]) if flag in args else default

    asyncio.run(run(league_id=opt("--league")))


if __name__ == "__main__":
    main()
