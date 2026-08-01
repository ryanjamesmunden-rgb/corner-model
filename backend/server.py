from fastapi import FastAPI, APIRouter, HTTPException, Depends, Request, Response
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
import math
import random
import uuid
from pathlib import Path
from pydantic import BaseModel
from typing import List, Optional, Dict
from datetime import datetime, timezone, timedelta
import httpx

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

app = FastAPI()
api_router = APIRouter(prefix="/api")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

EMERGENT_SESSION_URL = "https://demobackend.emergentagent.com/auth/v1/env/oauth/session-data"

# ----------------------------- Poisson Engine -----------------------------

def poisson_pmf(k: int, lam: float) -> float:
    if lam <= 0:
        return 1.0 if k == 0 else 0.0
    return math.exp(-lam) * (lam ** k) / math.factorial(k)


def poisson_ge(k: int, lam: float) -> float:
    if k <= 0:
        return 1.0
    cum = sum(poisson_pmf(i, lam) for i in range(0, k))
    return max(0.0, min(1.0, 1.0 - cum))


def fair_odds(p: float) -> Optional[float]:
    if p <= 0:
        return None
    return round(1.0 / p, 2)


def ev_percent(book_odds: float, p: float) -> float:
    return round((book_odds * p - 1.0) * 100.0, 2)


def tier_for_ev(ev: float) -> str:
    if ev >= 5.0:
        return "strong"
    if ev >= 0.0:
        return "small"
    return "none"


TOTAL_LINES = [6.5, 7.5, 8.5, 9.5, 10.5, 11.5, 12.5, 13.5]
TEAM_LINES = [2.5, 3.5, 4.5, 5.5, 6.5]

# ----------------------------- Mock Data Seed -----------------------------

LEAGUES = [
    {"league_id": "ned-ed", "name": "Eerste Divisie", "country": "Netherlands", "base": 10.6},
    {"league_id": "nor-el", "name": "Eliteserien", "country": "Norway", "base": 10.1},
    {"league_id": "aus-al", "name": "A-League", "country": "Australia", "base": 9.7},
    {"league_id": "bra-sa", "name": "Série A", "country": "Brazil", "base": 9.9},
    {"league_id": "fin-vk", "name": "Veikkausliiga", "country": "Finland", "base": 9.4},
    {"league_id": "swe-al", "name": "Allsvenskan", "country": "Sweden", "base": 10.0},
    {"league_id": "eng-pl", "name": "Premier League", "country": "England", "base": 10.8},
]

TEAM_NAMES = {
    "ned-ed": ["PSV II", "Utrecht II", "Willem II", "Roda JC", "FC Emmen", "VVV-Venlo", "Den Bosch", "Dordrecht", "Helmond Sport", "TOP Oss"],
    "nor-el": ["Bodo/Glimt", "Molde", "Rosenborg", "Brann", "Viking", "Lillestrom", "Tromso", "Sarpsborg 08", "Odd", "HamKam"],
    "aus-al": ["Melbourne City", "Sydney FC", "Wanderers", "Adelaide United", "Central Coast", "Macarthur FC", "Perth Glory", "Brisbane Roar", "Wellington", "Newcastle Jets"],
    "bra-sa": ["Flamengo", "Palmeiras", "Botafogo", "Fluminense", "Sao Paulo", "Gremio", "Internacional", "Atletico-MG", "Corinthians", "Cruzeiro"],
    "fin-vk": ["HJK", "KuPS", "Inter Turku", "Ilves", "SJK", "Honka", "VPS", "Lahti", "Haka", "AC Oulu"],
    "swe-al": ["Malmo FF", "AIK", "Djurgarden", "Hammarby", "IFK Goteborg", "Elfsborg", "Hacken", "Norrkoping", "Kalmar FF", "Sirius"],
    "eng-pl": ["Man City", "Arsenal", "Liverpool", "Tottenham", "Chelsea", "Newcastle", "Man United", "Aston Villa", "Brighton", "West Ham"],
}


def _rng(seed_str: str) -> random.Random:
    return random.Random(hash(seed_str) & 0xffffffff)


def team_split(matches: List[dict], split: str, window: int) -> dict:
    if split == "home":
        pool = [m for m in matches if m["home"]]
    elif split == "away":
        pool = [m for m in matches if not m["home"]]
    else:
        pool = matches
    pool = pool[-window:] if window else pool
    n = len(pool)
    if n == 0:
        return {"played": 0, "for_avg": 0, "against_avg": 0, "total_avg": 0}
    cf = sum(m["corners_for"] for m in pool)
    ca = sum(m["corners_against"] for m in pool)
    return {"played": n, "for_avg": round(cf / n, 2), "against_avg": round(ca / n, 2), "total_avg": round((cf + ca) / n, 2)}


def _src(team: dict) -> list:
    """Prefer real match data; fall back to (synthetic) matches only if no real games."""
    return team.get("real_matches") or team.get("matches") or []


