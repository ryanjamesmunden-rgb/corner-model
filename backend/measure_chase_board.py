"""Offline: does the chase board's RANKING pick better spots?

Everything measured so far has been probability accuracy. The chase board does a
different job — it orders spots and you bet the top of the list — so it needs a
different test. This replays the board over the cached fixtures, walk-forward, and
asks whether the spots it ranked highest actually did better.

    chase_score = lambda x (1 + 0.4*opp_fh) x (0.6 + 0.4*consistency)

THE TRAP THIS IS BUILT AROUND: the line moves with lambda (line = round(lambda) - 1),
so a highly ranked spot sits at a HIGHER line and will naturally hit less often. Raw
hit rate by rank is therefore meaningless — it mostly measures where the line landed.
The metric that survives that is the RESIDUAL:

    residual = actual hit rate - the model's own predicted probability

A ranking earns its keep only if it finds spots the model UNDERRATES: positive
residual at the top, and a gradient across the buckets. A flat residual means the
ordering carries no information the model didn't already have — the board would be
re-stating lambda, not adding to it.

ALREADY MEASURED, ALL FLAT (2026-08-27): chase_score +0.02, lambda_only +0.01,
no_opp_fh +0.03, against a FLAT control. They are kept below so a re-run reproduces
that null rather than asking anyone to take it on trust.

WHY THEY WERE FLAT, most likely: every one of them is a function of lambda and
consistency — and lambda is already inside the model probability they are scored
against. The ordering was re-stating the thing it was being compared to. So the new
candidates are chosen for being ORTHOGONAL to lambda: quantities the probability does
not already contain.

Rankings compared:
    chase_score      the live formula                        [known flat]
    lambda_only      lambda alone                            [known flat]
    no_opp_fh        falsified opponent term removed         [known flat]
    no_consistency   without the last-5 term                 [known flat]
    venue_delta      venue form vs the team's own average    CANDIDATE
    opp_conc_delta   opponent conceding more on this venue   CANDIDATE
    consistency_only last-5 hit rate alone                   CANDIDATE
    depth            games behind the estimate               diagnostic — a gradient
                     here argues for a SAMPLE BAR, not for betting the top harder
    slack            lambda above its rounded line           anchor — the probability
                     already captures this, so flat is EXPECTED. If slack shows a
                     gradient, something is wrong with the harness, not with the model.
    RANDOM           control: a shuffled score. Must come out flat. If it doesn't,
                     the harness is manufacturing a gradient and nothing else here
                     can be trusted.

RESULT (2026-08-27) — THE SEARCH IS CLOSED, AND IT FAILED:

    venue_delta       +9.1 -> FLAT once lambda was built venue-split, the way production
                      builds it. It had been correcting an error only THIS HARNESS made
                      (it pooled venues; production never did). Artifact, confirmed by
                      the collapse.
    consistency_only  +7.9 — and synthetic validation on data with NO edge by
                      construction already yields 7.5 from estimation error alone. 7.9
                      against 7.5 is not a finding.
    opp_conc_delta    flat
    RANDOM            flat  <- control passed throughout

Nothing ranks. The Daily 2 therefore selects on a STATED rule — a quality bar, then
model probability — labelled as not-an-edge everywhere it appears. See DAILY_PICK_RULE
in server.py. Do not re-open this with another score unless you have a candidate that is
orthogonal to lambda AND to its dispersion; the ones that were not, all died here.

NEXT HYPOTHESIS if anyone returns to it: consistency surviving where venue_delta died
points at DISPERSION, not the mean. Lambda is a mean and NB_R is fixed at 11 for every
team, while consistency counts how often a team CLEARED a line — shape information a
fixed r cannot hold. Per-league or per-team dispersion is the thing to test, and it is a
model change, not a ranking.

WHY A GRADIENT CAN BE REAL EVEN IF THE MODEL IS "RIGHT": lambda is ESTIMATED from a
10-game window, so it carries error. `consistency` is a second, independent look at the
same quantity — did this team clear this line on this venue lately — so it can correct
that error. In validation, on data drawn from the model's own distribution (where no
market edge exists by construction), consistency still separated the buckets by 7.5
points against a control floor of 1.8. That is a real effect, but it is a statement
about ESTIMATION, not about finding mispriced games: it says lambda is noisy and
consistency knows something lambda missed. The fix that implies is folding venue form
into lambda, not betting the top of the board harder.

RE-OPENED ONCE, FOR THE CONCEDED ANGLE (2026-09-30). The site now surfaces a CONCEDED
streak — a defence that keeps shipping 5+ corners, with the bet going to whoever plays them
next — so the question is whether that ordering finds spots the model underrates.

It is NOT orthogonal to lambda's mean: the opponent's conceded rate is already an input to
model_lambda, and the mean version of this died here as `opp_conc_delta`. What is left is
SHAPE — how often they conceded the line, and whether the run is unbroken — which a fixed
NB_R=11 cannot hold. That is `consistency_only`'s bet pointed at the defence, so it inherits
`consistency_only`'s problem: a floor that the RANDOM control does not measure.

AND THAT FLOOR WAS A COMMENT. `consistency_only` came back +7.9 against a control near
zero, which read as a finding until it was checked against synthetic data with no edge by
construction, where it still produced 7.5. That 7.5 has sat in this docstring ever since and
NOTHING IN THE REPO COULD REPRODUCE IT — the number deciding whether a candidate was real
was prose. It is measured now: every run also replays itself over synthetic data where every
team has one fixed true rate, and prints each ranking against the floor measured on that same
sample. See synthesise() and ESTIMATOR_FAMILY.

RESULT (2026-09-30, 11,700 spots over 7,521 fixtures) — IT DOES NOT RANK:

    opp_conc_consistency  +1.3 against a floor of 2.4
    opp_conc_run          +3.1 against a floor of 2.2
    RANDOM                -2.2  <- control

Both at their floor. A conceded run stays a way to FIND a spot and is not a reason to weight
one, which is what the site already says about it.

AND THE NULL PAID FOR ITSELF IMMEDIATELY, on a question nobody asked it. Every lambda-derived
ranking came back strongly INVERTED on the real data — chase_score -10.0, lambda_only -10.4,
no_consistency -12.1, top bucket residual about -5 and bottom about +6. Read against the
shuffled control that is five rankings flagged as broken. Read against their own nulls, which
are inverted HARDER still (-18.9, -19.4, -19.5), every one of them is at its floor: the
inversion is regression in a lambda estimated from ten games, not a fault in the ordering.
Without the null there was no way to tell those two apart, and the obvious reading was the
wrong one.

THE TOP-2 GAP IS SELECTION, NOT THE MODEL — CHASED AND SETTLED (2026-09-30). The
top-2-per-matchday view has chase_score picking spots priced at 64.8% that land 57.0%: a 7.8
point gap on exactly the rows the Daily 2 would select, at an average line of 5.4. The
obvious reading is that high lines over-promise, which points at NB_R being fixed at 11 for
every team. That reading is WRONG, and tune_model settles it directly:

    nb_r11 (live)   4+:65.9/65.7   5+:50.7/51.2   6+:36.9/37.9   7+:25.5/26.4   avg gap 0.61pp

r=11 has the SMALLEST per-line gap of every candidate swept, and at the high lines the model
UNDER-promises — the opposite sign to the one the bucket view suggested. Raising r makes it
worse in exactly the predicted way (r=24: 4+ goes to 68.2 against 65.7). Brier moves by
0.0002, which this harness's own note calls noise. Over 7,521 matches, 11 is right.

So the gap is what the null column below already says it is: sorting on an ESTIMATED
probability selects estimation error. measure_calibration's verdict names this case in
words — "the model is fine and the selection bleeds... do not retune anything on this" — and
this is that case. The fix, if one is wanted, is what the Daily 2 SELECTS on: a sample bar,
or not sorting on the estimate at all. Not the dispersion, and not a score.

DO NOT RE-OPEN THE DISPERSION ROUTE on the strength of a bucket table again. Bucketing by
ranked lambda cannot separate a miscalibrated model from a noisy estimate of a calibrated
one; only the per-line view in tune_model can, and it has answered.

Two views:
  1. Buckets over every scored row — is there a gradient at all?
  2. Top-N per matchday — what the board and the Daily 2 ledger actually do.

Run: python measure_chase_board.py
     python measure_chase_board.py --league eng-pl --top 2
     python measure_chase_board.py --no-null      # skips the floor; spreads then unreadable
"""
import asyncio
import os
import random
import sys
from collections import defaultdict, deque
from pathlib import Path

