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
     python measure_features.py --game-state  (test the chase thesis; needs no backfill)
     python measure_features.py --game-state --chase-gain 4 --delta-gain 1

The --game-state mode reports corners by half-time state and venue first. That table
is DESCRIPTIVE: it shows the chase effect exists, which is not the same as it being
predictable. A team's corner form already contains its own average chase effect, so
only the deviation from that team's usual chase likelihood is new information — which
is what the centred candidates below test.
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
# shrinkage for the chase trait: a team with few trailing games is pulled back towards
# 'no chase effect' rather than trusted
GAME_STATE_K = 5
# Chase propensity is a behavioural TRAIT, not recent form, so it gets its own much
# longer lookback. At the 10-match form window only ~2 of a team's games involve
# trailing at half-time — far too few to estimate a multiplier from, and the shrinkage
# (correctly) erases the trait before it can be measured at all.
STATE_WINDOW = 40
# how hard the centred chase terms push lambda; both are mean-neutralised afterwards,
# so these set the SPREAD of the multiplier, not its level
# Validated on synthetic data: these set how hard the centred chase terms push lambda.
# The right magnitude is unknown — sweep them with --chase-gain before reading much
# into a result. At 0.5/2.0 a deliberately absurd synthetic chase effect still only
# just moved Brier, because corner form already absorbs most of the mechanism.
CHASE_DELTA_GAIN = 0.5
CHASE_INTERACTION_GAIN = 2.0
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


def _ht_state(m, side, other):
    """Team's half-time state in a cached fixture: -1 trailing, 0 level, +1 leading."""
    mine, theirs = m.get(f"{side}_fh_goals"), m.get(f"{other}_fh_goals")
    if mine is None or theirs is None:
        return None
    return (mine > theirs) - (mine < theirs)


async def build_rows(league_id, window, min_games, required=None, state_window=STATE_WINDOW):
    """Walk-forward pass: one prediction row per team-side, using prior form only.

    `required` lists the features a team must have history for before its row is
    scored — the same-sample guard. Game-state rows derive from goals, which every
    cached fixture carries, so that mode only requires the base feature and keeps
    far more rows than the blocked-shots comparison can."""
    required = ALL_FEATURES if required is None else required
    q = {} if not league_id or league_id == "all" else {"league_id": league_id}
    matches = await db.fixture_stats.find(q, {"_id": 0}).to_list(60000)
    matches = [m for m in matches if m.get("date")]
    matches.sort(key=lambda m: m["date"])
    if not matches:
        return [], {}, {}, {}, matches, {}

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
    # PRODUCTION PRICES FROM VENUE-SPLIT FORM (expected_lambdas -> team_split(team,
    # venue)), and this harness pooled both venues until 2026-08-27. Sweeping a weight
    # against a lambda production does not use picks the optimum for the wrong model —
    # the same class of error that made venue_delta look like a +9.1 edge on the rank
    # test. These mirror production; the pooled deques stay for the eligibility gate, so
    # the row set does not move.
    vcf = defaultdict(lambda: deque(maxlen=window))
    vca = defaultdict(lambda: deque(maxlen=window))
    vfhg = defaultdict(lambda: deque(maxlen=window))
    vhist = {f: defaultdict(lambda: deque(maxlen=window)) for f in ALL_FEATURES}
    # (corners won, half-time state) per past match, for the chase-propensity trait
    state_hist = defaultdict(lambda: deque(maxlen=state_window))
    hist = {f: defaultdict(lambda: deque(maxlen=window)) for f in ALL_FEATURES}

    # descriptive, NOT predictive: corners actually won in each half-time state
    desc = {(s, v): [] for s in (-1, 0, 1) for v in (True, False)}

    rows, drops = [], {"form": 0, "feature": 0}
    for m in matches:
        h, a = m.get("home_id"), m.get("away_id")
        if h is None or a is None:
            continue
        for team, opp, side, actual in ((h, a, "home", m.get("home_corners")),
                                        (a, h, "away", m.get("away_corners"))):
            if actual is None:
                continue
            # eligibility stays on POOLED history so the row set is unchanged
            if len(cf[team]) < min_games or len(ca[opp]) < min_games:
                drops["form"] += 1
                continue
            if any(len(hist[f][team]) < min_games for f in required):
                drops["feature"] += 1
                continue
            opp_side = "away" if side == "home" else "home"

            def vform(pooled, venue_pool):
                """What production would use: this venue, falling back to everything
                when the team has never played there (mirrors team_split's played == 0)."""
                return avg(venue_pool) if venue_pool else avg(pooled)

            row = {"tf": vform(cf[team], vcf[(team, side)]),
                   "oa": vform(ca[opp], vca[(opp, opp_side)]),
                   "fh": vform(fhg[team], vfhg[(team, side)]),
                   "actual": actual}
            for f in ALL_FEATURES:
                row[f] = vform(hist[f][team], vhist[f][(team, side)])

            # --- game state, from prior matches only ---
            past = list(state_hist[team])
            trailing = [c for c, s in past if s == -1]
            all_c = [c for c, _ in past]
            base_c = sum(all_c) / len(all_c) if all_c else 0.0
            ratio = ((sum(trailing) / len(trailing)) / base_c) if trailing and base_c else 1.0
            # shrink towards 1.0 (no chase effect): a team with two trailing games has
            # not earned a strong multiplier
            n_t = len(trailing)
            row["chase_prop"] = (n_t * ratio + GAME_STATE_K) / (n_t + GAME_STATE_K)
            row["trail_games"] = n_t
            # likelihood of being the chasing side: opponent scores in H1 and we don't
            row["opp_fh"] = vform(fhg[opp], vfhg[(opp, opp_side)])
            row["p_trail"] = row["opp_fh"] * (1.0 - row["fh"])
            # How often this team USUALLY trails. Corner form already contains the
            # average chase effect — a team that chases hard simply averages more
            # corners — so only the DEVIATION from its own baseline is new information.
            row["p_trail_base"] = (n_t / len(past)) if past else 0.0
            row["p_trail_delta"] = row["p_trail"] - row["p_trail_base"]
            rows.append(row)

        # update rolling form AFTER predicting (no leakage)
        for team, side, other in ((h, "home", "away"), (a, "away", "home")):
            corners = m.get(f"{side}_corners") or 0
            cf[team].append(corners)
            ca[team].append(m.get(f"{other}_corners") or 0)
            fhg[team].append(1 if (m.get(f"{side}_fh_goals") or 0) >= 1 else 0)
            vcf[(team, side)].append(corners)
            vca[(team, side)].append(m.get(f"{other}_corners") or 0)
            vfhg[(team, side)].append(1 if (m.get(f"{side}_fh_goals") or 0) >= 1 else 0)
            st = _ht_state(m, side, other)
            if st is not None:
                state_hist[team].append((corners, st))
                desc[(st, side == "home")].append(corners)
            for f in ALL_FEATURES:
                v = m.get(f"{side}_{f}")
                if v is not None:               # uncovered fixtures never enter the window
                    hist[f][team].append(v)
                    vhist[f][(team, side)].append(v)
    return rows, lg, covered, drops, matches, desc


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


