"""Offline: was each settled pick graded against the right team?

WHY THIS EXISTS. measure_calibration (2026-09-21) found the model calibrated over 11,590
replayed spots — residual +0.1 — while the published ledger came in 16 points under its
own promise. One line carries most of that gap:

    ledger, line 3+    6 of 15   promised 75.3%   -35.3
    replay, line 3+    4,326     promised 67.9%    +3.8   (it OVER-delivers)

Both cannot be true, and 40% on 3+ team corners is not plausible on its face: a side
fails to win three corners in about one match in five, not three in five. Under the
model's own 75.3% that result has p = 0.004. Something other than luck is in it.

THE SUSPECT: settlement.py::_pick_side decides which team a pick is on by TOKEN OVERLAP
ON TEAM NAMES, falling back to the stored venue. Grade the wrong side and you record the
OPPONENT's corner count. That produces exactly this signature — a low line failing far
more often than a low line can — and it is invisible in the ledger, because the pick
still settles cleanly to a confident won/lost.

HOW THIS CHECKS IT, and why it is independent: it re-derives the side from TEAM IDS.

    pick.team -> db.teams -> api_team_id
    pick.fixture_id -> db.fixtures -> home_team_id / away_team_id -> api ids
    side = whichever of the two the pick's team actually is

Names never enter it. So this is a genuinely separate path from the one under suspicion,
rather than the same logic asking itself whether it was right. The corner counts come
from db.fixture_stats keyed by the API fixture id — the same cache settlement read, but
the SIDE MAPPING is what is being tested, not the counts.

NO API CALLS AND NO WRITES. It reads four collections and prints. A settlement bug is
found by reading, and a script that both diagnoses and repairs is one that can quietly
turn a misreading into corrupted history. If this finds something, the fix is a
deliberate, separate step.

WHAT THE RESULT MEANS:
  * Disagreements found -> the ledger's 52.3% is partly a grading artefact. The regraded
    hit rate printed at the end is what the record should have said, and _pick_side needs
    fixing before any conclusion is drawn from the published number.
  * NO disagreements -> the hypothesis is dead and the 3+ anomaly is something else. The
    next suspects would be the line the pick was stored at versus the line it was priced
    at, or `prob` being read off a different line than `line`.

Run: python audit_settlement.py
     python audit_settlement.py --league eng-pl
     python audit_settlement.py --line 3        (only picks at that line)
"""
import asyncio
import os
import sys
from collections import defaultdict
from pathlib import Path

from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

ROOT = Path(__file__).parent
load_dotenv(ROOT / ".env")
db = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]

SETTLED = {"won", "lost", "half_won", "half_lost"}


# --------------------------------------------------------------------------
# Pure
# --------------------------------------------------------------------------

def api_team_id(internal):
    """Internal team ids are '<league>-<apiTeamId>' — 'eng-pl-42' -> 42.

    Same rule as settlement._api_team_id, restated rather than imported so this audit
    does not depend on the module it is auditing."""
    if not internal:
        return None
    try:
        return int(str(internal).rsplit("-", 1)[-1])
    except (TypeError, ValueError):
        return None


def derive_side(team_api, home_api, away_api):
    """Which side the pick's team is on, by id. None when it is on neither — which is
    itself a finding: the pick was graded against a fixture it is not in."""
    if team_api is None or (home_api is None and away_api is None):
        return None
    if team_api == home_api:
        return "home"
    if team_api == away_api:
        return "away"
    return None


def corners_for(stats, side):
    if not stats or side not in ("home", "away"):
        return None
    return stats.get(f"{side}_corners")


def hit_at(line, corners):
    """A team line stored as 'X+' is Over (X - 0.5): X itself counts."""
    if line is None or corners is None:
        return None
    return 1 if corners >= line else 0


def recorded_hit(pick):
    status = (pick.get("status") or "").lower()
    if status in ("won", "half_won"):
        return 1
    if status in ("lost", "half_lost"):
        return 0
    return None


def audit_one(pick, fixture, stats, team_api):
    """Everything this pick disagrees with itself about. Pure, so it is testable."""
    home_api = (stats or {}).get("home_id")
    away_api = (stats or {}).get("away_id")
    if home_api is None and away_api is None and fixture:
        home_api = api_team_id(fixture.get("home_team_id"))
        away_api = api_team_id(fixture.get("away_team_id"))

    true_side = derive_side(team_api, home_api, away_api)
    stored_side = pick.get("settled_side") or pick.get("venue")
    true_corners = corners_for(stats, true_side)
    stored_corners = pick.get("result_corners")
    line = pick.get("line")

    problems = []
    if team_api is None:
        problems.append("team not resolvable to an api id")
    elif true_side is None:
        problems.append("pick's team is in neither side of the fixture it settled against")
    else:
        if stored_side and stored_side != true_side:
            problems.append(f"graded as {stored_side}, is actually {true_side}")
        if (true_corners is not None and stored_corners is not None
                and true_corners != stored_corners):
            problems.append(f"recorded {stored_corners} corners, fixture says {true_corners}")

    was = recorded_hit(pick)
    should = hit_at(line, true_corners)
    if was is not None and should is not None and was != should:
        problems.append(f"graded {'WON' if was else 'LOST'}, should be "
                        f"{'WON' if should else 'LOST'}")

    return {"team": pick.get("team"), "line": line, "date": pick.get("date"),
            "league_id": pick.get("league_id"),
            "home": pick.get("home"), "away": pick.get("away"),
            "stored_side": stored_side, "true_side": true_side,
            "stored_corners": stored_corners, "true_corners": true_corners,
            "was": was, "should": should, "problems": problems,
            "checkable": team_api is not None and true_corners is not None}


