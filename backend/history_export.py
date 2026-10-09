"""Offline: everything the site has published, graded, week by week.

WHY, AND THE ONE THING THAT DECIDES WHAT IS POSSIBLE HERE. A board on this site is
computed from the current team records, so "what the board said last Tuesday" does not
exist anywhere unless somebody wrote it down before the games were played. Two things
were written down and two were not:

  RECORDED — gradeable, and it is the real published record
    projection_snapshots   the projections board, frozen daily, every row, ranked by
                           lambda_total. The "highest projected corners" list.
    streak_snapshots       the angle board, frozen daily, each row carrying the mismatch
                           evidence it rested on (support.opp_conceded, support.opp_bar,
                           support.weak_opponent) and whether it was published.

  NOT RECORDED — and no honest version can be produced after the fact
    the 20-of-20 consistency board. snapshot_streaks freezes _angle_rows, which calls
    streaks(window=5, min_hits=5). Only the five-game board was ever frozen.
    the mismatch board as a board. Its evidence survives per streak row; the board's own
    ranking does not.

WHAT THIS DOES ABOUT THE SECOND LIST: a walk-forward REPLAY, which is a different claim
from a snapshot and is labelled as one everywhere it appears. For each past fixture it
rebuilds what the board would have shown using that side's games STRICTLY BEFORE that
kick-off, then settles against what actually happened. measure_calibration.py uses the
same two-view method and says why: the ledger is the real record and is small, the
replay is large and is not the record, and quoting one as the other is the mistake.

A REPLAY IS NOT A RECORD, and the three ways it can differ are worth stating because a
reader will otherwise treat the bigger number as the better one:

  - it reads today's stored match history, so any fixture the sync has since corrected
    or back-filled is replayed with data the board did not have;
  - it applies TODAY's rule, so where a board's bar has moved the replay grades the
    current rule against old games rather than the rule that was published;
  - it cannot know what was on screen. A row the board would have produced is not a row
    anybody was shown.

It is still worth having. It is the only way to see a 20-of-20 record at all, and it is
thousands of rows where the snapshots are dozens.

AND A GAP IS NOT A QUIET WEEK. The coverage table prints every week in range and says
how many snapshots it holds, because a week with no freeze and a week with nothing on
look identical in a summary that only counts rows.

Reads the database only. No API calls, no writes.

Run: python history_export.py
     python history_export.py --weeks 20
     python history_export.py --csv projections      # row-level, for a spreadsheet
"""
import argparse
import asyncio
import csv
import io
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from dotenv import load_dotenv

from measure_calibration import wilson
from server import (LOSS, OVER_LINE_FLOOR, WIN, _grade_entries, _grade_projections,
                    _src, _teams_for, db)

ROOT = Path(__file__).parent
load_dotenv(ROOT / ".env")

DEFAULT_WEEKS = 26
# The consistency replay's window: "cleared it in 20 of 20". Configurable because early
# in a season almost nobody has twenty games on file, and a run of zero rows should be
# explained by the history table below rather than read as nothing having happened.
DEFAULT_CONSISTENCY_WINDOW = 20
BAR = "-" * 78

KINDS = ("projections", "streaks", "consistency")


def iso_week(value) -> str:
    """"2026-W41" for a date, an ISO timestamp, or None."""
    if not value:
        return "unknown"
    try:
        d = datetime.fromisoformat(str(value).replace("Z", "+00:00")).date()
    except ValueError:
        try:
            d = date.fromisoformat(str(value)[:10])
        except ValueError:
            return "unknown"
    y, w, _ = d.isocalendar()
    return f"{y}-W{w:02d}"


def _rate(landed, settled):
    """A rate refuses to exist without a denominator — see recordCard.js. None, not 0."""
    return round(100.0 * landed / settled, 1) if settled else None


