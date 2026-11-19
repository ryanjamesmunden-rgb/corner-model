"""Which sides are new to their league this season: promoted, relegated, or arrived from
somewhere we do not sync.

WHY THESE ARE FLAGGED. A side that has just gone up or come down has two problems at
once. Its history in this league is only this season's games, so it is thin. And what it
did last season was done against a different standard of opponent: a promoted side that
won 7 corners a game in the Championship is not a 7-corner side in the Premier League,
and a relegated one bullying the division below is not the side its old numbers
describe. The model has no term for that, so its price on these games is less reliable
than its price on two established sides, and an edge it shows there is as likely to be
the gap as the value.

The sync stamps `new_to_league` on each team (not in last season's squad list for this
competition) and stores that list on each league as `prev_season_team_ids`. Working out
the DIRECTION needs the other leagues, which is why it is done here at read time rather
than in a single league's sync: a side new to League One is "relegated" if it was in the
Championship's list last season and "promoted" if it was in League Two's.
"""
from typing import Dict, Iterable, Optional

LABELS = {"promoted": "newly promoted", "relegated": "newly relegated",
          "new": "new to this league"}


def change_map(teams: Iterable[dict], leagues: Iterable[dict]) -> Dict[str, dict]:
    """{team_id: {"status", "label", "from_league"}} for every side new to its league."""
    leagues = list(leagues)
    by_id = {lg.get("league_id"): lg for lg in leagues}
    prev = {lg.get("league_id"): set(lg.get("prev_season_team_ids") or []) for lg in leagues}
    out: Dict[str, dict] = {}
    for t in teams:
        if not t.get("new_to_league"):
            continue
        own = by_id.get(t.get("league_id")) or {}
        api_id = t.get("api_team_id")
        came_from: Optional[dict] = None
        for lid, ids in prev.items():
            other = by_id.get(lid) or {}
            if (lid != own.get("league_id") and api_id in ids
                    and other.get("country") == own.get("country")):
                came_from = other
                break
        own_tier, from_tier = own.get("tier"), (came_from or {}).get("tier")
        if came_from and own_tier and from_tier:
            status = "promoted" if from_tier > own_tier else "relegated" if from_tier < own_tier else "new"
        elif own_tier == 1:
            # Nothing above a top flight to have come down from.
            status = "promoted"
        else:
            status = "new"
        out[t["team_id"]] = {"status": status, "label": LABELS[status],
                             "from_league": (came_from or {}).get("name")}
    return out


def annotate(rows: Iterable[dict], changes: Dict[str, dict]) -> None:
    """Stamp `league_change` (this side) and `opponent_league_change` (who they play) on
    board rows, in place. Rows for established sides against established sides get
    neither key, so a reader can test for presence."""
    for r in rows:
        mine = changes.get(r.get("team_id"))
        if mine:
            r["league_change"] = mine
        opp_id = (r.get("next_fixture") or {}).get("opponent_team_id")
        theirs = changes.get(opp_id) if opp_id else None
        if theirs:
            r["opponent_league_change"] = theirs


def describe(row: dict) -> Optional[str]:
    """"Molde newly promoted" / "Ipswich (opponent) newly relegated" — or None."""
    bits = []
    if row.get("league_change"):
        bits.append(f"{row.get('name', 'this side')} {row['league_change']['label']}")
    if row.get("opponent_league_change"):
        opp = (row.get("next_fixture") or {}).get("opponent") or "opponent"
        bits.append(f"{opp} {row['opponent_league_change']['label']}")
    return " · ".join(bits) or None
