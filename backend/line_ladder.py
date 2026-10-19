"""Offline: how many corner lines landed, and how many would have at one line lower?

THE QUESTION, ASKED AFTER A GOOD WEEKEND. "It looks like we won quite a few and cleared
the line by 5 or 6 on some of them." That is two separate claims and they point in
opposite directions, which is why this exists rather than a spreadsheet count:

  * HOW MANY LANDED is a record. It is already published; /api/results grades it.
  * HOW MANY WOULD HAVE LANDED ONE LINE LOWER is free information and always positive.
    4+ lands at least as often as 5+ in every sample ever taken, however bad the model
    is, so the count on its own establishes nothing at all.
  * CLEARING BY 5 OR 6 is the finding. It says the recommended lines were far below what
    the games delivered — the board being timid, not lucky — and the fix for that is
    HIGHER lines, which is the opposite of what the first two numbers suggest.

So this reports the whole ladder, one rung up as well as two down, and the margin
distribution underneath it. See ladder.py for the reasoning; the arithmetic is there and
tested, and this file is the half that reads the database.

WHERE THE ROWS COME FROM — both ledgers, deduplicated the same way /api/results does it:

  db.streak_snapshots   the board frozen before kick-off, daily, overlapping windows. One
                        claim per fixture, newest freeze wins, or a Sunday game frozen on
                        Friday and Saturday lands twice in the rate.
  db.posted_angles      angles posted by hand. ONLY `before_kickoff` ones are counted,
                        because the rest are memories and a rate you can add winners to
                        afterwards is not a rate.

THE SETTLE RULE IS CROSS-CHECKED, NOT TRUSTED. ladder.py reimplements server's
settle_streak_leg so its own tests can run without importing the app, and a silent drift
between the two would produce a confident, wrong record. So the first thing this does is
settle a grid both ways and refuse to print anything if they ever disagree.

NO PRICES, STATED LOUDLY. A line lower is a shorter price and this counts outcomes. Where
the ledger holds a price the units are reported beside the counts; most rows predate that
capture, so the honest answer is usually counts alone. A counterfactual hit rate read as
profit is the easiest way to talk yourself down the ladder one rung at a time.

Run: python line_ladder.py                 (the default window)
     python line_ladder.py --days 7        (last weekend only)
     python line_ladder.py --league eng-l1
"""
import asyncio
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

from dotenv import load_dotenv

import ladder as L
from server import (LOSS, _grade_entries, _teams_for, db, settle_streak_leg,
                    streak_line_label)

ROOT = Path(__file__).parent
load_dotenv(ROOT / ".env")

DEFAULT_DAYS = 10
BAR = "-" * 78


def check_settle_rule():
    """Refuse to report if the pure copy and server's own ever disagree.

    A GRID, NOT A SPOT CHECK. The disagreement that matters is the under's exact-line
    void, which is one cell of the table and the one a reimplementation gets wrong.
    """
    bad = []
    for direction in ("over", "under"):
        for line in range(0, 15):
            for value in range(0, 30):
                mine = L.settle_at(value, line, direction)
                theirs = settle_streak_leg(value, line, direction)
                if mine != theirs:
                    bad.append((direction, line, value, mine, theirs))
    if bad:
        print("REFUSING TO REPORT: ladder.settle_at disagrees with "
              "server.settle_streak_leg")
        for d, line, v, mine, theirs in bad[:10]:
            print(f"  {d} {line} vs {v}: ladder={mine} server={theirs}")
        print(f"  ...{len(bad)} cells differ" if len(bad) > 10 else "")
        raise SystemExit(1)


def _within(value, cutoff):
    return bool(value) and str(value)[:10] >= cutoff


async def collect(days: int, league_id=None):
    """Every claim that was on record before kick-off, graded, deduplicated."""
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).date().isoformat()

    snaps = await db.streak_snapshots.find({}, {"_id": 0}).sort("tag", -1).to_list(400)
    entries = [e for s in snaps for e in (s.get("entries") or [])]
    posted = await db.posted_angles.find({}, {"_id": 0}).sort("kickoff", -1).to_list(400)
    # The hand-posted half, filtered to the ones that were still predictions.
    posted = [p for p in posted if p.get("before_kickoff")]

    all_rows = entries + posted
    if league_id and league_id != "all":
        all_rows = [r for r in all_rows if r.get("league_id") == league_id]
    all_rows = [r for r in all_rows if _within(r.get("kickoff"), cutoff)]
    if not all_rows:
        return [], {"snapshots": len(snaps), "posted": len(posted), "cutoff": cutoff}

    teams = await _teams_for(all_rows)
    graded_rows = _grade_entries(all_rows, teams)

    # ONE CLAIM PER FIXTURE+LINE, newest first — the dedup /api/results performs for the
    # same reason: the snapshot window overlaps by design, so the same Sunday game is
    # frozen on consecutive days and would otherwise be counted once per day it sat there.
    seen, fresh = set(), []
    for r in graded_rows:
        key = (r.get("fixture_id"), r.get("team_id"), r.get("line"),
               r.get("direction"), r.get("subject"))
        if key in seen:
            continue
        seen.add(key)
        fresh.append(r)
    meta = {"snapshots": len(snaps), "posted": len(posted), "cutoff": cutoff,
            "before_dedup": len(graded_rows)}
    return fresh, meta


