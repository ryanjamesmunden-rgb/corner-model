"""Run the calibration record against the live database and print it.

WHY A SCRIPT AS WELL AS AN ENDPOINT. /api/calibration serves the page, and a page is not a
place to read a diagnosis from: it shows what a visitor needs and leaves out the grid, the
per-line detail at both markets, and the counts that say how much of this is derived. This
prints all of it, and it prints it somewhere that keeps — the harness files the output as a
GitHub issue, so a reading taken today can be compared with one taken in a month.

IT COSTS NOTHING. It reads db.projection_snapshots and db.teams and makes no API-Football
call, which is why it is a `measure` mode rather than one of the probes with its own
endpoint. The whole promise of /tools/measure is that everything on it is free.

Run: python calibration_report.py              (180 days)
     python calibration_report.py --days 60
"""
import asyncio
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

import calibration

ROOT = Path(__file__).parent
load_dotenv(ROOT / ".env")
db = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]

# Imported rather than reimplemented, for the reason every other harness here does it: a
# second copy of the distribution would make this grade a model the site does not run, and
# the two would drift apart silently the first time NB_R moved.
from server import NB_R, nb_ge, poisson_ge  # noqa: E402


def arg(name, fallback):
    return sys.argv[sys.argv.index(name) + 1] if name in sys.argv else fallback


async def load(days: int):
    """Every frozen fixture in the window, one row each, newest freeze winning.

    SAME DEDUPE AS THE ENDPOINT. A fixture three days out is frozen again each morning,
    and counting it three times would weight whichever games sat longest in the window —
    a thumb on the scale that nothing in the output would reveal.
    """
    from datetime import datetime, timezone, timedelta
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).date().isoformat()
    snaps = await db.projection_snapshots.find(
        {"tag": {"$gte": cutoff}}, {"_id": 0}).sort("tag", -1).to_list(400)
    seen, entries = set(), []
    for s in snaps:
        for e in (s.get("entries") or []):
            if e["fixture_id"] in seen:
                continue
            seen.add(e["fixture_id"])
            entries.append(e)
    return snaps, entries


async def actuals_for(entries):
    """What each fixture produced, per side. The home side's own record is the source."""
    ids = list({e["team_id"] for e in entries if e.get("team_id")})
    teams = {t["team_id"]: t for t in
             await db.teams.find({"team_id": {"$in": ids}}, {"_id": 0}).to_list(5000)}
    out = {}
    for e in entries:
        team = teams.get(e.get("team_id")) or {}
        for m in (team.get("real_matches") or []):
            if m.get("opponent") != e.get("opponent"):
                continue
            if e.get("kickoff") and (m.get("date") or "") < e["kickoff"][:10]:
                continue
            h, a = m.get("corners_for"), m.get("corners_against")
            if h is None or a is None:
                break
            out[e["fixture_id"]] = {"home_corners": h, "away_corners": a,
                                    "total_corners": h + a}
            break
    return out


HEAD = (f"  {'band':>12} {'lines':>7} {'games':>6} {'promised':>9} {'actual':>8} "
        f"{'resid':>7} {'95% range':>15}")


def table(rows, label):
    print(f"\n{label}")
    print(HEAD)
    for r in rows:
        key = r.get("band") or (f"{r['line']}+" if r.get("line") is not None else "?")
        if not r["claims"]:
            print(f"  {key:>12} {'-':>7} {'-':>6} {'-':>9} {'-':>8} {'-':>7} {'-':>15}")
            continue
        mark = "  (too few)" if r["thin"] else ""
        print(f"  {key:>12} {r['claims']:>7} {r['fixtures']:>6} {r['promised']:>8.1f}% "
              f"{r['actual']:>7.1f}% {r['residual']:>+7.1f} "
              f"{r['lo']:>6.1f}-{r['hi']:<6.1f}{mark}")


async def main():
    days = int(arg("--days", "180"))
    snaps, entries = await load(days)
    print("=" * 86)
    print(f"CALIBRATION — does a stated percentage come true that often?   ({days} days)")
    print("=" * 86)
    print(f"  {len(snaps)} snapshots, {len(entries)} distinct fixtures frozen before "
          f"kick-off, NB_R={NB_R}")

    if not entries:
        # NOT AN EMPTY TABLE. Nothing frozen and nothing graded look identical in a table
        # of dashes, and they have completely different causes — one is a snapshot job
        # that has stopped, the other a season that has not been played yet.
        print("\n  NOTHING FROZEN in this window. snapshot_projections has not run, or "
              "has refused on stale data — check the schedule before reading anything "
              "into the absence.")
        return

    actuals = await actuals_for(entries)
    rows, ungraded = [], 0
    for e in entries:
        a = actuals.get(e["fixture_id"])
        if not a:
            ungraded += 1
            continue
        for c in calibration.claims_for(e, nb_ge, poisson_ge):
            hit = calibration.grade_claim(c, a)
            if hit is not None:
                rows.append({**c, "hit": hit})

    out = calibration.summarise(rows, ungraded=ungraded)
    o = out["overall"]
    print(f"  {len(actuals)} graded, {ungraded} still without a result")
    print(f"  {o['claims']} lines graded across {o['fixtures']} fixtures")
    stored = o["claims"] - o["derived"]
    print(f"  probabilities: {stored} stored at freeze time, {o['derived']} derived from "
          f"the frozen expected corners")

    table(out["bands"], "BY STATED PROBABILITY — the headline")
    table(out["team_lines"], "BY TEAM LINE (one side's own corners)")
    table(out["match_lines"], "BY MATCH TOTAL")

    print("\nTHE GRID — a level error is flat down a column; a tail error tilts")
    for g in out["grid"]:
        cells = " ".join(f"{c['line']}+:{c['residual']:+.0f}" for c in g["lines"]
                         if not c["thin"])
        if cells:
            print(f"  {g['band']:>12}  {cells}")

    print("\n" + "-" * 86)
    print(f"  VERDICT: {out['verdict']}")
    if out.get("shape"):
        print(f"  SHAPE:   {out['shape']} — {out['shape_note']}")
    print("\n  Read with care: lines on the same fixture are NOT independent — a game "
          "going to\n  twelve corners lands 3+, 4+ and 5+ together — so the fixture count "
          "is much nearer\n  the real sample size than the line count is.")


if __name__ == "__main__":
    asyncio.run(main())
