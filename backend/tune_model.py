"""Offline model tuning: walk-forward compare candidate corner models on Brier +
calibration. Finds a v2 that beats v1 before anything ships to production.

WHY THE r SWEEP IS WIDER THAN IT WAS. This chose NB_R = 11 for team lines, and for a long
time the only candidates it compared were r=10 and r=11 — so "11 is best" meant "11 beat
10", which is a much smaller claim than it reads as. Nothing here had ever looked above 11.

tune_totals.py then produced a reason to. Convolving the shipped team curves (r=11) to get
a match total lands 4pp LOW at 7+ — 79.9% against an actual 84.0% — and raising r closes
it: r=24 reaches 82.4%. That is indirect evidence about the team curves, because it reaches
them through the convolution, but the obvious escape route does not work. Convolution
assumes the two sides are independent; they are positively correlated, so the true total is
WIDER than the convolution says, which would push P(7+) DOWN — further from the actual, not
towards it. Correlation cannot explain a convolution that is already too low. The team
curves being too dispersed can.

So this now sweeps r properly and scores it where it belongs: against team corner outcomes
directly, rather than inferred through a sum.

ANSWERED (2026-09-30, 7,521 matches): r=11 STAYS, and the case for raising it is dead.

    nb_r8    4+:64.4/65.7  5+:49.9/51.2  6+:36.8/37.9  7+:26.0/26.4   Brier 0.2205  gap 1.04
    nb_r11   4+:65.9/65.7  5+:50.7/51.2  6+:36.9/37.9  7+:25.5/26.4   Brier 0.2207  gap 0.61
    nb_r24   4+:68.2/65.7  5+:52.1/51.2  6+:37.1/37.9  7+:24.7/26.4   Brier 0.2216  gap 1.48

11 has the smallest per-line gap of anything swept. r=8 wins on Brier by 0.0002, which is
below the noise threshold this file already states. And the direction matters more than the
size: at 6+ and 7+ the live model UNDER-promises, so the tails are not too fat — raising r
pushes the low lines into over-promising (r=24 prices 4+ at 68.2 against an actual 65.7)
without fixing anything at the top.

THE CONVOLUTION ARGUMENT DOES NOT SURVIVE THE DIRECT TEST. tune_totals reaching r=24 through
a sum of two team curves was the reason to look higher; measured against team outcomes, which
is what this file exists to do, it is contradicted. If the match-total curve is still 4pp low
at 7+, that is now a fact about the CONVOLUTION — the independence assumption, or the total
being priced by Poisson rather than by the same NB — and not about the team curves.

Anyone arriving here from a bucket-ranked residual table (measure_chase_board's top-2 view
shows 64.8% priced against 57.0% landed) should read that file's note first: bucketing by
ranked lambda cannot separate a miscalibrated model from a noisy estimate of a calibrated
one. The per-line columns below can, and they say the model is fine.
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

LINES = [4, 5, 6, 7]
WINDOW = 10
MIN_GAMES = 5
# What ships today, and the range around it. 10 and 11 were the entire sweep before —
# see the note at the top for why the useful range turned out to be higher.
NB_R_LIVE = 11
R_SWEEP = [8, 10, 11, 14, 18, 24, 30]


def pois_ge(L, lam):
    if lam <= 0:
        return 0.0
    cum = sum(math.exp(-lam) * lam ** i / math.factorial(i) for i in range(L))
    return max(0.0, min(1.0, 1 - cum))


def nb_ge(L, lam, r):
    # negative binomial with mean lam, dispersion r (var = lam + lam^2/r)
    if lam <= 0:
        return 0.0
    p = r / (r + lam)
    # pmf(k) = C(k+r-1,k) p^r (1-p)^k ; use log-gamma for stability
    def pmf(k):
        return math.exp(math.lgamma(k + r) - math.lgamma(r) - math.lgamma(k + 1)
                        + r * math.log(p) + k * math.log(1 - p))
    cum = sum(pmf(k) for k in range(L))
    return max(0.0, min(1.0, 1 - cum))


def avg(d):
    return sum(d) / len(d) if d else 0.0


async def run():
    matches = await db.fixture_stats.find({}, {"_id": 0}).to_list(40000)
    # A cached fixture with no corner count is a document this cannot score, and reaching
    # m["home_corners"] on one is a KeyError thirty seconds into a run. tune_totals.py
    # already filters the same way.
    matches = [m for m in matches
               if m.get("home_corners") is not None and m.get("away_corners") is not None]
    matches.sort(key=lambda m: m.get("date") or "")
    all_sf = [m.get("home_shots", 0) for m in matches] + [m.get("away_shots", 0) for m in matches]
    lg_shots = sum(all_sf) / len(all_sf) if all_sf else 12.0

    cf = defaultdict(lambda: deque(maxlen=WINDOW))
    ca = defaultdict(lambda: deque(maxlen=WINDOW))
    sf = defaultdict(lambda: deque(maxlen=WINDOW))
    fhg = defaultdict(lambda: deque(maxlen=WINDOW))

    # model -> line -> [pred_sum, hit, n, brier]
    models = (["v1_pois"] + [f"nb_r{r}" for r in R_SWEEP]
              + ["nb10_shots", "nb10_shotsform", "nb11_shotsform"])
    stat = {m: {L: [0.0, 0, 0, 0.0] for L in LINES} for m in models}

    def predict(model, tf, oa, tsf, tfhg):
        lam = (tf + oa) / 2.0
        if model == "v1_pois":
            return lambda L: pois_ge(L, lam)
        if model.startswith("nb_r"):
            r = int(model.split("r")[1]); return lambda L: nb_ge(L, lam, r)
        # blends: mild shots-intent (+/-10%) and optional first-half-goal form (+/-3%)
        intent = 0.90 + 0.10 * max(0.6, min(1.5, tsf / lg_shots)) if lg_shots else 1.0
        form = 1.0 + 0.03 * (tfhg - 0.5)
        if model == "nb10_shots":
            return lambda L: nb_ge(L, lam * intent, 10)
        if model == "nb10_shotsform":
            return lambda L: nb_ge(L, lam * intent * form, 10)
        if model == "nb11_shotsform":
            return lambda L: nb_ge(L, lam * intent * form, 11)

    for m in matches:
        h, a = m["home_id"], m["away_id"]
        sides = [
            (list(cf[h]), list(ca[a]), list(sf[h]), list(fhg[h]), m["home_corners"],
             len(cf[h]) >= MIN_GAMES and len(ca[a]) >= MIN_GAMES),
            (list(cf[a]), list(ca[h]), list(sf[a]), list(fhg[a]), m["away_corners"],
             len(cf[a]) >= MIN_GAMES and len(ca[h]) >= MIN_GAMES),
        ]
        for tf_l, oa_l, sf_l, fhg_l, actual, can in sides:
            if not can:
                continue
            tf, oa, tsf, tfhg = avg(tf_l), avg(oa_l), avg(sf_l), avg(fhg_l)
            for model in models:
                fn = predict(model, tf, oa, tsf, tfhg)
                for L in LINES:
                    p = fn(L); hit = 1 if actual >= L else 0
                    s = stat[model][L]
                    s[0] += p; s[1] += hit; s[2] += 1; s[3] += (p - hit) ** 2
        cf[h].append(m["home_corners"]); ca[h].append(m["away_corners"]); sf[h].append(m.get("home_shots", 0)); fhg[h].append(1 if m.get("home_fh_goals", 0) >= 1 else 0)
        cf[a].append(m["away_corners"]); ca[a].append(m["home_corners"]); sf[a].append(m.get("away_shots", 0)); fhg[a].append(1 if m.get("away_fh_goals", 0) >= 1 else 0)

    print(f"matches={len(matches)}\n")
    print(f"{'model':22} {'Brier':>7} {'avg|gap|':>9}   per-line gap (model% vs actual%)")
    rows = []
    for model in models:
        tb = tn = 0.0; gaps = []; detail = []
        for L in LINES:
            s = stat[model][L]
            if s[2] == 0:
                continue
            mp = s[0] / s[2] * 100; ah = s[1] / s[2] * 100
            gaps.append(abs(mp - ah)); tb += s[3]; tn += s[2]
            detail.append(f"{L}+:{mp:4.1f}/{ah:4.1f}")
        brier = tb / tn if tn else 0
        gap = sum(gaps) / len(gaps) if gaps else 0
        rows.append((brier, gap, model))
        print(f"{model:22} {brier:7.4f} {gap:9.2f}   {' '.join(detail)}")

    # WITHOUT THIS IT IS A TABLE, AND A TABLE GETS READ AS WHICHEVER ROW THE READER LIKED.
    # The r sweep exists to answer one question — is 11 the right dispersion for a team
    # line — so the answer has to be stated, including when the answer is "yes, leave it".
    pure = [r for r in rows if r[2].startswith("nb_r")]
    if pure:
        best = min(pure)
        live = next((r for r in pure if r[2] == f"nb_r{NB_R_LIVE}"), None)
        print(f"\nbest r on Brier:  {best[2]} ({best[0]:.4f}, avg gap {best[1]:.2f}pp)")
        print(f"best r on gap:    {min(pure, key=lambda x: x[1])[2]}")
        if live:
            d = live[0] - best[0]
            print(f"live today:       nb_r{NB_R_LIVE} ({live[0]:.4f}, avg gap {live[1]:.2f}pp)")
            print(f"Brier improvement available: {d:+.4f}"
                  f"{'  — nothing beats what ships' if d <= 1e-9 else ''}")
        print("\nr is DISPERSION, and higher means narrower: var = lam + lam^2/r. A win of"
              "\nless than ~0.001 Brier is noise at this sample size — r=11 was itself chosen"
              "\non a margin this harness can reproduce. Read the per-line columns before"
              "\nmoving anything: a model that wins on average while missing badly at 5+ or 6+"
              "\nis worse where the lines actually get bet.")


if __name__ == "__main__":
    asyncio.run(run())