def expected_lambdas(home: dict, away: dict) -> dict:
    h_home = team_split(_src(home), "home", 0)
    a_away = team_split(_src(away), "away", 0)
    # fall back to overall if a team has no games on that venue
    if h_home["played"] == 0:
        h_home = team_split(_src(home), "overall", 0)
    if a_away["played"] == 0:
        a_away = team_split(_src(away), "overall", 0)
    lam_home = round((h_home["for_avg"] + a_away["against_avg"]) / 2, 2)
    lam_away = round((a_away["for_avg"] + h_home["against_avg"]) / 2, 2)
    return {"home": lam_home, "away": lam_away, "total": round(lam_home + lam_away, 2)}


async def seed_data():
    if await db.leagues.count_documents({}) > 0:
        return
    logger.info("Seeding mock corner data...")
    await db.leagues.insert_many([{**l} for l in LEAGUES])

    all_teams = []
    for lg in LEAGUES:
        rng = _rng(lg["league_id"])
        for name in TEAM_NAMES[lg["league_id"]]:
            strength = rng.uniform(0.85, 1.2)
            defense = rng.uniform(0.85, 1.2)
            home_for = (lg["base"] / 2) * strength * rng.uniform(1.05, 1.25)
            away_for = (lg["base"] / 2) * strength * rng.uniform(0.8, 0.98)
            home_ag = (lg["base"] / 2) * defense * rng.uniform(0.8, 0.98)
            away_ag = (lg["base"] / 2) * defense * rng.uniform(1.05, 1.25)
            matches = []
            for i in range(12):
                is_home = i % 2 == 0
                cf_mean = home_for if is_home else away_for
                ca_mean = home_ag if is_home else away_ag
                cf = max(0, int(round(rng.gauss(cf_mean, 1.6))))
                ca = max(0, int(round(rng.gauss(ca_mean, 1.6))))
                matches.append({"home": is_home, "corners_for": cf, "corners_against": ca})
            all_teams.append({
                "team_id": f"{lg['league_id']}-{name.lower().replace(' ', '-')}",
                "league_id": lg["league_id"], "name": name, "matches": matches,
            })
    await db.teams.insert_many(all_teams)

    fixtures = []
    now = datetime.now(timezone.utc)
    for lg in LEAGUES:
        teams = [t for t in all_teams if t["league_id"] == lg["league_id"]]
        rng = _rng(lg["league_id"] + "-fix")
        rng.shuffle(teams)
        for i in range(0, len(teams) - 1, 2):
            ht, at = teams[i], teams[i + 1]
            kickoff = now + timedelta(days=rng.randint(1, 6), hours=rng.randint(0, 10))
            fixtures.append({
                "fixture_id": str(uuid.uuid4()), "league_id": lg["league_id"], "round": "Upcoming Round",
                "home_team_id": ht["team_id"], "away_team_id": at["team_id"],
                "home_name": ht["name"], "away_name": at["name"],
                "date": kickoff.isoformat(), "status": "upcoming",
            })
    await db.fixtures.insert_many(fixtures)

    team_map = {t["team_id"]: t for t in all_teams}
    odds_docs = []
    for fx in fixtures:
        rng = _rng(fx["fixture_id"])
        if rng.random() > 0.7:
            continue
        lambdas = expected_lambdas(team_map[fx["home_team_id"]], team_map[fx["away_team_id"]])
        odds = {}
        for line in TOTAL_LINES:
            k = int(line) + 1
            p = poisson_ge(k, lambdas["total"])
            fo = fair_odds(p)
            if not fo:
                continue
            odds[f"total_over_{line}"] = round(fo * rng.uniform(0.9, 1.18), 2)
        odds_docs.append({"fixture_id": fx["fixture_id"], "odds": odds})
    if odds_docs:
        await db.odds.insert_many(odds_docs)
    logger.info("Seed complete: %d teams, %d fixtures, %d odds", len(all_teams), len(fixtures), len(odds_docs))


# ----------------------------- Model helpers -----------------------------

def _std(vals: List[float]) -> float:
    if len(vals) < 2:
        return 0.0
    m = sum(vals) / len(vals)
    return math.sqrt(sum((v - m) ** 2 for v in vals) / len(vals))


def confidence_for(home: dict, away: dict) -> dict:
    hs, as_ = _src(home), _src(away)
    played = min(len(hs), len(as_))
    sample_score = min(played / 10.0, 1.0)
    h_vals = [m["corners_for"] + m["corners_against"] for m in hs] or [0]
    a_vals = [m["corners_for"] + m["corners_against"] for m in as_] or [0]
    avg_total = (sum(h_vals) / len(h_vals) + sum(a_vals) / len(a_vals)) / 2 or 1
    stability = max(0.0, 1.0 - ((_std(h_vals) + _std(a_vals)) / 2) / avg_total)
    hf = team_split(hs, "home", 0)["total_avg"]
    af = team_split(as_, "away", 0)["total_avg"]
    overall = (team_split(hs, "overall", 0)["total_avg"] + team_split(as_, "overall", 0)["total_avg"]) / 2 or 1
    consistency = max(0.0, 1.0 - abs(hf - af) / overall)
    score = 0.45 * sample_score + 0.35 * stability + 0.2 * consistency
    label = "High" if score >= 0.7 else ("Medium" if score >= 0.5 else "Low")
    return {"score": round(score * 100), "label": label}


