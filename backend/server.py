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
from collections import defaultdict, deque
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


# ---- Model v2: Negative-Binomial (dispersion-corrected) + shots/form intent ----
NB_R = 11          # dispersion param tuned via backtester (Brier 0.2226, calibration gap 0.80%)
REF_SHOTS = 12.0   # fallback league avg shots when unknown


def nb_ge(k: int, lam: float, r: float = NB_R) -> float:
    """P(X >= k) under a Negative Binomial with mean lam (better tail fit than Poisson)."""
    if lam <= 0:
        return 0.0
    k = int(k)
    p = r / (r + lam)
    cum = 0.0
    for i in range(k):
        cum += math.exp(math.lgamma(i + r) - math.lgamma(r) - math.lgamma(i + 1)
                        + r * math.log(p) + i * math.log(1.0 - p))
    return max(0.0, min(1.0, 1.0 - cum))


def _shots_form(team: dict, venue: str):
    rms = (team or {}).get("real_matches") or []
    if venue == "home":
        pool = [m for m in rms if m["home"]]
    elif venue == "away":
        pool = [m for m in rms if not m["home"]]
    else:
        pool = rms
    if not pool:
        pool = rms
    if not pool:
        return None, None
    sf = sum(m.get("shots_for", 0) for m in pool) / len(pool)
    fh = sum(1 for m in pool if m.get("fh_goals_for", 0) >= 1) / len(pool)
    return sf, fh


def v2_lambda(base: float, team: dict, venue: str, league_shots: float) -> float:
    """Nudge base corner-lambda by shots-intent (+/-~10%) and first-half-goal form (+/-3%)."""
    sf, fh = _shots_form(team, venue)
    if sf is None or not league_shots:
        return round(base, 2)
    intent = 0.90 + 0.10 * max(0.6, min(1.5, sf / league_shots))
    form = 1.0 + 0.03 * (fh - 0.5)
    return round(base * intent * form, 2)


def _league_shots_map(teams: list) -> dict:
    agg = defaultdict(list)
    for t in teams:
        for m in (t.get("real_matches") or []):
            agg[t["league_id"]].append(m.get("shots_for", 0))
    return {lid: (sum(v) / len(v) if v else REF_SHOTS) for lid, v in agg.items()}


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


def expected_lambdas(home: dict, away: dict, league_shots: float = REF_SHOTS) -> dict:
    h_home = team_split(_src(home), "home", 0)
    a_away = team_split(_src(away), "away", 0)
    # fall back to overall if a team has no games on that venue
    if h_home["played"] == 0:
        h_home = team_split(_src(home), "overall", 0)
    if a_away["played"] == 0:
        a_away = team_split(_src(away), "overall", 0)
    lam_home = v2_lambda((h_home["for_avg"] + a_away["against_avg"]) / 2, home, "home", league_shots)
    lam_away = v2_lambda((a_away["for_avg"] + h_home["against_avg"]) / 2, away, "away", league_shots)
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
            p = nb_ge(k, lam) if group in ("home", "away") else poisson_ge(k, lam)
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
    league = await db.leagues.find_one({"league_id": fixture["league_id"]}, {"_id": 0}) or {}
    ls = league.get("avg_shots") or REF_SHOTS
    lambdas = expected_lambdas(home, away, ls)
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