def mean_one(mults):
    """Mean-neutralise an arbitrary multiplier list (see guard 2 in the module docstring)."""
    m = sum(mults) / len(mults) if mults else 1.0
    return [x / m for x in mults] if m else mults


def game_state_candidates(rows, weight=0.15, delta_gain=CHASE_DELTA_GAIN,
                          interaction_gain=CHASE_INTERACTION_GAIN):
    """Decompose the chase thesis into three testable claims.

    The app already assumes this mechanism (the chase board multiplies by the
    opponent's first-half-goal rate) but has never measured it. Splitting it apart
    says WHICH part carries signal, if any:
      chase_propensity — is 'chases hard when behind' a persistent team trait?
      opp_fh_rate      — does the opponent's scoring rate alone beat corner form?
      chase_delta      — does facing an unusually early-scoring opponent matter, for
                         any team? (league-level effect, no team trait)
      chase_interaction— the full hypothesis: this team's trait, applied to the extent
                         THIS fixture is more chase-prone than its usual one.

    The last two centre on the team's own baseline deliberately. Corner form already
    contains a team's average chase effect, so an uncentred term mostly re-states
    information the model has, which is why it measures as nothing.
    """
    lg_opp_fh = sum(r["opp_fh"] for r in rows) / len(rows) if rows else 0.0
    clamp = lambda x: max(0.6, min(1.5, x))                                  # noqa: E731
    return {
        "chase_propensity": mean_one(
            [(1 - weight) + weight * clamp(r["chase_prop"]) for r in rows]),
        "opp_fh_rate": mean_one(
            [(1 - weight) + weight * clamp(r["opp_fh"] / lg_opp_fh if lg_opp_fh else 1.0)
             for r in rows]),
        # league-level: this fixture is more/less chase-prone than this team's normal
        "chase_delta": mean_one(
            [1.0 + delta_gain * r["p_trail_delta"] for r in rows]),
        # the full hypothesis: the team's own trait, applied to that deviation
        "chase_interaction": mean_one(
            [1.0 + (clamp(r["chase_prop"]) - 1.0) * r["p_trail_delta"] * interaction_gain
             for r in rows]),
    }


