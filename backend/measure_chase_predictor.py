"""CAN YOU KNOW BEFORE KICK-OFF WHICH SIDE IS ABOUT TO BE CHASING?

THE QUESTION THIS EXISTS TO ANSWER, and it is the one measure_game_state.py ends on.
That harness found a large, consistent bias: scored across 17,058 team-matches, a side
trailing at half time beat the model's own price by about five points at 4+, 5+ and 6+,
and a side leading fell short by about six. The chase effect is real and it is one of the
biggest blind spots in the model.

But it is a POST-MORTEM. Its buckets are decided by what happened in the match being
predicted, so none of it can be acted on: at kick-off you do not know who will be behind.
Its own closing note says the next question is whether anything KNOWABLE BEFOREHAND
predicts landing in the trailing bucket. This is that question.

WHAT IS BEING TESTED. A team trails when its opponent scores. Both halves of that are
knowable in advance as rates:

    the OPPONENT's scoring rate   - how often they have scored at all, recently
    the TEAM's conceding rate     - how often this side has been breached, recently

"Aalesund have scored in 9 of their last 10" is the first of those, and it is the exact
observation that prompted this. It is NOT what the chase board tested and lost on: that
used `opp_fh_rate`, the opponent's FIRST-HALF scoring rate, which is a narrower thing —
a side that habitually scores on 70 minutes has an opp_fh_rate of zero and still puts
its opponent behind.

TWO CONTROLS RIDE ALONG, and they are the reason to believe anything this prints.

  opp FH-scored 7+/10 - the FALSIFIED feature. Five tests have failed to find an effect
                        from the first-half version, and measure_chase_board scored every
                        ordering built on it as indistinguishable from random. If it comes
                        out with a gap here, this harness is manufacturing gradients and
                        nothing else in the table can be trusted.
  RANDOM A / RANDOM B - a coin flip per row. Must come out flat.

A new feature is only interesting if it separates WHILE both controls stay flat.

EVERY RATE IS BUILT FROM GAMES STRICTLY BEFORE THE MATCH BEING SCORED, and a row is only
counted once BOTH sides have a full ten games on file — otherwise "9 of 10" is not a
sentence that can be said about them, and the baseline would be computed over a different
population from the buckets.

Usage:  python measure_chase_predictor.py
"""
import asyncio
import math
import os
import random
from collections import defaultdict, deque
from pathlib import Path

from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

ROOT = Path(__file__).parent
load_dotenv(ROOT / ".env")
db = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]

LINES = [4, 5, 6]
WINDOW = 10        # the window every rate is taken over, and the posts' own denominator
NB_R = 11          # what ships; this measures the live model, not a candidate
MIN_BUCKET = 40    # below this a bucket is an anecdote and is printed as such

#: Fixed so two runs of this agree. The controls exist to be flat, not to be surprising.
RNG = random.Random(20261109)


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


def buckets_for(opp_scored, team_conceded, opp_fh):
    """Every PRE-GAME bucket this match puts the team in.

    Counts out of ten, taken before kick-off. A match lands in several — the bands are
    not mutually exclusive with the compound — and each is scored separately.
    """
    out = []
    # The observation that prompted this, at its own threshold and the bands either side.
    if opp_scored >= 9:
        out.append("opp scored 9+/10")
    elif opp_scored >= 7:
        out.append("opp scored 7-8/10")
    else:
        out.append("opp scored <=6/10")

    if team_conceded >= 9:
        out.append("team conceded 9+/10")
    elif team_conceded <= 6:
        out.append("team conceded <=6/10")

    # Both sides of "will this team go behind" agreeing. If the mechanism is real this is
    # where it should show up hardest.
    if opp_scored >= 8 and team_conceded >= 8:
        out.append("LIKELY BEHIND (both 8+/10)")
    if opp_scored <= 5 and team_conceded <= 5:
        out.append("LIKELY NOT BEHIND (both <=5/10)")

    # CONTROL ONE: the falsified first-half version.
    if opp_fh >= 7:
        out.append("[control] opp FH-scored 7+/10")

    # CONTROL TWO: noise. Flat or this table means nothing.
    out.append("[control] RANDOM A" if RNG.random() < 0.5 else "[control] RANDOM B")
    return out