from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

from server import NB_R, V3_BLOCKED_WEIGHT, model_lambda, nb_ge, nb_pmf

ROOT = Path(__file__).parent
load_dotenv(ROOT / ".env")
db = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]

WINDOW = 10
MIN_GAMES = 5
MIN_VENUE_GAMES = 3      # the live board needs a venue pool before it ranks a team
BUCKETS = 5
TOP_N = 2                # the Daily 2
CONTROL_SEED = 20260812
MIN_ROWS = 2000


def avg(d):
    return sum(d) / len(d) if d else 0.0


def _run_from_end(values, line):
    """The unbroken run of values >= line, counted back from the most recent.

    FROM THE END, because that is what a streak is. These deques are appended
    chronologically, so the newest game is last — counting from the front would measure a
    run that ENDED some time ago and report it as one running into this fixture, which is
    the difference between the angle and a historical curiosity.
    """
    run = 0
    for v in reversed(list(values)):
        if v < line:
            break
        run += 1
    return run


def rate(hits, n):
    return (hits / n * 100) if n else 0.0


async def load_matches(league_id=None):
    """Every cached finished fixture, oldest first."""
    q = {} if not league_id or league_id == "all" else {"league_id": league_id}
    matches = await db.fixture_stats.find(q, {"_id": 0}).to_list(60000)
    matches = [m for m in matches if m.get("date")]
    matches.sort(key=lambda m: m["date"])
    return matches


