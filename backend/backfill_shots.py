"""Backfill shot-volume features (shots, shots on target, blocked shots, dangerous
attacks) onto this season's cached fixtures, then project them onto team.real_matches.

Unlike backfill_goals.py this DOES spend API-Football statistics calls — one per
fixture that hasn't been through the feature capture yet — so it is capped per league
and is resumable: fixtures already carrying `features_at` are skipped on a re-run.

Run: python backfill_shots.py                  (this season, every league)
     python backfill_shots.py eng-pl ita-sa    (named leagues only)
     python backfill_shots.py --limit 40       (at most 40 statistics calls per league)
     python backfill_shots.py --project-only   (no API calls; only cache -> real_matches)
"""
import asyncio
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import httpx
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

from sync_real import (LEAGUE_META, STAT_TYPES, STATS_CAP, af_get, current_season,
                       parse_team_stats, _feature_sample)

ROOT = Path(__file__).parent
load_dotenv(ROOT / ".env")
db = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]

FEATURE_KEYS = [f"{side}_{f}" for f in STAT_TYPES for side in ("home", "away")]


async def fetch_league(hc, lid, limit) -> dict:
    """Fill features on this season's cached fixtures for one league."""
    api = LEAGUE_META[lid]["api"]
    season = await current_season(hc, api)
    try:
        resp = await af_get(hc, "/fixtures", {"league": api, "season": season})
    except Exception as e:
        print(f"[{lid}] season fetch failed: {e}")
        return {"pending": 0, "filled": 0, "errors": 1}
    season_ids = {f["fixture"]["id"] for f in resp}
    if not season_ids:
        return {"pending": 0, "filled": 0, "errors": 0}

    pending = [c["_id"] async for c in db.fixture_stats.find(
        {"league_id": lid, "_id": {"$in": list(season_ids)}, "features_at": {"$exists": False}},
        {"_id": 1})]
    if not pending:
        print(f"[{lid}] season {season}: nothing pending")
        return {"pending": 0, "filled": 0, "errors": 0}

    todo = pending[:limit]
    filled, errors = 0, 0
    cov = {f: 0 for f in STAT_TYPES}
    for fid in todo:
        try:
            st = await af_get(hc, "/fixtures/statistics", {"fixture": fid})
        except Exception as e:
            print(f"  [{lid}] stat {fid} err {e}")
            errors += 1
            continue
        doc = await db.fixture_stats.find_one({"_id": fid}, {"home_id": 1, "away_id": 1})
        if not doc:
            continue
        per_team = {t["team"]["id"]: parse_team_stats(t.get("statistics")) for t in st}
        home_feat = per_team.get(doc.get("home_id"))
        away_feat = per_team.get(doc.get("away_id"))
        if not home_feat or not away_feat:
            errors += 1
            continue
        update = {f"home_{f}": home_feat[f] for f in STAT_TYPES}
        update.update({f"away_{f}": away_feat[f] for f in STAT_TYPES})
        update["features_at"] = datetime.now(timezone.utc).isoformat()
        await db.fixture_stats.update_one({"_id": fid}, {"$set": update})
        for f in STAT_TYPES:
            cov[f] += sum(1 for side in (home_feat, away_feat) if side[f] is not None)
        filled += 1
    left = len(pending) - len(todo)
    covs = " ".join(f"{f}={cov[f]}/{filled * 2}" for f in STAT_TYPES) if filled else "n/a"
    print(f"[{lid}] season {season}: filled {filled}/{len(pending)} fixtures"
          f"{f' ({left} left — raise --limit)' if left else ''} errors={errors} | coverage {covs}")
    return {"pending": len(pending), "filled": filled, "errors": errors}


async def project_onto_teams() -> dict:
    """Copy the cached per-fixture features onto team.real_matches (DB only, no API).

    Keyed on (api_team_id, match day), the same join backfill_fh.py uses."""
    lut = {}
    async for c in db.fixture_stats.find({"features_at": {"$exists": True}}, {"_id": 0}):
        day = (c.get("date") or "")[:10]
        if not day:
            continue
        home = {f: c.get(f"home_{f}") for f in STAT_TYPES}
        away = {f: c.get(f"away_{f}") for f in STAT_TYPES}
        if c.get("home_id") is not None:
            lut[(c["home_id"], day)] = _feature_sample(home, away)
        if c.get("away_id") is not None:
            lut[(c["away_id"], day)] = _feature_sample(away, home)

    teams, matches = 0, 0
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
    print(f"projected features onto {matches} matches across {teams} teams")
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
        totals = {"pending": 0, "filled": 0, "errors": 0}
        async with httpx.AsyncClient() as hc:
            for lid in targets:
                res = await fetch_league(hc, lid, limit)
                for k in totals:
                    totals[k] += res[k]
        print(f"fixtures filled: {totals['filled']} (pending was {totals['pending']}, "
              f"errors {totals['errors']})")
    await project_onto_teams()


if __name__ == "__main__":
    asyncio.run(main())