async def run():
    matches = await db.fixture_stats.find({}, {"_id": 0}).to_list(40000)
    matches = [m for m in matches
               if m.get("home_corners") is not None and m.get("away_corners") is not None]
    matches.sort(key=lambda m: m["date"])

    # corners won / conceded, for the lambda the live model would have used
    cf = defaultdict(lambda: deque(maxlen=WINDOW))
    ca = defaultdict(lambda: deque(maxlen=WINDOW))
    # did this side score / concede / score in the first half, per recent game
    scored = defaultdict(lambda: deque(maxlen=WINDOW))
    conceded = defaultdict(lambda: deque(maxlen=WINDOW))
    fh_scored = defaultdict(lambda: deque(maxlen=WINDOW))

    stat = defaultdict(lambda: {L: [0.0, 0, 0] for L in LINES})
    covered = no_state = thin_history = 0

    for m in matches:
        h, a = m["home_id"], m["away_id"]
        hfh, afh = m.get("home_fh_goals"), m.get("away_fh_goals")
        hft, aft = m.get("home_goals"), m.get("away_goals")
        has_goals = None not in (hft, aft)
        has_fh = None not in (hfh, afh)

        for team, opp, actual in ((h, a, m["home_corners"]), (a, h, m["away_corners"])):
            # A FULL TEN ON BOTH SIDES OR THE ROW IS NOT SCORED. Otherwise the rate bands
            # and the ALL baseline would describe different populations.
            if not (len(cf[team]) >= WINDOW and len(ca[opp]) >= WINDOW
                    and len(scored[opp]) >= WINDOW and len(conceded[team]) >= WINDOW
                    and len(fh_scored[opp]) >= WINDOW):
                thin_history += 1
                continue
            lam = (avg(list(cf[team])) + avg(list(ca[opp]))) / 2.0
            names = ["ALL"] + buckets_for(sum(scored[opp]), sum(conceded[team]),
                                          sum(fh_scored[opp]))
            covered += 1
            for L in LINES:
                p = nb_ge(L, lam)
                hit = 1 if actual >= L else 0
                for b in names:
                    s = stat[b][L]
                    s[0] += p
                    s[1] += hit
                    s[2] += 1

        # Histories advance only AFTER the match is scored, so nothing sees its own result.
        cf[h].append(m["home_corners"]); ca[h].append(m["away_corners"])
        cf[a].append(m["away_corners"]); ca[a].append(m["home_corners"])
        if has_goals:
            scored[h].append(1 if hft > 0 else 0)
            scored[a].append(1 if aft > 0 else 0)
            conceded[h].append(1 if aft > 0 else 0)
            conceded[a].append(1 if hft > 0 else 0)
        else:
            no_state += 1
        if has_fh:
            fh_scored[h].append(1 if hfh > 0 else 0)
            fh_scored[a].append(1 if afh > 0 else 0)

    print(f"team-matches scored = {covered}")
    print(f"  not scored for want of ten games on both sides = {thin_history}")
    if no_state:
        print(f"  fixtures with no full-time score = {no_state}")
    if not covered:
        print("\nNothing to measure. fixture_stats carries no goals yet:"
              "\n  python backfill_goals.py")
        return

    order = ["ALL",
             "opp scored 9+/10", "opp scored 7-8/10", "opp scored <=6/10",
             "team conceded 9+/10", "team conceded <=6/10",
             "LIKELY BEHIND (both 8+/10)", "LIKELY NOT BEHIND (both <=5/10)",
             "[control] opp FH-scored 7+/10",
             "[control] RANDOM A", "[control] RANDOM B"]

    print(f"\n{'pre-game bucket':32} {'n':>6}   "
          + "  ".join(f"{L}+ model/actual  gap" for L in LINES))
    base = {}
    rel = {}
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
            gap = mp - ah
            if b == "ALL":
                base[L] = gap
            rel.setdefault(b, {})[L] = gap - base.get(L, 0.0)
            cells.append(f"{mp:5.1f}/{ah:5.1f} {gap:+6.1f}")
        thin = "  (thin)" if n < MIN_BUCKET else ""
        print(f"{b:32} {n:>6}   " + "  ".join(cells) + thin)

    # THE COLUMN THAT ACTUALLY ANSWERS THE QUESTION. A bucket missing by the same amount
    # as everything else says nothing about the feature; the distance from ALL is the
    # effect, and printing it separately stops it being eyeballed wrongly.
    print(f"\n{'bucket':32} " + "  ".join(f"{L}+ vs ALL" for L in LINES))
    for b in order:
        if b == "ALL" or b not in rel:
            continue
        print(f"{b:32} " + "  ".join(f"{rel[b].get(L, 0.0):+8.1f}" for L in LINES))

    print("\nHOW TO READ IT. Gap is model% minus actual%, so NEGATIVE means the model"
          "\nunderrates that bucket and those corners land more often than the price says."
          "\nThe 'vs ALL' block is the one to read: it is the gap minus the model's overall"
          "\nbias, which is the part the bucket is responsible for.")
    print("\nTHE CONTROLS DECIDE WHETHER ANY OF IT COUNTS. Both RANDOM rows must sit near"
          "\nzero, and the FH-scored row is a feature five previous tests found nothing in."
          "\nIf either control shows a gap, this harness is finding structure that is not"
          "\nthere and no other row should move anything.")
    print("\nAND THIS IS STILL CORRELATION. These rates are knowable before kick-off, which"
          "\nis what separates them from measure_game_state's buckets — but a side whose"
          "\nopponent always scores is often simply the weaker side, and the model may be"
          "\nwrong about such teams for reasons that have nothing to do with chasing.")


if __name__ == "__main__":
    asyncio.run(run())
