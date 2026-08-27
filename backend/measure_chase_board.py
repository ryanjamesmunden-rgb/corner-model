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

A PERFECTLY GOOD OUTCOME IS "NOTHING RANKS". If every candidate is flat, the answer is
not to keep hunting for a score — it is that the Daily 2 should select on a stated,
transparent rule (a quality bar plus something readable like model probability), and
say plainly that it is not a discovered edge.

WHY A GRADIENT CAN BE REAL EVEN IF THE MODEL IS "RIGHT": lambda is ESTIMATED from a
10-game window, so it carries error. `consistency` is a second, independent look at the
same quantity — did this team clear this line on this venue lately — so it can correct
that error. In validation, on data drawn from the model's own distribution (where no
market edge exists by construction), consistency still separated the buckets by 7.5
points against a control floor of 1.8. That is a real effect, but it is a statement
about ESTIMATION, not about finding mispriced games: it says lambda is noisy and
consistency knows something lambda missed. The fix that implies is folding venue form
into lambda, not betting the top of the board harder.

Two views:
  1. Buckets over every scored row — is there a gradient at all?
  2. Top-N per matchday — what the board and the Daily 2 ledger actually do.

Run: python measure_chase_board.py
     python measure_chase_board.py --league eng-pl --top 2
"""
import asyncio
import os
import random
import sys
from collections import defaultdict, deque
from pathlib import Path

from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

from server import NB_R, V3_BLOCKED_WEIGHT, model_lambda, nb_ge

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


def rate(hits, n):
    return (hits / n * 100) if n else 0.0


async def build_spots(league_id=None, window=WINDOW, min_games=MIN_GAMES):
    """Replay every past fixture as the chase board would have seen it beforehand."""
    q = {} if not league_id or league_id == "all" else {"league_id": league_id}
    matches = await db.fixture_stats.find(q, {"_id": 0}).to_list(60000)
    matches = [m for m in matches if m.get("date")]
    matches.sort(key=lambda m: m["date"])
    if not matches:
        return [], matches

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
            lam = model_lambda("v3", avg(cf[team]), avg(ca[opp]), avg(sf[team]), lg_shots,
                               avg(fh[team]), avg(bl[team]) if len(bl[team]) >= min_games else 0.0,
                               lg_blocked, V3_BLOCKED_WEIGHT)
            line = max(3, round(lam) - 1)
            consistency = sum(1 for c in vpool if c >= line) / len(vpool)
            opp_fh = avg(fh[opp])
            spots.append({
                "date": m["date"][:10], "team": team, "line": line, "lambda": lam,
                "prob": nb_ge(line, lam) * 100, "hit": 1 if actual >= line else 0,
                "opp_fh": opp_fh, "consistency": consistency,
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
    return spots, matches


# Every ordering scored, in both views. The first four are already falsified (all flat
# against a flat control); they stay so a re-run reproduces the null rather than asking
# you to take it on trust. The next four are the candidates for what Daily 2 should
# select on, chosen for being ORTHOGONAL to lambda.
RANKINGS = [
    ("chase_score", "chase_score — the live board formula [known flat]"),
    ("lambda_only", "lambda_only — no chase, no consistency [known flat]"),
    ("no_opp_fh", "no_opp_fh — falsified opponent term removed [known flat]"),
    ("no_consistency", "no_consistency — last-5 term removed [known flat]"),
    ("venue_delta", "venue_delta — venue form vs the team's own average [CANDIDATE]"),
    ("opp_conc_delta", "opp_conc_delta — opponent conceding more on this venue [CANDIDATE]"),
    ("consistency_only", "consistency_only — last-5 hit rate alone [CANDIDATE]"),
    ("depth", "depth — games behind the estimate [diagnostic, argues for a bar]"),
    ("slack", "slack — lambda above the line [anchor, flat is EXPECTED]"),
    ("RANDOM", "RANDOM — control, must be flat"),
]


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


async def run(league_id=None, top_n=TOP_N, window=WINDOW, min_games=MIN_GAMES):
    spots, matches = await build_spots(league_id, window, min_games)
    if not matches:
        print("no cached fixtures — run sync_real.py first")
        return
    print(f"fixtures={len(matches)}  league={league_id or 'all'}  spots scored={len(spots)}")
    if not spots:
        print("no spot had enough history to rank — nothing to measure")
        return
    print(f"date range: {matches[0]['date'][:10]} -> {matches[-1]['date'][:10]}")
    overall = summarise(spots)
    print(f"\nevery spot: n={overall['n']}  avg line {overall['avg_line']:.2f}  "
          f"model {overall['model_prob']:.1f}%  actual {overall['hit_rate']:.1f}%  "
          f"residual {overall['residual']:+.1f}")
    print("(a non-zero residual here is the model's own calibration, not the ranking's doing —"
          "\n what matters below is whether the residual MOVES across buckets)")
    if len(spots) < MIN_ROWS:
        print(f"\n!! {len(spots)} spots is thin (want >= {MIN_ROWS}); treat this as a smoke test.")

    rng = random.Random(CONTROL_SEED)
    for r in spots:
        r["RANDOM"] = rng.random()

    spreads = {}
    for key, label in RANKINGS:
        spreads[key] = print_buckets(spots, key, label)

    print("\ntop-minus-bottom residual (how much the ordering separates good from bad):")
    for key, spread in spreads.items():
        print(f"  {key:16} {spread:+.1f} pts")

    n_days = len({r["date"] for r in spots})
    print(f"\ntop {top_n} per matchday — what the board and the Daily 2 ledger actually pick:")
    if n_days * top_n < 300:
        print(f"  (only ~{n_days * top_n} picks across {n_days} matchdays — this view is noisy;"
              f" read it against the RANDOM row, not in absolute terms)")
    print(f"  {'ranking':16} {'n':>6} {'avg line':>9} {'model %':>8} {'actual %':>9} {'residual':>9}")
    for key, _ in RANKINGS:
        print_top_n(spots, key, key, top_n)

    ctrl = abs(spreads.get("RANDOM", 0.0))
    print(f"\nREAD IT LIKE THIS: the control's spread ({spreads.get('RANDOM', 0):+.1f}) is the noise "
          f"floor.\nA ranking is only doing something if its spread clearly exceeds it.")
    if ctrl > 3:
        print("!! The control separated the buckets by more than 3 points — the sample is too "
              "noisy for\n!! any of these spreads to mean much.")


def main():
    args = sys.argv[1:]

    def opt(flag, default=None, cast=str):
        return cast(args[args.index(flag) + 1]) if flag in args else default

    asyncio.run(run(league_id=opt("--league"), top_n=opt("--top", TOP_N, int),
                    window=opt("--window", WINDOW, int),
                    min_games=opt("--min-games", MIN_GAMES, int)))


if __name__ == "__main__":
    main()