def tally(rows, result_key="result"):
    landed = sum(1 for r in rows if r.get(result_key) == WIN)
    missed = sum(1 for r in rows if r.get(result_key) == LOSS)
    settled = landed + missed
    # THE RESIDUAL, which is the number that decides whether a hit rate means anything.
    # 89% landed sounds like a result until you notice the board was pricing those rows
    # at 85% — the question is never "how often did it land" but "how often did it land
    # COMPARED WITH WHAT WE SAID". measure_calibration is built entirely around this.
    #
    # Over the SETTLED rows with a stored probability only. Averaging in a pending row's
    # forecast would compare a claim against a result that does not exist yet.
    priced = [r for r in rows if r.get(result_key) in (WIN, LOSS)
              and isinstance(r.get("prob"), (int, float))]
    mean_p = (sum(r["prob"] for r in priced) / len(priced)) if priced else None
    # Snapshots store prob as a percentage on some rows and a fraction on others; the
    # mean tells us which, and guessing wrong would move the residual by a factor of 100.
    if mean_p is not None and mean_p <= 1.0:
        mean_p *= 100
    actual = _rate(sum(1 for r in priced if r[result_key] == WIN), len(priced))
    lo, hi = wilson(landed, settled)
    return {"rows": len(rows), "landed": landed, "missed": missed,
            "settled": settled, "pending": len(rows) - settled,
            "hit_rate": _rate(landed, settled),
            "lo": round(lo, 1) if settled else None,
            "hi": round(hi, 1) if settled else None,
            "priced": len(priced),
            "mean_prob": round(mean_p, 1) if mean_p is not None else None,
            "residual": (round(actual - mean_p, 1)
                         if mean_p is not None and actual is not None else None)}


def projection_tally(rows):
    """Calibration, not a hit rate. The question a projections record answers is whether
    the number was right, and the number is a corner count — so the summary is the mean
    signed error (is it biased) and the mean absolute error (is it accurate). A rate
    would need a line, and no line was published."""
    done = [r for r in rows if r.get("settled") and r.get("error") is not None]
    over = sum(1 for r in done if r.get("beat_projection"))
    return {
        "rows": len(rows), "settled": len(done), "pending": len(rows) - len(done),
        "over": over,
        "over_rate": _rate(over, len(done)),
        "mean_error": round(sum(r["error"] for r in done) / len(done), 2) if done else None,
        "mean_abs_error": round(sum(r["abs_error"] for r in done) / len(done), 2)
                          if done else None,
    }


def projection_weekly(rows):
    buckets = defaultdict(list)
    for r in rows:
        buckets[r.get("week") or "unknown"].append(r)
    return [(w, projection_tally(buckets[w])) for w in sorted(buckets)]


def weekly(rows, week_key="week", result_key="result"):
    """Rows rolled up by ISO week, oldest first."""
    buckets = defaultdict(list)
    for r in rows:
        buckets[r.get(week_key) or "unknown"].append(r)
    return [(w, tally(buckets[w], result_key)) for w in sorted(buckets)]


# ----------------------------- the recorded boards -----------------------------

def projection_row(snap_tag, e, graded):
    """One frozen projection, flattened, with the outcome projection_record attached.

    NO WIN OR LOSS HERE. A projection is a number about a game, not a bet, and inventing
    a verdict would mean inventing a line nobody was offered. projection_record.grade
    already supplies the honest ones — a signed error, its magnitude, and the band the
    projection fell in — so this carries those rather than a second opinion.

    THE KEY IS `actual_total`, which is what grade() returns. The first version of this
    read `total` and therefore reported every single fixture as ungraded: a silent,
    total failure that looked exactly like a season with no results in it yet.

    `error` is actual MINUS projected throughout, so positive means the game had more
    corners than the model said. projection_record fixes that direction deliberately.
    """
    total = graded.get("actual_total")
    proj = e.get("lambda_total")
    return {
        "week": iso_week(e.get("kickoff")),
        "snapshot": snap_tag,
        "kickoff": (e.get("kickoff") or "")[:16],
        "rank": e.get("rank"),
        "league": e.get("league_name"),
        "home": e.get("home"),
        "away": e.get("away"),
        "lambda_total": e.get("lambda_total"),
        "lambda_home": e.get("lambda_home"),
        "lambda_away": e.get("lambda_away"),
        "league_avg_total": e.get("league_avg_total"),
        "corner_edge": e.get("corner_edge"),
        "band": graded.get("band"),
        "actual_total": total,
        "error": graded.get("error"),
        "abs_error": graded.get("abs_error"),
        # Plainly named, so it cannot be mistaken for a settled bet.
        "beat_projection": None if total is None or proj is None else total >= proj,
        "settled": total is not None,
    }


