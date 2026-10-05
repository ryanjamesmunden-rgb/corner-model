"""Offline: an attack in form against a defence that does not concede away.

THE ANGLE, AND IT IS NOT THE MISMATCH BOARD'S. The mismatch screen looks for an attack
against a defence that leaks CORNERS — a bad defence, found by its corner column. This
looks for the opposite kind of opponent: one whose AWAY GOALS-AGAINST column is almost
empty, met by a side scoring freely at home.

The claim is mechanical rather than statistical. A side that concedes nothing away is
usually not doing it by keeping the ball; it is doing it by putting bodies in front of
shots, clearing, and conceding the corner instead of the chance. Pressure that does not
become goals has to go somewhere, and a corner is where a blocked shot ends up. So the
fixture to want is a team in scoring form against a defence good enough to survive that
pressure — not one bad enough to be cut open, which ends the pressure early.

  Reading v Bradford, the example this was written from: Reading 3+ corners in 9 of 9
  and 12 goals in 4 home games, against a Bradford side that had conceded 2 in 3 away.

WHAT THIS IS NOT. It is not a card and must never be posted as one. Nothing here carries
a price, and every number on it is a venue split over a handful of games this season,
which is the thinnest kind of evidence this repo deals in — see THIN_GAMES. It is a list
of fixtures to go and look at.

AND IT IS NOT MEASURED. The ordering below puts the interesting rows near the top and is
not a confidence. measure_chase_board.py tried four orderings against a shuffled control
and could not separate any of them, and nothing here has been through that yet: whether
a resolute away defence actually produces MORE corners for the opponent than the model
already expects is an open question, and the column that would answer it — the model's
own lambda, printed beside each row — is here so the two can be compared by eye until it
is answered properly.

THE SAMPLE PROBLEM IS THE WHOLE PROBLEM. "Conceded 2 in 3 away games" is a rate computed
on three matches, and watchlist.py already paid for this lesson:

    "a five-game average is EXTREME by construction, so thin rows do not merely appear in
     the ranking, they lead it."

A screen that sorts by fewest goals conceded away, with no floor, returns a list of teams
that have played twice. So rows below THIN_GAMES at either venue are printed in their own
section underneath, never mixed in, and both sides' game counts ride on every line.

Reads the database only. No API calls, no writes.

Run: python press_board.py
     python press_board.py --days 7 --top 20
     python press_board.py --league eng-ch --min-scoring 1.8 --max-conceded 1.2
"""
import argparse
import asyncio
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

from server import _fixture_projections, _src, db, nb_ge

ROOT = Path(__file__).parent
load_dotenv(ROOT / ".env")

DEFAULT_DAYS = 7
DEFAULT_TOP = 20
# Goals per game at the venue, for the attacking side. Reading's example is 3.0; the
# default is deliberately below it, because a bar set at the one fixture that prompted
# the idea returns that fixture and nothing else.
DEFAULT_MIN_SCORING = 1.8
# Goals conceded per game at the opposite venue, for the opponent. Bradford's example is
# 0.67. One a game is the line between "hard to score against" and "ordinary".
DEFAULT_MAX_CONCEDED = 1.0
# Fewer than this at the venue and the row is printed apart rather than ranked. Three is
# the floor to appear at all: two games is not a rate by any reading.
THIN_GAMES = 6
MIN_GAMES = 3
# The line the run is reported at, the same rule the mismatch and chase boards use.
LINE_RULE = lambda lam: max(3, round(lam) - 1)          # noqa: E731


def venue_games(team: dict, home: bool) -> list:
    """This team's matches at one venue, newest last. The whole screen is venue-split:
    a season total hides exactly the thing being looked for, since a side can be
    resolute away and generous at home and the average says neither."""
    return [m for m in _src(team) if bool(m.get("home")) is home]


def per_game(rows: list, field: str):
    return (sum(r.get(field, 0) for r in rows) / len(rows)) if rows else None


def corner_run(rows: list, line: int) -> tuple:
    """(hits, played) at `line`+ corners over this venue's games — the run the angle is
    actually bet through. Reported, never screened on: a streak is one result from
    ending, and a screen that required one would drop the fixture the week it mattered."""
    return sum(1 for r in rows if (r.get("corners_for") or 0) >= line), len(rows)


def scan(fixtures: dict, teams_by_id: dict, min_scoring: float, max_conceded: float):
    """Every (attacking side, opponent) pair in the window that fits the shape.

    BOTH SIDES ARE TESTED, not just the home team. The example is a home side and the
    mechanism is not: a team scoring freely on the road against a defence that concedes
    nothing at home is the same fixture with the venues swapped, and screening only for
    home attacks would silently halve the board.
    """
    out = []
    for row in fixtures.values():
        fx = row.get("_fixture") or {}
        home = teams_by_id.get(fx.get("home_team_id"))
        away = teams_by_id.get(fx.get("away_team_id"))
        if not home or not away:
            continue
        for team, opp, venue in ((home, away, "home"), (away, home, "away")):
            at_home = venue == "home"
            mine = venue_games(team, at_home)
            theirs = venue_games(opp, not at_home)
            if len(mine) < MIN_GAMES or len(theirs) < MIN_GAMES:
                continue
            scoring = per_game(mine, "goals_for")
            conceded = per_game(theirs, "goals_against")
            if scoring is None or conceded is None:
                continue
            if scoring < min_scoring or conceded > max_conceded:
                continue
            lam = row["lambda_home"] if at_home else row["lambda_away"]
            line = LINE_RULE(lam)
            hits, played = corner_run(mine, line)
            out.append({
                "row": row, "team": team["name"], "opp": opp["name"], "venue": venue,
                "scoring": scoring, "scoring_games": len(mine),
                "conceded": conceded, "conceded_games": len(theirs),
                "corners": per_game(mine, "corners_for"),
                "blocked": per_game([m for m in theirs if m.get("blocked_shots_for") is not None],
                                    "blocked_shots_for"),
                "lam": lam, "line": line, "hits": hits, "played": played,
                "prob": nb_ge(line, lam),
                # THE ORDERING, AND IT IS NOT A CONFIDENCE. See the note at the top. The
                # gap is the angle restated as one number: how far a side's scoring at
                # this venue outruns what this opponent normally concedes at the other.
                "gap": scoring - conceded,
                "thin": min(len(mine), len(theirs)) < THIN_GAMES,
            })
    return sorted(out, key=lambda r: r["gap"], reverse=True)