def build_spots(matches, window=WINDOW, min_games=MIN_GAMES):
    """Replay every past fixture as the chase board would have seen it beforehand.

    TAKES THE MATCHES RATHER THAN FETCHING THEM, so the identical replay can be run over
    the real data and over the synthetic null. Two copies of this loop would be two
    slightly different measurements, and the whole point of the null is that it is the same
    measurement on data with no edge in it.
    """
    if not matches:
        return []

    shots = [m.get(f"{s}_shots", 0) for m in matches for s in ("home", "away")]
    lg_shots = (sum(shots) / len(shots)) if shots else 0.0
    blocked = [m[f"{s}_blocked_shots"] for m in matches for s in ("home", "away")
               if m.get(f"{s}_blocked_shots") is not None]
    lg_blocked = (sum(blocked) / len(blocked)) if blocked else 0.0

    cf = defaultdict(lambda: deque(maxlen=window))
    ca = defaultdict(lambda: deque(maxlen=window))
    sf = defaultdict(lambda: deque(maxlen=window))
    fh = defaultdict(lambda: deque(maxlen=window))
    bl = defaultdict(lambda: deque(maxlen=window))
    venue = defaultdict(lambda: deque(maxlen=5))        # last 5 corner counts on this venue
    venue_ca = defaultdict(lambda: deque(maxlen=5))     # ...and last 5 conceded there
    # venue-split form, so lambda here is built the way production builds it
    vcf = defaultdict(lambda: deque(maxlen=window))
    vca = defaultdict(lambda: deque(maxlen=window))
    vsf = defaultdict(lambda: deque(maxlen=window))
    vfh = defaultdict(lambda: deque(maxlen=window))

    spots = []
    for m in matches:
        h, a = m.get("home_id"), m.get("away_id")
        if h is None or a is None:
            continue
        for team, opp, side, actual in ((h, a, "home", m.get("home_corners")),
                                        (a, h, "away", m.get("away_corners"))):
            if actual is None:
                continue
            if len(cf[team]) < min_games or len(ca[opp]) < min_games:
                continue
            vpool = list(venue[(team, side)])
            if len(vpool) < MIN_VENUE_GAMES:
                continue
            opp_vpool = list(venue_ca[(opp, "away" if side == "home" else "home")])
            # PRODUCTION PRICES FROM VENUE-SPLIT FORM (expected_lambdas ->
            # team_split(team, venue)), and this harness pooled both venues until
            # 2026-08-27. That gap is exactly what made `venue_delta` look like a +9.1
            # edge: it was correcting an error only the HARNESS was making. Lambda is now
            # built the way production builds it, so venue_delta is measured against the
            # real model — and if its gradient collapses, that was the whole story.
            opp_side = "away" if side == "home" else "home"
            def vform(pooled, venue_pool):
                return avg(venue_pool) if venue_pool else avg(pooled)
            lam = model_lambda("v3",
                               vform(cf[team], vcf[(team, side)]),
                               vform(ca[opp], vca[(opp, opp_side)]),
                               vform(sf[team], vsf[(team, side)]), lg_shots,
                               vform(fh[team], vfh[(team, side)]),
                               avg(bl[team]) if len(bl[team]) >= min_games else 0.0,
                               lg_blocked, V3_BLOCKED_WEIGHT)
            line = max(3, round(lam) - 1)
            consistency = sum(1 for c in vpool if c >= line) / len(vpool)
            opp_fh = avg(fh[opp])
            spots.append({
                "date": m["date"][:10], "team": team, "line": line, "lambda": lam,
                "prob": nb_ge(line, lam) * 100, "hit": 1 if actual >= line else 0,
                "opp_fh": opp_fh, "consistency": consistency,
                # How many venue games that fraction is out of. Not used for ranking —
                # measure_calibration needs it to apply the Daily 2's quality bar
                # (DAILY_MIN_VENUE_GAMES) to the replay, which a bare fraction cannot do:
                # 3 of 3 and 4 of 5 are both "high" and only one of them clears the bar.
                "consistency_of": len(vpool),
                "chase_score": lam * (1 + 0.4 * opp_fh) * (0.6 + 0.4 * consistency),
                "lambda_only": lam,
                "no_opp_fh": lam * (0.6 + 0.4 * consistency),
                "no_consistency": lam * (1 + 0.4 * opp_fh),
                # --- candidates ORTHOGONAL to lambda ---
                # Everything above is a function of lambda and consistency, and lambda is
                # already inside the model's probability — which is very likely WHY they
                # all came out flat: the ordering was re-stating what it was scored
                # against. These are quantities the probability does NOT already contain.
                #
                # venue_delta: this venue's recent corner form vs the team's own 10-game
                # average. Lambda pools both venues, so a side that travels badly or is
                # far stronger at home carries information lambda has averaged away.
                "venue_delta": avg(vpool) - avg(cf[team]),
                # opp_conc_delta: same idea on the opponent's conceding, on THIS venue.
                "opp_conc_delta": (avg(opp_vpool) - avg(ca[opp])) if opp_vpool else 0.0,
                # consistency alone — never tested standalone; `no_consistency` only ever
                # removed it, which is not the same experiment.
                "consistency_only": consistency,
                # --- the conceded-run candidates ---
                # WHAT IS BEING ASKED. The site now surfaces a CONCEDED streak: a defence
                # that keeps shipping 5+ corners, and the bet is whoever plays them next.
                # These are that angle as a ranking — does knowing the opponent has
                # conceded THIS spot's line lately find spots the model underrates?
                #
                # AND THEY ARE NOT ORTHOGONAL TO LAMBDA'S MEAN. The opponent's conceded
                # rate is already an INPUT to lambda (model_lambda's second argument), so
                # the mean version of this was tested as `opp_conc_delta` and came back
                # flat. What is left is SHAPE: how often they conceded the line, and
                # whether the run is unbroken — which a fixed NB_R=11 cannot hold. That is
                # the same bet `consistency_only` made, pointed at the defence, which is
                # why it carries the same known noise floor (see NOISE_FAMILY below).
                #
                # opp_conc_consistency: the direct analogue of `consistency`, on the
                # opponent's conceding, on the venue they are playing.
                "opp_conc_consistency": (
                    sum(1 for c in opp_vpool if c >= line) / len(opp_vpool)
                    if len(opp_vpool) >= MIN_VENUE_GAMES else 0.0),
                # opp_conc_run: the site's own definition — the UNBROKEN run of conceding
                # the line, counted back from their most recent game. A 5-from-5 and a
                # 3-then-miss-then-2 are the same fraction and different streaks, and the
                # board sells the streak.
                "opp_conc_run": (_run_from_end(opp_vpool, line)
                                 if len(opp_vpool) >= MIN_VENUE_GAMES else 0),
                # Coverage, so a candidate scored 0 on a thin opponent pool is counted
                # rather than quietly sitting in the bottom bucket as if it were measured.
                "opp_pool": len(opp_vpool),
                # slack: how far lambda sits above the line it was rounded to. The
                # probability does capture this, so a flat result is EXPECTED — it is here
                # as a sanity anchor, not a candidate.
                "slack": lam - line,
                # depth: how much history is behind the estimate. Tests estimation
                # quality rather than edge; a gradient here argues for a sample bar, not
                # for betting the top of a list.
                "depth": min(len(cf[team]), len(ca[opp])),
            })

        for team, s, other in ((h, "home", "away"), (a, "away", "home")):
            corners = m.get(f"{s}_corners") or 0
            cf[team].append(corners)
            ca[team].append(m.get(f"{other}_corners") or 0)
            sf[team].append(m.get(f"{s}_shots") or 0)
            fh[team].append(1 if (m.get(f"{s}_fh_goals") or 0) >= 1 else 0)
            v = m.get(f"{s}_blocked_shots")
            if v is not None:
                bl[team].append(v)
            venue[(team, s)].append(corners)
            venue_ca[(team, s)].append(m.get(f"{other}_corners") or 0)
            vcf[(team, s)].append(corners)
            vca[(team, s)].append(m.get(f"{other}_corners") or 0)
            vsf[(team, s)].append(m.get(f"{s}_shots") or 0)
            vfh[(team, s)].append(1 if (m.get(f"{s}_fh_goals") or 0) >= 1 else 0)
    return spots