def tally(rows):
    """Recorded record vs regraded record, over the rows that could be checked."""
    checkable = [r for r in rows if r["checkable"] and r["was"] is not None
                 and r["should"] is not None]
    if not checkable:
        return None
    n = len(checkable)
    was = sum(r["was"] for r in checkable)
    should = sum(r["should"] for r in checkable)
    return {"n": n, "was": was, "should": should,
            "was_rate": was / n * 100, "should_rate": should / n * 100,
            "changed": sum(1 for r in checkable if r["was"] != r["should"])}


# --------------------------------------------------------------------------
# I/O
# --------------------------------------------------------------------------

async def team_api_ids():
    """name -> api id, and (league, name) -> api id.

    Both, because a CUP pick carries `ucl` as its league while its team doc lives under
    the domestic league — a (league, name) lookup alone silently fails on every European
    tie, and an audit that cannot resolve a pick reports nothing rather than a problem."""
    by_pair, by_name = {}, defaultdict(set)
    async for t in db.teams.find({}, {"_id": 0, "name": 1, "league_id": 1, "api_team_id": 1}):
        api = t.get("api_team_id")
        if api is None:
            continue
        by_pair[(t.get("league_id"), t.get("name"))] = api
        by_name[t.get("name")].add(api)
    return by_pair, by_name


def resolve_team(pick, by_pair, by_name):
    api = by_pair.get((pick.get("league_id"), pick.get("team")))
    if api is not None:
        return api
    # Unambiguous by name only — two clubs sharing a name across leagues is exactly the
    # case where guessing would invent a finding, so it declines instead.
    candidates = by_name.get(pick.get("team")) or set()
    return next(iter(candidates)) if len(candidates) == 1 else None


async def run(league_id=None, only_line=None):
    q = {"auto": True, "status": {"$in": sorted(SETTLED)}}
    if league_id and league_id != "all":
        q["league_id"] = league_id
    if only_line is not None:
        q["line"] = only_line
    picks = await db.picks.find(q, {"_id": 0}).to_list(20000)
    print("SETTLEMENT AUDIT — was each pick graded against the right team?")
    print("(reads only; nothing here writes to the database)\n")
    if not picks:
        print("no settled auto picks match — nothing to audit")
        return

    by_pair, by_name = await team_api_ids()
    rows = []
    for p in picks:
        stats = None
        if p.get("api_fixture_id"):
            stats = await db.fixture_stats.find_one({"_id": p["api_fixture_id"]}, {"_id": 0})
        fixture = None
        if p.get("fixture_id"):
            fixture = await db.fixtures.find_one({"fixture_id": p["fixture_id"]}, {"_id": 0})
        rows.append(audit_one(p, fixture, stats, resolve_team(p, by_pair, by_name)))

    checkable = [r for r in rows if r["checkable"]]
    bad = [r for r in rows if r["problems"]]
    print(f"settled picks: {len(rows)}   independently checkable: {len(checkable)}")
    unchecked = [r for r in rows if not r["checkable"]]
    if unchecked:
        print(f"could not check {len(unchecked)} (no cached fixture stats, or the team "
              f"name did not resolve to one api id)")
        for r in unchecked[:10]:
            print(f"    {r['date']}  {r['team']} {r['line']}+  ({r['home']} v {r['away']})")

    if not bad:
        print("\nNo disagreements. Every checkable pick was graded against the right team,")
        print("with the fixture's own corner count, and the recorded result follows from it.")
        print("\nSo _pick_side is NOT the cause of the 3+ anomaly. Next suspects: the line")
        print("the pick was STORED at versus the line it was PRICED at, and whether"
              " `model_prob`\nwas read off the same line as `line`.")
    else:
        print(f"\n{len(bad)} pick(s) disagree with the fixture:\n")
        for r in bad:
            print(f"  {r['date']}  {r['team']} {r['line']}+   {r['home']} v {r['away']}"
                  f"   [{r['league_id']}]")
            for p in r["problems"]:
                print(f"      - {p}")

    t = tally(rows)
    if t:
        print(f"\nrecorded:  {t['was']} of {t['n']} · {t['was_rate']:.1f}%")
        print(f"regraded:  {t['should']} of {t['n']} · {t['should_rate']:.1f}%"
              f"   ({t['changed']} result(s) change)")
        if t["changed"]:
            print("\nThe published record is wrong by the difference above. Fix _pick_side"
                  "\nbefore drawing any conclusion from the ledger — and re-settle these"
                  "\npicks deliberately, not from this script.")

    by_line = defaultdict(list)
    for r in rows:
        by_line[r["line"]].append(r)
    print("\nby line:")
    print(f"  {'line':>6} {'n':>5} {'recorded':>10} {'regraded':>10} {'changed':>8}")
    for line in sorted(by_line, key=lambda x: (x is None, x)):
        lt = tally(by_line[line])
        if lt:
            print(f"  {str(line) + '+':>6} {lt['n']:5} {lt['was_rate']:9.1f}% "
                  f"{lt['should_rate']:9.1f}% {lt['changed']:8}")


def main():
    args = sys.argv[1:]

    def opt(flag, default=None, cast=str):
        return cast(args[args.index(flag) + 1]) if flag in args else default

    asyncio.run(run(league_id=opt("--league"), only_line=opt("--line", None, int)))


if __name__ == "__main__":
    main()
