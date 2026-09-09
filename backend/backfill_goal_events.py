"""Backfill goal AND card detail — scorers, minutes, time spent trailing, and who went
down to ten — onto cached fixtures, then project it onto team.real_matches.

SPENDS API CREDITS: one `/fixtures/events` call per fixture that hasn't been done yet,
the same cost profile as backfill_shots.py. Capped per league, resumable (fixtures
carrying `events_at` are skipped), and the projection half is free.

CARDS RIDE ALONG. They are in the same `/fixtures/events` response as the goals, so a
fixture fetched from scratch gets both for one call. Fixtures already done for goals were
stored before cards existed and carry `events_at` but not `cards_at`, so they are re-fetched
once — that is the only part of this that spends anything, and it is a one-off.

What it buys:
  - who scored and when, per match
  - RED CARDS with the minute of the first dismissal, both ways round. A side going down
    to ten defends deeper and concedes corners; the opponent going down is the gift. This
    is the one big in-play swing the site could describe but never measure.
  - MINUTES SPENT TRAILING per team per match — the honest version of the chase
    measure. The game-state test used half-time state on full-match corners, so a team
    1-0 down from the 10th minute and one that conceded on 43 looked the same. This
    fixes half of that (the corner half needs half-split corners, which
    probe_corner_halves.py is checking for).

Run: python backfill_goal_events.py                 (every league)
     python backfill_goal_events.py eng-pl ita-sa   (named leagues)
     python backfill_goal_events.py --limit 50      (cap calls per league)
     python backfill_goal_events.py --project-only  (no API calls, cache -> teams)
"""
import asyncio
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import httpx
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

from card_events import card_summary, parse_card_events, team_card_sample
from goal_events import goal_summary, parse_goal_events, team_goal_sample
from sync_real import LEAGUE_META, STATS_CAP, af_get, current_season

ROOT = Path(__file__).parent
load_dotenv(ROOT / ".env")
db = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]


async def fetch_league(hc, lid, limit) -> dict:
    api = LEAGUE_META[lid]["api"]
    season = await current_season(hc, api)
    seasons = [season, season - 1]          # match the sync's pool, which tops up from last season
    season_ids = set()
    for yr in seasons:
        try:
            resp = await af_get(hc, "/fixtures", {"league": api, "season": yr})
        except Exception as e:
            print(f"[{lid}] {yr} fixture list failed: {e}")
            continue
        season_ids |= {f["fixture"]["id"] for f in resp}
    if not season_ids:
        return {"pending": 0, "filled": 0, "errors": 0, "goals": 0, "reds": 0}

    # Missing EITHER marker. `cards_at` is separate from `events_at` so fixtures already
    # done for goals are picked up exactly once for cards, instead of being skipped
    # forever or re-fetched on every run.
    pending = [c["_id"] async for c in db.fixture_stats.find(
        {"league_id": lid, "_id": {"$in": list(season_ids)},
         "$or": [{"events_at": {"$exists": False}}, {"cards_at": {"$exists": False}}]},
        {"_id": 1})]
    if not pending:
        print(f"[{lid}] nothing pending")
        return {"pending": 0, "filled": 0, "errors": 0, "goals": 0, "reds": 0}

    todo = pending[:limit]
    filled = errors = total_goals = total_reds = 0
    for fid in todo:
        doc = await db.fixture_stats.find_one({"_id": fid}, {"home_id": 1, "away_id": 1})
        if not doc or doc.get("home_id") is None:
            errors += 1
            continue
        try:
            events = await af_get(hc, "/fixtures/events", {"fixture": fid})
        except Exception as e:
            print(f"  [{lid}] events {fid} err {e}")
            errors += 1
            continue
        goals = parse_goal_events(events, doc["home_id"], doc["away_id"])
        summary = goal_summary(goals)
        cards = parse_card_events(events, doc["home_id"], doc["away_id"])
        csum = card_summary(cards)
        total_goals += len(goals)
        total_reds += csum["home_reds"] + csum["away_reds"]
        now = datetime.now(timezone.utc).isoformat()
        await db.fixture_stats.update_one({"_id": fid}, {"$set": {
            "goal_events": summary["goals"],
            "home_goal_minutes": summary["home_minutes"],
            "away_goal_minutes": summary["away_minutes"],
            "home_first_goal_min": summary["home_first_goal_min"],
            "away_first_goal_min": summary["away_first_goal_min"],
            "first_scorer_side": summary["first_scorer_side"],
            "card_events": csum["cards"],
            "home_reds": csum["home_reds"], "away_reds": csum["away_reds"],
            "home_yellows": csum["home_yellows"], "away_yellows": csum["away_yellows"],
            "home_first_red_min": csum["home_first_red_min"],
            "away_first_red_min": csum["away_first_red_min"],
            "events_at": now, "cards_at": now}})
        filled += 1
    left = len(pending) - len(todo)
    print(f"[{lid}] filled {filled}/{len(pending)} fixtures"
          f"{f' ({left} left — raise --limit)' if left else ''} "
          f"errors={errors} goals={total_goals} reds={total_reds}")
    return {"pending": len(pending), "filled": filled, "errors": errors,
            "goals": total_goals, "reds": total_reds}


