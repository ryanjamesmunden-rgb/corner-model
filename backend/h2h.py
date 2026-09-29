"""Previous meetings between the two sides of a fixture: score, corners, and who is unbeaten.

WHERE THE DATA COMES FROM, AND WHY IT COSTS NOTHING. db.fixture_stats is the one
collection in this app that is never deleted. Every other collection is swept and
rebuilt — sync_real deletes and re-inserts teams and fixtures on every run, and boot
cleanup drops anything belonging to an unmanaged league — but fixture_stats is an upsert
cache built on the fact that a finished match never changes its score. It has been
accumulating since the app started, it already carries both provider team ids, the
kick-off date, both corner counts and both goal counts, and nothing reads it for this.

So head-to-head needs no API call and no new sync: it is a query against data that has
been sitting there the whole time.

HOW DEEP IT GOES IS NOT A DESIGN DECISION, which matters when reading an empty panel.
The sync fetches statistics for the most recent STATS_CAP (250) finished fixtures per
league per run, plus the previous season when the current one is thin. Anything older
than the app's own install date was never fetched and is not there. Two sides who last
met three seasons ago will show NOTHING, and that is an absence of history in the cache,
not evidence they have never played. The payload says which it is (`window` below) so
the page can word it honestly instead of implying a first-ever meeting.

CUP TIES FALL OUT OF THIS FOR FREE. The query is on provider team ids, not on the
competition, so Arsenal v Bayern surfaces their European meetings without knowing that a
cup is what it is looking at. Each row carries the league it was played in for the same
reason: "drew 1-1" means something different in a league game and a second leg.
"""
from typing import Dict, List, Optional

# How many meetings to hand the page. Ten is already more than two sides in the cache
# window will usually have, and the panel reads newest-first, so the cap only ever bites
# on a pairing with unusual history.
MAX_MEETINGS = 10

# A run shorter than this is not a run. Two games unbeaten is a coincidence with a label
# on it, and putting it next to a genuine five would make both look the same.
MIN_UNBEATEN_RUN = 3


def _int(value) -> Optional[int]:
    """Provider counts arrive as ints, and as None on anything never backfilled."""
    if value is None or isinstance(value, bool):
        return None
    return value if isinstance(value, int) else None


def meeting_row(doc: dict, home_api_id: int) -> dict:
    """One stored fixture, re-oriented to the CURRENT fixture's home side.

    Every number in the row answers "what did the team who is at home THIS time do",
    regardless of which end of that older match they were. `venue` says where it was
    played, because a 7-4 corner win at home and the same scoreline away are different
    pieces of evidence and the row must not flatten them into one.
    """
    at_home = doc.get("home_id") == home_api_id
    hg, ag = _int(doc.get("home_goals")), _int(doc.get("away_goals"))
    hc, ac = _int(doc.get("home_corners")), _int(doc.get("away_corners"))

    goals_for, goals_against = (hg, ag) if at_home else (ag, hg)
    corners_for, corners_against = (hc, ac) if at_home else (ac, hc)

    # GRADED SEPARATELY FROM SCORED. Corners are guaranteed — sync_real refuses to store a
    # fixture whose corners are null — but goals were added to the cache later and older
    # rows can still carry None until the backfill reaches them. A meeting we cannot
    # decide the result of must say so rather than defaulting to a draw, which would read
    # as "unbeaten" and quietly inflate every run below it.
    graded = goals_for is not None and goals_against is not None
    if not graded:
        result = None
    elif goals_for > goals_against:
        result = "home_team"
    elif goals_for < goals_against:
        result = "away_team"
    else:
        result = "draw"

    total = None if corners_for is None or corners_against is None else corners_for + corners_against
    return {
        "date": doc.get("date"),
        "league_id": doc.get("league_id"),
        # Where the CURRENT fixture's home side played this one.
        "venue": "home" if at_home else "away",
        "goals_home_team": goals_for,
        "goals_away_team": goals_against,
        "corners_home_team": corners_for,
        "corners_away_team": corners_against,
        "total_corners": total,
        "result": result,
        "graded": graded,
    }


def meetings(docs: List[dict], home_api_id: int, limit: int = MAX_MEETINGS,
             league_names: Optional[Dict[str, str]] = None) -> List[dict]:
    """Every stored meeting, newest first, oriented to the current fixture's home side.

    `league_names` turns the stored id into what the competition is called. A row with no
    name falls back to the id rather than to an empty string, so an unmapped competition
    shows as `ucl` — visibly a gap — instead of a blank cell that reads as "no
    competition" and looks deliberate.
    """
    rows = [meeting_row(d, home_api_id) for d in docs if d.get("date")]
    for r in rows:
        r["league_name"] = (league_names or {}).get(r["league_id"]) or r["league_id"]
    rows.sort(key=lambda r: r["date"], reverse=True)
    return rows[:limit]