def streak_row(snap_tag, g):
    """One frozen streak row, with the mismatch evidence that was frozen beside it."""
    s = g.get("support") or {}
    return {
        "week": iso_week(g.get("kickoff")),
        "snapshot": snap_tag,
        "kickoff": (g.get("kickoff") or "")[:16],
        "team": g.get("name"),
        "league": g.get("league_id"),
        "opponent": g.get("opponent"),
        "is_home": g.get("is_home"),
        "subject": g.get("subject"),
        "direction": g.get("direction"),
        "line": g.get("line"),
        "hits": g.get("hits"),
        "window": g.get("window"),
        "streak_len": g.get("streak_len"),
        "games_on_file": g.get("games"),
        # THE MISMATCH HALF, frozen with the claim. opp_conceded is what that opponent
        # was shipping at the time, opp_bar the league-relative bar it was judged
        # against, and weak_opponent the verdict. None of the three is recomputable now.
        "opp_conceded": s.get("opp_conceded"),
        "opp_bar": s.get("opp_bar"),
        "league_avg": s.get("league_avg"),
        "weak_opponent": s.get("weak_opponent"),
        "prob": g.get("prob"),
        "lambda": s.get("lambda"),
        "cross_league": g.get("cross_league"),
        # PUBLISHED OR MERELY PRESENT. The whole board is frozen; only some of it was
        # ever shown. Counting the board as the record would be counting claims the site
        # never made, in both directions.
        "qualified": g.get("qualified"),
        "route": g.get("route"),
        "card": g.get("card"),
        "corners": g.get("value"),
        "result": g.get("result"),
    }


# ----------------------------- the replay -----------------------------

def consistency_replay(teams, window=DEFAULT_CONSISTENCY_WINDOW):
    """Walk-forward "cleared it in N of N", settled against the next game.

    THE LINE IS THE MINIMUM OF THE WINDOW, which is what "N of N" means: the highest
    rung every one of those games cleared. Taking a lower line would make the claim
    weaker than the board's and a higher one would make it false.

    STRICTLY BEFORE, and that is the whole discipline. The window for the game played on
    the 11th is the twenty games before the 11th. Sliding one game later — or using the
    team's record as it stands today — grades the model against a version of itself that
    has seen the result.
    """
    floor = OVER_LINE_FLOOR.get("team", 3)
    out = []
    for t in teams:
        ms = sorted(_src(t), key=lambda m: (m.get("date") or ""))
        for i in range(window, len(ms)):
            prior = ms[i - window:i]
            vals = [m.get("corners_for") for m in prior]
            if any(v is None for v in vals):
                continue
            line = min(vals)
            if line < floor:
                continue                      # no rung that all N cleared is worth one
            played = ms[i]
            actual = played.get("corners_for")
            if actual is None:
                continue
            out.append({
                "week": iso_week(played.get("date")),
                "played_at": (played.get("date") or "")[:10],
                "team": t.get("name"),
                "league": t.get("league_id"),
                "opponent": played.get("opponent"),
                "is_home": played.get("home"),
                "line": line,
                "hits": window,
                "window": window,
                "prior_avg": round(sum(vals) / len(vals), 2),
                "corners": actual,
                "result": WIN if actual >= line else LOSS,
            })
    return out


def history_depth(teams):
    """How many games each team has on file — the reason a replay window may be empty."""
    counts = sorted(len(_src(t)) for t in teams)
    if not counts:
        return {}
    mid = counts[len(counts) // 2]
    return {"teams": len(counts), "min": counts[0], "median": mid, "max": counts[-1],
            "with_20": sum(1 for c in counts if c >= 20),
            "with_10": sum(1 for c in counts if c >= 10)}


# ----------------------------- gathering -----------------------------

async def gather(weeks=DEFAULT_WEEKS, window=DEFAULT_CONSISTENCY_WINDOW):
    """Every row of all three, graded. Shared by the harness and the CSV endpoint so the
    download and the summary can never disagree about what the record says."""
    cutoff = (datetime.now(timezone.utc) - timedelta(weeks=weeks)).date().isoformat()

    psnaps = [s for s in await db.projection_snapshots.find({}, {"_id": 0}).to_list(400)
              if (s.get("tag") or "") >= cutoff]
    psnaps.sort(key=lambda s: s.get("tag") or "")
    projections = []
    for s in psnaps:
        graded = await _grade_projections(s.get("entries") or [])
        for e, g in zip(s.get("entries") or [], graded):
            projections.append(projection_row(s.get("tag"), e, g))

    ssnaps = [s for s in await db.streak_snapshots.find({}, {"_id": 0}).to_list(400)
              if (s.get("tag") or "") >= cutoff]
    ssnaps.sort(key=lambda s: s.get("tag") or "")
    streaks = []
    for s in ssnaps:
        entries = s.get("entries") or []
        graded = _grade_entries(entries, await _teams_for(entries))
        streaks += [streak_row(s.get("tag"), g) for g in graded]

    teams = await db.teams.find({}, {"_id": 0}).to_list(5000)
    depth = history_depth(teams)
    # A WINDOW OF N NEEDS N+1 GAMES — N behind the fixture and the fixture itself. The
    # sync stores a rolling twenty per team, so a twenty-game window can never grade
    # anything, and the first run of this printed "nothing recorded in this range" for
    # exactly that reason. That reads as "no side was ever 20 of 20", which is a claim
    # about football; the truth is a claim about our storage. So the window drops to
    # what the stored history can actually support, and the run says that it did.
    used = window
    if depth and depth.get("max", 0) <= window:
        used = max(3, depth["max"] - 1)
    consistency = [r for r in consistency_replay(teams, used)
                   if r["played_at"] >= cutoff]

    return {"projections": projections, "streaks": streaks,
            "consistency": consistency, "window_used": used,
            "coverage": {"projection_tags": [s.get("tag") for s in psnaps],
                         "streak_tags": [s.get("tag") for s in ssnaps]},
            "depth": depth, "window": window, "weeks": weeks}


def to_csv(rows):
    if not rows:
        return ""
    cols = list(rows[0].keys())
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=cols, extrasaction="ignore")
    w.writeheader()
    w.writerows(rows)
    return buf.getvalue()


