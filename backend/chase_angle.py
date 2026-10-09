"""Offline: a corner side that leaks goals, against a solid winner that gives corners up.

THE ANGLE, AND IT IS NOT PRESS BOARD'S. press_board looks for an attack in form against
a defence that concedes nothing away — pressure that cannot be converted has to go
somewhere, and a blocked shot becomes a corner. This is the other mechanism entirely:

  A side that wins a lot of corners but SHIPS GOALS, meeting a side that WINS GAMES,
  keeps them out, and gives corners up. Our team spends the game behind. A team that is
  behind throws bodies forward, crosses earlier and shoots from worse positions, and all
  three produce corners against a defence already willing to concede one.

press_board wants our attack scoring. This wants our defence leaking. Same sport,
opposite premise, and the fixture lists barely overlap.

WHAT THE REPO ALREADY KNOWS ABOUT THIS IDEA, because it is not a new one here and the
history is not encouraging:

  - The chase board was built on it and names itself after it. Its "opponent scores a
    first-half goal, so our side chases" term was REMOVED after five separate tests found
    no effect from it, and the board displayed "opp scores 1H 62%" as a reason for years
    while that was false.
  - measure_chase_board.py then replayed the whole board walk-forward, scoring each
    ordering by residual — actual hit rate minus the model's own probability:
        chase_score +0.02   lambda_only +0.01   no_opp_fh +0.03   RANDOM flat
    All four are the same number and the random control came out flat, which is what
    makes that trustworthy. The ordering carried no information the model did not
    already have.

SO WHY BUILD IT. Because what was measured is not quite what this screens on. The
falsified term was a PER-GAME event rate — how often the opponent happens to score
early. This is a SEASON SHAPE: who concedes goals, who wins, who gives corners up, over
a venue split. Those are different claims and the second has not been tested. It may
well go the same way. Until somebody runs the walk-forward on it, this is a list of
fixtures to go and look at and nothing more.

IT IS THEREFORE A SCREEN, NOT A RANKING, and not a card. Nothing here is priced. The
ordering below puts the bigger corner edge near the top because that is the thing being
bet, but measure_chase_board's result applies: do not read the order as a confidence.
The model's own lambda sits on every row for exactly that reason — where the model
already has the side high, the angle and the price agree and there is no edge in it. The
rows worth a second look are the ones where the shape is strong and lambda is NOT.

THE THRESHOLDS, and where each number comes from rather than being invented:

  corner bars are LEAGUE-RELATIVE. "6+ corners a game" is a different claim in the
  Eredivisie from what it is in League Two, and _browse_margin paid for that lesson
  twice: a fixed rung is the same rung for a side winning nine a game and a side
  winning three. Both corner tests are therefore stated against the division.

  goal bars are ABSOLUTE, because goals per team per game sit near 1.35 almost
  everywhere, so a division-relative bar would add a denominator without adding a
  distinction. MAX_CONCEDED reuses press_board's own 1.0 — "the line between hard to
  score against and ordinary" — rather than inventing a second number for one idea.

  MIN_WIN_RATE is 0.45. A mid-table side wins about a third of its games; 45% at one
  venue is a side that genuinely tends to lead.

  MIN_CLEAN_SHEETS is 0.35, and it is a SEPARATE leg from the goals-conceded average
  rather than a restatement of it. A side conceding exactly one most weeks and a side
  alternating shutouts with a 2-0 both average one a game, and only the second is a
  defence you expect to keep your side off the scoreboard for ninety minutes. The
  mechanism here is our team staying behind or level and chasing, so how often they
  actually shut a team out is the question the average was standing in for.

  sample floors reuse press_board's MIN_GAMES and THIN_GAMES unchanged, for the reason
  watchlist.py gives: "a five-game average is EXTREME by construction, so thin rows do
  not merely appear in the ranking, they lead it." Thin rows print in their own section.

Reads the database only. No API calls, no writes.

Run: python chase_angle.py
     python chase_angle.py --days 3 --top 30
     python chase_angle.py --min-leaking 1.2 --min-win-rate 0.4
"""
import argparse
import asyncio
from collections import defaultdict
from pathlib import Path

from dotenv import load_dotenv

from typing import Optional

from server import _fixture_projections, _match_result, _src, db, nb_ge

ROOT = Path(__file__).parent
load_dotenv(ROOT / ".env")

DEFAULT_DAYS = 7
DEFAULT_TOP = 20