@api_router.get("/export/csv")
async def export_csv(type: str = "teams", user: dict = Depends(get_current_user)):
    from fastapi.responses import PlainTextResponse
    leagues = {l["league_id"]: l for l in await db.leagues.find({}, {"_id": 0}).to_list(100)}
    rows = []
    if type == "fixtures":
        rows.append("League,Date,Home,Away,Lambda_Home,Lambda_Away,Lambda_Total,Confidence")
        teams = {t["team_id"]: t for t in await db.teams.find({}, {"_id": 0}).to_list(5000)}
        fixtures = await db.fixtures.find({}, {"_id": 0}).to_list(2000)
        fixtures.sort(key=lambda f: (f["league_id"], f["date"]))
        for fx in fixtures:
            h, a = teams.get(fx["home_team_id"]), teams.get(fx["away_team_id"])
            if not h or not a:
                continue
            lam = expected_lambdas(h, a)
            conf = confidence_for(h, a)
            ln = leagues.get(fx["league_id"], {}).get("name", fx["league_id"])
            rows.append(f"{ln},{fx['date'][:10]},{fx['home_name']},{fx['away_name']},{lam['home']},{lam['away']},{lam['total']},{conf['label']}")
    else:
        rows.append("League,Team,GamesReal,Won_Overall,Conc_Overall,Won_Home,Conc_Home,Won_Away,Conc_Away,Won_Last5,Conc_Last5,Total_PerGame")
        teams = await db.teams.find({}, {"_id": 0}).to_list(5000)
        for t in teams:
            src = _src(t)
            ov = team_split(src, "overall", 0)
            hm = team_split(src, "home", 0)
            aw = team_split(src, "away", 0)
            l5 = team_split(src, "overall", 5)
            ln = leagues.get(t["league_id"], {}).get("name", t["league_id"])
            name = t["name"].replace(",", " ")
            rows.append(f"{ln},{name},{t.get('real_samples',0)},{ov['for_avg']},{ov['against_avg']},{hm['for_avg']},{hm['against_avg']},{aw['for_avg']},{aw['against_avg']},{l5['for_avg']},{l5['against_avg']},{ov['total_avg']}")
    return PlainTextResponse("\n".join(rows), media_type="text/csv",
                             headers={"Content-Disposition": f"attachment; filename=corner-model-{type}.csv"})


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
    import subprocess, sys, os as _os
    subprocess.Popen([sys.executable, str(ROOT_DIR / "sync_real.py"), league_id], cwd=str(ROOT_DIR),
                     env={**_os.environ, "SYNC_TRIGGER": "manual"})
    return {"status": "syncing", "league_id": league_id, "started_at": now.isoformat()}


_last_refresh_all = {"at": None}


@api_router.post("/sync/refresh-all")
async def refresh_all(user: dict = Depends(get_current_user)):
    now = datetime.now(timezone.utc)
    last = _last_refresh_all["at"]
    if last and (now - last).total_seconds() < 300:
        return {"status": "already_syncing", "started_at": last.isoformat()}
    _last_refresh_all["at"] = now
    run_sync_all("manual")
    return {"status": "syncing", "started_at": now.isoformat()}


@api_router.get("/sync/runs")
async def sync_runs(limit: int = 8, user: dict = Depends(get_current_user)):
    runs = await db.sync_runs.find({}, {"_id": 0}).sort("started_at", -1).limit(limit).to_list(limit)
    return runs


def _pick_profit(p: dict) -> Optional[float]:
    """Profit in units at a flat 1u stake. A loss always costs -1u; a win pays
    (odds-1)u but only if we know the odds (some historical picks have none)."""
    if p["status"] == "lost":
        return -1.0
    if p["status"] == "won":
        return round(p["odds"] - 1.0, 2) if p.get("odds") else None
    return None


@api_router.get("/picks")
async def get_picks(user: dict = Depends(get_current_user)):
    picks = await db.picks.find({}, {"_id": 0}).to_list(500)
    picks.sort(key=lambda p: (p.get("date") or "", p.get("kickoff") or "", p.get("home") or p.get("team") or ""))
    for p in picks:
        p["profit"] = _pick_profit(p)
    won = sum(1 for p in picks if p["status"] == "won")
    lost = sum(1 for p in picks if p["status"] == "lost")
    pending = sum(1 for p in picks if p["status"] == "pending")
    settled = won + lost
    # flat 1u staking: only picks with a computable profit are "priced"
    priced = [p for p in picks if p["profit"] is not None]
    profit = round(sum(p["profit"] for p in priced), 2)
    staked = len(priced)
    unpriced_wins = sum(1 for p in picks if p["status"] == "won" and not p.get("odds"))
    return {"record": {"won": won, "lost": lost, "pending": pending, "total": len(picks),
                       "settled": settled, "win_rate": round(won / settled * 100, 1) if settled else 0.0,
                       "profit": profit, "staked": staked,
                       "roi": round(profit / staked * 100, 1) if staked else 0.0,
                       "unpriced_wins": unpriced_wins},
            "picks": picks}


