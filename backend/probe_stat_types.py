"""Which statistics does API-Football actually report for our leagues?

Answers "can we add crosses?" (and anything else) with evidence rather than a guess:
samples recent finished fixtures across several leagues and reports every statistic
`type` the provider returned, with how often it was non-null.

A type that never appears cannot be captured no matter what we change in the app —
that is a data-provider limit, not a code one.

Run: python probe_stat_types.py            (default 3 leagues x 4 fixtures)
     python probe_stat_types.py eng-pl ita-sa
"""
import os
import sys
import asyncio
from collections import Counter, defaultdict
from pathlib import Path

import httpx
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

from sync_real import af_get, current_season, LEAGUE_META, _norm_stat

ROOT = Path(__file__).parent
load_dotenv(ROOT / ".env")
db = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]

DEFAULT_LEAGUES = ["eng-pl", "ita-sa", "ned-ere"]
FIXTURES_PER_LEAGUE = 4

# What we would like to have, so the report can call out hits and misses explicitly.
WANTED = {
    "crosses": ("crosses", "total crosses", "accurate crosses"),
    "corner kicks": ("corner kicks",),
    "total shots": ("total shots", "shots total"),
    "shots on goal": ("shots on goal", "shots on target"),
    "blocked shots": ("blocked shots", "shots blocked"),
    "expected goals": ("expected_goals", "expected goals"),
}


async def probe(hc, league_ids):
    seen = Counter()          # normalised type -> times a non-null value came back
    seen_any = Counter()      # normalised type -> times the key was present at all
    per_league = defaultdict(set)
    sampled = 0

    for lid in league_ids:
        meta = LEAGUE_META.get(lid)
        if not meta:
            print(f"[{lid}] unknown league id, skipping")
            continue
        season = await current_season(hc, meta["api"])
        fixtures = await af_get(hc, "/fixtures", {"league": meta["api"], "season": season})
        ft = [f for f in fixtures if f["fixture"]["status"]["short"] == "FT"]
        ft.sort(key=lambda f: f["fixture"]["date"])
        for f in ft[-FIXTURES_PER_LEAGUE:]:
            fid = f["fixture"]["id"]
            try:
                stats = await af_get(hc, "/fixtures/statistics", {"fixture": fid})
            except Exception as exc:                          # noqa: BLE001
                print(f"[{lid}] fixture {fid}: {exc}")
                continue
            sampled += 1
            for team_block in stats:
                for s in team_block.get("statistics", []):
                    key = _norm_stat(s.get("type"))
                    seen_any[key] += 1
                    per_league[lid].add(key)
                    if s.get("value") is not None:
                        seen[key] += 1

    return seen, seen_any, per_league, sampled


def report(seen, seen_any, per_league, sampled):
    print(f"\n=== sampled {sampled} fixture(s) ===\n")
    if not seen_any:
        print("No statistics returned at all — check the API key and plan.")
        return
    print(f"{'statistic':<34}{'present':>9}{'non-null':>10}")
    print("-" * 53)
    for key, present in seen_any.most_common():
        print(f"{key:<34}{present:>9}{seen.get(key, 0):>10}")

    print("\n=== can we build on it? ===")
    for label, aliases in WANTED.items():
        hit = next((a for a in aliases if seen.get(a)), None)
        if hit:
            print(f"  YES  {label:<16} reported as {hit!r} ({seen[hit]} non-null samples)")
        elif any(a in seen_any for a in aliases):
            print(f"  EMPTY {label:<15} key present but always null — not usable")
        else:
            print(f"  NO   {label:<16} never returned by this plan/leagues")

    print("\nPer-league type counts:")
    for lid, keys in per_league.items():
        print(f"  {lid}: {len(keys)} distinct types")


async def main():
    league_ids = sys.argv[1:] or DEFAULT_LEAGUES
    async with httpx.AsyncClient() as hc:
        seen, seen_any, per_league, sampled = await probe(hc, league_ids)
    report(seen, seen_any, per_league, sampled)


if __name__ == "__main__":
    asyncio.run(main())
