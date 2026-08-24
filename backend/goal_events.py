"""Goal events: who scored, when, and what state each team spent the match in.

Unlike corners, goals ARE available with timings — `/fixtures/events` returns every
goal with its minute, scorer, assist and type. That gives two things the app has never
had:

  1. The detail you can read — scorers and minutes per match.
  2. MINUTES SPENT TRAILING, which is the proper version of the chase measure. The
     game-state test used half-time state on full-match corners, which is coarse in
     both directions: a team 1-0 down from the 10th minute and a team that conceded on
     43 minutes looked identical, and their first-half corners counted the same. This
     replaces the first half of that problem.

Pure functions only — no API, no DB — so the timeline maths is testable on its own.
"""
from typing import List, Optional

FULL_TIME = 90          # segments are accounted to 90; stoppage-time goals still count
STATE_LABELS = {-1: "trailing", 0: "level", 1: "leading"}


def parse_goal_events(events, home_id, away_id) -> List[dict]:
    """`/fixtures/events` -> the goals, sorted, as {minute, side, player, assist, kind}.

    Own goals are credited to the side that BENEFITS, since that is what moves the
    scoreline — the scorer's name is kept so the row still reads correctly."""
    goals = []
    for e in events or []:
        if str(e.get("type", "")).strip().lower() != "goal":
            continue
        detail = str(e.get("detail") or "").strip()
        if detail.lower() == "missed penalty":       # recorded as a Goal event, isn't one
            continue
        tid = ((e.get("team") or {}).get("id"))
        if tid not in (home_id, away_id):
            continue
        scoring_side = "home" if tid == home_id else "away"
        if detail.lower() == "own goal":
            scoring_side = "away" if scoring_side == "home" else "home"
        t = e.get("time") or {}
        minute = t.get("elapsed")
        if minute is None:
            continue
        goals.append({
            "minute": int(minute), "extra": t.get("extra") or 0, "side": scoring_side,
            "player": ((e.get("player") or {}).get("name")),
            "assist": ((e.get("assist") or {}).get("name")),
            "kind": detail or "Normal Goal",
            "own_goal": detail.lower() == "own goal",
        })
    goals.sort(key=lambda g: (g["minute"], g["extra"]))
    return goals


def match_state_minutes(goals: List[dict], full_time: int = FULL_TIME) -> dict:
    """How many minutes each side spent leading, level and trailing.

    Segments are clamped to `full_time`: a 90+3 winner leaves the previous state
    standing for the whole match rather than inventing extra minutes."""
    out = {side: {"leading": 0, "level": 0, "trailing": 0} for side in ("home", "away")}
    h = a = 0
    prev = 0
    for g in list(goals) + [{"minute": full_time, "side": None}]:
        at = max(0, min(int(g["minute"]), full_time))
        seg = max(0, at - prev)
        if seg:
            state = (h > a) - (h < a)
            out["home"][STATE_LABELS[state]] += seg
            out["away"][STATE_LABELS[-state]] += seg
        if g["side"] == "home":
            h += 1
        elif g["side"] == "away":
            a += 1
        prev = max(prev, at)
    return out


def first_goal_minute(goals: List[dict], side: str) -> Optional[int]:
    for g in goals:
        if g["side"] == side:
            return g["minute"]
    return None


def goal_summary(goals: List[dict]) -> dict:
    """Everything derived from one match's goals, ready to store per fixture."""
    mins = match_state_minutes(goals)
    opener = goals[0] if goals else None
    return {
        "goals": goals,
        "home_minutes": mins["home"], "away_minutes": mins["away"],
        "home_first_goal_min": first_goal_minute(goals, "home"),
        "away_first_goal_min": first_goal_minute(goals, "away"),
        "first_scorer_side": opener["side"] if opener else None,
        "first_goal_min": opener["minute"] if opener else None,
    }


def team_goal_sample(summary: dict, side: str) -> dict:
    """The per-team-per-match keys stored on team.real_matches."""
    other = "away" if side == "home" else "home"
    mins = summary[f"{side}_minutes"]
    return {
        "minutes_trailing": mins["trailing"],
        "minutes_level": mins["level"],
        "minutes_leading": mins["leading"],
        "first_goal_min": summary[f"{side}_first_goal_min"],
        "opp_first_goal_min": summary[f"{other}_first_goal_min"],
        "scored_first": (summary["first_scorer_side"] == side) if summary["first_scorer_side"] else None,
        "scorers": [{"minute": g["minute"], "player": g["player"], "kind": g["kind"]}
                    for g in summary["goals"] if g["side"] == side],
    }