def build_markets(lambdas: dict, odds: Dict[str, float]) -> List[dict]:
    rows = []
    specs = [("total", "Total", lambdas["total"], TOTAL_LINES),
             ("home", "Home Team", lambdas["home"], TEAM_LINES),
             ("away", "Away Team", lambdas["away"], TEAM_LINES)]
    for group, label, lam, lines in specs:
        for line in lines:
            k = int(line) + 1
            p = poisson_ge(k, lam)
            key = f"{group}_over_{line}"
            fo = fair_odds(p)
            book = odds.get(key)
            ev = ev_percent(book, p) if book else None
            rows.append({"key": key, "group": group, "group_label": label, "line": line,
                         "label": f"Over {line}", "prob": round(p * 100, 1), "fair_odds": fo,
                         "book_odds": book, "ev": ev, "tier": tier_for_ev(ev) if ev is not None else None})
    return rows


async def get_fixture_model(fixture: dict, odds: Dict[str, float]) -> dict:
    home = await db.teams.find_one({"team_id": fixture["home_team_id"]}, {"_id": 0})
    away = await db.teams.find_one({"team_id": fixture["away_team_id"]}, {"_id": 0})
    lambdas = expected_lambdas(home, away)
    return {"lambdas": lambdas, "markets": build_markets(lambdas, odds), "confidence": confidence_for(home, away)}


# ----------------------------- Auth -----------------------------

async def get_current_user(request: Request) -> dict:
    token = request.cookies.get("session_token")
    if not token:
        auth = request.headers.get("Authorization", "")
        if auth.startswith("Bearer "):
            token = auth[7:]
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    session = await db.user_sessions.find_one({"session_token": token}, {"_id": 0})
    if not session:
        raise HTTPException(status_code=401, detail="Invalid session")
    expires_at = session["expires_at"]
    if isinstance(expires_at, str):
        expires_at = datetime.fromisoformat(expires_at)
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=401, detail="Session expired")
    user = await db.users.find_one({"user_id": session["user_id"]}, {"_id": 0})
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return user


class SessionRequest(BaseModel):
    session_id: str


@api_router.post("/auth/session")
async def auth_session(body: SessionRequest, response: Response):
    async with httpx.AsyncClient() as hc:
        r = await hc.get(EMERGENT_SESSION_URL, headers={"X-Session-ID": body.session_id})
    if r.status_code != 200:
        raise HTTPException(status_code=401, detail="Invalid session_id")
    data = r.json()
    email = data["email"]
    user = await db.users.find_one({"email": email}, {"_id": 0})
    if not user:
        user = {"user_id": f"user_{uuid.uuid4().hex[:12]}", "email": email,
                "name": data.get("name", email), "picture": data.get("picture", ""),
                "created_at": datetime.now(timezone.utc).isoformat()}
        await db.users.insert_one(dict(user))
    session_token = data["session_token"]
    expires_at = datetime.now(timezone.utc) + timedelta(days=7)
    await db.user_sessions.insert_one({"user_id": user["user_id"], "session_token": session_token,
                                       "expires_at": expires_at.isoformat(),
                                       "created_at": datetime.now(timezone.utc).isoformat()})
    response.set_cookie("session_token", session_token, httponly=True, secure=True,
                        samesite="none", path="/", max_age=7 * 24 * 3600)
    return {"user_id": user["user_id"], "email": user["email"], "name": user["name"], "picture": user.get("picture", "")}


@api_router.get("/auth/me")
async def auth_me(user: dict = Depends(get_current_user)):
    return {"user_id": user["user_id"], "email": user["email"], "name": user["name"], "picture": user.get("picture", "")}


@api_router.post("/auth/logout")
async def auth_logout(request: Request, response: Response):
    token = request.cookies.get("session_token")
    if token:
        await db.user_sessions.delete_one({"session_token": token})
    response.delete_cookie("session_token", path="/")
    return {"ok": True}


# ----------------------------- App Routes -----------------------------

@api_router.get("/")
async def root():
    return {"message": "Corner Model 2.0 API"}


@api_router.get("/leagues")
async def get_leagues(user: dict = Depends(get_current_user)):
    return await db.leagues.find({}, {"_id": 0}).to_list(100)


_last_refresh = {}


@api_router.post("/leagues/{league_id}/refresh")
async def refresh_league(league_id: str, user: dict = Depends(get_current_user)):
    if not await db.leagues.find_one({"league_id": league_id}):
        raise HTTPException(status_code=404, detail="League not found")
    now = datetime.now(timezone.utc)
    last = _last_refresh.get(league_id)
    if last and (now - last).total_seconds() < 120:
        return {"status": "already_syncing", "league_id": league_id,
                "started_at": last.isoformat()}
    _last_refresh[league_id] = now
    import subprocess, sys
    subprocess.Popen([sys.executable, str(ROOT_DIR / "sync_real.py"), league_id], cwd=str(ROOT_DIR))
    return {"status": "syncing", "league_id": league_id, "started_at": now.isoformat()}