def print_ladder(rows):
    rungs = L.ladder(rows)
    print(f"\n{BAR}\nTHE LADDER — the same games settled at four different lines\n{BAR}")
    print(f"  {'line':>12} {'settled':>8} {'won':>5} {'lost':>5} {'rate':>7} {'vs rec':>7}")
    for r in rungs:
        label = {1: "one higher", 0: "AS RECOMMENDED",
                 -1: "one lower", -2: "two lower"}.get(r["offset"], str(r["offset"]))
        rate = f"{r['rate']:.1f}%" if r["rate"] is not None else "   -  "
        gained = "" if r["offset"] == 0 else f"{r['gained']:+d}"
        print(f"  {label:>12} {r['settled']:8} {r['won']:5} {r['lost']:5} {rate:>7} {gained:>7}")
    print("\n  A lower line wins more BY CONSTRUCTION — 4+ cannot land less often than")
    print("  5+. The column that carries information is the margin table below.")
    return rungs


def print_margins(rows):
    m = L.margins(rows)
    print(f"\n{BAR}\nTHE MARGINS — how far each result cleared the line we asked for\n{BAR}")
    if not m:
        print("  nothing graded in the window.")
        return None
    print(f"  {'margin':>8} {'n':>5}   (negative = missed)")
    for margin, n in sorted(m["counts"].items()):
        bar = "#" * min(n, 50)
        print(f"  {margin:+8d} {n:5}   {bar}")
    print(f"\n  cleared: {m['cleared']}   missed: {m['missed']}")
    if m["mean_cleared"] is not None:
        print(f"  the winners cleared by {m['mean_cleared']} corners on average")
    if m["mean_missed"] is not None:
        print(f"  the losers missed by {abs(m['mean_missed'])} on average")
    print(f"  {m['comfortable']} winners cleared by 3 or more — the board could have asked")
    print(f"     for a higher line on every one of those and still won")
    print(f"  {m['by_one']} losers missed by exactly one")
    return m


def print_by_line(rows):
    groups = L.by_line(rows)
    if len(groups) < 2:
        return
    print(f"\n{BAR}\nBY RECOMMENDED LINE — a board can be timid at one line and right at "
          f"another\n{BAR}")
    print(f"  {'line':>6} {'n':>4} {'rate':>7} {'one lower':>10} {'cleared by':>11}")
    for g in groups:
        rec = next((r for r in g["rungs"] if r["offset"] == 0), None)
        low = next((r for r in g["rungs"] if r["offset"] == -1), None)
        rate = f"{rec['rate']:.1f}%" if rec and rec["rate"] is not None else "   -  "
        lower = f"{low['rate']:.1f}%" if low and low["rate"] is not None else "   -  "
        mean = g["margins"]["mean_cleared"] if g["margins"] else None
        print(f"  {str(g['line']) + '+':>6} {g['n']:4} {rate:>7} {lower:>10} "
              f"{(f'{mean:+.1f}' if mean is not None else '   -'):>11}")


def print_losses(rows):
    """The misses, worst first. "A few losses that were freak results" is a claim this
    can check: a loss that missed by one is a near thing, and a loss that missed by five
    is the model being wrong about the game."""
    losses = [r for r in L.graded(rows)
              if L.settle_at(r["value"], r["line"], r.get("direction", "over")) == LOSS]
    if not losses:
        print(f"\n{BAR}\nTHE MISSES — none in the window\n{BAR}")
        return
    losses.sort(key=lambda r: L.margin_of(r))
    print(f"\n{BAR}\nTHE MISSES — worst first, so a freak result can be told from a bad "
          f"call\n{BAR}")
    print(f"  {'by':>4}  {'asked for':>12}  {'got':>4}  team vs opponent")
    for r in losses[:25]:
        label = streak_line_label(r["line"], r.get("direction", "over"))
        print(f"  {L.margin_of(r):+4d}  {label:>12}  {r['value']:4}  "
              f"{r.get('name', '?')} v {r.get('opponent', '?')}")
    if len(losses) > 25:
        print(f"  ...and {len(losses) - 25} more")