def print_state_descriptives(desc):
    """What the data says outright, before any model: corners by half-time state and
    venue. This is the effect itself — it says nothing about whether it is PREDICTABLE,
    since a team's corner form already contains its own average chase effect."""
    labels = {-1: "trailing at HT", 0: "level at HT", 1: "leading at HT"}
    total = [c for v in desc.values() for c in v]
    base = sum(total) / len(total) if total else 0.0
    print("\ncorners won by half-time state (descriptive, NOT a prediction) — "
          f"overall average {base:.2f}:")
    print(f"  {'state':16} {'home n':>8} {'home avg':>9} {'away n':>8} {'away avg':>9} "
          f"{'both':>7} {'vs overall':>11}")
    for s in (-1, 0, 1):
        hv, av = desc[(s, True)], desc[(s, False)]
        both = hv + av
        if not both:
            continue
        f = lambda v: (sum(v) / len(v)) if v else float("nan")            # noqa: E731
        print(f"  {labels[s]:16} {len(hv):8} {f(hv):9.2f} {len(av):8} {f(av):9.2f} "
              f"{f(both):7.2f} {(f(both) / base - 1) * 100:+10.1f}%")


async def run(league_id=None, window=WINDOW, min_games=MIN_GAMES, sweep=False,
              game_state=False, state_window=STATE_WINDOW,
              delta_gain=CHASE_DELTA_GAIN, chase_gain=CHASE_INTERACTION_GAIN):
    required = [BASE_FEATURE] if game_state else None
    rows, lg, covered, drops, matches, desc = await build_rows(league_id, window, min_games,
                                                               required, state_window)
    if not matches:
        print("no cached fixtures — run sync_real.py first")
        return

    sides = len(matches) * 2
    print(f"fixtures={len(matches)}  league={league_id or 'all'}  window={window}  "
          f"min_games={min_games}" + (f"  state_window={state_window}" if game_state else ""))
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
    placebo_names, corr_keys = [], []
    if game_state:
        # goals are on every cached fixture, so these need no backfill and no coverage
        # filter — the comparison runs on every row the baseline can score
        gs = game_state_candidates(rows, delta_gain=delta_gain, interaction_gain=chase_gain)
        for name, vals in gs.items():
            candidates[f"+{name}"] = {BASE_FEATURE: mult[BASE_FEATURE], name: vals}
        # does the chase term stand on its own, without the shots term underneath?
        candidates["chase_instead_of_shots"] = {"chase_interaction": gs["chase_interaction"]}
        for name, vals in gs.items():
            shuffled = list(vals)
            random.Random(PLACEBO_SEED).shuffle(shuffled)
            candidates[f"PLACEBO {name} (shuffled)"] = {BASE_FEATURE: mult[BASE_FEATURE],
                                                        name: shuffled}
            placebo_names.append(name)
        corr_keys = ["chase_prop", "opp_fh", "p_trail", "p_trail_delta"]
    else:
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
            placebo_names.append(f)
        corr_keys = list(FEATURES) + [BASE_FEATURE]

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
    bad_placebo = [f for f in placebo_names if verdicts[f"PLACEBO {f} (shuffled)"] == "better"]
    if game_state:
        print_state_descriptives(desc)
        trail = [r["trail_games"] for r in rows]
        print(f"\ntrailing games behind each chase_prop: median={sorted(trail)[len(trail) // 2]}, "
              f"rows with none={sum(1 for t in trail if t == 0)} (those shrink to no effect)")
    print("\nprior-form correlation with corners won (Pearson r):")
    for key in corr_keys:
        r = pearson([row[key] for row in rows], [row["actual"] for row in rows])
        tail = "  <- the stat already in the model, for scale" if key == BASE_FEATURE else ""
        print(f"  {key:18} r={r:+.4f}{tail}" if r is not None else f"  {key:18} r=n/a")

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
                    sweep="--sweep" in args,
                    game_state="--game-state" in args,
                    state_window=opt("--state-window", STATE_WINDOW, int),
                    delta_gain=opt("--delta-gain", CHASE_DELTA_GAIN, float),
                    chase_gain=opt("--chase-gain", CHASE_INTERACTION_GAIN, float)))


if __name__ == "__main__":
    main()