@api_router.get("/leagues/{league_id}/teams")
async def get_teams(league_id: str, split: str = "overall", window: int = 5, user: dict = Depends(get_current_user)):
    teams = await db.teams.find({"league_id": league_id}, {"_id": 0}).to_list(100)
    out = []
    for t in teams:
        src = _src(t)
        s = team_split(src, split, window)
        overall = team_split(src, "overall", 0)
        out.append({"team_id": t["team_id"], "name": t["name"], "played": s["played"],
                    "for_avg": s["for_avg"], "against_avg": s["against_avg"],
                    "total_avg": s["total_avg"], "season_total_avg": overall["total_avg"]})
    out.sort(key=lambda x: x["for_avg"], reverse=True)
    return out


async def _odds_for(fixture_id: str) -> Dict[str, float]:
    doc = await db.odds.find_one({"fixture_id": fixture_id}, {"_id": 0})
    return doc["odds"] if doc else {}


@api_router.get("/leagues/{league_id}/fixtures")
async def get_fixtures(league_id: str, user: dict = Depends(get_current_user)):
    fixtures = await db.fixtures.find({"league_id": league_id}, {"_id": 0}).to_list(100)
    fixtures.sort(key=lambda x: x["date"])
    out = []
    for fx in fixtures:
        odds = await _odds_for(fx["fixture_id"])
        model = await get_fixture_model(fx, odds)
        best = None
        for m in model["markets"]:
            if m["ev"] is not None and (best is None or m["ev"] > best["ev"]):
                best = m
        out.append({**fx, "lambdas": model["lambdas"], "confidence": model["confidence"],
                    "has_odds": len(odds) > 0, "best_bet": best})
    return out


@api_router.get("/fixtures/{fixture_id}")
async def fixture_detail(fixture_id: str, user: dict = Depends(get_current_user)):
    fx = await db.fixtures.find_one({"fixture_id": fixture_id}, {"_id": 0})
    if not fx:
        raise HTTPException(status_code=404, detail="Fixture not found")
    odds = await _odds_for(fixture_id)
    model = await get_fixture_model(fx, odds)
    home = await db.teams.find_one({"team_id": fx["home_team_id"]}, {"_id": 0})
    away = await db.teams.find_one({"team_id": fx["away_team_id"]}, {"_id": 0})

    def splits(team):
        return {sp: {str(w): team_split(_src(team), sp, w) for w in [3, 5, 10, 0]} for sp in ["home", "away", "overall"]}

    def recent(team):
        rms = team.get("real_matches") or []
        return [{"date": m["date"], "opponent": m["opponent"], "home": m["home"],
                 "won": m["corners_for"], "conceded": m["corners_against"],
                 "total": m["corners_for"] + m["corners_against"]}
                for m in reversed(rms)]

    return {"fixture": fx, "model": model,
            "home_team": {"name": home["name"], "splits": splits(home),
                          "recent": recent(home), "real_samples": home.get("real_samples", 0)},
            "away_team": {"name": away["name"], "splits": splits(away),
                          "recent": recent(away), "real_samples": away.get("real_samples", 0)}}


class OddsBody(BaseModel):
    odds: Dict[str, float]


@api_router.post("/fixtures/{fixture_id}/odds")
async def set_odds(fixture_id: str, body: OddsBody, user: dict = Depends(get_current_user)):
    fx = await db.fixtures.find_one({"fixture_id": fixture_id}, {"_id": 0})
    if not fx:
        raise HTTPException(status_code=404, detail="Fixture not found")
    existing = await _odds_for(fixture_id)
    merged = {**existing, **{k: v for k, v in body.odds.items() if v and v > 1.0}}
    await db.odds.update_one({"fixture_id": fixture_id}, {"$set": {"odds": merged}}, upsert=True)
    model = await get_fixture_model(fx, merged)
    return {"model": model, "odds": merged}


@api_router.get("/scanner")
async def scanner(league_id: Optional[str] = None, market: Optional[str] = None,
                  min_edge: float = -100.0, user: dict = Depends(get_current_user)):
    q = {"league_id": league_id} if league_id and league_id != "all" else {}
    fixtures = await db.fixtures.find(q, {"_id": 0}).to_list(200)
    leagues = {l["league_id"]: l["name"] for l in await db.leagues.find({}, {"_id": 0}).to_list(100)}
    results = []
    for fx in fixtures:
        odds = await _odds_for(fx["fixture_id"])
        if not odds:
            continue
        model = await get_fixture_model(fx, odds)
        for m in model["markets"]:
            if m["ev"] is None:
                continue
            if market and market != "all" and m["group"] != market:
                continue
            if m["ev"] < min_edge:
                continue
            results.append({"fixture_id": fx["fixture_id"], "league_id": fx["league_id"],
                            "league_name": leagues.get(fx["league_id"], ""), "home_name": fx["home_name"],
                            "away_name": fx["away_name"], "date": fx["date"],
                            "market_label": f"{m['group_label']} {m['label']}", "group": m["group"],
                            "book_odds": m["book_odds"], "fair_odds": m["fair_odds"], "prob": m["prob"],
                            "ev": m["ev"], "tier": m["tier"], "confidence": model["confidence"]})
    results.sort(key=lambda x: x["ev"], reverse=True)
    return results