# Every ordering scored, in both views. The first four are already falsified (all flat
# against a flat control); they stay so a re-run reproduces the null rather than asking
# you to take it on trust. The next four are the candidates for what Daily 2 should
# select on, chosen for being ORTHOGONAL to lambda.
RANKINGS = [
    ("chase_score", "chase_score — the live board formula [known flat]"),
    ("lambda_only", "lambda_only — no chase, no consistency [known flat]"),
    ("no_opp_fh", "no_opp_fh — falsified opponent term removed [known flat]"),
    ("no_consistency", "no_consistency — last-5 term removed [known flat]"),
    ("venue_delta", "venue_delta — venue form vs the team's own average [known artifact]"),
    ("opp_conc_delta", "opp_conc_delta — opponent conceding more on this venue [known flat]"),
    ("consistency_only", "consistency_only — last-5 hit rate alone [known: floor-bound]"),
    ("opp_conc_consistency",
     "opp_conc_consistency — opponent conceded the line, last 5 on venue [CANDIDATE]"),
    ("opp_conc_run",
     "opp_conc_run — opponent's UNBROKEN conceded run at the line [CANDIDATE]"),
    ("depth", "depth — games behind the estimate [diagnostic, argues for a bar]"),
    ("slack", "slack — lambda above the line [anchor, flat is EXPECTED]"),
    ("RANDOM", "RANDOM — control, must be flat"),
]