async def project_onto_teams() -> dict:
    """Copy goal and card detail onto team.real_matches. DB only, no API calls."""
    lut = {}
    async for c in db.fixture_stats.find({"events_at": {"$exists": True}}, {"_id": 0}):
        day = (c.get("date") or "")[:10]
        if not day:
            continue
        summary = {
            "goals": c.get("goal_events") or [],
            "home_minutes": c.get("home_goal_minutes") or {"leading": 0, "level": 90, "trailing": 0},
            "away_minutes": c.get("away_goal_minutes") or {"leading": 0, "level": 90, "trailing": 0},
            "home_first_goal_min": c.get("home_first_goal_min"),
            "away_first_goal_min": c.get("away_first_goal_min"),
            "first_scorer_side": c.get("first_scorer_side"),
            "first_goal_min": None,
        }
        # Cards only where this fixture has actually been fetched for them. A fixture
        # done before cards existed must not project ZEROS, which would read as a clean
        # match rather than as a gap and quietly dilute every rate computed from them.
        csum = ({"home_reds": c.get("home_reds", 0), "away_reds": c.get("away_reds", 0),
                 "home_yellows": c.get("home_yellows", 0), "away_yellows": c.get("away_yellows", 0),
                 "home_first_red_min": c.get("home_first_red_min"),
                 "away_first_red_min": c.get("away_first_red_min")}
                if c.get("cards_at") else None)
        for side, key in (("home", "home_id"), ("away", "away_id")):
            if c.get(key) is None:
                continue
            sample = team_goal_sample(summary, side)
            if csum:
                sample.update(team_card_sample(csum, side))
            lut[(c[key], day)] = sample

    teams = matches = 0
    async for t in db.teams.find({}, {"real_matches": 1, "api_team_id": 1}):
        aid = t.get("api_team_id")
        rms = t.get("real_matches") or []
        if aid is None or not rms:
            continue
        changed = False
        for m in rms:
            hit = lut.get((aid, (m.get("date") or "")[:10]))
            if hit:
                m.update(hit)
                matches += 1
                changed = True
        if changed:
            await db.teams.update_one({"_id": t["_id"]}, {"$set": {"real_matches": rms}})
            teams += 1
    print(f"projected goal detail onto {matches} matches across {teams} teams")
    return {"teams": teams, "matches": matches}


async def main():
    args = sys.argv[1:]
    limit = STATS_CAP
    if "--limit" in args:
        i = args.index("--limit")
        limit = int(args[i + 1])
        del args[i:i + 2]
    project_only = "--project-only" in args
    args = [a for a in args if not a.startswith("--")]
    targets = args or list(LEAGUE_META.keys())
    unknown = [t for t in targets if t not in LEAGUE_META]
    if unknown:
        raise SystemExit(f"unknown league(s): {unknown}")

    if not project_only:
        totals = {"pending": 0, "filled": 0, "errors": 0, "goals": 0, "reds": 0}
        async with httpx.AsyncClient() as hc:
            for lid in targets:
                res = await fetch_league(hc, lid, limit)
                for k in totals:
                    totals[k] += res[k]
        print(f"fixtures filled: {totals['filled']} (pending was {totals['pending']}, "
              f"errors {totals['errors']}, {totals['goals']} goals and "
              f"{totals['reds']} sendings-off recorded)")
    await project_onto_teams()


if __name__ == "__main__":
    asyncio.run(main())
