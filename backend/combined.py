"""The combined board: Quick Scan, Streaks and Perfect Games read together.

Each of the three boards answers a different question about the same team:

  - Quick Scan (mismatches): does this side win corners at pace against a defence that
    gives them up? That is the fixture-specific projection, and its lambda is what the
    price here is worked out from.
  - Streaks: has the side actually been clearing a line, game after game?
  - Perfect Games: do the run, the matchup and the opponent's own concession record all
    point the same way?

A team that turns up on more than one board for the SAME upcoming fixture is worth a
harder look. They are not independent (all three lean on how many corners the team
wins), so the count of boards is a reason to look, not a probability.

THE ANGLE IS ALWAYS A 5+ OR 6+ TEAM CORNERS LINE, because that is the bet being placed.
The streak and mismatch lines are reported beside it rather than replacing it.

THE FLOOR IS SHOWN BECAUSE IT IS THE "WHATEVER THE SCORE" TEST. The lowest count in the
run says whether the side kept winning corners when it was ahead, level or behind; a 6+
run with a floor of 1 is a different thing from one with a floor of 6.

This module holds the pure merge so it can be tested without a database. The endpoint in
server.py gathers the three boards, the teams and the prices, and hands them in.
"""
from typing import Callable, Dict, Iterable, List, Optional

COMBINED_LINES = (5, 6)
BOARD_NAMES = ("quick_scan", "streaks", "perfect_games")
# Below this many games a team's averages are too thin to lean on.
DEFAULT_MIN_SAMPLES = 15
# The opponent's venue record (what Quick Scan's "concedes" figure is built from).
# Under ten games it is flagged rather than dropped, so the reader can decide.
DEFAULT_MIN_OPP_GAMES = 10


def _fixture_id(row: dict) -> Optional[str]:
    return (row.get("next_fixture") or {}).get("fixture_id")


def _venue(row: dict) -> str:
    return "home" if (row.get("next_fixture") or {}).get("is_home") else "away"


def _best_streak(runs: List[dict], venue: str) -> Optional[dict]:
    """The run that speaks to THIS fixture: the venue split first, then overall.

    A home run says nothing about an away game, so the matching venue wins even when
    the overall run is longer."""
    by_side = {r.get("side"): r for r in runs}
    return by_side.get(venue) or by_side.get("overall")


def _streak_summary(run: Optional[dict]) -> Optional[dict]:
    if not run:
        return None
    return {"side": run.get("side"), "line": run.get("line"),
            "line_label": run.get("line_label"), "hits": run.get("hits"),
            "settled": run.get("settled"), "avg": run.get("avg"),
            "floor": run.get("min_won"),
            "length": (run.get("streak") or {}).get("length", 0),
            "recent": [g.get("corners") for g in (run.get("recent") or [])]}


def _angle(line: int, lam: Optional[float], venue: str, odds: Dict[str, float],
           prob_ge: Callable[[int, float], float]) -> Optional[dict]:
    if not lam:
        return None
    p = prob_ge(line, lam)
    key = f"{venue}_over_{line - 0.5}"
    book = odds.get(key)
    ev = round((book * p - 1) * 100, 1) if book else None
    return {"line": line, "label": f"{line}+", "market_key": key,
            "prob": round(p * 100, 1), "fair_odds": round(1 / p, 2) if p > 0 else None,
            "book_odds": book, "ev": ev}