# WHICH BASELINE EACH RANKING HAS TO BEAT, and this is the whole reason the conceded
# candidates could not simply be added and read off.
#
# The RANDOM control measures ONE kind of noise: sampling. A shuffled score separates the
# buckets by nothing because it correlates with nothing. But a ranking built from a team's
# RECENT REALISED COUNTS is not in that family — it correlates with the true rate, and
# lambda is an estimate of the true rate from a 10-game window, so such a ranking can
# separate the buckets with no market edge whatsoever. It is correcting the ESTIMATE, not
# finding a mispriced game.
#
# That is what happened to `consistency_only`: +7.9 against a RANDOM floor near zero, which
# read as a finding until it was checked against synthetic data with NO edge by
# construction, where it still produced 7.5. The file has carried that 7.5 in prose ever
# since, and NOTHING IN THE REPO COULD REPRODUCE IT — so the number deciding whether a
# candidate is real was a comment. `--null` now measures it, on this same sample.
#
# DERIVED, NOT LISTED, AND THE FIRST REAL RUN IS WHY. This was a hand-typed set of the six
# rankings that read realised counts, and it was wrong: `chase_score`, `lambda_only`,
# `no_opp_fh`, `no_consistency` and `slack` are all functions of LAMBDA, which is itself
# estimated from a ten-game window. Held against the shuffled control they came back
# "INVERTED past its floor" — five rankings flagged as broken. Held against their own nulls,
# which are MORE inverted still (-18.9 against -10.0 for chase_score), every one of them is
# at its floor: the inversion is regression in the estimate, not a fault in the ordering.
#
# So the rule is simply: the control bounds sampling noise and nothing else, and EVERY
# ranking built from the data is held to its own null. That is also one less hand-maintained
# list to get wrong — the same failure mode as the three tool registries, which broke three
# times before a test closed it.
ESTIMATOR_FAMILY = frozenset(k for k, _ in RANKINGS if k != "RANDOM")


def _nb_sample(lam, rng, cap=40):
    """One draw from the model's OWN distribution at mean `lam`, by inverse CDF.

    Inverse CDF off nb_pmf rather than a library sampler, deliberately: the null has to be
    drawn from exactly the distribution the model prices with, or the floor it measures
    belongs to some other model. No new dependency either.
    """
    u = rng.random()
    cum = 0.0
    for k in range(cap):
        cum += nb_pmf(k, lam, NB_R)
        if u <= cum:
            return k
    return cap