# ----------------------------- the printed summary -----------------------------

def _weeks_between(tags):
    """Every ISO week from the first tag to the last, so a gap is visible as a gap."""
    if not tags:
        return []
    try:
        start = date.fromisoformat(min(tags))
        end = date.fromisoformat(max(tags))
    except ValueError:
        return []
    out, cur = [], start
    while cur <= end:
        out.append(iso_week(cur.isoformat()))
        cur += timedelta(days=7)
    seen, uniq = set(), []
    for w in out:
        if w not in seen:
            seen.add(w)
            uniq.append(w)
    return uniq


def _show_projections(rows):
    """The projections section reads as calibration because that is what it is."""
    print(f"\n{BAR}\nHIGHEST PROJECTED CORNERS — recorded, every frozen row\n{BAR}")
    print("  No win or loss: a projection is a number, not a bet, and no line was")
    print("  published. `error` is actual minus projected, so + means the game had more")
    print("  corners than the model said. Mean error near zero is a calibrated board.")
    if not rows:
        print("  nothing recorded in this range")
        return
    t = projection_tally(rows)
    print(f"\n  {t['rows']} rows · {t['settled']} settled · {t['pending']} pending")
    if t["mean_error"] is not None:
        print(f"  mean error {t['mean_error']:+.2f} corners · "
              f"mean absolute error {t['mean_abs_error']:.2f} · "
              f"{t['over_rate']}% came in at or above the projection")
    print(f"\n  {'week':<10}{'rows':>6}{'settled':>9}{'mean err':>10}{'abs err':>9}"
          f"{'over':>7}")
    for w, s in projection_weekly(rows):
        me = f"{s['mean_error']:+.2f}" if s["mean_error"] is not None else "-"
        ae = f"{s['mean_abs_error']:.2f}" if s["mean_abs_error"] is not None else "-"
        ov = f"{s['over_rate']}%" if s["over_rate"] is not None else "-"
        print(f"  {w:<10}{s['rows']:>6}{s['settled']:>9}{me:>10}{ae:>9}{ov:>7}")


def _show_weekly(title, rows, note=""):
    print(f"\n{BAR}\n{title}\n{BAR}")
    if note:
        print(f"  {note}")
    if not rows:
        print("  nothing recorded in this range")
        return
    t = tally(rows)
    print(f"  {t['rows']} rows · {t['settled']} settled · {t['landed']} landed · "
          f"{t['pending']} pending")
    if t["hit_rate"] is not None:
        print(f"  hit rate {t['hit_rate']}%  (95% interval {t['lo']}-{t['hi']}%"
              f" on {t['settled']})")
    if t["residual"] is not None:
        verdict = ("beat its own price" if t["residual"] > 0 else
                   "fell short of its own price" if t["residual"] < 0 else "matched it")
        print(f"  the board priced these at {t['mean_prob']}% on average over "
              f"{t['priced']} rows")
        print(f"  RESIDUAL {t['residual']:+.1f} points — {verdict}. This, not the hit "
              f"rate, is the result.")
    print(f"\n  {'week':<10}{'rows':>6}{'settled':>9}{'landed':>8}{'rate':>8}"
          f"{'priced':>8}{'resid':>8}")
    for w, s in weekly(rows):
        rate = f"{s['hit_rate']}%" if s["hit_rate"] is not None else "   -"
        pr = f"{s['mean_prob']}%" if s["mean_prob"] is not None else "   -"
        rs = f"{s['residual']:+.1f}" if s["residual"] is not None else "   -"
        print(f"  {w:<10}{s['rows']:>6}{s['settled']:>9}{s['landed']:>8}{rate:>8}"
              f"{pr:>8}{rs:>8}")