def combine_boards(mismatches: Iterable[dict], runs: Iterable[dict],
                   perfect: Iterable[dict], teams_by_id: Dict[str, dict],
                   odds_by_fixture: Dict[str, Dict[str, float]],
                   prob_ge: Callable[[int, float], float],
                   min_samples: int = DEFAULT_MIN_SAMPLES,
                   min_opp_games: int = DEFAULT_MIN_OPP_GAMES,
                   min_boards: int = 2, lines: Iterable[int] = COMBINED_LINES) -> List[dict]:
    """Merge the three boards on (team, fixture) and price a 5+/6+ angle for each.

    `runs` is every streak row across the three venue tabs (each carries `side`).
    `prob_ge(k, lam)` is the model's P(corners >= k); passed in so this stays pure.
    """
    rows: Dict[tuple, dict] = {}

    def slot(row: dict) -> Optional[dict]:
        fid = _fixture_id(row)
        if not fid or not row.get("team_id"):
            return None
        key = (row["team_id"], fid)
        if key not in rows:
            rows[key] = {"base": row, "quick_scan": None, "runs": [], "perfect": None}
        return rows[key]

    for m in mismatches:
        s = slot(m)
        if s is not None:
            s["quick_scan"] = m
    for r in runs:
        s = slot(r)
        if s is not None:
            s["runs"].append(r)
    for p in perfect:
        s = slot(p)
        if s is not None:
            s["perfect"] = p

    out = []
    for (team_id, fid), s in rows.items():
        boards = [name for name, present in (("quick_scan", s["quick_scan"]),
                                             ("streaks", s["runs"]),
                                             ("perfect_games", s["perfect"])) if present]
        if len(boards) < min_boards:
            continue
        base = s["base"]
        nf = base["next_fixture"]
        venue = _venue(base)
        team = teams_by_id.get(team_id) or {}
        opp = teams_by_id.get(nf.get("opponent_team_id")) or {}
        samples = team.get("real_samples", base.get("real_samples", 0)) or 0
        if samples < min_samples:
            continue
        opp_samples = opp.get("real_samples", 0) or 0

        qs = s["quick_scan"]
        # The fixture projection. Quick Scan carries it; when the team is only on the
        # streak boards, the streak's own projection is for this same fixture.
        lam = (qs or {}).get("lambda")
        if lam is None:
            for r in s["runs"]:
                lam = (r.get("projection") or {}).get("lambda")
                if lam:
                    break
        odds = odds_by_fixture.get(fid) or {}
        angles = [a for a in (_angle(line, lam, venue, odds, prob_ge) for line in lines) if a]
        priced = [a for a in angles if a["ev"] is not None]
        best = max(priced, key=lambda a: a["ev"]) if priced else None

        opp_games = ((qs or {}).get("evidence") or {}).get("opponent", {}).get("games")
        warnings = []
        if opp_samples and opp_samples < min_samples:
            warnings.append(f"opponent has only {opp_samples} games")
        if opp_games is not None and opp_games < min_opp_games:
            warnings.append(f"opponent's venue record is {opp_games} games")
        if not priced:
            warnings.append("no bookmaker price for 5+/6+ yet")
        # Promoted / relegated sides: whichever board the row came from carries the flag.
        mine = next((r.get("league_change") for r in (qs, *s["runs"], s["perfect"])
                     if r and r.get("league_change")), None)
        theirs = next((r.get("opponent_league_change") for r in (qs, *s["runs"], s["perfect"])
                       if r and r.get("opponent_league_change")), None)
        if mine:
            warnings.append(f"{base.get('name')} {mine['label']}: price less reliable")
        if theirs:
            warnings.append(f"{nf.get('opponent')} {theirs['label']}: price less reliable")

        run = _best_streak(s["runs"], venue)
        perfect_row = s["perfect"]
        out.append({
            "team_id": team_id, "name": base.get("name"),
            "league_id": base.get("league_id"), "league_name": base.get("league_name"),
            "tier": base.get("tier"), "next_fixture": nf, "venue": venue,
            "boards": boards, "board_count": len(boards),
            "samples": samples, "opponent_samples": opp_samples,
            "quick_scan": None if not qs else {
                "team_for": qs.get("team_for"), "opp_conceded": qs.get("opp_conceded"),
                "lambda": qs.get("lambda"), "line": qs.get("line"),
                "prob": qs.get("prob"), "fair_odds": qs.get("fair_odds"),
                "opponent_venue_games": opp_games},
            "streak": _streak_summary(run),
            "perfect": None if not perfect_row else {
                "streak": perfect_row.get("streak"),
                "opp_leak": perfect_row.get("opp_leak")},
            "league_change": mine, "opponent_league_change": theirs,
            "lambda": lam, "angles": angles, "best": best,
            "value": bool(best and best["ev"] > 0),
            "warnings": warnings,
        })

    # Value first, established sides before new ones, then how many boards agree, then the size of the edge, then kick-off.
    # Promoted / relegated games sink below established ones at the same value.
    out.sort(key=lambda r: (not r["value"],
                            bool(r["league_change"] or r["opponent_league_change"]),
                            -r["board_count"],
                            -((r["best"] or {}).get("ev") or -999),
                            r["next_fixture"].get("date") or ""))
    return out
