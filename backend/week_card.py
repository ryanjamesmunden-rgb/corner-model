"""One card per fixture: both sides, the line to back, the price, and the run behind it.

WHAT THIS IS FOR. Every other board here is TEAM-shaped — one row per side, sorted by
how good that side looks. That answers "who is in form". It does not answer the question
somebody actually sits down with on a Monday night, which is "what is on this week, and
for each game, what is the bet and why". A game has two sides and a total, and reading
three boards to assemble one fixture by hand is what this replaces.

So the unit here is the FIXTURE, with both sides side by side, exactly the way a card is
written out on paper: left team, its line and price; right team, its line and price; the
match total underneath if there is one.

THE RUN AND THE LINE MUST BE THE SAME LINE, and this is the whole reason this file is
not twenty lines long. A side can have a 5+ run of nine in ten and a priced 6+ rung with
a bigger edge. Printing "6+ at 1.73" over "9/10" reads as a 6+ record and is not one —
the 9/10 belongs to 5+. So the pick PREFERS the rung at the line the run is actually on,
and when it cannot have that, the run is labelled with its own line and `run_matches_pick`
is false, so the card can say so rather than imply agreement. A stat that backs a
different bet than the one printed beside it is worse than no stat.

CREDIBILITY BEFORE SIZE, the same rule the value board sorts by. The biggest edge on a
side is very often the model's worst error on that side, and a card is read as a
recommendation in a way a ranked board is not.

WHAT IS NOT HERE, said plainly because the card looks complete:
  - LEAGUE POSITION AND WHAT IS AT STAKE. "Who needs to win", a relegation six-pointer, a
    dead rubber in May — none of it is in this database. There are corner tables, not
    points tables. The game-state verdict answers the part that has been measured (will
    this side be chasing, or sitting on a lead) and says nothing about the table.
  - A VERDICT ON THE CARD AS A WHOLE. Two sides and a total are three bets, not a treble,
    and nothing here combines them.
"""
from typing import Dict, Iterable, List, Optional

# home and away are the two team lines; total is the match line written underneath.
SIDE_GROUPS = ("home", "away")
TOTAL_GROUP = "total"

# Lower is more believable — the same order the value board ranks by.
DEFAULT_CREDIBILITY_ORDER = {"credible": 0, "stretch": 1, "outlier": 2, "implausible": 3}

# A rung this far past the market is shown, never led with. `implausible` is the band the
# value board already demotes; leading a card with one would put the model's worst error
# at the top of the page under a price somebody might take.
UNLEADABLE = "implausible"


def _priced(rung: dict) -> bool:
    return bool(rung.get("book_odds")) and rung.get("ev") is not None


def _rank(rung: dict, order: Dict[str, int]) -> tuple:
    """Credibility first, then the size of the edge. Lower sorts first."""
    return (order.get(rung.get("credibility"), 0),
            -(rung["ev"] if rung.get("ev") is not None else -999))


def pick_rung(ladder: Iterable[dict], group: str, run_line: Optional[float] = None,
              order: Optional[Dict[str, int]] = None) -> Optional[dict]:
    """The rung to lead with for one side of a fixture.

    In order of preference:
      1. a priced, leadable rung AT THE RUN'S OWN LINE — the stat and the bet agree
      2. the best priced leadable rung, by credibility then edge
      3. the best priced rung at all, even an implausible one, so a broken price is
         visible on the card rather than silently swapped for a quieter one
      4. an unpriced rung, which carries the model's fair price and no edge

    Returns None when the side has no rung at all.
    """
    order = order or DEFAULT_CREDIBILITY_ORDER
    rungs = [r for r in (ladder or []) if r and r.get("group") == group]
    if not rungs:
        return None
    priced = [r for r in rungs if _priced(r)]
    leadable = [r for r in priced if r.get("credibility") != UNLEADABLE]

    if run_line is not None:
        at_run = [r for r in leadable if r.get("line") == run_line]
        if at_run:
            return sorted(at_run, key=lambda r: _rank(r, order))[0]
    for pool in (leadable, priced):
        if pool:
            return sorted(pool, key=lambda r: _rank(r, order))[0]
    # Nothing quoted. The fair price is still worth printing — it is what the model
    # thinks the bet is worth, and "no price yet" is a fact about the book, not the bet.
    unpriced = [r for r in rungs if r.get("fair_odds")]
    if not unpriced:
        return None
    return sorted(unpriced, key=lambda r: -(r.get("prob") or 0))[0]


def side_card(name: str, team_id: Optional[str], group: str, ladder: Iterable[dict],
              board_row: Optional[dict] = None, game_state: Optional[dict] = None,
              order: Optional[Dict[str, int]] = None) -> dict:
    """One half of a card: the team, its line, its price, its run and its game state.

    `board_row` is the merged Quick Scan / Streaks / Perfect Games row for this team and
    this fixture, or None when the side is on no board — which is most sides, and is why
    a card can be mostly empty and still worth drawing.
    """
    run = (board_row or {}).get("streak") or None
    run_line = run.get("line") if run else None
    pick = pick_rung(ladder, group, run_line, order)
    return {
        "name": name,
        "team_id": team_id,
        "venue": group,
        "pick": pick,
        "run": run,
        # SAID OUT LOUD, never left to the reader to notice. False means the run printed
        # on this card is a record at a DIFFERENT line from the bet printed above it.
        "run_matches_pick": bool(run and pick and run.get("line") == pick.get("line")),
        "boards": list((board_row or {}).get("boards") or []),
        "warnings": list((board_row or {}).get("warnings") or []),
        "game_state": game_state,
    }


