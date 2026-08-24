"""Probe: can API-Football give us corners split by half, or corner timings at all?

Everything downstream of this question is expensive — a half-time snapshot poller
would be new infrastructure that only accumulates data going forward — so settle
whether the data is already reachable before building anything.

Costs a handful of API calls. Checks four routes on one finished fixture:

  1. /fixtures/statistics                — what stat types exist at all? (full match)
  2. /fixtures/statistics?half=true      — some API-Football versions document a half
                                           split here; if it works this is the whole
                                           answer and history is recoverable
  3. /fixtures/events                    — do corner events exist with minutes?
  4. /fixtures?id=                       — what the fixture object carries (goals do
                                           have a halftime split; corners may not)

Run: python probe_corner_halves.py            (picks a recent finished eng-pl fixture)
     python probe_corner_halves.py 1234567     (a specific fixture id)
"""
import asyncio
import json
import os
import sys
from pathlib import Path

import httpx
from dotenv import load_dotenv

from sync_real import LEAGUE_META, af_get, current_season

ROOT = Path(__file__).parent
load_dotenv(ROOT / ".env")
os.environ.setdefault("API_FOOTBALL_KEY", os.environ.get("API_FOOTBALL_KEY", ""))

CORNER_WORDS = ("corner",)


async def pick_fixture(hc, lid="eng-pl"):
    api = LEAGUE_META[lid]["api"]
    season = await current_season(hc, api)
    fixtures = await af_get(hc, "/fixtures", {"league": api, "season": season})
    ft = [f for f in fixtures if f["fixture"]["status"]["short"] == "FT"]
    ft.sort(key=lambda f: f["fixture"]["date"])
    if not ft:
        raise SystemExit(f"no finished fixtures for {lid} season {season}")
    return ft[-1]


async def main():
    arg = next((a for a in sys.argv[1:] if a.isdigit()), None)
    async with httpx.AsyncClient() as hc:
        if arg:
            fid = int(arg)
            print(f"probing fixture {fid}")
        else:
            f = await pick_fixture(hc)
            fid = f["fixture"]["id"]
            print(f"probing {f['teams']['home']['name']} v {f['teams']['away']['name']}"
                  f"  ({f['fixture']['date'][:10]}, id={fid})")

        # 1. what does the plain statistics call return?
        print("\n--- 1. /fixtures/statistics (full match) ---")
        try:
            st = await af_get(hc, "/fixtures/statistics", {"fixture": fid})
            types = [s.get("type") for s in (st[0].get("statistics") or [])] if st else []
            print(f"  stat types available ({len(types)}):")
            for t in types:
                print(f"    - {t}")
            corner_types = [t for t in types if any(w in str(t).lower() for w in CORNER_WORDS)]
            print(f"  corner-related types: {corner_types or 'NONE'}")
            print("  -> if only one corner type appears, there is no half split here")
        except Exception as e:
            print(f"  failed: {e}")

        # 2. the half parameter — if this works, history is recoverable and no poller
        #    is needed. This is the outcome worth hoping for.
        print("\n--- 2. /fixtures/statistics?half=true ---")
        try:
            st2 = await af_get(hc, "/fixtures/statistics", {"fixture": fid, "half": "true"})
            blob = json.dumps(st2)[:1200]
            has_halves = any(k in blob for k in ('"1st', '"2nd', "first_half", "second_half",
                                                 '"period', '"half'))
            print(f"  call succeeded. half-split structure present: {has_halves}")
            print(f"  sample: {blob[:600]}")
            if not has_halves:
                print("  -> the parameter was accepted but the payload looks identical to (1);"
                      " no half split")
        except Exception as e:
            print(f"  failed: {e}")
            print("  -> the parameter is not supported on this plan/version")

        # 3. events — corners would need to appear here to reconstruct timings
        print("\n--- 3. /fixtures/events ---")
        try:
            ev = await af_get(hc, "/fixtures/events", {"fixture": fid})
            kinds = sorted({f"{e.get('type')} / {e.get('detail')}" for e in ev})
            print(f"  event kinds ({len(kinds)}):")
            for k in kinds:
                print(f"    - {k}")
            corner_ev = [k for k in kinds if any(w in k.lower() for w in CORNER_WORDS)]
            print(f"  corner events: {corner_ev or 'NONE'}")
            print("  -> no corner events means timings cannot be reconstructed after the fact")
        except Exception as e:
            print(f"  failed: {e}")

        # 4. the fixture object itself (goals DO carry a halftime split)
        print("\n--- 4. /fixtures?id= (score object) ---")
        try:
            fx = await af_get(hc, "/fixtures", {"id": fid})
            score = (fx[0].get("score") or {}) if fx else {}
            print(f"  score keys: {list(score)}")
            print(f"  halftime: {score.get('halftime')}   fulltime: {score.get('fulltime')}")
            print("  -> goals split by half; corners are not in this object")
        except Exception as e:
            print(f"  failed: {e}")

    print("""
WHAT THE ANSWER MEANS
  If (2) returns a real half split      -> corners by half are available for HISTORY.
                                           Cheap: extend the existing sync, backfill,
                                           and the chase question can be re-tested on
                                           second-half corners only.
  If only (1) works and (3) has no
  corner events                         -> corners by half are NOT recoverable for past
                                           matches. The only route is snapshotting
                                           statistics at half-time on live fixtures,
                                           which accumulates going forward only.""")


if __name__ == "__main__":
    asyncio.run(main())
