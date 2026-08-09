"""Offline model tuning: walk-forward compare candidate corner models on Brier +
calibration. Finds a v2 that beats v1 before anything ships to production."""
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
    matches.sort(key=lambda m: m["date"])
    all_sf = [m.get("home_shots", 0) for m in matches] + [m.get("away_shots", 0) for m in matches]
    lg_shots = sum(all_sf) / len(all_sf) if all_sf else 12.0

    cf = defaultdict(lambda: deque(maxlen=WINDOW))
    ca = defaultdict(lambda: deque(maxlen=WINDOW))
    sf = defaultdict(lambda: deque(maxlen=WINDOW))
    fhg = defaultdict(lambda: deque(maxlen=WINDOW))

    # model -> line -> [pred_sum, hit, n, brier]
    models = ["v1_pois", "nb_r10", "nb_r11",
              "nb10_shots", "nb10_shotsform", "nb11_shotsform"]
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
        print(f"{model:22} {brier:7.4f} {sum(gaps)/len(gaps):9.2f}   {' '.join(detail)}")


if __name__ == "__main__":
    asyncio.run(run())
