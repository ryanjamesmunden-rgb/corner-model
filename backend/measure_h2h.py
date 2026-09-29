"""Offline: how much head-to-head history does the results cache actually hold?

THE QUESTION THIS EXISTS TO ANSWER. The Previous meetings panel reads db.fixture_stats
and renders nothing when a pairing has no stored meeting — deliberately, because an empty
panel would have to choose between "no history on file" and "they have never met" and
only one of those is true. That is the right behaviour and it is also invisible: a panel
that never appears looks exactly like a panel that was never built.

So this counts. Not whether the panel is correct — h2h.py's own tests do that — but
whether there is anything for it to show, per league, on the fixtures actually on the
board right now.

WHY THE ANSWER IS NOT OBVIOUS FROM THE CODE. fixture_stats is a persistent upsert cache:
it was never swept, so it holds whatever the sync has fetched since the app was first
pointed at each league. sync_real fetches statistics for the most recent STATS_CAP (250)
finished fixtures per league per run, and tops up from the PREVIOUS season only while the
current one has produced fewer than that. Both conditions moved over time, per league, so
the depth of the cache is a fact about this database's history and cannot be read off the
source. It has to be measured.

WHAT A THIN RESULT WOULD MEAN, since it is the finding worth acting on: if most upcoming
fixtures have no stored meeting, the panel is shipping dark and the fix is in the SYNC —
retaining more history — not in the panel.

READS ONLY. No API calls, no writes.

Run: python measure_h2h.py
     python measure_h2h.py --league eng-pl
"""
import asyncio
import os
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

import h2h

ROOT = Path(__file__).parent
load_dotenv(ROOT / ".env")
db = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]

# Buckets for "how many meetings does this fixture have". The 0 bucket is the whole point;
# 3+ is where the panel starts carrying an unbeaten run worth printing.
BUCKETS = ("0", "1", "2", "3+")


def pair_key(a, b):
    """The unordered pairing, so a home-and-away tie indexes to one key.

    RETURNS None RATHER THAN A TUPLE OF Nones when either id is missing. A synthesized
    fixture carries a string team id and no provider id, and letting those collapse into a
    single (None, None) key would file every such fixture as the same pairing — which
    would report history for teams that have never played.
    """
    if not isinstance(a, int) or not isinstance(b, int):
        return None
    return (a, b) if a <= b else (b, a)


def index_meetings(docs):
    """Every stored fixture, grouped by the pairing that played it."""
    out = defaultdict(list)
    for d in docs:
        key = pair_key(d.get("home_id"), d.get("away_id"))
        if key:
            out[key].append(d)
    return out


def bucket(n):
    return "0" if n == 0 else "1" if n == 1 else "2" if n == 2 else "3+"


def graded(doc):
    """Does this stored meeting carry a result, or only corners?

    An ungraded meeting still shows in the panel — the corners are real — but it STOPS an
    unbeaten run rather than being stepped over, so a cache full of them produces a panel
    with history and no runs. That is a different shortfall from having no history, and it
    has a different fix (backfill_goals), so it is counted separately.
    """
    return doc.get("home_goals") is not None and doc.get("away_goals") is not None


def fixture_coverage(fixtures, api_by_team_id, index):
    """For each upcoming fixture, how many stored meetings its pairing has."""
    rows = []
    for fx in fixtures:
        key = pair_key(api_by_team_id.get(fx.get("home_team_id")),
                       api_by_team_id.get(fx.get("away_team_id")))
        met = index.get(key, []) if key else []
        rows.append({
            "fixture_id": fx.get("fixture_id"),
            "league_id": fx.get("league_id"),
            "home": fx.get("home_name"), "away": fx.get("away_name"),
            "date": fx.get("date"),
            # No provider ids at all is a DIFFERENT finding from no meetings: those
            # fixtures are synthesized and could never have history, so counting them as
            # "uncovered" would blame the cache for something the sync did.
            "resolvable": key is not None,
            "meetings": len(met),
            "graded": sum(1 for d in met if graded(d)),
        })
    return rows


def unbeaten_hits(rows, index, api_by_team_id, fixtures_by_id):
    """How many fixtures would actually PRINT an unbeaten run.

    Runs the shipped code (h2h.build) rather than re-deriving the rule here. That is the
    right way round for a coverage probe: the number wanted is what the panel will show,
    so a probe with its own copy of the rule would answer a question nobody asked and
    would keep agreeing with itself after the panel changed.
    """
    hits = 0
    for r in rows:
        if not r["meetings"]:
            continue
        fx = fixtures_by_id.get(r["fixture_id"]) or {}
        home_api = api_by_team_id.get(fx.get("home_team_id"))
        key = pair_key(home_api, api_by_team_id.get(fx.get("away_team_id")))
        built = h2h.build(index.get(key, []), home_api, r["home"] or "", r["away"] or "")
        if built["unbeaten"]["home_team"] or built["unbeaten"]["away_team"]:
            hits += 1
    return hits


