"""Offline: which fixtures to watch when football comes back.

THE JOB. An international break empties the board for ten days or so. This looks past it
and names the games worth having prices alerted on when the domestic leagues return, so
the watching can be set up before the odds appear rather than after.

WHAT IT IS NOT. It is not a card and must never be posted as one. Nothing here has a
price, because no book has put these games up yet — that is the whole premise — and a
list of fixtures with model numbers on them, read three weeks early, is the easiest thing
in this repo to mistake for a set of selections.

RANKED ON THE MISMATCH, NOT ON THE STREAK, AND THAT IS THE POINT.

A streak is the wrong signal at this range. Between now and the return there are more
rounds to play, and a run is one result from ending: today's 6 from 6 is quite possibly
6 from 8 by then, and the row you planned around has gone. Ranking a three-week watchlist
by current runs is planning around the most perishable number on the board.

A mismatch survives it. `team_for` and `opp_conceded` are venue-split season averages —
what this side wins at home, what that side concedes away — over a window measured in
dozens of games. Two more rounds move them by a fraction of a corner. The fixture that
projects high today is very likely still the fixture that projects high in three weeks,
because the reason is structural rather than a run of form.

So the order is `corner_edge` — the fixture's projected total against its league's own
average, which is already what the site computes and already what the board shows. No new
score is invented here: this repo has measured four orderings against a shuffled control
and could not separate any of them (see measure_chase_board.py), so an ordering exists to
put the interesting rows near the top and is not a confidence.

STREAKS ARE STILL SHOWN, as context, stamped with the date they were true on. They are
the reason a row might be worth a second look; they are not the reason it is on the list.

THE WINDOW DEFAULTS TO DAYS 14-28 and is overridable, because the break's exact dates are
a fact about the calendar rather than about this data. A fixture-count histogram is
printed for the whole run-up so the gap is visible and the window can be corrected in one
re-run rather than guessed at twice.

WELL-SAMPLED FIXTURES RANK FIRST; THIN ONES HAVE THEIR OWN SECTION UNDERNEATH. Marking
them in place was the first design and the first real run showed it was wrong for the job:
a five-game average is EXTREME by construction, so thin rows do not merely appear in the
ranking, they lead it. Four of the top ten were thin, one of them asserting an opponent
who concedes 12.0 corners per away game over eight games — not a rate, a small sample —
and the fixtures actually worth watching were pushed off the end of the list.

They are still printed, because a silent omission reads as the list being broken rather
than as the row being weak. They are just no longer allowed to crowd out the rest.

Reads the database only. No API calls, no writes.

Run: python watchlist.py
     python watchlist.py --from 14 --to 28
     python watchlist.py --league eng-pl --top 15
"""
import asyncio
import os
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

from dotenv import load_dotenv

from server import _fixture_projections

ROOT = Path(__file__).parent
load_dotenv(ROOT / ".env")

DEFAULT_FROM = 14
DEFAULT_TO = 28
DEFAULT_TOP = 15
# Below this the projection is arithmetic on a handful of games.
#
# WELL-SAMPLED ROWS RANK FIRST, AND THIN ONES GO IN THEIR OWN SECTION. Marking them in
# place was the first design and it was wrong for the job: a five-game average is EXTREME
# by construction, so thin rows do not merely appear in the ranking, they dominate the top
# of it. The first real run put four of them in the top ten, and one claimed an opponent
# conceding 12.0 corners per away game over eight games — which is not a rate, it is a
# small sample. That pushed the usable fixtures off the end of a fifteen-row list.
#
# They are still PRINTED, below, because the original reason for not dropping them holds:
# at this range a newly promoted side is often the game a reader expects to see, and a
# silent omission reads as the list being broken rather than as the row being weak.
THIN_GAMES = 10


def day_of(iso):
    return (iso or "")[:10]


def in_window(rows, first, last):
    return [r for r in rows.values() if first <= day_of(r.get("date")) <= last]


def best_angle(row):
    """The strongest team mismatch on the fixture, or None.

    `prob` is the model's own confidence on that side's line, which is what makes two
    angles on different lines comparable at all.
    """
    angles = [a for a in (row.get("angles") or []) if a.get("kind") == "mismatch"]
    return max(angles, key=lambda a: a.get("prob") or 0) if angles else None


def thin(row):
    return min(row.get("home_games") or 0, row.get("away_games") or 0) < THIN_GAMES