# Our side: corners won per game at the venue, as corners ABOVE what the division does.
# One clear corner a game above average is "a strong corner team" without being so
# extreme that the screen returns the two sides that prompted it.
DEFAULT_CORNER_EDGE = 1.0
# Our side: goals conceded per game at the venue. A typical side concedes about 1.35, so
# 1.5 is plainly leaky; press_board calls 1.0 or below "hard to score against".
DEFAULT_MIN_LEAKING = 1.5
# Opponent: share of games won at their venue. A mid-table side wins about a third.
DEFAULT_MIN_WIN_RATE = 0.45
# Opponent: goals conceded per game at their venue. press_board's own constant.
DEFAULT_MAX_CONCEDED = 1.0
# Opponent: share of games shut out at their venue. A DISTINCT LEG from the average
# above and not a restatement of it — see clean_sheet_rate for why the two come apart.
# A third of games is "lots of clean sheets" without being so rare that the screen only
# returns the one side in Europe doing it; a side conceding a goal a game typically
# shuts out somewhere between a third and a half.
DEFAULT_MIN_CLEAN_SHEETS = 0.35
# Opponent: corners conceded per game, against the division. Zero means "at or above
# average" — this one is a floor rather than an edge, because a solid side that is also
# merely average at giving corners up is still the shape; it is the goals that matter.
DEFAULT_OPP_CORNER_EDGE = 0.0

THIN_GAMES = 6
MIN_GAMES = 3
LINE_RULE = lambda lam: max(3, round(lam) - 1)          # noqa: E731


def venue_games(team: dict, home: bool) -> list:
    """This team's matches at one venue, newest last.

    THE WHOLE SCREEN IS VENUE-SPLIT, and for this angle it has to be: a side can be
    resolute at home and generous away, and the season average says neither. The game
    state this is reaching for is produced by the two records that will actually meet.
    """
    return [m for m in _src(team) if bool(m.get("home")) is home]


def per_game(rows: list, field: str):
    return (sum(r.get(field, 0) for r in rows) / len(rows)) if rows else None


def clean_sheet_rate(rows: list):
    """Share of games shut out, over the games whose score was actually synced.

    NOT THE SAME CLAIM AS GOALS CONCEDED PER GAME, and the difference is the mechanism.
    A side conceding exactly one most weeks and a side alternating shutouts with a 2-0
    both average one a game, and only the second is a defence you expect to keep YOUR
    side off the scoreboard for ninety minutes. This angle rests on our team staying
    behind or level and chasing, so "how often do they keep a clean sheet" is the
    question, and the average was standing in for it.

    Counted over synced scores only, for win_rate's reason: an unsynced fixture is not
    a game they failed to shut out.
    """
    scored = [m for m in rows if m.get("goals_against") is not None]
    if not scored:
        return None, 0
    return sum(1 for m in scored if m["goals_against"] == 0) / len(scored), len(scored)


def win_rate(rows: list):
    """Share of games won, over the games whose score was actually synced.

    OVER THE SCORED GAMES, NOT ALL OF THEM. A fixture with no stored score is not a game
    this side failed to win, and dividing by it would quietly punish the leagues whose
    goal backfill has not reached them — which is a property of our sync, not of them.
    """
    results = [r for r in (_match_result(m) for m in rows) if r]
    if not results:
        return None, 0
    return sum(1 for r in results if r == "W") / len(results), len(results)


def league_pars(teams: list) -> dict:
    """Corners won and conceded per team-game, by division."""
    pool = defaultdict(lambda: {"for": [], "against": []})
    for t in teams:
        for m in _src(t):
            pool[t["league_id"]]["for"].append(m.get("corners_for") or 0)
            pool[t["league_id"]]["against"].append(m.get("corners_against") or 0)
    return {lid: {k: (sum(v) / len(v) if v else None) for k, v in d.items()}
            for lid, d in pool.items()}


