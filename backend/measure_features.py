"""Offline: do the shot-volume features improve corner prediction?

Walk-forward over the cached fixture_stats, exactly like tune_model.py: every
prediction uses PRIOR form only, and rolling history is updated after predicting.
The live v2 model is the baseline (imported from server.py, so it is the real one),
and each candidate adds a feature as a multiplicative intent term of the same shape
the production lambda already uses for shots.

Three guards, because each of these will otherwise manufacture a result:

1. SAME SAMPLE. Feature coverage is partial, so a candidate scored only on fixtures
   that carry blocked shots would be compared against a baseline scored on
   everything — a different, easier sample. Rows lacking history for ANY feature
   under test are dropped for every model alike, and the drop count is reported.
2. MEAN-NEUTRAL INTENT. An intent term whose average is above 1 quietly scales
   lambda up. If the baseline under-predicts (it usually does at the low lines),
   that alone improves Brier and every feature looks predictive. Each intent term
   is divided by its own mean over the scored rows, so a candidate can only win by
   ranking teams correctly, not by shifting the overall level.
3. PLACEBO. Every feature is also scored with its values SHUFFLED across rows,
   destroying the team link while keeping the distribution. A shuffled feature must
   come out as no effect. If it doesn't, the harness is measuring an artifact and
   the real result cannot be trusted either — the script says so explicitly.

Reported differences are paired per-row with a 95% interval; on a few hundred rows
the third decimal is noise and a raw difference will look like a win anyway.

Run: python measure_features.py                 (every league, cached fixtures)
     python measure_features.py --league eng-pl
     python measure_features.py --window 10 --min-games 5
     python measure_features.py --sweep       (try several blocked-shots intent weights)
"""
import asyncio
import math
import os
import random
import sys
from collections import defaultdict, deque
from pathlib import Path

from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

from server import NB_R, nb_ge

ROOT = Path(__file__).parent
load_dotenv(ROOT / ".env")
db = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]

LINES = [4, 5, 6, 7]
WINDOW = 10
MIN_GAMES = 5
# below this many scored rows the comparison cannot separate a real effect from noise
MIN_ROWS = 2000
FEATURES = ["blocked_shots", "shots_on_target"]
BASE_FEATURE = "shots"          # what the live lambda already uses
ALL_FEATURES = [BASE_FEATURE] + FEATURES
PLACEBO_SEED = 20260812
# candidate weights for --sweep (the live shots term uses 0.10)
SWEEP_WEIGHTS = [0.05, 0.10, 0.15, 0.20, 0.30]


def avg(d):
    return sum(d) / len(d) if d else 0.0


def raw_intent(value, league_avg, weight=0.10):
    """The production intent term: +/-10% on lambda, clamped at 0.6-1.5x league average."""
    if not league_avg or value is None:
        return 1.0
    return (1.0 - weight) + weight * max(0.6, min(1.5, value / league_avg))


def pearson(xs, ys):
    n = len(xs)
    if n < 3:
        return None
    mx, my = sum(xs) / n, sum(ys) / n
    sx = math.sqrt(sum((x - mx) ** 2 for x in xs))
    sy = math.sqrt(sum((y - my) ** 2 for y in ys))
    if sx == 0 or sy == 0:
        return None
    return sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / (sx * sy)


def mean_ci(diffs):
    """Mean paired per-row difference with a 95% normal-approx interval."""
    n = len(diffs)
    if n < 2:
        return 0.0, 0.0
    m = sum(diffs) / n
    var = sum((d - m) ** 2 for d in diffs) / (n - 1)
    return m, 1.96 * math.sqrt(var / n)