def _real_avg(team, side, field):
    rms = (team or {}).get("real_matches") or []
    if side == "home":
        pool = [m for m in rms if m["home"]]
    elif side == "away":
        pool = [m for m in rms if not m["home"]]
    else:
        pool = rms
    if not pool:
        pool = rms
    if not pool:
        return None
    return sum(m[field] for m in pool) / len(pool)


async def _next_fixtures(q):
    fixtures = await db.fixtures.find(q, {"_id": 0}).to_list(2000)
    fixtures.sort(key=lambda f: f["date"])
    nf = {}
    for fx in fixtures:
        for tid, opp, opp_id, is_home in ((fx["home_team_id"], fx["away_name"], fx["away_team_id"], True),
                                          (fx["away_team_id"], fx["home_name"], fx["home_team_id"], False)):
            if tid not in nf:
                nf[tid] = {"fixture_id": fx["fixture_id"], "date": fx["date"],
                           "opponent": opp, "opponent_team_id": opp_id, "is_home": is_home}
    return nf


@api_router.get("/streaks")
async def streaks(league_id: Optional[str] = None, side: str = "overall", window: int = 5,
                  min_hits: int = 5, threshold: Optional[int] = None, min_line: int = 3,
                  within_days: Optional[int] = None,
                  user: dict = Depends(get_current_user)):
    """Teams that hit a team-corner threshold consistently over recent REAL games
    (e.g. 4+ corners in 5/5 home games, or 8/10 last 10)."""
    q = {} if not league_id or league_id == "all" else {"league_id": league_id}
    teams = await db.teams.find(q, {"_id": 0}).to_list(1000)
    teams_by_id = {t["team_id"]: t for t in teams}
    leagues = {l["league_id"]: l["name"] for l in await db.leagues.find({}, {"_id": 0}).to_list(100)}

    # earliest upcoming fixture per team
    fixtures = await db.fixtures.find(q, {"_id": 0}).to_list(1000)
    fixtures.sort(key=lambda f: f["date"])
    next_fx = {}
    for fx in fixtures:
        for tid, opp, opp_id, is_home in ((fx["home_team_id"], fx["away_name"], fx["away_team_id"], True),
                                          (fx["away_team_id"], fx["home_name"], fx["home_team_id"], False)):
            if tid not in next_fx:
                next_fx[tid] = {"fixture_id": fx["fixture_id"], "date": fx["date"],
                                "opponent": opp, "opponent_team_id": opp_id, "is_home": is_home}
    # odds entered for the relevant upcoming fixtures (for live edge %)
    fx_ids = list({v["fixture_id"] for v in next_fx.values()})
    odds_docs = await db.odds.find({"fixture_id": {"$in": fx_ids}}, {"_id": 0}).to_list(2000)
    odds_map = {o["fixture_id"]: o.get("odds", {}) for o in odds_docs}
    now = datetime.now(timezone.utc)

    results = []
    for t in teams:
        rms = t.get("real_matches") or []
        if side == "home":
            pool = [m for m in rms if m["home"]]
        elif side == "away":
            pool = [m for m in rms if not m["home"]]
        else:
            pool = list(rms)
        pool = pool[-window:]
        if len(pool) < window:
            continue
        wons = [m["corners_for"] for m in pool]
        if threshold is not None:
            line = int(threshold)
            hits = sum(1 for w in wons if w >= line)
        else:
            line = max((x for x in range(1, 16) if sum(1 for w in wons if w >= x) >= min_hits), default=0)
            hits = sum(1 for w in wons if w >= line)
        if line < min_line or hits < min_hits:
            continue
        recent = [{"corners": m["corners_for"], "opponent": m["opponent"], "home": m["home"], "date": m["date"]}
                  for m in reversed(pool)]
        nf = next_fx.get(t["team_id"])
        if within_days is not None:
            if not nf:
                continue
            try:
                dt = datetime.fromisoformat(nf["date"].replace("Z", "+00:00"))
            except Exception:
                continue
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            if dt < now or dt > now + timedelta(days=within_days):
                continue
        projection = None
        if nf:
            opp = teams_by_id.get(nf["opponent_team_id"])
            team_venue = "home" if nf["is_home"] else "away"
            opp_venue = "away" if nf["is_home"] else "home"
            t_for = _real_avg(t, team_venue, "corners_for")
            o_against = _real_avg(opp, opp_venue, "corners_against")
            if t_for is not None and o_against is not None:
                lam = round((t_for + o_against) / 2, 2)
                p = poisson_ge(line, lam)
                mkey = f"{team_venue}_over_{line - 0.5}"
                book = odds_map.get(nf["fixture_id"], {}).get(mkey)
                ev = round((book * p - 1) * 100, 2) if book else None
                projection = {"team_for": round(t_for, 2), "opp_conceded": round(o_against, 2),
                              "lambda": lam, "prob": round(p * 100, 1), "fair_odds": fair_odds(p),
                              "market_key": mkey, "book_odds": book, "ev": ev,
                              "tier": tier_for_ev(ev) if ev is not None else None}
        results.append({
            "team_id": t["team_id"], "name": t["name"], "league_id": t["league_id"],
            "league_name": leagues.get(t["league_id"], ""), "side": side, "window": window,
            "min_hits": min_hits, "hits": hits, "line": line,
            "avg": round(sum(wons) / len(wons), 2), "min_won": min(wons), "max_won": max(wons),
            "real_samples": t.get("real_samples", 0), "recent": recent,
            "next_fixture": nf, "projection": projection,
        })
    results.sort(key=lambda x: (x["line"], x["hits"], x["avg"]), reverse=True)
    return results


