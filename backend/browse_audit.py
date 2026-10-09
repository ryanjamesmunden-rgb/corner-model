"""Offline: how much the front door's Streaks and Trends filters actually keep.

WHY THIS EXISTS. The streak filter on /browse has now been tuned four times, each time
on reasoning rather than on a count:

  1. At the fixture panel's bar it kept EVERYTHING — OVER_LINE_FLOOR is 3, so almost
     every side in football is on a run of "3+ in N straight" and the filter was off.
  2. Tightened to a team-relative bar, which still let ordinary sides through: a run is
     reported at the HIGHEST line it held, which for a low-variance side is its floor.
  3. Tightened to a league-relative bar AND narrowed to one slice — a team's own corners,
     over, overall. That is a sixth of what the fixture panel shows, and the filter came
     back nearly empty: "the streaks and trends only come up with a few options".
  4. Widened to every subject, both directions, both venues, and taught to read every
     candidate line rather than live_streak's single headline pick.

The first run of this harness then found the fifth problem: it keeps 54% of the card,
where the note at the bottom of this file says a quarter to a third is the shape to want.
That is a filter that has stopped selecting, and the trend filter at 90% has stopped
being a filter at all.

AND THE FIRST VERSION OF THIS HARNESS MEASURED THE WRONG FUNCTION. Its breakdown called
live_streak — the single best-by-length pick — while the endpoint walks
live_streak_candidates. So the per-subject tables described the bug that had already
been fixed, and read as though overs were being rejected at 98%. The headline shares
were right because they came from browse() itself; the breakdown was fiction. It now
calls the same function the endpoint does, and the sweep below exists so the NEXT
threshold is read off a curve instead of guessed a fifth time.

WHAT IT PRINTS, per window:

  - how many games survive `all`, `streaks` and `trends`, and what share that is
  - SWEEPS: how the surviving share moves as the division bar, the trend bar and the
    minimum run length are varied, so a threshold can be chosen rather than invented
  - what the filter actually shows, by subject, direction and venue — the best passing
    candidate per side, which is the row a reader gets
  - and what it threw away: sides that carried a run but nothing unusual enough

A SHARE, NOT A COUNT, is what to read. "41 games" means nothing without the card it came
from; "41 of 212" says whether the filter is a filter.

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

from server import (BROWSE_SUBJECTS, BROWSE_TREND_MIN, BROWSE_TREND_WINDOW,
                    BROWSE_TREND_MIN_GAMES, BROWSE_MAX_MIN_RUN, PANEL_MIN_RUN,
                    _browse_margin, _src, _trends_of, browse, db,
                    live_streak_candidates, streak_value)

ROOT = Path(__file__).parent
load_dotenv(ROOT / ".env")

DEFAULT_WINDOWS = (3, 7, 14)
BAR = "-" * 78

# The curves. Each is the knob as it could be set, not as it is set.
MARGIN_STEPS = (0.0, 0.25, 0.5, 0.75, 1.0, 1.25, 1.5, 2.0, 2.5, 3.0)
TREND_STEPS = (1.0, 1.25, 1.5, 1.75, 2.0, 2.5, 3.0)


def _pct(n, d):
    return f"{100.0 * n / d:5.1f}%" if d else "    - "


def _table(title, counter, total):
    print(f"\n  {title}")
    if not counter:
        print("    (none)")
        return
    for key, n in counter.most_common():
        print(f"    {key:<34} {n:>5}  {_pct(n, total)}")


def _curve(title, knob, pairs, total):
    """One sweep: the knob, how many games survive, and the share."""
    print(f"\n  {title}")
    print(f"    {knob:<10} {'games':>7}  share")
    for value, n in pairs:
        print(f"    {value:<10} {n:>7}  {_pct(n, total)}")


def _raw_margin(run, par):
    """The margin BEFORE the keep/reject test, so a sweep has something to sweep.

    Mirrors _browse_margin's arithmetic deliberately rather than importing it, because
    that one collapses everything at or below zero to None. The two are checked against
    each other on every row below — if this drifts from production the run says so
    rather than reporting a curve for a rule nobody ships.
    """
    avg = par.get(run["subject"])
    if avg is None:
        return None
    return (run["line"] - avg) if run["direction"] == "over" else (avg - (run["line"] - 1))


def _trend_deltas(team):
    """Every |recent - season| this side offers, whatever the current bar is."""
    out = []
    for subject in ("team", "conceded"):
        vals = [streak_value(m, subject) for m in _src(team)]
        if len(vals) < BROWSE_TREND_MIN_GAMES:
            continue
        recent = vals[-BROWSE_TREND_WINDOW:]
        out.append(abs((sum(recent) / len(recent)) - (sum(vals) / len(vals))))
    return out


async def run(windows):
    teams = await db.teams.find({}, {"_id": 0}).to_list(5000)
    by_id = {t["team_id"]: t for t in teams}

    # The same yardstick browse() builds, rebuilt here because the endpoint computes it
    # inline. _raw_margin is cross-checked against _browse_margin on every row, so a
    # drift between the two shows up as a loud mismatch rather than a quiet wrong curve.
    par, pool = {}, {}
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
    print(f"  min run       {PANEL_MIN_RUN} (ceiling {BROWSE_MAX_MIN_RUN})")
    print(f"  trend bar     {BROWSE_TREND_MIN} corners a game off a side's own rate")
    print(f"  teams on file {len(teams)} across {len(par)} competitions")

    mismatches = [0]      # a list so the inner loops can bump it without a global
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

        now = datetime.now(timezone.utc)
        horizon = now + timedelta(days=days)
        shown, starved = Counter(), Counter()
        # Per GAME, the best thing available — which is what decides whether the game
        # survives, and therefore what a sweep has to be computed over.
        game_margin, game_run, game_trend = [], [], []
        seen_side = set()

        for fx in await db.fixtures.find({}, {"_id": 0}).to_list(5000):
            try:
                dt = datetime.fromisoformat((fx.get("date") or "").replace("Z", "+00:00"))
            except Exception:                                    # noqa: BLE001
                continue
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            if dt < now or dt > horizon:
                continue

            best_margin, best_run, best_trend = None, 0, None
            for key, side in (("home_team_id", "home"), ("away_team_id", "away")):
                t = by_id.get(fx[key])
                if not t:
                    continue
                p = par.get(t["league_id"], {})

                deltas = _trend_deltas(t)
                if deltas:
                    best_trend = max([best_trend or 0.0] + deltas)

                # THE SAME WALK THE ENDPOINT DOES: every candidate line, both venues.
                side_best, side_had_any = None, False
                for subject in BROWSE_SUBJECTS:
                    for direction in ("over", "under"):
                        for venue in (side, "overall"):
                            for r in live_streak_candidates(t, venue, subject, direction,
                                                            min_len=PANEL_MIN_RUN):
                                side_had_any = True
                                raw = _raw_margin(r, p)
                                if raw is None:
                                    continue
                                # The cross-check: production's verdict must agree with
                                # this one's sign, or the curve below is for another rule.
                                kept = _browse_margin(r, p) is not None
                                if kept != (raw > 0):
                                    mismatches[0] += 1
                                if best_margin is None or raw > best_margin:
                                    best_margin = raw
                                if kept and r["run"] > best_run:
                                    best_run = r["run"]
                                label = f"{subject} {direction} ({venue})"
                                if kept and (side_best is None
                                             or (r["run"], raw) > side_best[0]):
                                    side_best = ((r["run"], raw), label)
                if (t["team_id"], side) not in seen_side:
                    seen_side.add((t["team_id"], side))
                    if side_best:
                        shown[side_best[1]] += 1
                    elif side_had_any:
                        starved["carried a run, none unusual enough"] += 1

            game_margin.append(best_margin)
            game_run.append(best_run)
            game_trend.append(best_trend)

        _curve("STREAKS — raise the division bar", "margin",
               [(f"> {m}", sum(1 for x in game_margin if x is not None and x > m))
                for m in MARGIN_STEPS], total)
        _curve("STREAKS — raise the minimum run", "run",
               [(f"{n}+", sum(1 for x in game_run if x >= n))
                for n in range(PANEL_MIN_RUN, BROWSE_MAX_MIN_RUN + 1)], total)
        _curve("TRENDS — raise the move required", "corners/g",
               [(f">= {b}", sum(1 for x in game_trend if x is not None and x >= b))
                for b in TREND_STEPS], total)

        total_sides = sum(shown.values()) + sum(starved.values())
        _table("SHOWN — the row a reader actually gets, per side", shown, total_sides)
        _table("NOTHING TO SHOW", starved, total_sides)

    print(f"\n{BAR}")
    if mismatches[0]:
        print(f"!! {mismatches[0]} rows where this harness and _browse_margin disagreed — the")
        print("   curves above are for a rule the site does not ship. Fix before reading.")
    else:
        print("The margin arithmetic here agrees with _browse_margin on every row.")
    print("HOW TO READ IT. The share is the number, not the count. A streak filter under")
    print("a tenth is hiding the site from the one screen meant to surface it; over a")
    print("half it is not selecting anything. Pick the knob off the curve where the share")
    print("lands between a quarter and a third, and prefer raising the DIVISION BAR over")
    print("the minimum run: a long run at an ordinary line is the thing worth removing,")
    print("and raising the run removes short runs at remarkable lines as well.")
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
