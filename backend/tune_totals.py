"""Which distribution should price a MATCH TOTAL? Walk-forward, on Brier + calibration.

WHY THIS EXISTS. Team corner lines are priced with a Negative Binomial (NB_R = 11, chosen
on tune_model.py with a recorded Brier). Match totals are priced with a Poisson. Nothing
in the repo records Poisson-for-totals ever being compared against anything — it reads
like a default nobody went back to.

It is not a small difference. The two disagree about the SAME fixture by up to ~6
percentage points, and they disagree directionally: at 7.5 home / 3.5 away the Poisson
says 7+ is 85.7% (fair 1.17) while convolving the model's own two team curves says 79.5%
(fair 1.26). Low lines come out too likely, high lines not likely enough. Both curves are
drawn on the same fixture page, so they visibly fail to add up.

That is an argument that something is wrong, not evidence for what is right. This settles
it the way r=11 was settled: walk forward through real matches, predict with each
candidate using only what was known beforehand, and score.

CANDIDATES
  pois_total      Poisson on the total lambda. What ships today.
  nb_total_rN     Negative Binomial on the total lambda, r swept.
  convolve_rN     The two team NB curves convolved. Coherent by construction — the total
                  IS the sum of the parts, so this is the only candidate that cannot
                  contradict the team prices sitting next to it.

A CAVEAT THE NUMBERS CANNOT SETTLE. Convolution assumes the two sides' corner counts are
independent. They are not: an open, stretched game produces more for both. Positive
correlation widens the true distribution further, so if convolve wins here it likely wins
by more than it shows, and if Poisson wins it is not because matches are Poisson.

Usage:  python tune_totals.py
"""
import os
import math
import asyncio
from collections import defaultdict, deque
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient
from pathlib import Path

ROOT = Path(__file__).parent
load_dotenv(ROOT / ".env")
db = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]

# The integer thresholds behind TOTAL_LINES (6.5 .. 13.5) in server.py — "7+" is the
# market, 6.5 is how it is stored.
LINES = [7, 8, 9, 10, 11, 12, 13, 14]
WINDOW = 10
MIN_GAMES = 5
R_SWEEP = [8, 11, 14, 18, 24]
MAX_K = 60          # far past any real corner total; the convolution tail is negligible


def pois_ge(L, lam):
    if lam <= 0:
        return 0.0
    cum = sum(math.exp(-lam) * lam ** i / math.factorial(i) for i in range(L))
    return max(0.0, min(1.0, 1 - cum))


def nb_pmf(k, lam, r):
    if lam <= 0:
        return 1.0 if k == 0 else 0.0
    p = r / (r + lam)
    return math.exp(math.lgamma(k + r) - math.lgamma(r) - math.lgamma(k + 1)
                    + r * math.log(p) + k * math.log(1 - p))


def nb_ge(L, lam, r):
    if lam <= 0:
        return 0.0
    return max(0.0, min(1.0, 1 - sum(nb_pmf(k, lam, r) for k in range(L))))


def convolved_ge(L, lam_h, lam_a, r):
    """P(home + away >= L) with each side its own NB. Cached per (lam, r) pair because the
    same two teams' lambdas recur across the sweep and the convolution is the slow part."""
    a = _nb_vec(round(lam_h, 3), r)
    b = _nb_vec(round(lam_a, 3), r)
    tot = 0.0
    # Only the head is needed: P(sum < L) is a triangle, and L is never more than 14.
    for i in range(min(L, len(a))):
        ai = a[i]
        if ai < 1e-12:
            continue
        for j in range(L - i):
            if j < len(b):
                tot += ai * b[j]
    return max(0.0, min(1.0, 1 - tot))


_VEC = {}


def _nb_vec(lam, r):
    key = (lam, r)
    if key not in _VEC:
        _VEC[key] = [nb_pmf(k, lam, r) for k in range(MAX_K)]
    return _VEC[key]


def avg(d):
    return sum(d) / len(d) if d else 0.0