def synthesise(matches, seed):
    """The same fixtures with the corner counts redrawn — NO EDGE BY CONSTRUCTION.

    WHAT THIS IS FOR. A ranking built from recent realised counts can separate the buckets
    with no market edge at all, because it corrects the noise in a lambda estimated from
    ten games. To tell that apart from a real finding you need the same measurement on data
    where a real finding is impossible, and this builds it.

    HOW. Every team is given ONE fixed true attack rate and ONE fixed true concede rate,
    taken from their real full-sample averages so the spread across teams stays realistic.
    Each match's corners are then drawn from the model's own NB at the mean production
    would use — (true attack + opponent's true concede) / 2. Nothing about a team varies
    over time, so there is nothing for a ranking to discover: any bucket separation it
    produces is estimation error, and that number is the floor.

    THE SHOTS AND FIRST-HALF GOALS ARE LEFT REAL, and that is conservative in the right
    direction. They feed lambda but no longer correlate with the redrawn corners, so lambda
    here is NOISIER than in production — which makes the floor higher, so a candidate has a
    HARDER bar to clear rather than an easier one.
    """
    rng = random.Random(seed)
    cf, ca = defaultdict(list), defaultdict(list)
    for m in matches:
        for side, other in (("home", "away"), ("away", "home")):
            tid = m.get(f"{side}_id")
            if tid is None:
                continue
            if m.get(f"{side}_corners") is not None:
                cf[tid].append(m[f"{side}_corners"])
            if m.get(f"{other}_corners") is not None:
                ca[tid].append(m[f"{other}_corners"])
    pool = [c for v in cf.values() for c in v]
    league = (sum(pool) / len(pool)) if pool else 5.0
    attack = {t: (avg(v) or league) for t, v in cf.items()}
    concede = {t: (avg(v) or league) for t, v in ca.items()}

    out = []
    for m in matches:
        h, a = m.get("home_id"), m.get("away_id")
        if h is None or a is None:
            out.append(m)
            continue
        row = dict(m)
        row["home_corners"] = _nb_sample(
            (attack.get(h, league) + concede.get(a, league)) / 2, rng)
        row["away_corners"] = _nb_sample(
            (attack.get(a, league) + concede.get(h, league)) / 2, rng)
        out.append(row)
    return out


def summarise(rows):
    n = len(rows)
    if not n:
        return None
    hits = sum(r["hit"] for r in rows)
    model = sum(r["prob"] for r in rows) / n
    return {"n": n, "hit_rate": rate(hits, n), "model_prob": model,
            "residual": rate(hits, n) - model,
            "avg_line": sum(r["line"] for r in rows) / n,
            "avg_lambda": sum(r["lambda"] for r in rows) / n}


def print_buckets(spots, key, label):
    ranked = sorted(spots, key=lambda r: r[key], reverse=True)
    size = len(ranked) // BUCKETS
    print(f"\n{label}")
    print(f"  {'bucket':10} {'n':>6} {'avg line':>9} {'model %':>8} {'actual %':>9} "
          f"{'residual':>9}")
    for i in range(BUCKETS):
        chunk = ranked[i * size:(i + 1) * size] if i < BUCKETS - 1 else ranked[i * size:]
        s = summarise(chunk)
        if not s:
            continue
        tag = "top 20%" if i == 0 else ("bottom 20%" if i == BUCKETS - 1 else f"{i + 1}/{BUCKETS}")
        print(f"  {tag:10} {s['n']:6} {s['avg_line']:9.2f} {s['model_prob']:8.1f} "
              f"{s['hit_rate']:9.1f} {s['residual']:+9.1f}")
    top, bottom = summarise(ranked[:size]), summarise(ranked[-size:])
    return (top["residual"] - bottom["residual"]) if top and bottom else 0.0


def print_top_n(spots, key, label, top_n):
    """What the board and the Daily 2 actually do: take the best N of each matchday."""
    by_day = defaultdict(list)
    for r in spots:
        by_day[r["date"]].append(r)
    picked = []
    for day, rows in by_day.items():
        picked += sorted(rows, key=lambda r: r[key], reverse=True)[:top_n]
    s = summarise(picked)
    if not s:
        return None
    print(f"  {label:16} {s['n']:6} {s['avg_line']:9.2f} {s['model_prob']:8.1f} "
          f"{s['hit_rate']:9.1f} {s['residual']:+9.1f}")
    return s


def spreads_for(spots, show=True):
    """Every ranking's top-minus-bottom residual over these spots."""
    rng = random.Random(CONTROL_SEED)
    for r in spots:
        r["RANDOM"] = rng.random()
    out = {}
    for key, label in RANKINGS:
        out[key] = print_buckets(spots, key, label) if show else _spread(spots, key)
    return out


