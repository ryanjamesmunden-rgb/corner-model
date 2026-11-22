"""DOES THE GAME-STATE VERDICT PICK BETTER SPOTS, OR JUST LOOK LIKE IT DOES?

game_state.py labels each side of a fixture chase_spot / neutral / caution / avoid, from
three things knowable before kick-off: how the side's corners have moved when it trailed
and when it led at half-time, how much stronger the opponent is by goal difference, and
whether the side shoots enough to win corners at all. The value board shows that label
beside every team line. This replays it.

THE SAME FUNCTION, NOT A COPY. Every team's history is rebuilt from fixture_stats in the
real_matches shape and handed to game_state.side_verdict — the call the live board makes.
A harness that re-implemented the rules would be measuring its own reading of them.

WALK-FORWARD. A side's history only ever holds games played BEFORE the match being
scored, and is updated after it. A row counts only once both sides have FORM_WINDOW
games on file.

WHAT IS SCORED is the gap between the model's probability and what happened, at 4+, 5+
and 6+, inside each bucket. The model here is the plain one every harness in this folder
uses (the side's corners won and the opponent's conceded, averaged, through the shipped
negative binomial), so a bucket's gap is how far that bucket sits from the price.

  model% ABOVE actual%  -> the model overrates corners there. Backing overs is worse
                           than the board says. `avoid` should look like this.
  model% BELOW actual%  -> it underrates them. `chase_spot` should look like this.

READ THE "vs ALL" BLOCK, which is each bucket's gap minus the model's overall gap — the
part the bucket is responsible for.

CONTROLS. RANDOM A / RANDOM B are a coin flip per row and must come out flat. If they
show a gap, the harness is manufacturing structure and no other row should move anything.

WHAT WOULD COUNT. `chase_spot` below ALL and `avoid` above it, by more than the random
rows wander, on a bucket of a few hundred or more. Anything less and the label stays a
label: the board keeps showing it and keeps not sorting on it.

Usage:  python measure_chase_filter.py
"""
import asyncio
import math
import os
import random
from collections import defaultdict, deque
from pathlib import Path

from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

import game_state as gs

ROOT = Path(__file__).parent
load_dotenv(ROOT / ".env")

LINES = [4, 5, 6]
NB_R = 11           # what ships; this measures the live model, not a candidate
MIN_BUCKET = 40     # below this a bucket is an anecdote and is printed as such
LEAGUE_SHOTS_KEEP = 400   # team-games per league behind the rolling shots average

#: Fixed so two runs agree. The controls exist to be flat, not to be surprising.
RNG = random.Random(20261122)


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


def gap_band(gap):
    if gap is None:
        return None
    if gap >= 1.5:
        return "gap: opp 1.5+ better"
    if gap >= gs.MISMATCH_GD:
        return f"gap: opp {gs.MISMATCH_GD}-1.5 better"
    if gap >= 0.4:
        return "gap: opp 0.4-1.0 better"
    if gap >= gs.CLOSE_LOW:
        return "gap: level (+/-0.4)"
    return "gap: we are 0.4+ better"


def row_for(m: dict, side: str) -> dict:
    """One fixture_stats document -> one real_matches-shaped row for `side`."""
    o = "away" if side == "home" else "home"
    return {"home": side == "home",
            "corners_for": m[f"{side}_corners"], "corners_against": m[f"{o}_corners"],
            "goals_for": m.get(f"{side}_goals"), "goals_against": m.get(f"{o}_goals"),
            "fh_goals_for": m.get(f"{side}_fh_goals"),
            "fh_goals_against": m.get(f"{o}_fh_goals"),
            "shots_for": m.get(f"{side}_shots") or 0}


def buckets(v: dict):
    out = ["verdict: " + v["verdict"]]
    out += ["flag: " + f for f in v["flags"] if f != "market_short"]
    b = gap_band(v["gap"])
    if b:
        out.append(b)
    out.append("[control] RANDOM A" if RNG.random() < 0.5 else "[control] RANDOM B")
    return out