def unbeaten_run(rows: List[dict], side: str, venue: Optional[str] = None) -> int:
    """How many of the most recent meetings this side has gone without losing.

    `side` is "home_team" or "away_team" — the current fixture's sides, not the older
    match's. `venue` optionally restricts to meetings played at the current home side's
    ground ("home") or the away side's ("away").

    AN UNGRADED MEETING STOPS THE COUNT. The alternative — skipping it and carrying on —
    would produce "unbeaten in their last 5 meetings" spanning a game whose result is not
    in the database. The run would be a claim about matches nobody checked, and it would
    be indistinguishable on the page from one that was checked. So a missing result ends
    the run where it sits, which understates rather than invents.
    """
    loser = "away_team" if side == "home_team" else "home_team"
    run = 0
    for r in rows:
        if venue and r["venue"] != venue:
            continue
        if not r["graded"] or r["result"] == loser:
            break
        run += 1
    return run


def _venue_for(side: str, split: str) -> Optional[str]:
    """Which meetings count as this side's home games.

    THE TWO SIDES SHARE ONE AXIS, which is the trap in reusing the usual home/away split
    here. In a league table "home" means a different set of matches for every team; in a
    head-to-head there is only one pairing, so the home side's home meetings are exactly
    the away side's away meetings. Deriving the venue from the side rather than reading
    `split` literally is what keeps "Chelsea unbeaten in 3 away" pointing at the games
    Chelsea were actually the visitors in.
    """
    if split == "overall":
        return None
    if side == "home_team":
        return "home" if split == "home" else "away"
    return "away" if split == "home" else "home"


def runs_for(rows: List[dict], side: str, min_run: int = MIN_UNBEATEN_RUN) -> List[dict]:
    """The unbeaten runs worth printing for one side, longest first.

    Only splits that actually reach `min_run` come back, so the page shows a fact or
    shows nothing — never "unbeaten in 1", which is a result wearing a run's clothes.
    """
    out = []
    for split in ("overall", "home", "away"):
        venue = _venue_for(side, split)
        run = unbeaten_run(rows, side, venue)
        played = len([r for r in rows if venue is None or r["venue"] == venue])
        if run >= min_run:
            out.append({"split": split, "run": run, "played": played})
    out.sort(key=lambda r: r["run"], reverse=True)
    return out


def corner_totals(rows: List[dict]) -> Optional[dict]:
    """What these two produce together, over the meetings on file.

    The whole reason a corner site shows a head-to-head: not who won, but whether this
    pairing is a scrappy 7 or an open 13. Averages only, and always with the count they
    were taken over, because three meetings is a hint and not a rate.
    """
    scored = [r for r in rows if r["total_corners"] is not None]
    if not scored:
        return None
    n = len(scored)
    return {
        "played": n,
        "avg_total": round(sum(r["total_corners"] for r in scored) / n, 2),
        "avg_home_team": round(sum(r["corners_home_team"] for r in scored) / n, 2),
        "avg_away_team": round(sum(r["corners_away_team"] for r in scored) / n, 2),
        "highest": max(r["total_corners"] for r in scored),
        "lowest": min(r["total_corners"] for r in scored),
    }


def build(docs: List[dict], home_api_id: int, home_name: str, away_name: str,
          limit: int = MAX_MEETINGS, min_run: int = MIN_UNBEATEN_RUN,
          league_names: Optional[Dict[str, str]] = None) -> dict:
    """The head-to-head panel's whole payload, from stored fixtures.

    `window` is the honest half of an empty panel: no rows here means the cache holds no
    meeting between these two, which is NOT the same claim as "they have never met". See
    the note at the top of this file.
    """
    rows = meetings(docs, home_api_id, limit, league_names)
    return {
        "home_name": home_name,
        "away_name": away_name,
        "meetings": rows,
        "corners": corner_totals(rows),
        "unbeaten": {
            "home_team": runs_for(rows, "home_team", min_run),
            "away_team": runs_for(rows, "away_team", min_run),
        },
        "record": _record(rows),
        # What the absence of rows means, said in the payload so the page does not have to
        # guess and cannot word it as "first meeting".
        "window": "Meetings the results cache has on file — it goes back as far as this "
                  "site has been syncing the competition, not to the start of time.",
    }


def _record(rows: List[dict]) -> dict:
    """Won / drawn / lost from the current home side's point of view, graded rows only."""
    graded = [r for r in rows if r["graded"]]
    return {
        "played": len(graded),
        "home_wins": sum(1 for r in graded if r["result"] == "home_team"),
        "draws": sum(1 for r in graded if r["result"] == "draw"),
        "away_wins": sum(1 for r in graded if r["result"] == "away_team"),
        # Rows we have corners for but no score. Named rather than dropped, so a panel
        # showing six meetings and a record reading "4 played" explains itself.
        "ungraded": len(rows) - len(graded),
    }


def query(home_api_id, away_api_id) -> Optional[Dict]:
    """The db.fixture_stats filter for every meeting between two sides, either way round.

    Returns None when either id is missing, which is the case for a synthesized fixture —
    those carry no provider team id and have no history to look up. A None here means the
    caller must skip the query entirely rather than run one that matches everything.
    """
    if not isinstance(home_api_id, int) or not isinstance(away_api_id, int):
        return None
    return {"$or": [{"home_id": home_api_id, "away_id": away_api_id},
                    {"home_id": away_api_id, "away_id": home_api_id}]}