@api_router.get("/leagues/{league_id}/matchups")
async def matchups(league_id: str, side: str = "overall", user: dict = Depends(get_current_user)):
    """Top corner-winning teams in a league (by venue) with their next fixture + opponent-concede mismatch."""
    teams = await db.teams.find({"league_id": league_id}, {"_id": 0}).to_list(200)
    teams_by_id = {t["team_id"]: t for t in teams}
    next_fx = await _next_fixtures({"league_id": league_id})
    all_won = [m["corners_for"] for t in teams for m in (_src(t))]
    avg = (sum(all_won) / len(all_won)) if all_won else 5.0
    out = []
    for t in teams:
        side_for = _real_avg(t, side, "corners_for") or 0
        overall_for = _real_avg(t, "overall", "corners_for") or 0
        overall_ag = _real_avg(t, "overall", "corners_against") or 0
        nf = next_fx.get(t["team_id"])
        projection, tier = None, "none"
        if nf:
            venue = "home" if nf["is_home"] else "away"
            opp_venue = "away" if nf["is_home"] else "home"
            team_for = _real_avg(t, venue, "corners_for") or overall_for
            opp = teams_by_id.get(nf["opponent_team_id"])
            opp_conc = (_real_avg(opp, opp_venue, "corners_against") if opp else None)
            if opp_conc is not None:
                lam = round((team_for + opp_conc) / 2, 2)
                line = max(3, round(lam) - 1)
                p = poisson_ge(line, lam)
                projection = {"team_for": round(team_for, 2), "opp_conceded": round(opp_conc, 2),
                              "lambda": lam, "line": line, "prob": round(p * 100, 1), "fair_odds": fair_odds(p)}
                if team_for >= avg * 1.1 and opp_conc >= avg * 1.1:
                    tier = "strong"
                elif lam >= avg * 1.08:
                    tier = "decent"
        out.append({"team_id": t["team_id"], "name": t["name"], "side": side,
                    "side_for": round(side_for, 2), "overall_for": round(overall_for, 2),
                    "overall_against": round(overall_ag, 2), "real_samples": t.get("real_samples", 0),
                    "next_fixture": nf, "projection": projection, "tier": tier})
    out.sort(key=lambda x: x["side_for"], reverse=True)
    return {"league_avg_won": round(avg, 2), "teams": out}


@api_router.get("/trends")
async def trends(league_id: Optional[str] = None, window: int = 5, metric: str = "total",
                 side: str = "overall", user: dict = Depends(get_current_user)):
    """Teams currently averaging MORE corners than their season baseline (hot form), by venue."""
    q = {} if not league_id or league_id == "all" else {"league_id": league_id}
    teams = await db.teams.find(q, {"_id": 0}).to_list(1000)
    leagues = {l["league_id"]: l["name"] for l in await db.leagues.find({}, {"_id": 0}).to_list(100)}
    next_fx = await _next_fixtures(q)
    out = []
    for t in teams:
        src = _src(t)
        if side == "home":
            pool = [m for m in src if m["home"]]
        elif side == "away":
            pool = [m for m in src if not m["home"]]
        else:
            pool = src
        if len(pool) < window + 1:
            continue
        recent = pool[-window:]

        def mean(rows, fn):
            return round(sum(fn(m) for m in rows) / len(rows), 2)

        rec_total = mean(recent, lambda m: m["corners_for"] + m["corners_against"])
        season_total = mean(pool, lambda m: m["corners_for"] + m["corners_against"])
        rec_won = mean(recent, lambda m: m["corners_for"])
        season_won = mean(pool, lambda m: m["corners_for"])
        delta = round((rec_total - season_total) if metric == "total" else (rec_won - season_won), 2)
        if delta <= 0:
            continue
        out.append({"team_id": t["team_id"], "name": t["name"], "league_id": t["league_id"],
                    "league_name": leagues.get(t["league_id"], ""), "window": window, "side": side,
                    "recent_total": rec_total, "season_total": season_total,
                    "recent_won": rec_won, "season_won": season_won,
                    "delta": delta, "real_samples": t.get("real_samples", 0),
                    "next_fixture": next_fx.get(t["team_id"])})
    out.sort(key=lambda x: x["delta"], reverse=True)
    return out


