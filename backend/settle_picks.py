"""Resolve 'Corner Model 2.0 Picks' to real API-Football fixtures and settle them
Win/Loss once played, using the picked team's Corner Kicks vs the pick line.
Reuses the permanent fixture_stats cache so finished games are fetched once."""
import os
import re
import sys
import asyncio
from datetime import datetime, timezone, timedelta
from pathlib import Path
import httpx
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

from sync_real import af_get, current_season, LEAGUE_META

ROOT = Path(__file__).parent
load_dotenv(ROOT / ".env")
db = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]


def _tokens(s):
    s = re.sub(r"[^a-z0-9 ]", " ", (s or "").lower())
    return {t for t in s.split() if len(t) >= 3}


def _overlap(a, b):
    ta, tb = _tokens(a), _tokens(b)
    return len(ta & tb)


def _match_fixture(pick, fixtures):
    """Best API fixture for a pick, scored by both teams' token overlap."""
    best, best_score = None, 0
    for f in fixtures:
        hn = f["teams"]["home"]["name"]
        an = f["teams"]["away"]["name"]
        score = _overlap(pick["home"], hn) + _overlap(pick["away"], an)
        if score > best_score:
            best, best_score = f, score
    return best if best_score >= 2 else None


async def _team_corners(hc, api_fid, team_api_id):
    """Corner Kicks for a team in a fixture, via permanent cache or one API call."""
    c = await db.fixture_stats.find_one({"_id": api_fid})
    if c:
        if team_api_id == c.get("home_id"):
            return c["home_corners"]
        if team_api_id == c.get("away_id"):
            return c["away_corners"]
    st = await af_get(hc, "/fixtures/statistics", {"fixture": api_fid})
    corners = {}
    for t in st:
        cc = next((s["value"] for s in t["statistics"] if s["type"] == "Corner Kicks"), None)
        corners[t["team"]["id"]] = cc if isinstance(cc, int) else 0
    return corners.get(team_api_id)


async def settle(hc):
    picks = await db.picks.find({"status": "pending"}).to_list(500)
    if not picks:
        print("no pending picks"); return
    # group by league to fetch each league's fixture window once
    by_league = {}
    for p in picks:
        by_league.setdefault(p["league_id"], []).append(p)
    settled = 0
    for lid, plist in by_league.items():
        meta = LEAGUE_META.get(lid)
        if not meta:
            print(f"[{lid}] no meta, skip"); continue
        api_id = meta["api"]
        try:
            season = await current_season(hc, api_id)
            dates = sorted({p["date"] for p in plist})
            frm = (datetime.fromisoformat(dates[0]) - timedelta(days=1)).strftime("%Y-%m-%d")
            to = (datetime.fromisoformat(dates[-1]) + timedelta(days=1)).strftime("%Y-%m-%d")
            fixtures = await af_get(hc, "/fixtures", {"league": api_id, "season": season, "from": frm, "to": to})
        except Exception as e:
            print(f"[{lid}] fixture fetch failed: {e}"); continue
        for p in plist:
            fx = _match_fixture(p, fixtures)
            if not fx:
                print(f"  no fixture match: {p['home']} v {p['away']}"); continue
            api_fid = fx["fixture"]["id"]
            update = {"api_fixture_id": api_fid, "kickoff": fx["fixture"]["date"]}
            status_short = fx["fixture"]["status"]["short"]
            if status_short == "FT":
                # which side is the picked team?
                home_name = fx["teams"]["home"]["name"]
                away_name = fx["teams"]["away"]["name"]
                team_side = fx["teams"]["home"] if _overlap(p["team"], home_name) >= _overlap(p["team"], away_name) else fx["teams"]["away"]
                try:
                    corners = await _team_corners(hc, api_fid, team_side["id"])
                except Exception as e:
                    print(f"  stats err {api_fid}: {e}"); corners = None
                if corners is not None:
                    update["result_corners"] = corners
                    update["status"] = "won" if corners >= p["line"] else "lost"
                    update["settled_at"] = datetime.now(timezone.utc).isoformat()
                    settled += 1
                    print(f"  {'✅' if update['status']=='won' else '❌'} {p['team']} {p['line']}+ -> {corners} corners")
            await db.picks.update_one({"_id": p["_id"]}, {"$set": update})
    print(f"settled {settled} pick(s)")


async def main():
    async with httpx.AsyncClient() as hc:
        await settle(hc)


if __name__ == "__main__":
    asyncio.run(main())