async def run(weeks=DEFAULT_WEEKS, window=DEFAULT_CONSISTENCY_WINDOW, csv_kind=None):
    data = await gather(weeks, window)

    if csv_kind:
        print(to_csv(data.get(csv_kind) or []))
        return

    print("=" * 78)
    print("WHAT THE SITE HAS PUBLISHED, GRADED")
    print("=" * 78)
    print(f"  looking back {weeks} weeks")
    d = data["depth"]
    if d:
        print(f"  match history: {d['teams']} teams, median {d['median']} games "
              f"(min {d['min']}, max {d['max']}); {d['with_20']} with 20+, "
              f"{d['with_10']} with 10+")

    # COVERAGE FIRST, because a week with no snapshot and a week with nothing on look
    # identical in a table that only counts rows.
    pt, st = data["coverage"]["projection_tags"], data["coverage"]["streak_tags"]
    print(f"\n  projection snapshots: {len(pt)} days"
          + (f", {min(pt)} to {max(pt)}" if pt else " — NONE"))
    print(f"  streak snapshots:     {len(st)} days"
          + (f", {min(st)} to {max(st)}" if st else " — NONE"))
    for name, tags in (("projection", pt), ("streak", st)):
        have = {iso_week(t) for t in tags}
        missing = [w for w in _weeks_between(tags) if w not in have]
        if missing:
            print(f"  weeks with NO {name} snapshot: {', '.join(missing)}")

    _show_projections(data["projections"])

    pub = [r for r in data["streaks"] if r.get("qualified")]
    _show_weekly("THE STREAK BOARD — recorded, rows the card actually published",
                 pub, "the mismatch evidence each rested on is in the CSV: "
                      "opp_conceded, opp_bar,\n  weak_opponent.")
    _show_weekly("THE STREAK BOARD — recorded, the whole frozen board",
                 data["streaks"],
                 "wider than what was shown. Counting this as the record would count "
                 "claims\n  the site never made.")

    used = data.get("window_used", window)
    note = ("NOT A RECORD. Rebuilt from each side's games strictly before each "
            "kick-off,\n  under today's rule, from today's stored history. It is "
            "the only way to see this\n  board at all, and it is not evidence of "
            "what anybody was shown.")
    if used != window:
        note += (f"\n\n  ASKED FOR {window} OF {window} AND COULD NOT: a window of N "
                 f"needs N+1 games — N behind\n  the fixture and the fixture itself — "
                 f"and the sync stores at most "
                 f"{(data.get('depth') or {}).get('max', '?')} per team.\n  Dropped to "
                 f"{used} of {used}, which the stored history does support. An empty "
                 f"section here\n  would have read as 'no side was ever "
                 f"{window} of {window}', which is a claim about football;\n  the "
                 f"truth is a claim about our storage.")
    _show_weekly(f"{used} OF {used} — REPLAYED, never snapshotted",
                 data["consistency"], note)

    print(f"\n{BAR}")
    print("HOW TO READ IT. The two recorded sections are the published record and are")
    print("small; the replay is large and is NOT the record. measure_calibration makes")
    print("the same split for the same reason — quoting the replay as the record is the")
    print("mistake, and a hit rate without its denominator is unfalsifiable either way.")
    print("For the row level, pull the CSV: /api/tools/history.csv?kind=projections")
    print("(also streaks, consistency) with the tools token.")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--weeks", type=int, default=DEFAULT_WEEKS)
    ap.add_argument("--window", type=int, default=DEFAULT_CONSISTENCY_WINDOW)
    ap.add_argument("--csv", dest="csv_kind", choices=KINDS, default=None)
    a = ap.parse_args()
    asyncio.run(run(a.weeks, a.window, a.csv_kind))


if __name__ == "__main__":
    main()