def _verdict(key, spread, floor, have_null):
    """What this spread means, against the floor that applies to it.

    THE SIGN IS NOT DECORATION, and reading it off `abs()` is how a smoke test caught this
    file claiming a -13.7 spread had "cleared its floor by +7.4". The claim a ranking makes
    is that its TOP bucket beats its BOTTOM one, so only a positive spread can support it.
    A large negative spread is the ordering inverted — the worst spots on top — which is
    never a reason to bet the top of the list and usually means the score's sign is wrong.
    """
    if key == "RANDOM":
        return "control"
    if not have_null and key in ESTIMATOR_FAMILY:
        return "no null measured — unreadable"
    bar = floor + 1.0
    if spread > bar:
        return f"clears its floor ({floor:.1f}) by {spread - floor:+.1f}"
    if spread < -bar:
        return f"INVERTED past its floor ({floor:.1f}) — worst spots on top, not a finding"
    return f"AT THE FLOOR ({floor:.1f}) — not a finding"


def _spread(spots, key):
    ranked = sorted(spots, key=lambda r: r[key], reverse=True)
    size = len(ranked) // BUCKETS
    if not size:
        return 0.0
    top, bottom = summarise(ranked[:size]), summarise(ranked[-size:])
    return (top["residual"] - bottom["residual"]) if top and bottom else 0.0