_last_pick_settle = {"at": None}


@api_router.post("/picks/settle")
async def settle_picks_now(user: dict = Depends(get_current_user)):
    now = datetime.now(timezone.utc)
    last = _last_pick_settle["at"]
    if last and (now - last).total_seconds() < 120:
        return {"status": "already_running", "started_at": last.isoformat()}
    _last_pick_settle["at"] = now
    import subprocess, sys, os as _os
    subprocess.Popen([sys.executable, str(ROOT_DIR / "settle_picks.py")], cwd=str(ROOT_DIR),
                     env={**_os.environ})
    return {"status": "settling", "started_at": now.isoformat()}


# ---- Phase 3: Claude explainer — justify a model-flagged corner pick ----
from emergentintegrations.llm.chat import LlmChat, UserMessage

EMERGENT_LLM_KEY = os.environ.get("EMERGENT_LLM_KEY")
_explain_calls = defaultdict(deque)  # per-user timestamps for LLM rate limiting


class ExplainReq(BaseModel):
    key: str
    team: str
    opponent: str
    league: str = ""
    is_home: bool = True
    line: int
    team_for: float
    opp_conceded: float
    lam: float
    prob: float
    fair_odds: float
    team_shots: Optional[float] = None
    fh_goal_rate: Optional[float] = None


@api_router.post("/explain")
async def explain_pick(req: ExplainReq, user: dict = Depends(get_current_user)):
    # derive the cache key server-side from the actual stats (ignore client key to prevent poisoning)
    import hashlib
    sig = f"{req.team}|{req.opponent}|{req.line}|{round(req.team_for,1)}|{round(req.opp_conceded,1)}|{round(req.lam,1)}|{round(req.prob)}"
    ckey = hashlib.md5(sig.encode()).hexdigest()
    cached = await db.explanations.find_one({"_id": ckey}, {"_id": 0})
    if cached:
        return {"explanation": cached["text"], "cached": True}
    if not EMERGENT_LLM_KEY:
        raise HTTPException(status_code=503, detail="LLM key not configured")
    # light per-user throttle on uncached (paid) calls
    now_ts = datetime.now(timezone.utc).timestamp()
    bucket = _explain_calls[user["user_id"]]
    while bucket and now_ts - bucket[0] > 60:
        bucket.popleft()
    if len(bucket) >= 20:
        raise HTTPException(status_code=429, detail="Too many explanations — please wait a moment.")
    bucket.append(now_ts)
    venue = "at home" if req.is_home else "away"
    extra = ""
    if req.team_shots is not None:
        extra += f"\n- {req.team} average shots/game: {req.team_shots:.1f}"
    if req.fh_goal_rate is not None:
        extra += f"\n- {req.team} scores a first-half goal in {round(req.fh_goal_rate * 100)}% of games"
    prompt = (
        f"Fixture: {req.team} vs {req.opponent} ({req.league}), {req.team} playing {venue}.\n"
        f"Model read on the '{req.team} {req.line}+ team corners' market:\n"
        f"- {req.team} wins {req.team_for:.1f} corners/game (recent form)\n"
        f"- {req.opponent} concedes {req.opp_conceded:.1f} corners/game\n"
        f"- Projected corners (lambda) for {req.team}: {req.lam:.1f}\n"
        f"- Model probability of {req.line}+: {req.prob:.0f}%  (fair odds {req.fair_odds:.2f}){extra}\n\n"
        f"Explain in 2 short sentences WHY this is a strong corner angle, in plain punter language. "
        f"Reference the concrete numbers. Do not invent stats, injuries or news. No preamble, no disclaimer."
    )
    chat = LlmChat(
        api_key=EMERGENT_LLM_KEY,
        session_id=f"explain-{req.key}",
        system_message="You are a sharp, concise football corners betting analyst. You only use the numbers provided.",
    ).with_model("anthropic", "claude-sonnet-4-6")
    try:
        resp = await chat.send_message(UserMessage(text=prompt))
    except Exception as e:
        logger.error("explain LLM error: %s", e)
        raise HTTPException(status_code=502, detail="Could not generate explanation")
    text = (resp if isinstance(resp, str) else str(resp)).strip()
    await db.explanations.update_one(
        {"_id": ckey},
        {"$set": {"_id": ckey, "text": text, "created_at": datetime.now(timezone.utc).isoformat()}},
        upsert=True)
    return {"explanation": text, "cached": False}