async def _all_mismatches(within_days: Optional[int] = None, limit: int = 20):
    teams = await db.teams.find({}, {"_id": 0}).to_list(2000)
    teams_by_id = {t["team_id"]: t for t in teams}
    leagues = {l["league_id"]: l["name"] for l in await db.leagues.find({}, {"_id": 0}).to_list(100)}
    next_fx = await _next_fixtures({})
    # per-league average corners won
    league_avgs = {}
    for t in teams:
        vals = [m["corners_for"] for m in _src(t)]
        league_avgs.setdefault(t["league_id"], []).extend(vals)
    league_avgs = {k: (sum(v) / len(v) if v else 5.0) for k, v in league_avgs.items()}
    now = datetime.now(timezone.utc)
    out = []
    for t in teams:
        nf = next_fx.get(t["team_id"])
        if not nf:
            continue
        if within_days is not None:
            try:
                dt = datetime.fromisoformat(nf["date"].replace("Z", "+00:00"))
            except Exception:
                continue
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            if dt < now or dt > now + timedelta(days=within_days):
                continue
        venue = "home" if nf["is_home"] else "away"
        opp_venue = "away" if nf["is_home"] else "home"
        team_for = _real_avg(t, venue, "corners_for")
        opp = teams_by_id.get(nf["opponent_team_id"])
        opp_conc = (_real_avg(opp, opp_venue, "corners_against") if opp else None)
        if team_for is None or opp_conc is None:
            continue
        avg = league_avgs.get(t["league_id"], 5.0)
        if not (team_for >= avg * 1.1 and opp_conc >= avg * 1.1):
            continue
        lam = round((team_for + opp_conc) / 2, 2)
        line = max(3, round(lam) - 1)
        p = poisson_ge(line, lam)
        out.append({"team_id": t["team_id"], "name": t["name"], "league_id": t["league_id"],
                    "league_name": leagues.get(t["league_id"], ""), "team_for": round(team_for, 2),
                    "opp_conceded": round(opp_conc, 2), "lambda": lam, "line": line,
                    "prob": round(p * 100, 1), "fair_odds": fair_odds(p),
                    "next_fixture": nf, "real_samples": t.get("real_samples", 0)})
    out.sort(key=lambda x: x["lambda"], reverse=True)
    return out[:limit]


@api_router.get("/top-mismatches")
async def top_mismatches(within_days: Optional[int] = None, limit: int = 20,
                         user: dict = Depends(get_current_user)):
    return await _all_mismatches(within_days, limit)


@api_router.get("/best-bets")
async def best_bets(user: dict = Depends(get_current_user)):
    val = await scanner(league_id="all", market="all", min_edge=0.0, user=user)
    strk = await streaks(league_id="all", side="overall", window=5, min_hits=5,
                         threshold=None, min_line=3, within_days=None, user=user)
    mism = await _all_mismatches(within_days=None, limit=1)
    return {"value": val[0] if val else None,
            "streak": strk[0] if strk else None,
            "mismatch": mism[0] if mism else None}


# ----------------------------- Bet Tracking + Kelly -----------------------------

def kelly_fraction(prob: float, book_odds: float) -> float:
    b = book_odds - 1.0
    if b <= 0:
        return 0.0
    q = 1.0 - prob
    f = (b * prob - q) / b
    return max(0.0, round(f, 4))


def bet_profit(bet: dict) -> float:
    if bet["status"] == "won":
        return round(bet["stake"] * (bet["book_odds"] - 1.0), 2)
    if bet["status"] == "lost":
        return round(-bet["stake"], 2)
    return 0.0


class BankrollBody(BaseModel):
    bankroll: float


@api_router.get("/bankroll")
async def get_bankroll(user: dict = Depends(get_current_user)):
    return {"bankroll": user.get("bankroll", 1000.0)}


@api_router.put("/bankroll")
async def set_bankroll(body: BankrollBody, user: dict = Depends(get_current_user)):
    await db.users.update_one({"user_id": user["user_id"]}, {"$set": {"bankroll": round(body.bankroll, 2)}})
    return {"bankroll": round(body.bankroll, 2)}


class BetBody(BaseModel):
    fixture_id: str
    market_key: str
    stake: float


@api_router.post("/bets")
async def create_bet(body: BetBody, user: dict = Depends(get_current_user)):
    fx = await db.fixtures.find_one({"fixture_id": body.fixture_id}, {"_id": 0})
    if not fx:
        raise HTTPException(status_code=404, detail="Fixture not found")
    odds = await _odds_for(body.fixture_id)
    model = await get_fixture_model(fx, odds)
    market = next((m for m in model["markets"] if m["key"] == body.market_key), None)
    if not market or market["book_odds"] is None:
        raise HTTPException(status_code=400, detail="No book odds entered for this market")
    prob = market["prob"] / 100.0
    bet = {
        "bet_id": f"bet_{uuid.uuid4().hex[:12]}", "user_id": user["user_id"],
        "fixture_id": fx["fixture_id"], "league_id": fx["league_id"],
        "home_name": fx["home_name"], "away_name": fx["away_name"],
        "market_key": market["key"], "market_label": f"{market['group_label']} {market['label']}",
        "book_odds": market["book_odds"], "fair_odds": market["fair_odds"], "prob": market["prob"],
        "ev": market["ev"], "tier": market["tier"], "kelly_fraction": kelly_fraction(prob, market["book_odds"]),
        "stake": round(body.stake, 2), "status": "pending",
        "placed_at": datetime.now(timezone.utc).isoformat(), "settled_at": None,
    }
    await db.bets.insert_one(dict(bet))
    return {**bet, "profit": 0.0}