async def build_rows(league_id, window, min_games):
    """Walk-forward pass: one prediction row per team-side, using prior form only."""
    q = {} if not league_id or league_id == "all" else {"league_id": league_id}
    matches = await db.fixture_stats.find(q, {"_id": 0}).to_list(60000)
    matches = [m for m in matches if m.get("date")]
    matches.sort(key=lambda m: m["date"])
    if not matches:
        return [], {}, {}, {}, matches

    lg, covered = {}, {}
    sides = len(matches) * 2
    for f in ALL_FEATURES:
        vals = [m[f"{side}_{f}"] for m in matches for side in ("home", "away")
                if m.get(f"{side}_{f}") is not None]
        lg[f] = (sum(vals) / len(vals)) if vals else 0.0
        covered[f] = len(vals)

    cf = defaultdict(lambda: deque(maxlen=window))
    ca = defaultdict(lambda: deque(maxlen=window))
    fhg = defaultdict(lambda: deque(maxlen=window))
    hist = {f: defaultdict(lambda: deque(maxlen=window)) for f in ALL_FEATURES}

    rows, drops = [], {"form": 0, "feature": 0}
    for m in matches:
        h, a = m.get("home_id"), m.get("away_id")
        if h is None or a is None:
            continue
        for team, opp, actual in ((h, a, m.get("home_corners")), (a, h, m.get("away_corners"))):
            if actual is None:
                continue
            if len(cf[team]) < min_games or len(ca[opp]) < min_games:
                drops["form"] += 1
                continue
            if any(len(hist[f][team]) < min_games for f in ALL_FEATURES):
                drops["feature"] += 1
                continue
            row = {"tf": avg(cf[team]), "oa": avg(ca[opp]), "fh": avg(fhg[team]),
                   "actual": actual}
            for f in ALL_FEATURES:
                row[f] = avg(hist[f][team])
            rows.append(row)

        # update rolling form AFTER predicting (no leakage)
        for team, side, other in ((h, "home", "away"), (a, "away", "home")):
            cf[team].append(m.get(f"{side}_corners") or 0)
            ca[team].append(m.get(f"{other}_corners") or 0)
            fhg[team].append(1 if (m.get(f"{side}_fh_goals") or 0) >= 1 else 0)
            for f in ALL_FEATURES:
                v = m.get(f"{side}_{f}")
                if v is not None:               # uncovered fixtures never enter the window
                    hist[f][team].append(v)
    return rows, lg, covered, drops, matches


def score(rows, lg, intents):
    """Score one candidate. `intents` maps feature -> per-row multiplier list (mean 1)."""
    stat = {L: [0.0, 0, 0, 0.0] for L in LINES}
    row_err = []
    for i, row in enumerate(rows):
        lam = (row["tf"] + row["oa"]) / 2.0
        for f, mult in intents.items():
            lam *= mult[i]
        lam *= 1.0 + 0.03 * (row["fh"] - 0.5)
        errs = []
        for L in LINES:
            p = nb_ge(L, lam, NB_R)
            hit = 1 if row["actual"] >= L else 0
            s = stat[L]
            s[0] += p; s[1] += hit; s[2] += 1; s[3] += (p - hit) ** 2
            errs.append((p - hit) ** 2)
        row_err.append(sum(errs) / len(errs))
    return stat, row_err


def normalised(values, league_avg, weight=0.10):
    """Intent multipliers with mean exactly 1, so a candidate cannot win by simply
    scaling lambda up against an under-predicting baseline."""
    mults = [raw_intent(v, league_avg, weight) for v in values]
    m = sum(mults) / len(mults) if mults else 1.0
    return [x / m for x in mults] if m else mults


