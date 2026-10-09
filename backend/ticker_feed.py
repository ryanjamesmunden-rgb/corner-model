"""Offline: the corner ticker's two lists, as JSON ready to paste.

WHY A SCRIPT AND NOT A LOOKUP. The ticker that runs along the bottom of a recording
carries its teams as literals, because it is a standalone page with no connection to
this database and it has to keep working on a laptop with the site closed. That makes
the numbers a snapshot taken by hand, and a snapshot taken by hand goes stale quietly —
the figures stay plausible and simply stop being true. This prints the current ones in
exactly the shape that page wants, so refreshing is a copy and a paste rather than a
transcription.

TWO LISTS, because the page has two tabs and they answer different questions:

  season   corners won per game over everything on file. Who is a high-corner side.
  last 5   corners won per game over the five most recent. Who is one RIGHT NOW.

A side can top one and be absent from the other, which is the whole reason the page
shows both — and the reason the five-game list carries the flame: it is the one making
a claim about form rather than about a team.

A LAST-FIVE LIST NEEDS FIVE GAMES. A side with three on file has a three-game average,
which is a different and much noisier number wearing the same label, and it would lead
the ranking rather than merely appear in it — watchlist.py's lesson, quoted in
press_board: "a five-game average is EXTREME by construction, so thin rows do not
merely appear in the ranking, they lead it." Here the window IS five, so the fix is to
require five and drop the rest rather than to rank them apart.

NEWEST LAST, by date, and the window is taken off the end. The stored order is whatever
the sync wrote and sorting is the only thing that makes "the last five" mean the last
five rather than five of them.

Reads the database only. No API calls, no writes.

Run: python ticker_feed.py
     python ticker_feed.py --top 20 --window 10
"""
import argparse
import asyncio
import json
from pathlib import Path

from dotenv import load_dotenv

from server import _src, db

ROOT = Path(__file__).parent
load_dotenv(ROOT / ".env")

DEFAULT_TOP = 15
DEFAULT_WINDOW = 5
# A season figure off four games is not a season figure. Lower than the five-game
# window's requirement on purpose: there the window IS the claim, so it has to be full;
# here the claim is "over everything on file" and a short file is honestly described.
MIN_SEASON_GAMES = 6


def rate_over(team: dict, window: int):
    """Corners won per game over the last `window` games, or over everything at 0.

    None when the pool cannot support the claim — too few games, or a gap in the corner
    column. A gap is not a nil: averaging over it would quietly report a quiet side.
    """
    games = sorted(_src(team), key=lambda m: (m.get("date") or ""))
    pool = games[-window:] if window else games
    need = window if window else MIN_SEASON_GAMES
    if len(pool) < need:
        return None
    vals = [m.get("corners_for") for m in pool]
    if any(v is None for v in vals):
        return None
    return sum(vals) / len(vals)


def build(teams, league_names, window, top):
    """The ticker's rows, best first, in the page's own shape."""
    rows = []
    for t in teams:
        avg = rate_over(t, window)
        if avg is None:
            continue
        rows.append({
            "name": t.get("name") or t.get("team_id"),
            "league": league_names.get(t.get("league_id"), ""),
            "value": round(avg, 2),
            # The flame marks a claim about FORM. A season average is not one.
            "hot": bool(window),
        })
    rows.sort(key=lambda r: r["value"], reverse=True)
    return rows[:top]


def show(label, rows, note):
    print(f"\n{'=' * 78}\n{label}\n{'=' * 78}")
    print(f"  {note}")
    if not rows:
        print("  nothing qualifies — check the game counts above")
        return
    print(f"  {len(rows)} teams, {rows[0]['value']:.2f} down to {rows[-1]['value']:.2f}"
          " corners/game\n")
    # The page stores these literally, so they are printed exactly as it holds them:
    # one object per line, trailing comma free, ready to replace the array wholesale.
    for i, r in enumerate(rows):
        tail = "" if i == len(rows) - 1 else ","
        print("      " + json.dumps(r, ensure_ascii=False) + tail)


async def run(top=DEFAULT_TOP, window=DEFAULT_WINDOW):
    teams = await db.teams.find({}, {"_id": 0}).to_list(5000)
    league_names = {l["league_id"]: l.get("name", l["league_id"])
                    for l in await db.leagues.find({}, {"_id": 0}).to_list(200)}

    counts = sorted(len(_src(t)) for t in teams)
    enough = sum(1 for c in counts if c >= window)
    print("=" * 78)
    print("CORNER TICKER — the two lists, current")
    print("=" * 78)
    print(f"  {len(teams)} teams on file across {len(league_names)} competitions")
    if counts:
        print(f"  games per team: min {counts[0]}, median {counts[len(counts) // 2]}, "
              f"max {counts[-1]}  ·  {enough} have the {window} a form list needs")

    show(f"HOTTEST — LAST {window} GAMES",
         build(teams, league_names, window, top),
         f"corners won per game over the {window} most recent. Sides with fewer than "
         f"{window}\n  on file are dropped, not ranked low: a {window}-game label over "
         "three games is a\n  different and noisier number wearing the same name.")

    show("TOP CORNER TEAMS — SEASON",
         build(teams, league_names, 0, top),
         f"corners won per game over everything on file, minimum {MIN_SEASON_GAMES} "
         "games.")

    print(f"\n{'-' * 78}")
    print("HOW TO USE IT. Open the Corner Ticker Builder, and replace the array inside")
    print("form5Teams() with the first block and seasonTeams() with the second. The page")
    print("keeps your edits in that browser's storage, so a list you have customised is")
    print("not overwritten by reloading — clear it there first if you want these exactly.")
    print("THESE ARE DESCRIPTIONS, NOT PICKS. Corners won per game is a rate, not an")
    print("edge: a side top of this list is not thereby value at any price, and nothing")
    print("here has been compared with a market.")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--top", type=int, default=DEFAULT_TOP)
    ap.add_argument("--window", type=int, default=DEFAULT_WINDOW)
    a = ap.parse_args()
    asyncio.run(run(max(1, min(a.top, 60)), max(2, min(a.window, 20))))


if __name__ == "__main__":
    main()
