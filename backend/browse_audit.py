"""Offline: how much the front door's Streaks and Trends filters actually keep.

WHY THIS EXISTS. The streak filter on /browse has now been tuned three times, each time
on reasoning rather than on a count:

  1. At the fixture panel's bar it kept EVERYTHING — OVER_LINE_FLOOR is 3, so almost
     every side in football is on a run of "3+ in N straight" and the filter was off.
  2. Tightened to a team-relative bar, which still let ordinary sides through: a run is
     reported at the HIGHEST line it held, which for a low-variance side is its floor.
  3. Tightened to a league-relative bar AND narrowed to one slice — a team's own corners,
     over, overall. That is a sixth of what the fixture panel shows, and the filter came
     back nearly empty. The user's words: "the streaks and trends only come up with a few
     options, there should be loads, why is this".

Every one of those was a guess about a number nobody had looked at. This prints the
number. Run it after a change to BROWSE_SUBJECTS, _browse_margin, PANEL_MIN_RUN or
BROWSE_TREND_MIN and the next decision is made on evidence.

WHAT IT PRINTS, per window:

  - how many games survive `all`, `streaks` and `trends`, and what share that is
  - the streaks broken down by subject, direction and venue, which is the breakdown that
    would have caught the one-slice mistake on the day it was made
  - what the margin rule REJECTED, counted the same way — a filter is as much the runs it
    throws away as the ones it keeps, and the rejected pile is where "too strict" shows
  - the trends by subject and direction

A SHARE, NOT A COUNT, is what to read. "41 games" means nothing without the card it came
from; "41 of 212" says whether the filter is a filter. Roughly a quarter to a third on
streaks is the shape to want: below a tenth it is hiding the site, and above a half it is
not selecting anything.

Reads the database only. No API calls, no writes.

Run: python browse_audit.py
     python browse_audit.py --days 3
"""
import argparse
import asyncio
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

from dotenv import load_dotenv

from server import (BROWSE_SUBJECTS, BROWSE_TREND_MIN, PANEL_MIN_RUN, _browse_margin,
                    _src, _trends_of, browse, db, live_streak, streak_value)

ROOT = Path(__file__).parent
load_dotenv(ROOT / ".env")

DEFAULT_WINDOWS = (3, 7, 14)
BAR = "-" * 78


def _pct(n, d):
    return f"{100.0 * n / d:5.1f}%" if d else "    - "


def _table(title, counter, total):
    print(f"\n  {title}")
    if not counter:
        print("    (none)")
        return
    for key, n in counter.most_common():
        print(f"    {key:<34} {n:>5}  {_pct(n, total)}")


async def run(windows):
    teams = await db.teams.find({}, {"_id": 0}).to_list(5000)
    by_id = {t["team_id"]: t for t in teams}

    # The same yardstick browse() builds, rebuilt here rather than imported, because the
    # endpoint computes it inline. If that ever drifts this harness reports the wrong bar,
    # so the two are checked against each other at the bottom of this run.
    par = {}
    pool = {}
    for t in teams:
        d = pool.setdefault(t["league_id"], {s: [] for s in BROWSE_SUBJECTS})
        for m in _src(t):
            for s in BROWSE_SUBJECTS:
                d[s].append(streak_value(m, s))
    for lid, subs in pool.items():
        par[lid] = {s: (sum(v) / len(v) if v else None) for s, v in subs.items()}

    print("=" * 78)
    print("WHAT THE FRONT DOOR'S FILTERS KEEP")
    print("=" * 78)
    print(f"  subjects      {', '.join(BROWSE_SUBJECTS)}, both directions")
    print(f"  min run       {PANEL_MIN_RUN}")
    print(f"  trend bar     {BROWSE_TREND_MIN} corners a game off a side's own rate")
    print(f"  teams on file {len(teams)} across {len(par)} competitions")

    for days in windows:
        every = await browse(days=days, show="all", user=None)
        streaks = await browse(days=days, show="streaks", user=None)
        trends = await browse(days=days, show="trends", user=None)
        total = every["total"]

        print(f"\n{BAR}\n{days} DAYS — {total} games\n{BAR}")
        print(f"  streaks  {streaks['total']:>5}  {_pct(streaks['total'], total)}")
        print(f"  trends   {trends['total']:>5}  {_pct(trends['total'], total)}")
        if not total:
            continue

        # The breakdown, recomputed per side rather than read off the row, because the row
        # carries only the BEST run and the question here is what the whole pass found.
        kept, rejected, seen = Counter(), Counter(), set()
        tr = Counter()
        now = datetime.now(timezone.utc)
        horizon = now + timedelta(days=days)
        for fx in await db.fixtures.find({}, {"_id": 0}).to_list(5000):
            try:
                dt = datetime.fromisoformat((fx.get("date") or "").replace("Z", "+00:00"))
            except Exception:                                    # noqa: BLE001
                continue
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            if dt < now or dt > horizon:
                continue
            for key, side in (("home_team_id", "home"), ("away_team_id", "away")):
                t = by_id.get(fx[key])
                if not t or (t["team_id"], side) in seen:
                    continue
                seen.add((t["team_id"], side))
                p = par.get(t["league_id"], {})
                for subject in BROWSE_SUBJECTS:
                    for direction in ("over", "under"):
                        for venue in (side, "overall"):
                            r = live_streak(t, venue, subject, direction,
                                            min_len=PANEL_MIN_RUN)
                            if not r:
                                continue
                            label = f"{subject} {direction} ({venue})"
                            if _browse_margin(r, p) is None:
                                rejected[label] += 1
                            else:
                                kept[label] += 1
                for x in _trends_of(t):
                    tr[f"{x['label']} {x['direction']}"] += 1

        total_runs = sum(kept.values()) + sum(rejected.values())
        print(f"\n  {total_runs} runs of {PANEL_MIN_RUN}+ exist across the sides playing; "
              f"{sum(kept.values())} clear the division bar")
        _table("KEPT — past what the division does", kept, total_runs)
        _table("REJECTED — a run, but an ordinary one for that league", rejected,
               total_runs)
        _table("TRENDS", tr, sum(tr.values()))

    print(f"\n{BAR}")
    print("HOW TO READ IT. The share is the number, not the count. A streak filter under")
    print("a tenth is hiding the site from the one screen meant to surface it; over a")
    print("half it is not selecting anything. The REJECTED table is the other half of")
    print("the question: if one subject is almost entirely rejected, its bar is wrong for")
    print("that subject rather than the filter being strict — conceded and match totals")
    print("run on different scales from a team's own corners and were, at one point, all")
    print("being measured against the same number.")
    print("NOTHING HERE IS A CONFIDENCE. It counts what the filter does. Whether a run")
    print("past the division's average predicts anything is a separate question that")
    print("measure_chase_board's method would have to answer.")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--days", type=int, action="append", default=None,
                    help="window to audit; repeatable. Default 3, 7 and 14.")
    a = ap.parse_args()
    asyncio.run(run(a.days or list(DEFAULT_WINDOWS)))


if __name__ == "__main__":
    main()