def print_totals(rows):
    """THE BARNSLEY V CAMBRIDGE QUESTION, counted rather than remembered.

    One 11-11 game is an anecdote. Every graded fixture with both sides known is a
    sample, and the table says what a flat match-total line would have done on the games
    the board had already picked for other reasons.
    """
    totals = L.fixture_totals(rows)
    usable = [t for t in totals if t["total"] is not None]
    both = [t for t in usable if t["both_on_board"]]
    print(f"\n{BAR}\nMATCH TOTALS — what a total-corners line would have done\n{BAR}")
    print(f"  {len(totals)} fixtures in the window, {len(usable)} with both sides' counts "
          f"known,\n  {len(both)} of those on the board from BOTH ends.")
    if not usable:
        print("\n  Not enough paired rows to say anything. A total needs both sides of a")
        print("  game; one count plus a guess at the other is not a match total.")
        return totals
    print(f"\n  the biggest totals in the window:")
    print(f"  {'total':>6}  {'date':>10}  fixture")
    for t in usable[:12]:
        mark = "  <- both sides on the board" if t["both_on_board"] else ""
        print(f"  {t['total']:6}  {t['date']:>10}  {' v '.join(t['teams'][:2])}{mark}")

    print(f"\n  a flat over-N on these {len(usable)} fixtures:")
    print(f"  {'line':>8} {'won':>5} {'lost':>5} {'rate':>7}")
    for r in L.total_ladder(usable, lines=range(16, 25)):
        print(f"  {str(r['line']) + '+':>8} {r['won']:5} {r['lost']:5} {r['rate']:6.1f}%")
    if both:
        print(f"\n  ...and on the {len(both)} that were on the board from both ends:")
        print(f"  {'line':>8} {'won':>5} {'lost':>5} {'rate':>7}")
        for r in L.total_ladder(both, lines=range(16, 25)):
            print(f"  {str(r['line']) + '+':>8} {r['won']:5} {r['lost']:5} {r['rate']:6.1f}%")
    print("\n  READ THIS AS A BIASED SAMPLE, because it is one by construction: these are")
    print("  games chosen for having corner-winning sides in them, so the rate is not a")
    print("  league-wide price. It answers 'would a total line have landed on the games we")
    print("  were already on', and nothing wider than that.")
    return totals


def print_teams(rows):
    """Which teams keep turning up, and how they have actually done.

    "Track certain teams to see how they are performing" — this is that, in text, from the
    rows already graded. A team on the board four times at 2 of 4 is a different
    proposition from one on it once and right.
    """
    by_team = defaultdict(list)
    for r in L.graded(rows):
        by_team[r.get("name") or "?"].append(r)
    repeat = {k: v for k, v in by_team.items() if len(v) >= 2}
    if not repeat:
        return
    print(f"\n{BAR}\nTEAMS ON THE BOARD MORE THAN ONCE\n{BAR}")
    print(f"  {'n':>3} {'won':>4} {'rate':>7} {'cleared by':>11}  team")
    ranked = sorted(repeat.items(),
                    key=lambda kv: (-len(kv[1]), kv[0]))
    for name, rs in ranked[:30]:
        t = L.tally([{**r, "result": L.settle_at(r["value"], r["line"],
                                                 r.get("direction", "over"))} for r in rs])
        m = L.margins(rs)
        rate = f"{t['rate']:.1f}%" if t["rate"] is not None else "   -  "
        mean = f"{m['mean_cleared']:+.1f}" if m and m["mean_cleared"] is not None else "   -"
        print(f"  {len(rs):3} {t['won']:4} {rate:>7} {mean:>11}  {name}")


async def run(days=DEFAULT_DAYS, league_id=None):
    check_settle_rule()
    rows, meta = await collect(days, league_id)
    print(f"LINE LADDER — claims with a kick-off on or after {meta['cutoff']}"
          + (f", {league_id} only" if league_id and league_id != "all" else ""))
    print(f"{meta['snapshots']} snapshots and {meta['posted']} hand-posted angles read; "
          f"{len(rows)} claims in the window"
          + (f" ({meta.get('before_dedup', 0) - len(rows)} duplicate freezes dropped)"
             if meta.get("before_dedup") else ""))
    if not rows:
        print("\nNothing to measure. Either the window is too short or the snapshot did")
        print("not run — check /api/health for the scheduler before reading anything")
        print("into an empty board.")
        return
    g = L.graded(rows)
    print(f"{len(g)} of them have a played result; {len(rows) - len(g)} are still pending.")

    print_ladder(rows)
    print_margins(rows)
    print_by_line(rows)
    print_losses(rows)
    print_totals(rows)
    print_teams(rows)

    priced = [r for r in g if (r.get("price") or 0) > 1]
    print(f"\n{BAR}")
    print(f"PRICES: {len(priced)} of {len(g)} graded claims carry one. Every rate above is")
    print("a COUNT. A line lower is a shorter price, so none of this says a lower rung")
    print("was worth backing — that needs the odds for each rung, which the ledger does")
    print("not hold. Read the margin table for whether the lines were set too low.")


def main():
    args = sys.argv[1:]

    def opt(flag, default=None, cast=str):
        return cast(args[args.index(flag) + 1]) if flag in args else default

    asyncio.run(run(days=opt("--days", DEFAULT_DAYS, int), league_id=opt("--league")))


if __name__ == "__main__":
    main()