async def run(league_id=None, window=WINDOW, min_games=MIN_GAMES, sweep=False):
    rows, lg, covered, drops, matches = await build_rows(league_id, window, min_games)
    if not matches:
        print("no cached fixtures — run sync_real.py first")
        return

    sides = len(matches) * 2
    print(f"fixtures={len(matches)}  league={league_id or 'all'}  window={window}  min_games={min_games}")
    print(f"date range: {matches[0]['date'][:10]} -> {matches[-1]['date'][:10]}")
    print("coverage (team-sides carrying the stat):")
    for f in ALL_FEATURES:
        print(f"  {f:18} {covered[f]:6}/{sides} ({covered[f] / sides * 100:5.1f}%)  league avg {lg[f]:.2f}")
    print(f"\nrows scored={len(rows)}  dropped(no corner form)={drops['form']}  "
          f"dropped(no feature history)={drops['feature']}")
    if not rows:
        print("\nNOTHING SCORED — no team has enough backfilled history yet. "
              "Run backfill_shots.py on more fixtures and re-run.")
        return
    if len(rows) < MIN_ROWS:
        print(f"\n!! {len(rows)} rows is too few to conclude anything (want >= {MIN_ROWS}).")
        print("!! Treat the table below as a smoke test that the pipeline works, NOT as evidence.")

    # per-row intent multipliers, mean-neutralised; plus a shuffled placebo per feature
    mult = {f: normalised([r[f] for r in rows], lg[f]) for f in ALL_FEATURES}
    rng = random.Random(PLACEBO_SEED)
    placebo = {}
    for f in FEATURES:
        shuffled = list(mult[f])
        rng.shuffle(shuffled)
        placebo[f] = shuffled

    candidates = {"v2_baseline (live)": {BASE_FEATURE: mult[BASE_FEATURE]}}
    for f in FEATURES:
        candidates[f"+{f}"] = {BASE_FEATURE: mult[BASE_FEATURE], f: mult[f]}
    candidates["+both"] = {BASE_FEATURE: mult[BASE_FEATURE],
                           **{f: mult[f] for f in FEATURES}}
    candidates["blocked_instead_of_shots"] = {"blocked_shots": mult["blocked_shots"]}
    if sweep:
        # the +/-10% weight was copied from the shots term; blocked shots may want its own
        for w in SWEEP_WEIGHTS:
            vals = normalised([r["blocked_shots"] for r in rows], lg["blocked_shots"], w)
            candidates[f"blocked_swap w={w:.2f}"] = {"blocked_shots": vals}
    for f in FEATURES:
        candidates[f"PLACEBO {f} (shuffled)"] = {BASE_FEATURE: mult[BASE_FEATURE], f: placebo[f]}

    results = {name: score(rows, lg, ints) for name, ints in candidates.items()}
    base = "v2_baseline (live)"
    base_err = results[base][1]

    print(f"\n{'model':30} {'Brier':>7} {'avg|gap|':>9} {'dBrier vs base (95% CI)':>27}   per-line model%/actual%")
    verdicts = {}
    for name, (stat, row_err) in results.items():
        tb = tn = 0.0
        gaps, detail = [], []
        for L in LINES:
            s = stat[L]
            if s[2] == 0:
                continue
            mp, ah = s[0] / s[2] * 100, s[1] / s[2] * 100
            gaps.append(abs(mp - ah)); tb += s[3]; tn += s[2]
            detail.append(f"{L}+:{mp:4.1f}/{ah:4.1f}")
        brier = tb / tn if tn else 0.0
        if name == base:
            cell, verdicts[name] = f"{'—':>27}", "baseline"
        else:
            m, ci = mean_ci([c - b for c, b in zip(row_err, base_err)])
            v = "better" if m + ci < 0 else ("worse" if m - ci > 0 else "no effect")
            verdicts[name] = v
            cell = f"{m:+.5f} +/-{ci:.5f} {v:>9}"
        print(f"{name:30} {brier:7.4f} {sum(gaps) / len(gaps):9.2f} {cell}   {' '.join(detail)}")

    # only a placebo that scores BETTER is a problem: shuffling destroys the team link,
    # so a shuffled feature can legitimately come out slightly worse (it adds noise to
    # lambda), but it can never legitimately improve the prediction
    bad_placebo = [f for f in FEATURES if verdicts[f"PLACEBO {f} (shuffled)"] == "better"]
    print("\nprior-form correlation with corners won (Pearson r):")
    for f in FEATURES:
        r = pearson([row[f] for row in rows], [row["actual"] for row in rows])
        print(f"  {f:18} r={r:+.4f}" if r is not None else f"  {f:18} r=n/a")
    r_base = pearson([row[BASE_FEATURE] for row in rows], [row["actual"] for row in rows])
    print(f"  {BASE_FEATURE:18} r={r_base:+.4f}  <- the stat already in the model, for scale"
          if r_base is not None else "")

    if bad_placebo:
        print(f"\n!! PLACEBO FAILED for {', '.join(bad_placebo)}: a SHUFFLED feature scored as "
              f"'better', which is impossible on merit.")
        print("!! The harness is picking up an artifact — do NOT trust the real result above.")
    else:
        print("\nplacebo check passed: no shuffled feature scored better, so a 'better' above "
              "reflects the team link rather than the harness. (A placebo scoring slightly "
              "worse is expected — shuffling only adds noise to lambda.)")
    print("NOTE: rows are team-sides and teams repeat, so the interval is a guard against "
          "noise, not a formal significance test.")


def main():
    args = sys.argv[1:]

    def opt(flag, default=None, cast=str):
        return cast(args[args.index(flag) + 1]) if flag in args else default

    asyncio.run(run(league_id=opt("--league"),
                    window=opt("--window", WINDOW, int),
                    min_games=opt("--min-games", MIN_GAMES, int),
                    sweep="--sweep" in args))


if __name__ == "__main__":
    main()