def verdict(rows, total_stats):
    """What to do about it, if anything."""
    usable = [r for r in rows if r["resolvable"]]
    if not total_stats:
        return ("The results cache is EMPTY. Nothing has ever been synced into it, so the "
                "panel cannot appear anywhere. This is a sync problem, not a panel one.")
    if not usable:
        return ("No upcoming fixture carries a provider team id, so no pairing can be "
                "looked up. Every fixture on the board is synthesized — check sync_real "
                "before reading anything else here.")
    covered = [r for r in usable if r["meetings"]]
    pct = 100.0 * len(covered) / len(usable)
    if pct >= 60:
        return (f"{pct:.0f}% of upcoming fixtures have history on file. The panel is "
                f"doing its job; nothing to change.")
    if pct >= 25:
        return (f"Only {pct:.0f}% of upcoming fixtures have a stored meeting, so the panel "
                f"is absent on most of the board. That is the cache's depth, not a fault "
                f"— it holds what has been synced since this app was pointed at each "
                f"league. Worth widening only if the panel is meant to be a headline "
                f"feature rather than a bonus where history exists.")
    return (f"THE PANEL IS EFFECTIVELY DARK: only {pct:.0f}% of upcoming fixtures have a "
            f"stored meeting. The fix is in the SYNC — retaining more finished fixtures, "
            f"or topping up from previous seasons — and not in the panel, which is "
            f"correctly showing nothing where it knows nothing.")


async def run(league=None):
    now = datetime.now(timezone.utc)
    print("HEAD-TO-HEAD COVERAGE — is there history for the Previous meetings panel to show?")
    print("(reads db.fixture_stats, db.fixtures and db.teams; no API calls, no writes)\n")

    stats = await db.fixture_stats.find(
        {}, {"_id": 0, "home_id": 1, "away_id": 1, "date": 1, "league_id": 1,
             "home_goals": 1, "away_goals": 1}).to_list(200000)
    print(f"stored fixtures in the results cache: {len(stats)}")
    if stats:
        dates = sorted(d["date"] for d in stats if d.get("date"))
        if dates:
            print(f"  oldest {dates[0][:10]}   newest {dates[-1][:10]}")
        no_goals = sum(1 for d in stats if not graded(d))
        print(f"  carrying a result: {len(stats) - no_goals}   corners only: {no_goals}")
        if no_goals:
            print("  (corners-only rows still show in the panel; they STOP an unbeaten run "
                  "rather than being stepped over — backfill_goals fills them)")

    index = index_meetings(stats)
    print(f"  distinct pairings with at least one meeting: {len(index)}")

    fq = {"status": "upcoming"}
    if league:
        fq["league_id"] = league
    fixtures = await db.fixtures.find(fq, {"_id": 0}).to_list(5000)
    teams = await db.teams.find({}, {"_id": 0, "team_id": 1, "api_team_id": 1}).to_list(5000)
    api_by_team_id = {t["team_id"]: t.get("api_team_id") for t in teams}
    fixtures_by_id = {f.get("fixture_id"): f for f in fixtures}

    rows = fixture_coverage(fixtures, api_by_team_id, index)
    usable = [r for r in rows if r["resolvable"]]
    print(f"\nupcoming fixtures: {len(rows)}   league={league or 'all'}")
    if len(usable) != len(rows):
        print(f"  {len(rows) - len(usable)} carry no provider team id (synthesized) and are "
              f"excluded below — they could never have history")
    if not usable:
        print(f"\n{'=' * 78}\nVERDICT\n{'=' * 78}\n  {verdict(rows, len(stats))}")
        return

    counts = Counter(bucket(r["meetings"]) for r in usable)
    print(f"\nMEETINGS ON FILE, per upcoming fixture")
    for b in BUCKETS:
        n = counts.get(b, 0)
        pct = 100.0 * n / len(usable)
        bar = "#" * int(round(pct / 4))
        print(f"  {b:>3}  {n:5}  {pct:5.1f}%  {bar}")

    covered = [r for r in usable if r["meetings"]]
    with_runs = unbeaten_hits(usable, index, api_by_team_id, fixtures_by_id)
    print(f"\n  fixtures that WILL show the panel: {len(covered)}/{len(usable)} "
          f"({100.0 * len(covered) / len(usable):.0f}%)")
    print(f"  of those, showing an unbeaten run (>= {h2h.MIN_UNBEATEN_RUN} meetings "
          f"unbeaten): {with_runs}")

    # PER LEAGUE, because the cache was filled at a different time for each one and an
    # overall percentage can hide a league with nothing at all in it.
    by_league = defaultdict(lambda: {"n": 0, "covered": 0, "meetings": 0})
    for r in usable:
        e = by_league[r["league_id"]]
        e["n"] += 1
        e["covered"] += 1 if r["meetings"] else 0
        e["meetings"] += r["meetings"]
    print(f"\n{'league':>10}  {'fixtures':>8}  {'with history':>12}  {'%':>5}  {'avg meetings':>12}")
    for lid in sorted(by_league):
        e = by_league[lid]
        pct = 100.0 * e["covered"] / e["n"]
        avg = e["meetings"] / e["n"]
        flag = "   <- nothing on file" if not e["covered"] else ""
        print(f"{lid:>10}  {e['n']:8}  {e['covered']:12}  {pct:5.0f}  {avg:12.2f}{flag}")

    deepest = sorted(usable, key=lambda r: -r["meetings"])[:8]
    if deepest and deepest[0]["meetings"]:
        print(f"\nDEEPEST HISTORIES on the board right now")
        for r in deepest:
            if not r["meetings"]:
                break
            ug = r["meetings"] - r["graded"]
            note = f"  ({ug} without a result)" if ug else ""
            print(f"  {r['meetings']:2} meetings  {(r['date'] or '')[:10]}  "
                  f"{r['home']} v {r['away']}{note}")

    print(f"\n{'=' * 78}\nVERDICT\n{'=' * 78}")
    print(f"  {verdict(rows, len(stats))}")
    print(f"\n  (measured {now.isoformat()[:19]}Z)")


def main():
    args = sys.argv[1:]

    def opt(flag, default=None):
        return args[args.index(flag) + 1] if flag in args else default

    asyncio.run(run(league=opt("--league")))


if __name__ == "__main__":
    main()