async def run():
    matches = await db.fixture_stats.find({}, {"_id": 0}).to_list(40000)
    matches = [m for m in matches
               if m.get("home_corners") is not None and m.get("away_corners") is not None]
    matches.sort(key=lambda m: m["date"])

    cf = defaultdict(lambda: deque(maxlen=WINDOW))
    ca = defaultdict(lambda: deque(maxlen=WINDOW))

    models = ["pois_total"] + [f"nb_total_r{r}" for r in R_SWEEP] \
                            + [f"convolve_r{r}" for r in R_SWEEP]
    stat = {m: {L: [0.0, 0, 0, 0.0] for L in LINES} for m in models}
    used = 0

    for m in matches:
        h, a = m["home_id"], m["away_id"]
        can = (len(cf[h]) >= MIN_GAMES and len(ca[a]) >= MIN_GAMES
               and len(cf[a]) >= MIN_GAMES and len(ca[h]) >= MIN_GAMES)
        if can:
            used += 1
            # The same lambda the live model builds: a team's own corners won, averaged
            # with what the opponent concedes.
            lam_h = (avg(cf[h]) + avg(ca[a])) / 2.0
            lam_a = (avg(cf[a]) + avg(ca[h])) / 2.0
            lam_t = lam_h + lam_a
            actual = m["home_corners"] + m["away_corners"]
            for model in models:
                for L in LINES:
                    if model == "pois_total":
                        p = pois_ge(L, lam_t)
                    elif model.startswith("nb_total_r"):
                        p = nb_ge(L, lam_t, int(model.split("r")[-1]))
                    else:
                        p = convolved_ge(L, lam_h, lam_a, int(model.split("r")[-1]))
                    hit = 1 if actual >= L else 0
                    s = stat[model][L]
                    s[0] += p
                    s[1] += hit
                    s[2] += 1
                    s[3] += (p - hit) ** 2

        cf[h].append(m["home_corners"]); ca[h].append(m["away_corners"])
        cf[a].append(m["away_corners"]); ca[a].append(m["home_corners"])

    print(f"matches with enough history on both sides = {used} of {len(matches)}\n")
    print(f"{'model':16} {'Brier':>7} {'avg|gap|':>9}   per-line  model% vs actual%")
    rows = []
    for model in models:
        tb = tn = 0.0
        gaps, detail = [], []
        for L in LINES:
            s = stat[model][L]
            if s[2] == 0:
                continue
            mp, ah = s[0] / s[2] * 100, s[1] / s[2] * 100
            gaps.append(abs(mp - ah))
            tb += s[3]
            tn += s[2]
            detail.append(f"{L}+:{mp:4.1f}/{ah:4.1f}")
        if not tn:
            continue
        brier, gap = tb / tn, sum(gaps) / len(gaps)
        rows.append((brier, gap, model))
        print(f"{model:16} {brier:7.4f} {gap:9.2f}   {' '.join(detail)}")

    if rows:
        rows.sort()
        best_b = rows[0]
        best_g = min(rows, key=lambda r: r[1])
        live = next((r for r in rows if r[2] == "pois_total"), None)
        print(f"\nbest Brier:       {best_b[2]} ({best_b[0]:.4f})")
        print(f"best calibration: {best_g[2]} (avg gap {best_g[1]:.2f}pp)")
        if live:
            print(f"live today:       pois_total ({live[0]:.4f}, avg gap {live[1]:.2f}pp)")
            d = live[0] - best_b[0]
            print(f"\nBrier improvement available: {d:+.4f}"
                  f"{'  — nothing beats what ships' if d <= 0 else ''}")
        print("\nA WIN HERE IS NOT A MANDATE TO SHIP. r=11 was chosen on a margin this "
              "harness can reproduce;\nanything closer than that is noise, and the "
              "convolution's independence assumption is still\nan assumption. Read the "
              "per-line columns: a model that wins on Brier while missing badly at\none "
              "line is worse where it matters than the average says.")


if __name__ == "__main__":
    asyncio.run(run())