async def run(league_id=None, top_n=TOP_N, window=WINDOW, min_games=MIN_GAMES,
              with_null=True):
    matches = await load_matches(league_id)
    if not matches:
        print("no cached fixtures — run sync_real.py first")
        return
    spots = build_spots(matches, window, min_games)
    print(f"fixtures={len(matches)}  league={league_id or 'all'}  spots scored={len(spots)}")
    if not spots:
        print("no spot had enough history to rank — nothing to measure")
        return
    print(f"date range: {matches[0]['date'][:10]} -> {matches[-1]['date'][:10]}")
    # COVERAGE OF THE CONCEDED CANDIDATES, named rather than assumed. Both score 0 where
    # the opponent has too few venue games, and a candidate that is a constant on a third
    # of the sample has a degenerate bottom bucket — which would look like a flat result
    # for a reason that has nothing to do with the angle.
    thin = sum(1 for r in spots if r["opp_pool"] < MIN_VENUE_GAMES)
    print(f"opponent venue pool < {MIN_VENUE_GAMES} on {thin} of {len(spots)} spots "
          f"({100.0 * thin / len(spots):.1f}%) — the conceded candidates score 0 there")
    overall = summarise(spots)
    print(f"\nevery spot: n={overall['n']}  avg line {overall['avg_line']:.2f}  "
          f"model {overall['model_prob']:.1f}%  actual {overall['hit_rate']:.1f}%  "
          f"residual {overall['residual']:+.1f}")
    print("(a non-zero residual here is the model's own calibration, not the ranking's doing —"
          "\n what matters below is whether the residual MOVES across buckets)")
    if len(spots) < MIN_ROWS:
        print(f"\n!! {len(spots)} spots is thin (want >= {MIN_ROWS}); treat this as a smoke test.")

    spreads = spreads_for(spots)

    # THE NULL: the same replay on data with no edge in it, so each candidate's spread can
    # be read against a floor MEASURED on this sample rather than against a number quoted
    # in a comment. See synthesise(); this is the half that was missing.
    null = {}
    if with_null:
        print(f"\n{'=' * 78}")
        print("NULL RUN — the same measurement on synthetic data with NO edge by construction")
        print(f"{'=' * 78}")
        print("Every team gets one fixed true attack and concede rate; corners are redrawn")
        print("from the model's own NB at the mean production would use. Nothing varies over")
        print("time, so there is nothing to discover — whatever a ranking separates here is")
        print("estimation error, and that is the bar a candidate has to clear.")
        null_spots = build_spots(synthesise(matches, CONTROL_SEED + 1), window, min_games)
        if len(null_spots) < MIN_ROWS:
            print(f"  !! only {len(null_spots)} null spots — the floor itself is noisy here")
        null = spreads_for(null_spots, show=False) if null_spots else {}
        print(f"  null spots scored: {len(null_spots)}")

    print("\ntop-minus-bottom residual (how much the ordering separates good from bad):")
    ctrl_floor = abs(spreads.get("RANDOM", 0.0))
    print(f"  {'ranking':22} {'real':>7} {'null':>7}  verdict")
    for key, _ in RANKINGS:
        spread = spreads.get(key, 0.0)
        # WHICH FLOOR APPLIES IS THE WHOLE JUDGEMENT. A ranking that reads a team's recent
        # realised counts is correcting a noisy lambda, so it must beat the NULL; one that
        # correlates with nothing only has to beat the shuffled control.
        floor = max(abs(null.get(key, 0.0)), ctrl_floor) if key in ESTIMATOR_FAMILY \
            else ctrl_floor
        verdict = _verdict(key, spread, floor, bool(null))
        nullv = f"{null.get(key, 0.0):+7.1f}" if key in null else "      –"
        print(f"  {key:22} {spread:+7.1f} {nullv}  {verdict}")

    n_days = len({r["date"] for r in spots})
    print(f"\ntop {top_n} per matchday — what the board and the Daily 2 ledger actually pick:")
    if n_days * top_n < 300:
        print(f"  (only ~{n_days * top_n} picks across {n_days} matchdays — this view is noisy;"
              f" read it against the RANDOM row, not in absolute terms)")
    print(f"  {'ranking':16} {'n':>6} {'avg line':>9} {'model %':>8} {'actual %':>9} {'residual':>9}")
    for key, _ in RANKINGS:
        print_top_n(spots, key, key, top_n)

    print(f"\n{'=' * 78}\nHOW TO READ IT\n{'=' * 78}")
    print(f"  Two floors, and which one applies depends on the ranking.")
    print(f"  RANDOM ({spreads.get('RANDOM', 0):+.1f}) is the sampling floor — it correlates with")
    print(f"  nothing, so anything at that level is noise.")
    if with_null and null:
        print(f"  The NULL column is the ESTIMATOR floor: the same ranking on data with no edge")
        print(f"  in it. A ranking built from recent realised counts can separate the buckets")
        print(f"  with no edge at all, because it is correcting a lambda estimated from ten")
        print(f"  games. Those rankings have to clear the null, not the control.")
    if ctrl_floor > 3:
        print("\n!! The control separated the buckets by more than 3 points — the sample is too "
              "noisy for\n!! any of these spreads to mean much.")

    # THE ANSWER TO THE QUESTION THIS RUN WAS DISPATCHED FOR, in one line, so it cannot be
    # read off the wrong column.
    if with_null and null:
        print(f"\n{'=' * 78}\nTHE CONCEDED ANGLE AS A RANKING\n{'=' * 78}")
        for key in ("opp_conc_consistency", "opp_conc_run"):
            spread = spreads.get(key, 0.0)
            floor = max(abs(null.get(key, 0.0)), ctrl_floor)
            # POSITIVE ONLY, for the reason in _verdict: the claim is that the top of the
            # ordering beats the bottom, and a negative spread is the opposite of that
            # rather than a stronger version of it.
            gap = spread - floor
            if gap > 1.0:
                print(f"  {key}: {spread:+.1f} against a floor of {floor:.1f} — CLEARS IT by "
                      f"{gap:+.1f}. Worth a second look before anything is built on it.")
            elif spread < -(floor + 1.0):
                print(f"  {key}: {spread:+.1f} against a floor of {floor:.1f} — INVERTED. The "
                      f"ordering puts the worst spots on top, which is not an edge upside down;"
                      f" check the score's sign before reading anything into it.")
            else:
                print(f"  {key}: {spread:+.1f} against a floor of {floor:.1f} — does NOT rank.")
        print("  A conceded run stays a way to FIND a spot, not a reason to weight it. The site")
        print("  labels it that way already; nothing here changes that.")


def main():
    args = sys.argv[1:]

    def opt(flag, default=None, cast=str):
        return cast(args[args.index(flag) + 1]) if flag in args else default

    asyncio.run(run(league_id=opt("--league"), top_n=opt("--top", TOP_N, int),
                    window=opt("--window", WINDOW, int),
                    min_games=opt("--min-games", MIN_GAMES, int),
                    # The null doubles the replay, and it is on by default because EVERY
                    # ranking here is built from estimated quantities — so without it the
                    # whole table is unreadable, not just part of it. That is what --no-null
                    # now means: a fast structural check that the replay still runs, never a
                    # shortcut to an answer. Reading a spread against the shuffled control
                    # is how +7.9 was once mistaken for a finding, and how five rankings
                    # were briefly flagged as broken.
                    with_null="--no-null" not in args))


if __name__ == "__main__":
    main()
