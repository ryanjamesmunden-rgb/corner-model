"""WHERE THE CORNER MODEL IS WRONG, split by what was happening in the game.

THE QUESTION THIS ANSWERS. The model prices a team's corners from two numbers: what that
team wins, and what its opponent concedes. It knows nothing about the state of the match.
But a side 2-0 up at half time is not playing the same game as a side 2-0 down — one sits
back and the other throws bodies forward — and both of them produce a corner count the
model expected from neither.

So this does not ask "is the model good". tune_model.py already answers that on average.
It asks WHERE the average is hiding a bias, by scoring the same prediction separately
inside each game state and printing the gap between what the model said and what happened.

HOW TO READ IT. Each bucket prints model% against actual%. A gap near zero means the model
is already right about that state and nothing needs adding. A consistent gap in one
direction is the interesting result: it means game state carries information the price is
not using, and how much.

  model% HIGHER than actual%  -> the model OVERRATES corners in that state. Backing overs
                                 there is worse than the site says.
  model% LOWER than actual%   -> it UNDERRATES them, and those are the spots being missed.

WALK-FORWARD, so the prediction only ever uses games already played. The bucket is decided
by what actually happened in the match being predicted — which is the point: this is a
post-mortem of where the model's blind spot is, not a feature it could have used in
advance. If a bucket shows a real gap, the next question is whether anything KNOWABLE
BEFOREHAND predicts landing in it.

WHAT IS NOT HERE. League position, and anything of the "needs three points" or "can go top
with a win" kind. fixture_stats carries no table, and a running one cannot be rebuilt from
it honestly — points depend on every game in the division including ones not stored here.
That needs standings from the API. The half-time buckets below are the part the existing
data can answer, and they cover most of what game state does to a corner count.

Usage:  python measure_game_state.py
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

LINES = [4, 5, 6]
WINDOW = 10
MIN_GAMES = 5
NB_R = 11          # what ships; this measures the live model, not a candidate
MIN_BUCKET = 40    # below this a bucket is an anecdote, and is printed as such


def nb_ge(L, lam, r=NB_R):
    if lam <= 0:
        return 0.0
    p = r / (r + lam)

    def pmf(k):
        return math.exp(math.lgamma(k + r) - math.lgamma(r) - math.lgamma(k + 1)
                        + r * math.log(p) + k * math.log(1 - p))
    return max(0.0, min(1.0, 1 - sum(pmf(k) for k in range(L))))


def avg(d):
    return sum(d) / len(d) if d else 0.0


def buckets_for(fh_for, fh_against, ft_for, ft_against):
    """Every state this match puts the team in. A match lands in several — "led at HT" and
    "won" are both true and both worth scoring, so they are not mutually exclusive."""
    out = []
    lead = fh_for - fh_against
    out.append("HT leading" if lead > 0 else "HT level" if lead == 0 else "HT trailing")
    if fh_for >= 1:
        out.append("scored 1+ in FH")
    if fh_for >= 2:
        out.append("scored 2+ in FH")
    if lead >= 2:
        out.append("2+ up at HT")
    if lead <= -2:
        out.append("2+ down at HT")
    if fh_for == 0 and fh_against == 0:
        out.append("0-0 at HT")
    if ft_for is not None and ft_against is not None:
        out.append("won" if ft_for > ft_against
                   else "drew" if ft_for == ft_against else "lost")
        # The specific shape asked about: ahead early, and only needing to see it out.
        if lead > 0 and ft_for > ft_against:
            out.append("led at HT, won")
        if lead > 0 and ft_for <= ft_against:
            out.append("led at HT, did NOT win")
    return out


async def run():
    matches = await db.fixture_stats.find({}, {"_id": 0}).to_list(40000)
    matches = [m for m in matches
               if m.get("home_corners") is not None and m.get("away_corners") is not None]
    matches.sort(key=lambda m: m["date"])

    cf = defaultdict(lambda: deque(maxlen=WINDOW))
    ca = defaultdict(lambda: deque(maxlen=WINDOW))

    # bucket -> line -> [pred_sum, hits, n]
    stat = defaultdict(lambda: {L: [0.0, 0, 0] for L in LINES})
    covered = skipped = 0

    for m in matches:
        h, a = m["home_id"], m["away_id"]
        hfh, afh = m.get("home_fh_goals"), m.get("away_fh_goals")
        has_state = hfh is not None and afh is not None
        hft, aft = m.get("home_goals"), m.get("away_goals")

        sides = [
            (list(cf[h]), list(ca[a]), m["home_corners"], hfh, afh, hft, aft,
             len(cf[h]) >= MIN_GAMES and len(ca[a]) >= MIN_GAMES),
            (list(cf[a]), list(ca[h]), m["away_corners"], afh, hfh, aft, hft,
             len(cf[a]) >= MIN_GAMES and len(ca[h]) >= MIN_GAMES),
        ]
        for tf_l, oa_l, actual, fh_f, fh_a, ft_f, ft_a, can in sides:
            if not can:
                continue
            if not has_state:
                skipped += 1
                continue
            covered += 1
            lam = (avg(tf_l) + avg(oa_l)) / 2.0
            names = ["ALL"] + buckets_for(fh_f, fh_a, ft_f, ft_a)
            for L in LINES:
                p = nb_ge(L, lam)
                hit = 1 if actual >= L else 0
                for b in names:
                    s = stat[b][L]
                    s[0] += p
                    s[1] += hit
                    s[2] += 1

        cf[h].append(m["home_corners"]); ca[h].append(m["away_corners"])
        cf[a].append(m["away_corners"]); ca[a].append(m["home_corners"])

    print(f"team-matches scored = {covered}"
          + (f"   (skipped {skipped} with no half-time score — run backfill_goals.py)"
             if skipped else ""))
    if not covered:
        print("\nNothing to measure. fixture_stats has no half-time goals yet:"
              "\n  python backfill_goals.py")
        return

    order = ["ALL", "0-0 at HT", "HT level", "HT leading", "HT trailing",
             "scored 1+ in FH", "scored 2+ in FH", "2+ up at HT", "2+ down at HT",
             "led at HT, won", "led at HT, did NOT win", "won", "drew", "lost"]
    print(f"\n{'game state':24} {'n':>6}   " + "  ".join(f"{L}+ model/actual  gap" for L in LINES))
    base = {}
    for b in order:
        if b not in stat:
            continue
        cells, n = [], 0
        for L in LINES:
            s = stat[b][L]
            n = s[2]
            if not n:
                cells.append("        —      ")
                continue
            mp, ah = s[0] / n * 100, s[1] / n * 100
            if b == "ALL":
                base[L] = mp - ah
            cells.append(f"{mp:5.1f}/{ah:5.1f} {mp - ah:+6.1f}")
        thin = "  (thin)" if n < MIN_BUCKET else ""
        print(f"{b:24} {n:>6}   " + "  ".join(cells) + thin)

    print("\nHOW TO READ THE GAP: model% minus actual%. Positive means the model expected"
          "\nmore corners than the team won in that state — backing an over there is worse"
          "\nthan the price says. Negative means those are the spots it is underrating.")
    print("A bucket under", MIN_BUCKET, "is marked thin and should move nothing on its own.")
    print("\nThe ALL row is the model's overall bias. What matters in every other row is"
          "\nhow far it sits FROM that row, not from zero — a state that misses by the same"
          "\namount as everything else is not telling you anything about game state.")


if __name__ == "__main__":
    asyncio.run(run())
