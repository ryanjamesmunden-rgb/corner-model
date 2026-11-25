"""Each side's record IN THE COMPETITION IT IS PLAYING, for a cup tie's fixture page.

THE COMPLAINT THIS ANSWERS, in one line: open Inter v VfB Stuttgart in the Champions
League and the page shows you Atalanta, Como, AC Milan, Venezia — Serie A, every one.

That is not a bug. `cups.py` explains why: a cup has no teams of its own, so its fixtures
point at the team documents the domestic syncs built, and every projection on the page is
computed from the side's full domestic season. Twenty games of Serie A is a far better
basis for a lambda than four of anything. Which is right for the MODEL and wrong for the
page, because the reader is not asking the model's question. They are asking "how has
this side played in THIS competition", and the answer was sitting unread in
db.fixtures_played the whole time: the cup sync stores every tie it syncs with both
corner counts, keyed by the same domestic team ids the fixture uses.

SO THIS ADDS A VIEW, IT DOES NOT REPLACE ONE. The competition's own games go at the top,
with their count beside them, and the domestic form stays underneath. Two reasons, and
the second is the one that matters:

  - THE SAMPLE IS TINY AND SOMETIMES ZERO. A European league phase is eight games a side
    across four months, and the played store only keeps what the sync re-inserts. Right
    now that is one game for most sides. Replacing forty domestic games with one European
    one would be a worse page that happened to answer the question asked.
  - BOTH ARE TRUE AT ONCE. "Inter win six corners a game in Serie A" and "Inter won four
    in their last European game" are not in competition; the first is the larger sample
    and the second is the closer match. A page that shows one and hides the other is
    choosing for the reader, and the count is what lets them choose.

EVERY FIGURE CARRIES ITS DENOMINATOR, which on a sample this thin is the whole point. A
record of one is printed as a record of one, never as a rate.
"""
from typing import Dict, Iterable, List, Optional


def _side(game: dict, team_id: str) -> Optional[str]:
    """"home", "away", or None when this team did not play in this game."""
    if game.get("home_team_id") == team_id:
        return "home"
    if game.get("away_team_id") == team_id:
        return "away"
    return None


def games_for(team_id: str, played: Iterable[dict], limit: int = 10) -> List[dict]:
    """This side's games in one competition, newest first, from its played fixtures.

    Shaped like the `recent` rows the fixture page already draws — `won` is corners won
    BY THIS TEAM whichever end of the fixture it was at — so the page needs no second way
    of rendering a game.

    A TIE WITH NO CORNER COUNT IS LEFT OUT ENTIRELY. The cup sync spends one statistics
    call per tie and stores `corners_known: False` when it has not made that call yet, so
    a game with no corners on it is not a goalless one — it is one nobody has fetched. On
    a list this short a single phantom zero would move the average more than any real
    result on it.
    """
    out = []
    for g in played or []:
        side = _side(g, team_id)
        if side is None or not g.get("corners_known"):
            continue
        mine, theirs = ("home", "away") if side == "home" else ("away", "home")
        won, conceded = g.get(f"{mine}_corners"), g.get(f"{theirs}_corners")
        if won is None or conceded is None:
            continue
        out.append({
            "fixture_id": g.get("fixture_id"),
            "date": g.get("date"),
            "round": g.get("round"),
            "opponent": g.get(f"{theirs}_name"),
            "home": side == "home",
            "won": won, "conceded": conceded, "total": won + conceded,
            "gf": g.get(f"{mine}_goals"), "ga": g.get(f"{theirs}_goals"),
            # FT, AET or PEN. On a knockout tie "it went to extra time" is thirty more
            # minutes of corners and the one thing a count alone cannot show.
            "finished_as": g.get("finished_as"),
        })
    out.sort(key=lambda r: str(r.get("date") or ""), reverse=True)
    return out[:limit]


def summarise(games: List[dict]) -> Optional[Dict[str, object]]:
    """Totals over those games, or None when there are none.

    NONE RATHER THAN ZEROES, because "this side has not played a game we hold a corner
    count for" and "this side averages nothing" are different statements and only one of
    them is true. A caller that got {"games": 0, "avg_won": 0.0} would print the second.
    """
    if not games:
        return None
    won = [g["won"] for g in games]
    conceded = [g["conceded"] for g in games]
    return {
        "games": len(games),
        "avg_won": round(sum(won) / len(won), 2),
        "avg_conceded": round(sum(conceded) / len(conceded), 2),
        "avg_total": round(sum(g["total"] for g in games) / len(games), 2),
        "low": min(won), "high": max(won),
    }


def for_fixture(fixture: dict, played: Iterable[dict],
                limit: int = 10) -> Dict[str, Optional[dict]]:
    """Both sides' competition records, keyed "home" and "away".

    Returns `{"home": None, "away": None}` for a fixture that is not a cup tie, so the
    caller has one shape to handle rather than a branch.
    """
    if not fixture or not fixture.get("cup"):
        return {"home": None, "away": None}
    rows = list(played or [])
    out = {}
    for slot, key in (("home", "home_team_id"), ("away", "away_team_id")):
        tid = fixture.get(key)
        games = games_for(tid, rows, limit) if tid else []
        out[slot] = {"games": games, "summary": summarise(games)} if games else None
    return out
