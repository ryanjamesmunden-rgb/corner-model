"""Does a side concede more corners in the games it keeps clean?

THE CLAIM BEING TESTED, in the words it was put to us: "no goals conceded = more corners
conceded when the game gets desperate". The reasoning is that a team protecting a lead
invites pressure, the opponent throws bodies forward, and the corners pile up at one end.

IT IS NOT OBVIOUS, AND THE OPPOSITE IS JUST AS ARGUABLE. A defence nobody breaks down may
simply be facing nobody who gets near its box — in which case clean sheets would come
with FEWER corners conceded, not more, and a context line asserting the mechanism would
be telling readers the reverse of what the record says.

So this measures it rather than assuming it. Three cuts, because the claim has three
readable versions and they can disagree:

  CLEAN SHEET      corners conceded in games the side conceded no goal, against games it
                   did. The literal reading of the claim.
  BY RESULT        corners conceded when winning / drawing / losing. "Desperate" is
                   really about the scoreline, and a 1-0 win is the case described.
  LEADING AT HALF  corners conceded having led at half-time, which is the state that
                   leaves the most time for the other side to chase.

WHAT THIS CANNOT SEE, and the reason no cut here is a clean test of the mechanism: corner
data is FULL-MATCH ONLY (probe_corner_halves.py, issue #260). A side that goes ahead on
80 minutes and one that led from the 5th land in the same bucket, and a chase effect
concentrated in the last ten minutes reads diluted across ninety. So a positive result
here is consistent with the mechanism rather than proof of it, and a null result does not
rule it out. Both of those get said out loud wherever the number is used.

Pure functions, no database and no imports from server, so the arithmetic is testable
without either.
"""
from typing import Dict, List, Optional

MIN_BUCKET = 30     # team-games before a bucket's mean is worth printing


def _ft(m: dict) -> Optional[int]:
    f, a = m.get("goals_for"), m.get("goals_against")
    if f is None or a is None:
        return None
    return (f > a) - (f < a)


def _ht(m: dict) -> Optional[int]:
    f, a = m.get("fh_goals_for"), m.get("fh_goals_against")
    if f is None or a is None:
        return None
    return (f > a) - (f < a)


def _stats(rows: List[dict]) -> dict:
    """Mean corners conceded and won over a bucket, with its size."""
    n = len(rows)
    if not n:
        return {"games": 0, "conceded": None, "won": None, "total": None}
    ca = sum(m["corners_against"] for m in rows)
    cf = sum(m["corners_for"] for m in rows)
    return {"games": n,
            "conceded": round(ca / n, 3),
            "won": round(cf / n, 3),
            "total": round((ca + cf) / n, 3)}


def _usable(m: dict) -> bool:
    return (m.get("corners_for") is not None
            and m.get("corners_against") is not None
            and m.get("goals_against") is not None)


def bucket_state_corners(teams: List[dict]) -> dict:
    """Aggregate every team-game into the three cuts above.

    One row per team per match, which double-counts each FIXTURE — both sides of it
    appear, once from each point of view. That is correct here: the unit of the claim is
    a team's own game, and a 1-0 contributes the winner's clean sheet AND the loser's
    defeat, which are two different observations of two different states."""
    pool = [m for t in (teams or []) for m in (t.get("real_matches") or []) if _usable(m)]

    clean = [m for m in pool if m["goals_against"] == 0]
    leaked = [m for m in pool if m["goals_against"] > 0]

    by_result = {}
    for label, want in (("won", 1), ("drew", 0), ("lost", -1)):
        by_result[label] = _stats([m for m in pool if _ft(m) == want])

    by_ht = {}
    for label, want in (("leading", 1), ("level", 0), ("trailing", -1)):
        by_ht[label] = _stats([m for m in pool if _ht(m) == want])

    out = {
        "team_games": len(pool),
        "baseline": _stats(pool),
        "clean_sheet": _stats(clean),
        "conceded_a_goal": _stats(leaked),
        "by_result": by_result,
        "by_half_time_state": by_ht,
    }
    out["verdict"] = verdict(out)
    return out


def verdict(agg: dict) -> dict:
    """Does the record support the claim, and by how much.

    `direction` is the only thing a context line may lean on, and it is allowed to be
    "unclear": a gap smaller than NOTABLE on a corner count is not something a reader
    should be told about, and a thin bucket gets no verdict at all."""
    NOTABLE = 0.25        # corners per game. Below this the sentence is not worth saying.
    cs, lk = agg["clean_sheet"], agg["conceded_a_goal"]
    if (cs["games"] < MIN_BUCKET or lk["games"] < MIN_BUCKET
            or cs["conceded"] is None or lk["conceded"] is None):
        return {"direction": "insufficient", "gap": None,
                "says": "Not enough games on file to answer this."}
    gap = round(cs["conceded"] - lk["conceded"], 3)
    if abs(gap) < NOTABLE:
        return {"direction": "unclear", "gap": gap,
                "says": (f"No real difference: {cs['conceded']:.2f} corners conceded in "
                         f"clean sheets against {lk['conceded']:.2f} otherwise "
                         f"({gap:+.2f}). The claim is not supported, and not refuted "
                         f"either — a full-match corner count cannot see a late chase.")}
    if gap > 0:
        return {"direction": "supports", "gap": gap,
                "says": (f"Sides concede {gap:+.2f} MORE corners a game in matches they "
                         f"keep clean ({cs['conceded']:.2f} against "
                         f"{lk['conceded']:.2f}), over {cs['games']} clean sheets. "
                         f"Consistent with a side under pressure protecting a lead.")}
    return {"direction": "contradicts", "gap": gap,
            "says": (f"Sides concede {abs(gap):.2f} FEWER corners a game in matches "
                     f"they keep clean ({cs['conceded']:.2f} against "
                     f"{lk['conceded']:.2f}), over {cs['games']} clean sheets. The "
                     f"claim runs the wrong way: a clean sheet looks more like an easy "
                     f"night than a siege.")}


def report(agg: dict) -> str:
    """Printable, for a workflow log."""
    b = agg["baseline"]
    lines = [f"team-games: {agg['team_games']}",
             f"baseline            conceded {b['conceded']} | won {b['won']} "
             f"| total {b['total']}  (n={b['games']})"]
    for label in ("clean_sheet", "conceded_a_goal"):
        s = agg[label]
        lines.append(f"{label:<20}conceded {s['conceded']} | won {s['won']} "
                     f"| total {s['total']}  (n={s['games']})")
    for cut in ("by_result", "by_half_time_state"):
        lines.append(f"-- {cut} --")
        for label, s in agg[cut].items():
            lines.append(f"  {label:<18}conceded {s['conceded']} | won {s['won']} "
                         f"| total {s['total']}  (n={s['games']})")
    v = agg["verdict"]
    lines += ["", f"VERDICT [{v['direction']}] {v['says']}"]
    return "\n".join(lines)