def show(rows: list, top: int, title: str):
    print(title)
    if not rows:
        print("  nothing in the window fits the shape\n")
        return
    for i, r in enumerate(rows[:top], 1):
        row = r["row"]
        when = (row.get("date") or "")[:10]
        at = "home" if r["venue"] == "home" else "away"
        print(f"{i:2}. {when}  {row['home']} v {row['away']}   [{row['league_name']}]")
        print(f"     {r['team']} ({at}): {r['scoring']:.2f} goals/game over "
              f"{r['scoring_games']}  ·  {r['corners']:.2f} corners/game")
        print(f"     {r['opp']}: concedes {r['conceded']:.2f}/game over "
              f"{r['conceded_games']} {'away' if at == 'home' else 'home'}"
              + (f"  ·  blocks {r['blocked']:.2f} shots/game" if r["blocked"] else ""))
        model = f"     model: {r['lam']:.2f} corners for {r['team']}"
        if r["prob"] > 0:
            model += (f"  ·  {r['line']}+ {r['prob'] * 100:.1f}% "
                      f"(fair {1 / r['prob']:.2f})")
        print(model)
        print(f"     run at {r['line']}+: {r['hits']}/{r['played']} at this venue"
              f"   ·   gap {r['gap']:+.2f}")
    print()


async def run(days=DEFAULT_DAYS, top=DEFAULT_TOP, league_id=None,
              min_scoring=DEFAULT_MIN_SCORING, max_conceded=DEFAULT_MAX_CONCEDED):
    print("PRESS BOARD — an attack in form against a defence that concedes nothing away")
    print("(reads the database only; nothing here is priced, and this is not a card)\n")
    print(f"screen: scoring >= {min_scoring:.2f}/game at the venue, opponent conceding "
          f"<= {max_conceded:.2f}/game at the other, both over {MIN_GAMES}+ games")
    print(f"window: next {days} days   league={league_id or 'all'}\n")

    fixtures = await _fixture_projections(days, league_id)
    if not fixtures:
        print("no upcoming fixtures in range — run sync_real.py first")
        return

    # _fixture_projections drops the raw fixture, and the team ids are what this needs to
    # reach the venue splits. Re-read rather than change that function's contract: it has
    # two callers already and both are on the hot path of a page.
    raw = {f["fixture_id"]: f for f in await db.fixtures.find({}, {"_id": 0}).to_list(5000)}
    for fid, row in fixtures.items():
        row["_fixture"] = raw.get(fid, {})
    teams = await db.teams.find({}, {"_id": 0}).to_list(5000)
    teams_by_id = {t["team_id"]: t for t in teams}

    rows = scan(fixtures, teams_by_id, min_scoring, max_conceded)
    solid = [r for r in rows if not r["thin"]]
    thin = [r for r in rows if r["thin"]]

    print(f"{len(fixtures)} fixtures in the window, {len(rows)} fit the shape "
          f"({len(solid)} well-sampled, {len(thin)} thin)\n")
    show(solid, top, "=" * 78 + "\nWELL SAMPLED — both sides have "
         f"{THIN_GAMES}+ games at the venue\n" + "=" * 78)
    show(thin, top, "-" * 78 + f"\nTHIN — fewer than {THIN_GAMES} games behind one side. "
         "Listed so nothing is\nmissing, ranked below the rest because a short venue "
         "split produces\nEXTREME rates: these rows do not merely appear in a ranking, "
         "they lead it.\n" + "-" * 78)

    print("=" * 78)
    print("HOW TO READ IT. `gap` is the angle as one number and is an ordering, not a")
    print("confidence — nothing here has been measured against a control, unlike the")
    print("lines the model prices. The model's own projection sits on every row for")
    print("exactly that reason: where the model already has the side high, the angle and")
    print("the price agree and there is no edge in it. The rows worth a second look are")
    print("the ones where the shape is strong and the model is NOT high, because that is")
    print("where this says something the board does not.")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--days", type=int, default=DEFAULT_DAYS)
    ap.add_argument("--top", type=int, default=DEFAULT_TOP)
    ap.add_argument("--league", default=None)
    ap.add_argument("--min-scoring", type=float, default=DEFAULT_MIN_SCORING)
    ap.add_argument("--max-conceded", type=float, default=DEFAULT_MAX_CONCEDED)
    a = ap.parse_args()
    asyncio.run(run(a.days, a.top, a.league, a.min_scoring, a.max_conceded))


if __name__ == "__main__":
    main()