def build_card(row: dict, board_rows: Dict[str, dict],
               states: Optional[Dict[str, dict]] = None,
               order: Optional[Dict[str, int]] = None) -> dict:
    """One fixture's card from a value-board row carrying its full ladder.

    `board_rows` maps "home"/"away" to that side's merged board row, if any.
    `states` maps "home"/"away" to that side's game-state verdict, if any.
    """
    states = states or {}
    ladder = row.get("ladder") or []
    sides = {}
    for group, name_key, id_key in (("home", "home_name", "home_team_id"),
                                    ("away", "away_name", "away_team_id")):
        sides[group] = side_card(row.get(name_key) or "", row.get(id_key), group, ladder,
                                 board_rows.get(group), states.get(group), order)
    total = pick_rung(ladder, TOTAL_GROUP, None, order)
    # WHAT MAKES THE CARD WORTH OPENING, counted here so the page can sort and the reader
    # can skim: a side with a run behind it is a different proposition from a side with
    # only a price. Not a score — two of these is not twice as good as one.
    runs = sum(1 for s in sides.values() if s["run"])
    picks = sum(1 for s in sides.values() if s["pick"])
    return {
        "fixture_id": row.get("fixture_id"),
        "date": row.get("date"),
        "round": row.get("round"),
        # WHAT HAPPENED, on a card for a day that has been played. None while the game is
        # still to come. A card that vanished at kick-off was the complaint this answers:
        # the day you most want to look at a card is the day after.
        "result": row.get("result"),
        "league_id": row.get("league_id"),
        "league_name": row.get("league_name"),
        "tier": row.get("tier"),
        "status": row.get("status"),
        "note": row.get("note"),
        "lambda_total": row.get("lambda_total"),
        "confidence": row.get("confidence"),
        "home": sides["home"],
        "away": sides["away"],
        "total": total,
        "run_count": runs,
        "pick_count": picks,
        "boards": sorted({b for s in sides.values() for b in s["boards"]}),
    }


def settle_card(card: dict, settle) -> dict:
    """Attach what happened to each priced pick on a card whose game has been played.

    `settle(market_key)` returns the settlement for that key, or None — passed in so this
    module still needs no database and no second copy of the grading rules.

    THE MATCH LINE IS SETTLED TOO, and so is a side whose pick was never priced: the
    model's fair price on an unquoted rung is still a claim about the game, and whether it
    would have landed is exactly what a week's review is for. What it cannot have is a
    return, because there was no price to return at.
    """
    if not card.get("result"):
        return card
    for slot in ("home", "away"):
        side = card.get(slot) or {}
        pick = side.get("pick")
        if pick and pick.get("key"):
            got = settle(pick["key"])
            if got:
                pick["result"] = got["result"]
                pick["actual"] = got["value"]
    total = card.get("total")
    if total and total.get("key"):
        got = settle(total["key"])
        if got:
            total["result"] = got["result"]
            total["actual"] = got["value"]
    picks = [p for p in (((card.get("home") or {}).get("pick")),
                         ((card.get("away") or {}).get("pick")),
                         card.get("total")) if p and p.get("result")]
    card["settled"] = len(picks)
    card["landed"] = sum(1 for p in picks if p["result"] == "won")
    return card


def card_sort_key(card: dict) -> tuple:
    """Kick-off order. A card is a diary entry, not a ranking.

    The boards already rank by edge, and this view exists to be read down the day in the
    order the games are played — which is how the card it replaces was written by hand.
    """
    return (card.get("date") or "", card.get("league_name") or "",
            (card.get("home") or {}).get("name") or "")


def build_cards(rows: Iterable[dict], board_rows: Iterable[dict],
                states_for=None, order: Optional[Dict[str, int]] = None) -> List[dict]:
    """Every fixture's card, in kick-off order.

    `rows` are value-board rows with `ladder=True`. `board_rows` are merged board rows
    keyed by team and fixture internally. `states_for(row, group)` returns that side's
    game-state verdict, or None — passed in so this module needs no database.
    """
    by_team_fixture: Dict[tuple, dict] = {}
    for b in board_rows or []:
        fid = (b.get("next_fixture") or {}).get("fixture_id")
        if fid and b.get("team_id"):
            by_team_fixture[(b["team_id"], fid)] = b

    out = []
    for row in rows or []:
        fid = row.get("fixture_id")
        mine, states = {}, {}
        for group, id_key in (("home", "home_team_id"), ("away", "away_team_id")):
            tid = row.get(id_key)
            if tid and fid:
                found = by_team_fixture.get((tid, fid))
                if found:
                    mine[group] = found
            if states_for:
                states[group] = states_for(row, group)
        out.append(build_card(row, mine, states, order))
    out.sort(key=card_sort_key)
    return out