def model_lambda(model: str, team_for: float, opp_against: float,
                 team_shots: float = 0.0, league_shots: float = 0.0, team_fh: float = 0.5) -> float:
    """Expected team corners. v1 = corner form only. v2 = + shots-intent x first-half-goal form
    (matches the tuned production formula)."""
    base = (team_for + opp_against) / 2.0
    if model == "v2" and league_shots > 0 and team_shots > 0:
        intent = 0.90 + 0.10 * max(0.6, min(1.5, team_shots / league_shots))
        form = 1.0 + 0.03 * (team_fh - 0.5)
        base = base * intent * form
    return base


@api_router.get("/backtest")
async def backtest(league_id: str = "all", window: int = 10, min_games: int = 5,
                   model: str = "v1", user: dict = Depends(get_current_user)):
    """Walk-forward backtest over cached fixture stats: for each past match we predict
    team-corner probabilities from prior form only, then compare to what actually happened."""
    q = {} if league_id == "all" else {"league_id": league_id}
    matches = await db.fixture_stats.find(q, {"_id": 0}).to_list(30000)
    matches.sort(key=lambda m: m["date"])
    # league average shots (for v2 intent scaling)
    all_shots = [m.get("home_shots", 0) for m in matches] + [m.get("away_shots", 0) for m in matches]
    league_shots = (sum(all_shots) / len(all_shots)) if all_shots else 0.0

    hist_for = defaultdict(lambda: deque(maxlen=window))
    hist_against = defaultdict(lambda: deque(maxlen=window))
    hist_shots = defaultdict(lambda: deque(maxlen=window))
    hist_fh = defaultdict(lambda: deque(maxlen=window))
    lines = [4, 5, 6, 7]
    stats = {L: {"n": 0, "pred": 0.0, "hit": 0, "brier": 0.0} for L in lines}
    preds = 0

    def avg(d):
        return sum(d) / len(d) if d else 0.0

    prob_fn = nb_ge if model == "v2" else poisson_ge
    for m in matches:
        h, a = m["home_id"], m["away_id"]
        sides = [
            ("home", hist_for[h], hist_against[a], hist_shots[h], hist_fh[h], m["home_corners"],
             len(hist_for[h]) >= min_games and len(hist_against[a]) >= min_games),
            ("away", hist_for[a], hist_against[h], hist_shots[a], hist_fh[a], m["away_corners"],
             len(hist_for[a]) >= min_games and len(hist_against[h]) >= min_games),
        ]
        for _side, tf_d, oa_d, ts_d, fh_d, actual, can in sides:
            if not can:
                continue
            lam = model_lambda(model, avg(tf_d), avg(oa_d), avg(ts_d), league_shots, avg(fh_d))
            preds += 1
            for L in lines:
                p = prob_fn(L, lam)
                hit = 1 if actual >= L else 0
                s = stats[L]
                s["n"] += 1; s["pred"] += p; s["hit"] += hit; s["brier"] += (p - hit) ** 2
        # update rolling form AFTER predicting (no leakage)
        hist_for[h].append(m["home_corners"]); hist_against[h].append(m["away_corners"]); hist_shots[h].append(m.get("home_shots", 0)); hist_fh[h].append(1 if m.get("home_fh_goals", 0) >= 1 else 0)
        hist_for[a].append(m["away_corners"]); hist_against[a].append(m["home_corners"]); hist_shots[a].append(m.get("away_shots", 0)); hist_fh[a].append(1 if m.get("away_fh_goals", 0) >= 1 else 0)

    out_lines, total_brier, total_n = [], 0.0, 0
    for L in lines:
        s = stats[L]
        if s["n"] == 0:
            continue
        out_lines.append({"line": L, "n": s["n"],
                          "model_prob": round(s["pred"] / s["n"] * 100, 1),
                          "actual_hit_rate": round(s["hit"] / s["n"] * 100, 1),
                          "calibration_gap": round(abs(s["pred"] - s["hit"]) / s["n"] * 100, 1),
                          "brier": round(s["brier"] / s["n"], 4)})
        total_brier += s["brier"]; total_n += s["n"]
    return {"league_id": league_id, "model": model, "window": window, "min_games": min_games,
            "matches": len(matches), "predictions": preds,
            "overall_brier": round(total_brier / total_n, 4) if total_n else None,
            "lines": out_lines}


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