async def run():
    db = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
    matches = await db.fixture_stats.find({}, {"_id": 0}).to_list(60000)
    matches = [m for m in matches
               if m.get("home_corners") is not None and m.get("away_corners") is not None
               and m.get("home_id") and m.get("away_id") and m.get("date")]
    matches.sort(key=lambda m: m["date"])

    hist = defaultdict(lambda: deque(maxlen=gs.STATE_WINDOW))
    league_shots = defaultdict(lambda: deque(maxlen=LEAGUE_SHOTS_KEEP))
    stat = defaultdict(lambda: {L: [0.0, 0, 0] for L in LINES})
    scored = thin = 0

    for m in matches:
        h, a = m["home_id"], m["away_id"]
        ls = avg(league_shots[m.get("league_id")]) or None
        for side, us, them in (("home", h, a), ("away", a, h)):
            mine, theirs = list(hist[us]), list(hist[them])
            if len(mine) < gs.FORM_WINDOW or len(theirs) < gs.FORM_WINDOW:
                thin += 1
                continue
            v = gs.side_verdict(mine, theirs, ls)
            lam = (avg([r["corners_for"] for r in mine[-gs.FORM_WINDOW:]])
                   + avg([r["corners_against"] for r in theirs[-gs.FORM_WINDOW:]])) / 2.0
            actual = m[f"{side}_corners"]
            scored += 1
            for b in ["ALL"] + buckets(v):
                for L in LINES:
                    s = stat[b][L]
                    s[0] += nb_ge(L, lam)
                    s[1] += 1 if actual >= L else 0
                    s[2] += 1
        # Histories advance only AFTER the match is scored.
        hist[h].append(row_for(m, "home"))
        hist[a].append(row_for(m, "away"))
        for side in ("home", "away"):
            if m.get(f"{side}_shots"):
                league_shots[m.get("league_id")].append(m[f"{side}_shots"])

    print(f"team-matches scored = {scored}   (skipped {thin} without {gs.FORM_WINDOW} "
          f"games on file for both sides)")
    if not scored:
        print("\nNothing to measure. fixture_stats has no usable history yet.")
        return

    order = (["ALL"]
             + [f"verdict: {v}" for v in ("chase_spot", "neutral", "caution", "avoid")]
             + [f"flag: {f}" for f in ("close", "mismatch", "blunt", "chaser",
                                       "fades_behind", "parker")]
             + ["gap: opp 1.5+ better", f"gap: opp {gs.MISMATCH_GD}-1.5 better",
                "gap: opp 0.4-1.0 better", "gap: level (+/-0.4)", "gap: we are 0.4+ better"]
             + ["[control] RANDOM A", "[control] RANDOM B"])

    print(f"\n{'bucket':28} {'n':>6}   "
          + "  ".join(f"{L}+ model/actual   gap" for L in LINES))
    base, rel = {}, {}
    for b in order:
        if b not in stat:
            continue
        cells, n = [], 0
        for L in LINES:
            s = stat[b][L]
            n = s[2]
            mp, ah = s[0] / n * 100, s[1] / n * 100
            gap = mp - ah
            if b == "ALL":
                base[L] = gap
            rel.setdefault(b, {})[L] = gap - base.get(L, 0.0)
            cells.append(f"{mp:5.1f}/{ah:5.1f} {gap:+6.1f}")
        print(f"{b:28} {n:>6}   " + "  ".join(cells)
              + ("  (thin)" if n < MIN_BUCKET else ""))

    print(f"\n{'bucket':28} " + "  ".join(f"{L}+ vs ALL" for L in LINES))
    for b in order:
        if b == "ALL" or b not in rel:
            continue
        print(f"{b:28} " + "  ".join(f"{rel[b][L]:+8.1f}" for L in LINES))

    print("\nHOW TO READ IT. Gap is model% minus actual%. NEGATIVE in the 'vs ALL' block"
          "\nmeans corners land MORE often than the price says in that bucket — where"
          "\nchase_spot should sit. POSITIVE means they land less often — where avoid"
          "\nshould sit. The RANDOM rows show how far a bucket wanders by chance; a"
          "\nverdict that moves no further than they do has not been shown to work.")
    print("\nCORNERS ARE FULL-MATCH ONLY, so the chase and park traits are built from"
          "\nfull-match counts in games trailing or leading at half-time (issue #260).")


if __name__ == "__main__":
    asyncio.run(run())