def rank(rows):
    """Fixtures carrying at least one mismatch, strongest projection first."""
    return sorted([r for r in rows if best_angle(r)],
                  key=lambda r: r.get("corner_edge") or 0, reverse=True)


def split_by_sample(rows):
    """(well_sampled, thin) — both ranked, kept apart. See THIN_GAMES."""
    ranked = rank(rows)
    return [r for r in ranked if not thin(r)], [r for r in ranked if thin(r)]


def histogram(rows):
    """Fixtures per day across the whole run-up, so the break is visible."""
    return Counter(day_of(r.get("date")) for r in rows.values() if r.get("date"))


async def run(days_from=DEFAULT_FROM, days_to=DEFAULT_TO, top=DEFAULT_TOP, league_id=None):
    today = datetime.now(timezone.utc).date()
    first = (today + timedelta(days=days_from)).isoformat()
    last = (today + timedelta(days=days_to)).isoformat()

    print("WATCHLIST — the games to have prices alerted on when football returns")
    print("(reads the database only; no prices exist for these yet, and this is not a card)\n")

    rows = await _fixture_projections(days_to, league_id)
    if not rows:
        print("no upcoming fixtures in range — run sync_real.py first")
        return

    hist = histogram(rows)
    print(f"fixtures on file to {last}: {len(rows)}   league={league_id or 'all'}")
    print("\nfixtures per day (the gap is the break):")
    for day in sorted(hist):
        n = hist[day]
        mark = "  <- window" if first <= day <= last else ""
        print(f"  {day}  {n:3}  {'#' * min(n, 40)}{mark}")

    window = in_window(rows, first, last)
    print(f"\nwindow {first} -> {last}: {len(window)} fixtures")
    if not window:
        print("\nNothing on file in that window. Either the fixtures are not published yet,")
        print("or the window has missed the restart — read the histogram above and re-run")
        print("with --from / --to.")
        return

    solid, thin_rows = split_by_sample(window)
    if not solid and not thin_rows:
        print("\nFixtures are on file but none carries a mismatch. That is a real answer:")
        print("no side in the window is projecting unusually against its opponent.")
        return

    def show(rows, start=1):
        for i, r in enumerate(rows, start):
            a = best_angle(r)
            games = f"{r.get('home_games')}/{r.get('away_games')} games"
            print(f"{i:2}. {day_of(r['date'])}  {r['home']} v {r['away']}   [{r.get('league_name')}]")
            print(f"     projected {r.get('lambda_total')} corners vs league "
                  f"{r.get('league_avg_total')}  (edge {r.get('corner_edge')})   {games}")
            print(f"     watch: {a.get('team')} {a.get('label')}"
                  f"  — wins {a.get('team_for')} {'home' if a.get('team') == r['home'] else 'away'},"
                  f" opponent concedes {a.get('opp_conceded')}"
                  f"  · model {a.get('prob')}% (fair {a.get('fair_odds')})")

    print(f"\ntop {min(top, len(solid))} by projected corners against the league's own average")
    print(f"(both sides have {THIN_GAMES}+ games on file)\n")
    if solid:
        show(solid[:top])
    else:
        print("  None. Every mismatch in this window rests on a thin sample — see below.")

    if thin_rows:
        print(f"\n{'-' * 78}")
        print(f"THIN — fewer than {THIN_GAMES} games behind one side. Listed so nothing is")
        print("missing, ranked below the rest because a short sample produces EXTREME")
        print("averages: these rows do not merely appear in a ranking, they lead it.\n")
        show(thin_rows[:max(3, top // 3)])

    print(f"\n{'=' * 78}")
    print("HOW TO USE IT. These are fixtures to set a price alert on, not selections.")
    print("Every number above is today's form projected onto a game that is weeks away, and")
    print("more rounds will be played before then — so re-run this in the week itself and")
    print("bet off THAT, not off this. What this list is for is knowing where to look when")
    print("the odds drop, which is the part that cannot be done at the last minute.")
    print(f"\n{len(solid)} well-sampled and {len(thin_rows)} thin fixtures carry a mismatch "
          f"in this window.")


def main():
    args = sys.argv[1:]

    def opt(flag, default=None, cast=str):
        return cast(args[args.index(flag) + 1]) if flag in args else default

    asyncio.run(run(days_from=opt("--from", DEFAULT_FROM, int),
                    days_to=opt("--to", DEFAULT_TO, int),
                    top=opt("--top", DEFAULT_TOP, int),
                    league_id=opt("--league")))


if __name__ == "__main__":
    main()