def scan(fixtures: dict, teams_by_id: dict, pars: dict, corner_edge: float,
         min_leaking: float, min_win_rate: float, max_conceded: float,
         opp_corner_edge: float, min_clean_sheets: float = DEFAULT_MIN_CLEAN_SHEETS,
         vetoes: Optional[dict] = None):
    """Every (our side, opponent) pair in the window that fits the shape.

    BOTH SIDES ARE TESTED, not just the home team, for press_board's reason: the
    mechanism has nothing to do with which ground it is played on. A side that leaks
    goals away against a resolute home winner is the same fixture with the venues
    swapped, and screening one way round would silently halve the board.
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
            par_mine = pars.get(team["league_id"]) or {}
            par_theirs = pars.get(opp["league_id"]) or {}
            if not par_mine.get("for") or not par_theirs.get("against"):
                continue

            my_corners = per_game(mine, "corners_for")
            my_leak = per_game(mine, "goals_against")
            their_corners_against = per_game(theirs, "corners_against")
            their_goals_against = per_game(theirs, "goals_against")
            their_wins, scored_games = win_rate(theirs)
            their_sheets, sheet_games = clean_sheet_rate(theirs)
            if None in (my_corners, my_leak, their_corners_against,
                        their_goals_against, their_wins, their_sheets):
                continue

            my_edge = my_corners - par_mine["for"]
            their_edge = their_corners_against - par_theirs["against"]

            # SIX LEGS, every one of them the angle as stated, and each veto COUNTED.
            # An empty board otherwise says nothing about which bar emptied it, and the
            # reader's only move is to loosen all six at once — which is how a screen
            # ends up with thresholds nobody can defend. browse_audit paid for this.
            legs = (("our corner edge", my_edge < corner_edge),
                    ("our goals conceded", my_leak < min_leaking),
                    ("their win rate", their_wins < min_win_rate),
                    ("their goals conceded", their_goals_against > max_conceded),
                    ("their clean sheets", their_sheets < min_clean_sheets),
                    ("their corners conceded", their_edge < opp_corner_edge))
            failed = [name for name, bad in legs if bad]
            if failed:
                if vetoes is not None:
                    # The FIRST failing leg, so the tally sums to the number of pairs
                    # rejected rather than double-counting a side that misses on four.
                    vetoes[failed[0]] = vetoes.get(failed[0], 0) + 1
                continue

            lam = row["lambda_home"] if at_home else row["lambda_away"]
            line = LINE_RULE(lam)
            hits = sum(1 for m in mine if (m.get("corners_for") or 0) >= line)
            out.append({
                "row": row, "team": team["name"], "opp": opp["name"], "venue": venue,
                "my_corners": my_corners, "my_edge": my_edge, "my_leak": my_leak,
                "my_games": len(mine),
                "their_corners_against": their_corners_against, "their_edge": their_edge,
                "their_goals_against": their_goals_against, "their_wins": their_wins,
                "their_sheets": their_sheets, "their_sheet_games": sheet_games,
                "their_games": len(theirs), "their_scored": scored_games,
                # THE ORDERING, AND IT IS NOT A CONFIDENCE. See the note at the top. It
                # is the corner half of the angle restated as one number: how far our
                # corner rate outruns the division, plus how far this opponent's
                # generosity does. Goals are not added in — mixing goals and corners in
                # one sum produces a number in no units that nothing can interpret.
                "edge": my_edge + their_edge,
                # And the game-state half, printed beside it rather than ranked on,
                # because a per-game version of exactly this was measured and came out
                # flat five times.
                "behind": my_leak - their_goals_against,
                "lam": lam, "line": line, "hits": hits, "played": len(mine),
                "prob": nb_ge(line, lam),
                "thin": min(len(mine), len(theirs)) < THIN_GAMES,
            })
    return sorted(out, key=lambda r: r["edge"], reverse=True)


def show(rows: list, top: int, title: str):
    print(title)
    if not rows:
        print("  nothing in the window fits the shape\n")
        return
    for i, r in enumerate(rows[:top], 1):
        row = r["row"]
        when = (row.get("date") or "")[:10]
        at = r["venue"]
        other = "away" if at == "home" else "home"
        print(f"{i:2}. {when}  {row['home']} v {row['away']}   [{row['league_name']}]")
        print(f"     {r['team']} ({at}): {r['my_corners']:.2f} corners/game "
              f"({r['my_edge']:+.2f} v division)  ·  concedes {r['my_leak']:.2f} "
              f"goals/game   over {r['my_games']}")
        print(f"     {r['opp']} ({other}): wins {r['their_wins'] * 100:.0f}% "
              f"of {r['their_scored']}  ·  clean sheets in "
              f"{r['their_sheets'] * 100:.0f}% of {r['their_sheet_games']}")
        print(f"     {' ' * len(r['opp'])}  concedes {r['their_goals_against']:.2f} "
              f"goals/game  ·  gives up {r['their_corners_against']:.2f} corners/game "
              f"({r['their_edge']:+.2f})")
        model = f"     model: {r['lam']:.2f} corners for {r['team']}"
        if r["prob"] > 0:
            model += f"  ·  {r['line']}+ {r['prob'] * 100:.1f}% (fair {1 / r['prob']:.2f})"
        print(model)
        print(f"     run at {r['line']}+: {r['hits']}/{r['played']} at this venue"
              f"   ·   corner edge {r['edge']:+.2f}   ·   goal gap {r['behind']:+.2f}")
    print()


async def run(days=DEFAULT_DAYS, top=DEFAULT_TOP, league_id=None,
              corner_edge=DEFAULT_CORNER_EDGE, min_leaking=DEFAULT_MIN_LEAKING,
              min_win_rate=DEFAULT_MIN_WIN_RATE, max_conceded=DEFAULT_MAX_CONCEDED,
              opp_corner_edge=DEFAULT_OPP_CORNER_EDGE,
              min_clean_sheets=DEFAULT_MIN_CLEAN_SHEETS):
    print("CHASE ANGLE — a corner side that leaks goals, against a solid winner that")
    print("gives corners up. The inverse premise to press_board: our defence is the")
    print("one that fails, so our side spends the game chasing.")
    print("(reads the database only; nothing here is priced, and this is not a card)\n")
    print(f"screen: our side  >= {corner_edge:+.2f} corners/game v its division "
          f"AND concedes >= {min_leaking:.2f} goals/game")
    print(f"        opponent  wins >= {min_win_rate * 100:.0f}% "
          f"AND clean sheets in >= {min_clean_sheets * 100:.0f}% "
          f"AND concedes <= {max_conceded:.2f} goals/game")
    print(f"                  AND gives up >= {opp_corner_edge:+.2f} corners/game "
          f"v its division")
    print(f"        both over {MIN_GAMES}+ games at the venue they are playing")
    print(f"window: next {days} days   league={league_id or 'all'}\n")

    fixtures = await _fixture_projections(days, league_id)
    if not fixtures:
        print("no upcoming fixtures in range — run sync_real.py first")
        return

    # _fixture_projections drops the raw fixture and the team ids are what this needs to
    # reach the venue splits. Re-read rather than widen that function's contract: it has
    # callers on the hot path of a page. Same reasoning as press_board.
    raw = {f["fixture_id"]: f for f in await db.fixtures.find({}, {"_id": 0}).to_list(5000)}
    for fid, row in fixtures.items():
        row["_fixture"] = raw.get(fid, {})
    teams = await db.teams.find({}, {"_id": 0}).to_list(5000)
    teams_by_id = {t["team_id"]: t for t in teams}

    vetoes = {}
    rows = scan(fixtures, teams_by_id, league_pars(teams), corner_edge, min_leaking,
                min_win_rate, max_conceded, opp_corner_edge, min_clean_sheets, vetoes)
    solid = [r for r in rows if not r["thin"]]
    thin = [r for r in rows if r["thin"]]

    print(f"{len(fixtures)} fixtures in the window, {len(rows)} fit the shape "
          f"({len(solid)} well-sampled, {len(thin)} thin)")
    # WHICH BAR DID THE REJECTING. Without it an empty board leaves one move — loosen
    # all six at once — and that is how a screen ends up with thresholds nobody can
    # defend. Counted on the FIRST failing leg, so these sum to the pairs rejected.
    if vetoes:
        print("rejected on (first failing leg): "
              + ", ".join(f"{k} {v}" for k, v in
                          sorted(vetoes.items(), key=lambda kv: -kv[1])))
    print()
    show(solid, top, "=" * 78 + f"\nWELL SAMPLED — both sides have {THIN_GAMES}+ games "
         "at the venue\n" + "=" * 78)
    show(thin, top, "-" * 78 + f"\nTHIN — fewer than {THIN_GAMES} games behind one side. "
         "Listed so nothing is\nmissing, ranked below the rest because a short venue "
         "split is extreme by\nconstruction and would otherwise lead.\n" + "-" * 78)

    print("=" * 78)
    print("HOW TO READ IT. `corner edge` is the angle's corner half as one number and is")
    print("an ordering, not a confidence — the chase premise this screen rests on has")
    print("been tested in its per-game form five times and found flat every time, and")
    print("this season-shape form has not been tested at all. The model's own projection")
    print("sits on every row for that reason: where the model already has the side high,")
    print("the angle and the price agree and there is nothing here. The rows worth a")
    print("second look are the ones where the shape is strong and lambda is NOT.")
    print("`goal gap` is the game-state half — how much more our side concedes than this")
    print("opponent does — and is deliberately NOT ranked on.")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--days", type=int, default=DEFAULT_DAYS)
    ap.add_argument("--top", type=int, default=DEFAULT_TOP)
    ap.add_argument("--league", default=None)
    ap.add_argument("--corner-edge", type=float, default=DEFAULT_CORNER_EDGE)
    ap.add_argument("--min-leaking", type=float, default=DEFAULT_MIN_LEAKING)
    ap.add_argument("--min-win-rate", type=float, default=DEFAULT_MIN_WIN_RATE)
    ap.add_argument("--max-conceded", type=float, default=DEFAULT_MAX_CONCEDED)
    ap.add_argument("--opp-corner-edge", type=float, default=DEFAULT_OPP_CORNER_EDGE)
    ap.add_argument("--min-clean-sheets", type=float, default=DEFAULT_MIN_CLEAN_SHEETS)
    a = ap.parse_args()
    asyncio.run(run(a.days, a.top, a.league, a.corner_edge, a.min_leaking,
                    a.min_win_rate, a.max_conceded, a.opp_corner_edge,
                    a.min_clean_sheets))


if __name__ == "__main__":
    main()