@api_router.get("/leagues/{league_id}/corner-table")
async def corner_table(league_id: str, user: dict = Depends(get_current_user)):
    """Corner-league standings: teams ranked by corners won/game, with shots taken/game (real data)."""
    teams = await db.teams.find({"league_id": league_id}, {"_id": 0}).to_list(200)
    league = await db.leagues.find_one({"league_id": league_id}, {"_id": 0}) or {}
    out = []
    for t in teams:
        real = t.get("real_matches") or []
        n = len(real)
        if n == 0:
            won = concd = shots = 0.0
        else:
            won = sum(m["corners_for"] for m in real) / n
            concd = sum(m["corners_against"] for m in real) / n
            shots = sum(m.get("shots_for", 0) for m in real) / n
        out.append({"team_id": t["team_id"], "name": t["name"], "games": n,
                    "corners_won": round(won, 2), "corners_conceded": round(concd, 2),
                    "shots": round(shots, 1), "real_samples": t.get("real_samples", 0)})
    out.sort(key=lambda x: x["corners_won"], reverse=True)
    return {"league_id": league_id, "league_name": league.get("name", league_id),
            "country": league.get("country", ""), "teams": out}


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
            if market and market != "all":
                if market == "team":
                    if m["group"] not in ("home", "away"):
                        continue
                elif m["group"] != market:
                    continue
            if m["ev"] < min_edge:
                continue
            results.append({"fixture_id": fx["fixture_id"], "league_id": fx["league_id"],
                            "league_name": leagues.get(fx["league_id"], ""), "home_name": fx["home_name"],
                            "away_name": fx["away_name"], "date": fx["date"],
                            "round": fx.get("round"),
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
                           "round": fx.get("round"),
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
    ls_map = _league_shots_map(teams)
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
                                "round": fx.get("round"),
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
                lam = v2_lambda((t_for + o_against) / 2, t, team_venue, ls_map.get(t["league_id"], REF_SHOTS))
                p = nb_ge(line, lam)
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
    ls = _league_shots_map(teams).get(league_id, REF_SHOTS)
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
                lam = v2_lambda((team_for + opp_conc) / 2, t, venue, ls)
                line = max(3, round(lam) - 1)
                p = nb_ge(line, lam)
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
    ls_map = _league_shots_map(teams)
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
        lam = v2_lambda((team_for + opp_conc) / 2, t, venue, ls_map.get(t["league_id"], REF_SHOTS))
        line = max(3, round(lam) - 1)
        p = nb_ge(line, lam)
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
    val = await scanner(league_id="all", market="team", min_edge=0.0, user=user)
    strk = await streaks(league_id="all", side="overall", window=5, min_hits=5,
                         threshold=None, min_line=3, within_days=None, user=user)
    mism = await _all_mismatches(within_days=None, limit=1)
    return {"value": val[0] if val else None,
            "streak": strk[0] if strk else None,
            "mismatch": mism[0] if mism else None}


@api_router.get("/export")
async def export_report(user: dict = Depends(get_current_user)):
    from fastapi.responses import PlainTextResponse
    leagues = await db.leagues.find({}, {"_id": 0}).to_list(100)
    leagues.sort(key=lambda l: (l.get("country", ""), l.get("name", "")))
    now = datetime.now(timezone.utc)
    lines = []
    lines.append("# The Corner Model 2.0 — Full Data Export")
    lines.append(f"Generated: {now.strftime('%Y-%m-%d %H:%M UTC')}")
    lines.append("Corner stats are REAL (API-Football). Bookmaker odds are user-entered; model figures are the fair values.\n")

    for lg in leagues:
        lid = lg["league_id"]
        teams = await db.teams.find({"league_id": lid}, {"_id": 0}).to_list(200)
        teams_by_id = {t["team_id"]: t for t in teams}
        fixtures = await db.fixtures.find({"league_id": lid}, {"_id": 0}).to_list(200)
        fixtures.sort(key=lambda f: f["date"])
        all_won = [m["corners_for"] for t in teams for m in _src(t)]
        avg = round(sum(all_won) / len(all_won), 2) if all_won else 0
        lines.append(f"\n## {lg.get('country','')} — {lg.get('name','')} (season {lg.get('season','?')}, avg {avg} corners won/team/game)")

        # Upcoming fixtures with model projections
        lines.append("\n### Upcoming fixtures (model projections)")
        for fx in fixtures:
            h, a = teams_by_id.get(fx["home_team_id"]), teams_by_id.get(fx["away_team_id"])
            if not h or not a:
                continue
            lam = expected_lambdas(h, a)
            conf = confidence_for(h, a)
            d = fx["date"][:10]
            lines.append(f"- {d}  {fx['home_name']} vs {fx['away_name']}  | total λ {lam['total']} (home {lam['home']} / away {lam['away']}) | confidence {conf['label']} ({conf['score']})")

        # Team corner form (real games)
        rows = []
        for t in teams:
            gp = len(_src(t))
            ov = team_split(_src(t), "overall", 0)
            hm = team_split(_src(t), "home", 0)
            aw = team_split(_src(t), "away", 0)
            l5 = team_split(_src(t), "overall", 5)
            rows.append((ov["for_avg"], t["name"], gp, ov, hm, aw, l5, t.get("real_samples", 0)))
        rows.sort(key=lambda x: x[0], reverse=True)
        lines.append("\n### Team corner form — won/conceded per game (real games)")
        lines.append("| Team | GP(real) | Overall W/C | Home W/C | Away W/C | Last5 W/C | Total/g |")
        lines.append("|---|---|---|---|---|---|---|")
        for _, name, gp, ov, hm, aw, l5, rs in rows:
            lines.append(f"| {name} | {rs} | {ov['for_avg']}/{ov['against_avg']} | {hm['for_avg']}/{hm['against_avg']} | {aw['for_avg']}/{aw['against_avg']} | {l5['for_avg']}/{l5['against_avg']} | {ov['total_avg']} |")

    # Cross-league sections
    mism = await _all_mismatches(within_days=None, limit=40)
    lines.append("\n\n## Top corner mismatches (strong team vs leaky defence, all leagues)")
    lines.append("| Team | League | Next | Team/g | Opp conc | Proj λ | Model line |")
    lines.append("|---|---|---|---|---|---|---|")
    for r in mism:
        nf = r.get("next_fixture") or {}
        vs = f"{'vs' if nf.get('is_home') else '@'} {nf.get('opponent','')}"
        lines.append(f"| {r['name']} | {r['league_name']} | {vs} {(nf.get('date') or '')[:10]} | {r['team_for']} | {r['opp_conceded']} | {r['lambda']} | {r['line']}+ @ {r['fair_odds']} |")

    trend = await trends(league_id="all", window=5, metric="total", side="overall", user=user)
    lines.append("\n## Hot form — averaging more total corners than season baseline (Last 5)")
    lines.append("| Team | League | Recent avg | Season avg | Δ |")
    lines.append("|---|---|---|---|---|")
    for r in trend[:40]:
        lines.append(f"| {r['name']} | {r['league_name']} | {r['recent_total']} | {r['season_total']} | +{r['delta']} |")

    strk = await streaks(league_id="all", side="overall", window=5, min_hits=5,
                         threshold=None, min_line=3, within_days=None, user=user)
    lines.append("\n## Consistency streaks — hit a team-corner line in all of last 5 games")
    lines.append("| Team | League | Line | Avg | Recent (won) |")
    lines.append("|---|---|---|---|---|")
    for r in strk[:60]:
        rec = ",".join(str(m["corners"]) for m in r["recent"])
        lines.append(f"| {r['name']} | {r['league_name']} | {r['line']}+ (5/5) | {r['avg']} | {rec} |")

    return PlainTextResponse("\n".join(lines))


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
                      "ned-ere", "ned-ed", "bra-sa", "bra-sb", "ita-sa", "fra-l1", "esp-ll",
                      "ger-bl", "ger-bl2", "por-pl", "bel-pl", "sco-pl", "tur-sl", "usa-ml",
                      "den-sl", "sui-sl", "aut-bl", "gre-sl", "jpn-j1", "arg-lp"}


STALE_HOURS = 12          # data older than this triggers a boot-time refresh
SYNC_LOCK_MINUTES = 20     # don't relaunch a sync if one started within this window


def run_sync_all(trigger="scheduled"):
    import subprocess, sys, os as _os
    logger.info("Sync (%s): launching sync_real.py for all leagues", trigger)
    subprocess.Popen([sys.executable, str(ROOT_DIR / "sync_real.py")], cwd=str(ROOT_DIR),
                     env={**_os.environ, "SYNC_TRIGGER": trigger})


async def _maybe_sync_on_boot():
    """Refresh on boot when data is missing or stale, guarded by a DB lock so
    frequent restarts (hot-reload) don't spawn overlapping syncs."""
    now = datetime.now(timezone.utc)
    real = await db.leagues.count_documents({"data_source": "real"})
    newest = await db.leagues.find({"data_source": "real"}, {"_id": 0, "synced_at": 1}) \
        .sort("synced_at", -1).limit(1).to_list(1)
    stale = True
    if newest and newest[0].get("synced_at"):
        try:
            last = datetime.fromisoformat(newest[0]["synced_at"])
            stale = (now - last).total_seconds() > STALE_HOURS * 3600
        except Exception:
            stale = True
    if real > 0 and not stale:
        return
    lock = await db.meta.find_one({"_id": "sync_lock"})
    if lock and lock.get("started_at"):
        try:
            started = datetime.fromisoformat(lock["started_at"])
            if (now - started).total_seconds() < SYNC_LOCK_MINUTES * 60:
                logger.info("Boot sync skipped — a sync started %s", lock["started_at"])
                return
        except Exception:
            pass
    await db.meta.update_one({"_id": "sync_lock"}, {"$set": {"started_at": now.isoformat()}}, upsert=True)
    logger.info("Boot sync: real=%s stale=%s — launching API-Football sync", real, stale)
    run_sync_all("boot")


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
    await _maybe_sync_on_boot()
    from apscheduler.schedulers.asyncio import AsyncIOScheduler
    from apscheduler.triggers.cron import CronTrigger
    scheduler = AsyncIOScheduler(timezone="UTC")
    scheduler.add_job(run_sync_all, CronTrigger(hour="7,19", minute=0), id="sync_all", replace_existing=True)
    scheduler.start()
    app.state.scheduler = scheduler
    logger.info("Auto-refresh scheduler started (07:00 & 19:00 UTC daily)")


@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()