@api_router.get("/bets")
async def list_bets(user: dict = Depends(get_current_user)):
    bets = await db.bets.find({"user_id": user["user_id"]}, {"_id": 0}).to_list(500)
    bets.sort(key=lambda b: b["placed_at"], reverse=True)
    return [{**b, "profit": bet_profit(b)} for b in bets]


class BetStatusBody(BaseModel):
    status: str


@api_router.patch("/bets/{bet_id}")
async def update_bet(bet_id: str, body: BetStatusBody, user: dict = Depends(get_current_user)):
    if body.status not in ["pending", "won", "lost", "void"]:
        raise HTTPException(status_code=400, detail="Invalid status")
    bet = await db.bets.find_one({"bet_id": bet_id, "user_id": user["user_id"]}, {"_id": 0})
    if not bet:
        raise HTTPException(status_code=404, detail="Bet not found")
    settled = None if body.status == "pending" else datetime.now(timezone.utc).isoformat()
    await db.bets.update_one({"bet_id": bet_id, "user_id": user["user_id"]},
                             {"$set": {"status": body.status, "settled_at": settled}})
    bet["status"] = body.status
    bet["settled_at"] = settled
    return {**bet, "profit": bet_profit(bet)}


@api_router.delete("/bets/{bet_id}")
async def delete_bet(bet_id: str, user: dict = Depends(get_current_user)):
    res = await db.bets.delete_one({"bet_id": bet_id, "user_id": user["user_id"]})
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Bet not found")
    return {"ok": True}


@api_router.get("/bets/stats")
async def bet_stats(user: dict = Depends(get_current_user)):
    bets = await db.bets.find({"user_id": user["user_id"]}, {"_id": 0}).to_list(500)
    leagues = {l["league_id"]: l["name"] for l in await db.leagues.find({}, {"_id": 0}).to_list(100)}
    settled = [b for b in bets if b["status"] in ("won", "lost")]
    staked = round(sum(b["stake"] for b in settled), 2)
    profit = round(sum(bet_profit(b) for b in settled), 2)
    wins = len([b for b in settled if b["status"] == "won"])
    pending = [b for b in bets if b["status"] == "pending"]
    by_league = {}
    for b in settled:
        key = leagues.get(b["league_id"], b["league_id"])
        d = by_league.setdefault(key, {"league": key, "staked": 0.0, "profit": 0.0, "count": 0})
        d["staked"] = round(d["staked"] + b["stake"], 2)
        d["profit"] = round(d["profit"] + bet_profit(b), 2)
        d["count"] += 1
    for d in by_league.values():
        d["roi"] = round(d["profit"] / d["staked"] * 100, 1) if d["staked"] else 0.0
    return {
        "bankroll": user.get("bankroll", 1000.0),
        "total_bets": len(bets), "settled": len(settled), "pending": len(pending),
        "pending_stake": round(sum(b["stake"] for b in pending), 2),
        "staked": staked, "profit": profit,
        "roi": round(profit / staked * 100, 1) if staked else 0.0,
        "win_rate": round(wins / len(settled) * 100, 1) if settled else 0.0,
        "by_league": sorted(by_league.values(), key=lambda x: x["profit"], reverse=True),
    }


app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','),
    allow_methods=["*"],
    allow_headers=["*"],
)


MANAGED_LEAGUE_IDS = {"eng-pl", "eng-ch", "eng-l1", "eng-l2", "eng-nl", "aus-al", "nor-el",
                      "ned-ere", "ned-ed", "bra-sa", "bra-sb", "ita-sa", "fra-l1", "esp-ll"}


def run_sync_all():
    import subprocess, sys
    logger.info("Scheduled sync: launching sync_real.py for all leagues")
    subprocess.Popen([sys.executable, str(ROOT_DIR / "sync_real.py")], cwd=str(ROOT_DIR))


@app.on_event("startup")
async def on_startup():
    # remove any legacy / non-managed leagues (e.g. old mock leagues from an earlier deploy)
    stale = await db.leagues.find({"league_id": {"$nin": list(MANAGED_LEAGUE_IDS)}}, {"_id": 0, "league_id": 1}).to_list(100)
    stale_ids = [l["league_id"] for l in stale]
    if stale_ids:
        await db.leagues.delete_many({"league_id": {"$in": stale_ids}})
        await db.teams.delete_many({"league_id": {"$in": stale_ids}})
        await db.fixtures.delete_many({"league_id": {"$in": stale_ids}})
        logger.info("Removed stale leagues: %s", stale_ids)
    # first boot (e.g. fresh production DB): if no real data yet, pull it now
    real = await db.leagues.count_documents({"data_source": "real"})
    if real == 0:
        logger.info("No real data found — launching initial API-Football sync")
        run_sync_all()
    from apscheduler.schedulers.asyncio import AsyncIOScheduler
    scheduler = AsyncIOScheduler(timezone="UTC")
    scheduler.add_job(run_sync_all, "interval", hours=12, id="sync_all", replace_existing=True)
    scheduler.start()
    app.state.scheduler = scheduler
    logger.info("Auto-refresh scheduler started (every 12h)")


@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()
