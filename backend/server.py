from fastapi import FastAPI, APIRouter, HTTPException, Depends, Request, Response
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import asyncio
import contextvars
import os
import logging
import math
import random
import re
import uuid
from pathlib import Path
from pydantic import BaseModel
from typing import List, Optional, Dict
from datetime import datetime, timezone, timedelta
from collections import defaultdict, deque

import settlement
from settlement import settle_pending

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

app = FastAPI()
api_router = APIRouter(prefix="/api")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

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

# v3 (live): the shots-intent term is driven by BLOCKED shots instead. Chosen on the
# backtester — 0.15 beat 0.10 on Brier (0.2219 -> 0.2214) and on calibration
# (0.71 -> 0.68) — after the offline harness showed the swap beating both the live
# model and adding blocked shots alongside shots (the two are largely collinear).
V3_BLOCKED_WEIGHT = 0.15
# a team needs this many games carrying the stat before it moves a price; below it,
# pricing falls back to v2's shots intent rather than trusting a thin sample
MIN_BLOCKED_GAMES = 5


def _intent(value: float, league_avg: float, weight: float) -> float:
    """Intent multiplier: +/- `weight` on lambda, clamped to 0.6-1.5x the league average."""
    return (1.0 - weight) + weight * max(0.6, min(1.5, value / league_avg))



def nb_pmf(k: int, lam: float, r: float = NB_R) -> float:
    """P(X == k) under a Negative Binomial with mean lam."""
    if lam <= 0:
        return 1.0 if k == 0 else 0.0
    k = int(k)
    if k < 0:
        return 0.0
    p = r / (r + lam)
    return math.exp(math.lgamma(k + r) - math.lgamma(r) - math.lgamma(k + 1)
                    + r * math.log(p) + k * math.log(1.0 - p))


def nb_ge(k: int, lam: float, r: float = NB_R) -> float:
    """P(X >= k) under a Negative Binomial with mean lam (better tail fit than Poisson)."""
    if lam <= 0:
        return 0.0
    k = int(k)
    cum = 0.0
    for i in range(k):
        cum += nb_pmf(i, lam, r)
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


def _blocked_form(team: dict, venue: str) -> Optional[float]:
    """Team's blocked-shots average on this venue, or None where the backfill hasn't
    reached far enough. A missing stat is never read as zero, and a handful of games
    is not enough to move a price — under MIN_BLOCKED_GAMES we say we don't know."""
    rms = (team or {}).get("real_matches") or []
    if venue == "home":
        pool = [m for m in rms if m["home"]]
    elif venue == "away":
        pool = [m for m in rms if not m["home"]]
    else:
        pool = rms
    if not pool:
        pool = rms
    vals = [m["blocked_shots_for"] for m in pool if m.get("blocked_shots_for") is not None]
    if len(vals) < MIN_BLOCKED_GAMES:
        return None
    return sum(vals) / len(vals)


def _blocked_covered(team: dict, venue: str) -> int:
    """Games on this venue that carry blocked shots — the count `_blocked_form` tests."""
    rms = (team or {}).get("real_matches") or []
    if venue == "home":
        pool = [m for m in rms if m["home"]]
    elif venue == "away":
        pool = [m for m in rms if not m["home"]]
    else:
        pool = rms
    if not pool:
        pool = rms
    return sum(1 for m in pool if m.get("blocked_shots_for") is not None)


def intent_breakdown(team: dict, venue: str, league_shots: float,
                     league_blocked: float = 0.0) -> dict:
    """Which intent term the live model applies to this team here, and why.

    `live_lambda` is DEFINED in terms of this, so a panel built on it cannot claim one
    thing while pricing quietly does another.

    source: blocked (v3) | shots (v2 fallback) | none (no shot history at all)"""
    sf, fh = _shots_form(team, venue)
    covered = _blocked_covered(team, venue)
    flat = {"source": "none", "multiplier": 1.0, "form": 1.0, "value": None,
            "league_avg": None, "weight": None, "covered": covered,
            "min_games": MIN_BLOCKED_GAMES, "fh_rate": None, "reason": "no shot data yet"}
    if sf is None:
        return flat
    form = 1.0 + 0.03 * (fh - 0.5)
    blocked = _blocked_form(team, venue)
    if blocked is not None and league_blocked:
        return {"source": "blocked", "multiplier": _intent(blocked, league_blocked, V3_BLOCKED_WEIGHT),
                "form": form, "value": round(blocked, 2), "league_avg": round(league_blocked, 2),
                "weight": V3_BLOCKED_WEIGHT, "covered": covered, "min_games": MIN_BLOCKED_GAMES,
                "fh_rate": round(fh, 3), "reason": None}
    if not league_shots:
        return {**flat, "reason": "league has no shot average"}
    reason = ("league has no blocked-shots data" if not league_blocked
              else f"only {covered} game(s) here carry blocked shots — needs {MIN_BLOCKED_GAMES}")
    return {"source": "shots", "multiplier": _intent(sf, league_shots, 0.10), "form": form,
            "value": round(sf, 2), "league_avg": round(league_shots, 2), "weight": 0.10,
            "covered": covered, "min_games": MIN_BLOCKED_GAMES, "fh_rate": round(fh, 3),
            "reason": reason}


def live_lambda(base: float, team: dict, venue: str, league_shots: float,
                league_blocked: float = 0.0) -> float:
    """Production corner-lambda (v3): blocked-shots intent x first-half-goal form.

    Falls back to v2's shots intent for any team without enough blocked-shots history,
    so a thinly-covered team prices exactly as it does today rather than worse. Both
    branches are the same shape; only the stat driving the intent differs."""
    b = intent_breakdown(team, venue, league_shots, league_blocked)
    return round(base * b["multiplier"] * b["form"], 2)


def _league_shots_map(teams: list) -> dict:
    agg = defaultdict(list)
    for t in teams:
        for m in (t.get("real_matches") or []):
            agg[t["league_id"]].append(m.get("shots_for", 0))
    return {lid: (sum(v) / len(v) if v else REF_SHOTS) for lid, v in agg.items()}


def _league_blocked_map(teams: list) -> dict:
    """League average blocked shots, over the fixtures that actually carry the stat.
    A league missing from the map has no blocked data and falls back to shots intent."""
    agg = defaultdict(list)
    for t in teams:
        for m in (t.get("real_matches") or []):
            v = m.get("blocked_shots_for")
            if v is not None:
                agg[t["league_id"]].append(v)
    return {lid: sum(v) / len(v) for lid, v in agg.items() if v}


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


# Per-feature averages exposed on every team split, each with its OWN sample count.
# Coverage differs sharply by feature — shots are reported for ~100% of fixtures but
# on-target for only ~half — so one shared count would misdescribe the thinner ones.
SPLIT_FEATURES = (("shots", "shots"), ("shots_on_target", "sot"))


def _feature_avgs(pool: List[dict], field: str, prefix: str) -> dict:
    """for/against averages over only the fixtures the provider actually covered, so a
    coverage gap reads as a smaller sample instead of dragging the average toward zero."""
    covered = [m for m in pool
               if m.get(f"{field}_for") is not None or m.get(f"{field}_against") is not None]
    fors = [m[f"{field}_for"] for m in covered if m.get(f"{field}_for") is not None]
    againsts = [m[f"{field}_against"] for m in covered if m.get(f"{field}_against") is not None]
    return {f"{prefix}_for_avg": round(sum(fors) / len(fors), 2) if fors else None,
            f"{prefix}_against_avg": round(sum(againsts) / len(againsts), 2) if againsts else None,
            f"{prefix}_games": len(covered)}


def team_split(matches: List[dict], split: str, window: int) -> dict:
    if split == "home":
        pool = [m for m in matches if m["home"]]
    elif split == "away":
        pool = [m for m in matches if not m["home"]]
    else:
        pool = matches
    pool = pool[-window:] if window else pool
    n = len(pool)
    empty_feats = {k: (0 if k.endswith("_games") else None)
                   for field, prefix in SPLIT_FEATURES
                   for k in (f"{prefix}_for_avg", f"{prefix}_against_avg", f"{prefix}_games")}
    if n == 0:
        return {"played": 0, "for_avg": 0, "against_avg": 0, "total_avg": 0, **empty_feats}
    cf = sum(m["corners_for"] for m in pool)
    ca = sum(m["corners_against"] for m in pool)
    feats = {}
    for field, prefix in SPLIT_FEATURES:
        feats.update(_feature_avgs(pool, field, prefix))
    return {"played": n, "for_avg": round(cf / n, 2), "against_avg": round(ca / n, 2),
            "total_avg": round((cf + ca) / n, 2), **feats}


# ----------------------------- Shot-volume features -----------------------------
# Captured per team per fixture by sync_real.py alongside corners. These are NOT wired
# into the projection — they are exposed so their predictive value can be measured
# before anything depends on them. A fixture the provider didn't cover carries None,
# so every average travels with the sample size it was actually computed from.

SHOT_FEATURES = ("shots", "shots_on_target", "blocked_shots", "dangerous_attacks")


def _feature_avg(pool: List[dict], key: str) -> Optional[float]:
    vals = [m[key] for m in pool if m.get(key) is not None]
    return round(sum(vals) / len(vals), 2) if vals else None


def team_features(matches: List[dict], split: str = "overall", window: int = 0) -> dict:
    """Per-game feature averages for a team, with the coverage behind each one.

    `covered` counts the games in the pool that actually carried the stat: an average
    over 3 of 12 games is not the same evidence as one over 12, and the caller has to
    be able to tell the difference."""
    if split == "home":
        pool = [m for m in matches if m["home"]]
    elif split == "away":
        pool = [m for m in matches if not m["home"]]
    else:
        pool = list(matches)
    pool = pool[-window:] if window else pool
    out = {"played": len(pool), "covered": {}}
    for f in SHOT_FEATURES:
        out[f"{f}_for"] = _feature_avg(pool, f"{f}_for")
        out[f"{f}_against"] = _feature_avg(pool, f"{f}_against")
        out["covered"][f] = sum(1 for m in pool if m.get(f"{f}_for") is not None)
    return out


# ----------------------------- Corners by match state -----------------------------
# Corners grouped by the state the team was in. NOTE the limitation this carries:
# API-Football gives corner totals for the whole match only — there are no corner
# timings and no half split — so these are the team's FULL-MATCH corners in games
# where it was, say, behind at half-time. That is not the same as "corners won while
# behind", and a chase effect concentrated in the second half will read diluted here.
# probe_corner_halves.py checks whether a real half split is obtainable.

HT_LABELS = {-1: "trailing", 0: "level", 1: "leading"}
FT_LABELS = {-1: "lost", 0: "drew", 1: "won"}


def _match_state(m: dict, phase: str) -> Optional[int]:
    """-1 behind, 0 level, +1 ahead — at half-time or at full-time."""
    if phase == "ht":
        f, a = m.get("fh_goals_for"), m.get("fh_goals_against")
    else:
        f, a = m.get("goals_for"), m.get("goals_against")
    if f is None or a is None:
        return None
    return (f > a) - (f < a)


def team_state_splits(matches: List[dict], split: str = "overall", window: int = 0) -> dict:
    """Corners won/conceded per game, grouped by half-time state and by final result.

    `games` travels with every bucket: a 6.8 average over three matches is not the
    same evidence as one over twenty, and these buckets get thin fast."""
    if split == "home":
        pool = [m for m in matches if m["home"]]
    elif split == "away":
        pool = [m for m in matches if not m["home"]]
    else:
        pool = list(matches)
    pool = pool[-window:] if window else pool

    out = {}
    for phase, labels in (("ht", HT_LABELS), ("ft", FT_LABELS)):
        buckets, covered = {}, 0
        for state, label in labels.items():
            rows = [m for m in pool if _match_state(m, phase) == state]
            covered += len(rows)
            n = len(rows)
            buckets[label] = {
                "games": n,
                "won": round(sum(m["corners_for"] for m in rows) / n, 2) if n else None,
                "conceded": round(sum(m["corners_against"] for m in rows) / n, 2) if n else None,
                "total": round(sum(m["corners_for"] + m["corners_against"] for m in rows) / n, 2) if n else None,
            }
        # games the provider left without the goals needed to classify them
        buckets["unknown_games"] = len(pool) - covered
        out[phase] = buckets
    out["played"] = len(pool)
    return out


GOAL_WINDOWS = [(0, 15), (16, 30), (31, 45), (46, 60), (61, 75), (76, 90)]


def _goal_window(minute: int) -> str:
    for lo, hi in GOAL_WINDOWS:
        if minute <= hi:
            return f"{lo or 1}-{hi}"
    return "76-90"                      # 90+ stoppage time belongs to the last window


def goal_profile(matches: List[dict], split: str = "overall", window: int = 0) -> dict:
    """Who scores, when, and how long this team spends chasing.

    Built from `/fixtures/events`, which — unlike the corner data — does carry minutes.
    `minutes_trailing` is the reason this exists: the game-state split classifies a match
    by its half-time score, so a team a goal down from the 10th minute and one that
    conceded on 43 land in the same bucket. Minutes separate them.

    Only matches the goal backfill has reached carry these keys, so `games` is the count
    of COVERED matches, not of matches played."""
    if split == "home":
        pool = [m for m in matches if m["home"]]
    elif split == "away":
        pool = [m for m in matches if not m["home"]]
    else:
        pool = list(matches)
    pool = pool[-window:] if window else pool
    covered = [m for m in pool if m.get("minutes_trailing") is not None]
    n = len(covered)
    if not n:
        return {"games": 0, "played": len(pool), "scorers": [], "windows": {},
                "minutes": {}, "first_goal": {}}

    def avg(key):
        return round(sum(m.get(key) or 0 for m in covered) / n, 1)

    tally: Dict[str, dict] = {}
    windows = {f"{lo or 1}-{hi}": 0 for lo, hi in GOAL_WINDOWS}
    for m in covered:
        for g in m.get("scorers") or []:
            name = g.get("player") or "unknown"
            row = tally.setdefault(name, {"player": name, "goals": 0, "minutes": []})
            row["goals"] += 1
            row["minutes"].append(g.get("minute"))
            windows[_goal_window(int(g.get("minute") or 0))] += 1

    scored_first = [m for m in covered if m.get("scored_first") is not None]
    firsts = [m["first_goal_min"] for m in covered if m.get("first_goal_min") is not None]
    conceded = [m["opp_first_goal_min"] for m in covered if m.get("opp_first_goal_min") is not None]
    return {
        "games": n, "played": len(pool),
        "scorers": sorted(tally.values(), key=lambda r: (-r["goals"], r["player"]))[:12],
        "windows": windows,
        "minutes": {"trailing": avg("minutes_trailing"), "level": avg("minutes_level"),
                    "leading": avg("minutes_leading")},
        "first_goal": {
            "scored_first_pct": round(sum(1 for m in scored_first if m["scored_first"])
                                      / len(scored_first) * 100, 1) if scored_first else None,
            "avg_first_scored_min": round(sum(firsts) / len(firsts), 1) if firsts else None,
            "avg_first_conceded_min": round(sum(conceded) / len(conceded), 1) if conceded else None,
        },
    }


def _src(team: dict) -> list:
    """Prefer real match data; fall back to (synthetic) matches only if no real games."""
    return team.get("real_matches") or team.get("matches") or []


def expected_lambdas(home: dict, away: dict, league_shots: float = REF_SHOTS,
                     league_blocked: float = 0.0) -> dict:
    h_home = team_split(_src(home), "home", 0)
    a_away = team_split(_src(away), "away", 0)
    # fall back to overall if a team has no games on that venue
    if h_home["played"] == 0:
        h_home = team_split(_src(home), "overall", 0)
    if a_away["played"] == 0:
        a_away = team_split(_src(away), "overall", 0)
    lam_home = live_lambda((h_home["for_avg"] + a_away["against_avg"]) / 2, home, "home",
                           league_shots, league_blocked)
    lam_away = live_lambda((a_away["for_avg"] + h_home["against_avg"]) / 2, away, "away",
                           league_shots, league_blocked)
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
    lb = league.get("avg_blocked") or 0.0
    lambdas = expected_lambdas(home, away, ls, lb)
    return {"lambdas": lambdas, "markets": build_markets(lambdas, odds), "confidence": confidence_for(home, away)}


# ----------------------------- Public access -----------------------------
# Auth was removed when the app went public: every request acts as a single
# shared local user, which keeps the bankroll/bets storage model intact.

PUBLIC_USER_ID = "public"


async def get_current_user(request: Request) -> dict:
    user = await db.users.find_one({"user_id": PUBLIC_USER_ID}, {"_id": 0})
    if not user:
        user = {"user_id": PUBLIC_USER_ID, "email": "", "name": "Guest", "picture": "",
                "created_at": datetime.now(timezone.utc).isoformat()}
        await db.users.insert_one(dict(user))
        user.pop("_id", None)
    return user


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


@api_router.get("/health")
async def health():
    """Liveness + scheduler visibility. Used by the platform healthcheck and by any
    external uptime ping; reports the scheduler because a dead scheduler is the
    failure mode that would otherwise go unnoticed."""
    jobs = []
    scheduler = getattr(app.state, "scheduler", None)
    if scheduler:
        jobs = [{"id": j.id, "next_run": j.next_run_time.isoformat() if j.next_run_time else None}
                for j in scheduler.get_jobs()]
    try:
        await db.command("ping")
        db_ok = True
    except Exception:                                         # noqa: BLE001
        db_ok = False
    screens = {}
    if db_ok:
        try:
            built = {d["_id"]: d for d in await db.screens.find({}, {"payload": 0}).to_list(50)}
            screens = {name: bool(built.get(name)) and not await _screen_is_stale(built[name])
                       for name in SCREENS}
        except Exception:                                     # noqa: BLE001
            screens = {}
    return {"status": "ok" if db_ok else "degraded", "db": db_ok,
            "scheduler_running": bool(scheduler and scheduler.running), "jobs": jobs,
            "screens_fresh": screens,
            "explainer": bool(_llm()), "time": datetime.now(timezone.utc).isoformat()}


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
    """Profit in units at a flat 1u stake, including Asian half-wins and pushes."""
    return settlement.pick_profit(p.get("status"), p.get("odds"))


# statuses that represent a graded outcome; a void returns the stake, so it counts
# as settled but must stay out of strike-rate and ROI denominators
_WIN_STATUSES = (settlement.WON, settlement.HALF_WON)
_LOSS_STATUSES = (settlement.LOST, settlement.HALF_LOST)
_GRADED = _WIN_STATUSES + _LOSS_STATUSES


def _record(picks: List[dict]) -> dict:
    """Flat 1u summary. Strike rate covers graded picks (voids excluded); profit
    only those with a real price, since a win at an unknown price has no return."""
    graded = [p for p in picks if p.get("status") in _GRADED]
    voided = [p for p in picks if p.get("status") == settlement.VOID]
    # A pick counts toward profit only when its PRICE is known. Testing profit-is-not-None
    # instead would silently keep every unpriced loss (a loss costs 1u whatever the price)
    # while dropping every unpriced win, which forces ROI to -100% no matter how well the
    # picks actually did. Both sides must be priced or neither is counted.
    priced = [p for p in graded if p.get("odds")]
    won = sum(1 for p in graded if p["status"] in _WIN_STATUSES)
    profit = round(sum(_pick_profit(p) for p in priced), 2)
    return {"picks": len(picks), "settled": len(graded), "void": len(voided),
            "won": won, "lost": len(graded) - won,
            "pending": sum(1 for p in picks if p.get("status") == settlement.PENDING),
            "win_rate": round(won / len(graded) * 100, 1) if graded else 0.0,
            "staked": len(priced), "profit": profit,
            "roi": round(profit / len(priced) * 100, 1) if priced else 0.0,
            "unpriced": sum(1 for p in graded if not p.get("odds")),
            "unpriced_wins": sum(1 for p in picks
                                 if p.get("status") in _WIN_STATUSES and not p.get("odds"))}


@api_router.get("/picks")
async def get_picks(user: dict = Depends(get_current_user)):
    # auto-tracked Daily 2 picks live on their own ledger (/ledger), not the curated board
    picks = await db.picks.find({"auto": {"$ne": True}}, {"_id": 0}).to_list(500)
    picks.sort(key=lambda p: (p.get("date") or "", p.get("kickoff") or "", p.get("home") or p.get("team") or ""))
    for p in picks:
        p["profit"] = _pick_profit(p)
    return {"record": {**_record(picks), "total": len(picks)}, "picks": picks}


_settle_state = {"at": None, "running": False, "last_result": None}
SETTLE_MIN_INTERVAL_SECONDS = 60


async def _run_settlement() -> dict:
    """Grade pending picks. Safe to call repeatedly — settlement is idempotent and
    a short interval guard stops overlapping runs (e.g. cron ping + UI button)."""
    now = datetime.now(timezone.utc)
    last = _settle_state["at"]
    if _settle_state["running"]:
        return {"status": "already_running", "started_at": last.isoformat() if last else None,
                **(_settle_state["last_result"] or {})}
    if last and (now - last).total_seconds() < SETTLE_MIN_INTERVAL_SECONDS:
        return {"status": "throttled", "started_at": last.isoformat(),
                **(_settle_state["last_result"] or {})}
    _settle_state.update({"at": now, "running": True})
    try:
        import httpx
        async with httpx.AsyncClient() as hc:
            result = await settle_pending(db, hc)
    except Exception as exc:                                  # noqa: BLE001
        logger.exception("settlement run failed")
        _settle_state["running"] = False
        return {"status": "error", "error": str(exc)}
    _settle_state.update({"running": False, "last_result": result})
    return {"status": "ok", **result}


@api_router.post("/settle")
async def settle_now(user: dict = Depends(get_current_user)):
    """Settlement entrypoint — also the target for an external cron ping."""
    return await _run_settlement()


@api_router.post("/picks/settle")
async def settle_picks_now(user: dict = Depends(get_current_user)):
    return await _run_settlement()


# ----------------------------- Daily 2 — auto-tracked ledger -----------------------------
# The day's two strongest chase spots are snapshotted into db.picks BEFORE kickoff and
# never recomputed. This is the whole point: a ledger that re-selected its picks from
# finished games would be look-ahead biased and could not evidence anything.

DAILY_PICK_COUNT = 2


# WHAT THE DAILY 2 SELECTS ON.
#
# THE SEARCH FOR A RANKING IS OVER, AND IT FAILED. Every candidate was replayed
# walk-forward and scored by residual — actual hit rate minus the model's own probability,
# i.e. does the order find spots the model UNDERRATES:
#
#   chase_score  +0.02   lambda_only  +0.01   no_opp_fh  +0.03   RANDOM  flat
#   venue_delta  +9.1 -> FLAT once lambda was built venue-split, as production builds it.
#                 It was correcting an error only the HARNESS was making.
#   consistency_only  +7.9 — but synthetic validation on data with NO edge by
#                 construction already produces 7.5 from estimation error alone. 7.9
#                 against 7.5 is not a finding.
#
# So this is a STATED rule, not a discovered edge, and it is labelled as one everywhere
# it appears. Two parts:
#
#   1. A QUALITY BAR. Spots where the estimate is thin or uncorroborated are dropped.
#      `consistency` is used here as a RELIABILITY FILTER — this team has actually cleared
#      this line lately — NOT as a ranking. That distinction is the whole point: filtering
#      on corroboration is defensible, claiming it beats the price is not.
#   2. Then order by MODEL PROBABILITY. Readable, and it makes the ledger measure
#      something meaningful: how the model's most confident calls actually land. That is a
#      calibration record, which is worth having, rather than a fake edge.
#
# WHAT THIS DELIBERATELY DOES NOT DO: chase long odds. Highest probability means lowest
# lines. If you want the ledger to chase value instead, that is a different rule and it
# needs its own measurement — do not just flip the sort.
#
# NEXT HYPOTHESIS, if anyone picks this up: consistency surviving where venue_delta died
# points at DISPERSION rather than the mean. Lambda is a mean and NB_R is fixed at 11 for
# every team; consistency counts how often a team CLEARED a line, which carries shape
# information a fixed r cannot. Per-league or per-team dispersion is the thing to test.
DAILY_PICK_RULE = "quality_bar_then_probability"
DAILY_MIN_VENUE_GAMES = 4      # the chase board's own floor; stated here so it is visible
DAILY_MIN_CONSISTENCY = 0.8    # cleared the line in 4 of the last 5 on this venue


def daily_pick_qualifies(c: dict, min_consistency: float = DAILY_MIN_CONSISTENCY) -> bool:
    """The quality bar. A filter on corroboration, NOT a claim about beating the price."""
    of = c.get("consistency_of") or 0
    if of < DAILY_MIN_VENUE_GAMES:
        return False
    return (c.get("consistency") or 0) / of >= min_consistency


def daily_pick_order(c: dict) -> float:
    """Order among qualifying spots: the model's own confidence, nothing cleverer."""
    return c.get("prob") or 0.0


async def _daily_shortlist(day: str, count: int = DAILY_PICK_COUNT) -> List[dict]:
    """Chase spots kicking off on `day` (UTC) that clear the quality bar, most confident
    first. See DAILY_PICK_RULE — this ordering is stated, not discovered."""
    board = await _chase_board(within_days=2, limit=500)
    now = datetime.now(timezone.utc)
    out = []
    for c in board:
        nf = c.get("next_fixture") or {}
        try:
            dt = datetime.fromisoformat((nf.get("date") or "").replace("Z", "+00:00"))
        except Exception:
            continue
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        if dt <= now or dt.date().isoformat() != day:
            continue
        if not daily_pick_qualifies(c):
            continue
        out.append(c)
    # A thin day yields fewer than `count`, deliberately: the bar is absolute, and
    # topping up with spots that failed it would defeat the whole point.
    out.sort(key=daily_pick_order, reverse=True)
    return out[:count]


async def _snapshot_daily_picks(day: Optional[str] = None) -> dict:
    """Lock in the day's picks. Idempotent — a pick already stored is never rewritten."""
    day = day or datetime.now(timezone.utc).date().isoformat()
    shortlist = await _daily_shortlist(day)
    inserted = []
    for c in shortlist:
        nf = c["next_fixture"]
        key = {"auto": True, "date": day, "team": c["name"], "line": c["line"]}
        if await db.picks.find_one(key):
            continue
        doc = {**key, "signal": "chase", "venue": "home" if nf["is_home"] else "away",
               "home": c["name"] if nf["is_home"] else nf["opponent"],
               "away": nf["opponent"] if nf["is_home"] else c["name"],
               "league_id": c["league_id"], "league_name": c["league_name"],
               "kickoff": nf["date"], "fixture_id": nf["fixture_id"],
               "odds": c.get("book_odds"), "model_odds": c.get("fair_odds"),
               "model_prob": c.get("prob"), "chase_score": c.get("chase_score"),
               # which rule picked this, so a later rule change leaves the ledger's
               # history readable rather than silently mixing two strategies
               "selected_by": DAILY_PICK_RULE,
               "status": "pending", "created_at": datetime.now(timezone.utc).isoformat()}
        await db.picks.insert_one(dict(doc))
        doc.pop("_id", None)
        inserted.append(doc)
    return {"day": day, "shortlisted": len(shortlist), "inserted": len(inserted), "picks": inserted}


@api_router.post("/ledger/snapshot")
async def ledger_snapshot(day: Optional[str] = None, user: dict = Depends(get_current_user)):
    return await _snapshot_daily_picks(day)


def _ledger_agg(subset: List[dict]) -> dict:
    return _record(subset)


@api_router.get("/ledger")
async def ledger(user: dict = Depends(get_current_user)):
    picks = await db.picks.find({"auto": True}, {"_id": 0}).to_list(5000)
    picks.sort(key=lambda p: (p.get("kickoff") or p.get("date") or "", p.get("team") or ""))
    running = 0.0
    rows = []
    for p in picks:
        profit = _pick_profit(p)
        if profit is not None:
            running = round(running + profit, 2)
        rows.append({**p, "profit": profit, "balance": running if profit is not None else None})
    signals = sorted({p.get("signal") or "chase" for p in picks})
    summary = _ledger_agg(picks)
    return {"summary": summary,
            "unpriced_wins": summary["unpriced_wins"],
            "by_venue": {v: _ledger_agg([p for p in picks if p.get("venue") == v]) for v in ("home", "away")},
            "by_signal": {s: _ledger_agg([p for p in picks if (p.get("signal") or "chase") == s]) for s in signals},
            "rows": rows}


# ----------------------------- Precomputed screens -----------------------------
# Every scanner screen scans the whole team collection. Doing that once per visitor is
# what would take a free-tier Atlas down, so each screen's default payload is built once
# per sync and served from a single document. A request whose parameters differ from the
# canonical set still computes live — this is an optimisation, never a limit on what the
# API can answer.
#
# `_building_screen` is a ContextVar rather than a plain flag so it is visible only to
# the task doing the build: a builder calls the same endpoint functions the cache fronts,
# and must reach the live path without concurrent requests also being pushed onto it.

SCREEN_STALE_HOURS = 13  # a little over the 12h sync cadence
# BUMP THIS whenever a screen's payload SHAPE changes. Staleness is otherwise keyed on
# the data alone, so a deploy that adds a field would keep serving the old shape from
# cache until the next sync happened to move data_version.
SCREEN_SCHEMA = 3
# Must match TOP_TEAMS_LIMIT in frontend/src/components/BestTeams.jsx, or that screen
# misses its cache on every visit.
TOP_TEAMS_LIMIT = 60
_building_screen = contextvars.ContextVar("building_screen", default=False)
_screen_locks: Dict[str, asyncio.Lock] = {}


def _cache_ok() -> bool:
    return not _building_screen.get()


async def _screen_chase():
    return await chase_board(within_days=7, limit=25, league_id="all", user={})


async def _screen_mismatches():
    return await top_mismatches(within_days=7, limit=30, user={})


async def _screen_streaks():
    return await streaks(league_id="all", side="home", window=5, min_hits=5,
                         min_line=3, direction="over", subject="team", user={})


async def _screen_top_teams():
    return await top_corner_teams(side="overall", window=0, limit=TOP_TEAMS_LIMIT,
                                  league_id="all", user={})


async def _screen_best_bets():
    return await best_bets(user={})


async def _screen_fixture_board():
    # days=3 mirrors the home page's default tab, not this endpoint's own default
    return await fixture_board(days=3, user={})


# Canonical payloads — these mirror what the frontend requests on first paint.
SCREENS = {
    "best_bets": _screen_best_bets,
    "fixture_board": _screen_fixture_board,
    "chase": _screen_chase,
    "mismatches": _screen_mismatches,
    "streaks": _screen_streaks,
    "top_teams": _screen_top_teams,
}


def _iso_to_dt(value) -> Optional[datetime]:
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt


async def _data_version() -> Optional[str]:
    """Newest league sync timestamp — what a screen's contents actually depend on."""
    newest = await db.leagues.find({}, {"_id": 0, "synced_at": 1}) \
        .sort("synced_at", -1).limit(1).to_list(1)
    return (newest[0].get("synced_at") if newest else None) or None


async def _screen_is_stale(doc: dict) -> bool:
    if doc.get("schema") != SCREEN_SCHEMA:
        return True
    version = await _data_version()
    if version and doc.get("data_version") != version:
        return True
    built = _iso_to_dt(doc.get("built_at"))
    if not built:
        return True
    return (datetime.now(timezone.utc) - built).total_seconds() > SCREEN_STALE_HOURS * 3600


async def _build_screen(name: str) -> dict:
    token = _building_screen.set(True)
    try:
        payload = await SCREENS[name]()
    finally:
        _building_screen.reset(token)
    doc = {"_id": name, "payload": payload, "schema": SCREEN_SCHEMA,
           "built_at": datetime.now(timezone.utc).isoformat(),
           "data_version": await _data_version()}
    await db.screens.update_one({"_id": name}, {"$set": doc}, upsert=True)
    return doc


async def _screen(name: str):
    """Cached payload, rebuilt when missing or out of date.

    The per-screen lock matters: without it the first visitors after a sync would all
    miss together and each kick off the same full scan."""
    cached = await db.screens.find_one({"_id": name})
    if cached and not await _screen_is_stale(cached):
        return cached["payload"]
    lock = _screen_locks.setdefault(name, asyncio.Lock())
    async with lock:
        cached = await db.screens.find_one({"_id": name})  # may have been rebuilt while waiting
        if cached and not await _screen_is_stale(cached):
            return cached["payload"]
        try:
            return (await _build_screen(name))["payload"]
        except Exception:                                     # noqa: BLE001
            logger.exception("screen rebuild failed: %s", name)
            if cached:
                return cached["payload"]                      # stale beats nothing
            raise


async def _rebuild_screens() -> dict:
    out = {}
    for name in SCREENS:
        try:
            await _build_screen(name)
            out[name] = "ok"
        except Exception as exc:                              # noqa: BLE001
            logger.exception("screen build failed: %s", name)
            out[name] = f"error: {exc}"
    logger.info("screens rebuilt: %s", out)
    return {"rebuilt": out, "at": datetime.now(timezone.utc).isoformat()}


@api_router.post("/screens/rebuild")
async def screens_rebuild(user: dict = Depends(get_current_user)):
    return await _rebuild_screens()


@api_router.get("/screens/status")
async def screens_status(user: dict = Depends(get_current_user)):
    version = await _data_version()
    docs = {d["_id"]: d for d in await db.screens.find({}, {"payload": 0}).to_list(50)}
    return {"data_version": version,
            "screens": {name: {"built_at": (docs.get(name) or {}).get("built_at"),
                               "fresh": bool(docs.get(name)) and not await _screen_is_stale(docs[name])}
                        for name in SCREENS}}


# ---- Claude explainer — justify a model-flagged corner pick ----
try:
    import anthropic
except ImportError:  # keep the app importable; the endpoint reports 503 instead
    anthropic = None

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")
EXPLAIN_MODEL = "claude-opus-5"
_anthropic_client = None


def _llm():
    """One shared async client, built on first use. None when unconfigured."""
    global _anthropic_client
    if _anthropic_client is None and anthropic and ANTHROPIC_API_KEY:
        _anthropic_client = anthropic.AsyncAnthropic(api_key=ANTHROPIC_API_KEY)
    return _anthropic_client


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
    client = _llm()
    if client is None:
        raise HTTPException(status_code=503, detail="Explainer not configured (set ANTHROPIC_API_KEY)")
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
    try:
        resp = await client.beta.messages.create(
            model=EXPLAIN_MODEL,
            # deliberately short answer; low effort keeps a per-pick endpoint cheap
            max_tokens=2000,
            output_config={"effort": "low"},
            # on a policy decline, the API re-runs the request on a fallback model
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
            system="You are a sharp, concise football corners betting analyst. "
                   "You only use the numbers provided.",
            messages=[{"role": "user", "content": prompt}],
        )
    except anthropic.RateLimitError:
        raise HTTPException(status_code=429, detail="Explainer busy — try again shortly.")
    except anthropic.APIStatusError as e:
        logger.error("explain LLM error %s: %s", e.status_code, e.message)
        raise HTTPException(status_code=502, detail="Could not generate explanation")
    except anthropic.APIConnectionError as e:
        logger.error("explain LLM connection error: %s", e)
        raise HTTPException(status_code=502, detail="Could not generate explanation")

    if resp.stop_reason == "refusal":
        logger.warning("explain refused (%s)", getattr(resp.stop_details, "category", None))
        raise HTTPException(status_code=502, detail="Could not generate explanation")
    text = "".join(b.text for b in resp.content if b.type == "text").strip()
    if not text:
        logger.error("explain returned no text (stop_reason=%s)", resp.stop_reason)
        raise HTTPException(status_code=502, detail="Could not generate explanation")
    await db.explanations.update_one(
        {"_id": ckey},
        {"$set": {"_id": ckey, "text": text, "created_at": datetime.now(timezone.utc).isoformat()}},
        upsert=True)
    return {"explanation": text, "cached": False}


def model_lambda(model: str, team_for: float, opp_against: float,
                 team_shots: float = 0.0, league_shots: float = 0.0, team_fh: float = 0.5,
                 team_blocked: float = 0.0, league_blocked: float = 0.0,
                 blocked_weight: float = V3_BLOCKED_WEIGHT) -> float:
    """Expected team corners.
    v1 = corner form only.
    v2 = + shots-intent x first-half-goal form (matches the tuned production formula).
    v3 = v2 with the shots-intent term SWAPPED for blocked-shots intent (candidate).

    v3 FALLS BACK TO v2 when a team has no blocked-shots history. Blocked shots only
    exist as far back as the backfill reached, while shots are on every cached fixture,
    so without this a team short on blocked data would price off bare corner form —
    losing the first-half-goal term too, and coming out WORSE than the model it is
    meant to replace. The backtester skips those rows, so it would never show it."""
    base = (team_for + opp_against) / 2.0
    form = 1.0 + 0.03 * (team_fh - 0.5)
    if model == "v3" and league_blocked > 0 and team_blocked > 0:
        return base * _intent(team_blocked, league_blocked, blocked_weight) * form
    if model in ("v2", "v3") and league_shots > 0 and team_shots > 0:
        return base * _intent(team_shots, league_shots, 0.10) * form
    return base


def _backtest_summary(stats: dict, lines: List[int]) -> dict:
    out_lines, total_brier, total_n, gaps = [], 0.0, 0, []
    for L in lines:
        s = stats[L]
        if s["n"] == 0:
            continue
        gap = round(abs(s["pred"] - s["hit"]) / s["n"] * 100, 1)
        gaps.append(gap)
        out_lines.append({"line": L, "n": s["n"],
                          "model_prob": round(s["pred"] / s["n"] * 100, 1),
                          "actual_hit_rate": round(s["hit"] / s["n"] * 100, 1),
                          "calibration_gap": gap,
                          "brier": round(s["brier"] / s["n"], 4)})
        total_brier += s["brier"]; total_n += s["n"]
    return {"overall_brier": round(total_brier / total_n, 4) if total_n else None,
            "avg_calibration_gap": round(sum(gaps) / len(gaps), 2) if gaps else None,
            "lines": out_lines}


# ----------------------------- Tool runners (phone-operable) -----------------------------
# The analysis scripts are the one part of the workflow that needs a shell. These run them
# as subprocesses and store the output so the whole loop works from a browser.
#
# The app is PUBLIC (auth was removed), and backfill_shots.py spends API-Football credits,
# so these are gated behind TOOLS_TOKEN and are DISABLED unless that env var is set.
# Arguments are built from validated values only — never from raw user strings.

TOOLS_TOKEN = os.environ.get("TOOLS_TOKEN")
TOOL_SCRIPTS = {"backfill_shots": "backfill_shots.py", "measure_features": "measure_features.py",
                "measure_chase_board": "measure_chase_board.py",
                "backfill_fh": "backfill_fh.py",
                "backfill_goal_events": "backfill_goal_events.py",
                "probe_corner_halves": "probe_corner_halves.py",
                "probe_stat_types": "probe_stat_types.py",
                "probe_leagues": "probe_leagues.py"}
TOOL_COOLDOWN = {"backfill_shots": 600, "measure_features": 120,
                 "measure_chase_board": 120, "backfill_fh": 120,
                 "backfill_goal_events": 600,
                 "probe_corner_halves": 600,
                 "probe_stat_types": 600, "probe_leagues": 120}    # seconds
# mode -> (script, fixed argv, accepts --league). Modes are an enum precisely so
# nothing user-supplied ever reaches argv; --league is appended only after validation
# AND only for the scripts that actually take it — backfill_fh.py does not, and passing
# it would kill the run with an unrecognised-argument error.
MEASURE_MODES = {
    "features": ("measure_features", [], True),
    "sweep": ("measure_features", ["--sweep"], True),
    "game_state": ("measure_features", ["--game-state"], True),
    "chase_board": ("measure_chase_board", [], True),
    "backfill_fh": ("backfill_fh", [], False),
}
TOOL_OUTPUT_CAP = 60000                                            # chars kept per run


def _check_tools_token(token: Optional[str]):
    import secrets
    if not TOOLS_TOKEN:
        raise HTTPException(status_code=503,
                            detail="Tool endpoints are disabled — set TOOLS_TOKEN in the backend env")
    if not token or not secrets.compare_digest(token, TOOLS_TOKEN):
        raise HTTPException(status_code=403, detail="Bad or missing token")


async def _tool_guard(script: str):
    """One run of a script at a time, and not more often than its cooldown."""
    running = await db.script_runs.find_one({"script": script, "status": "running"}, {"_id": 1})
    if running:
        raise HTTPException(status_code=409, detail=f"{script} is already running")
    last = await db.script_runs.find({"script": script}, {"_id": 0, "started_at": 1}) \
        .sort("started_at", -1).limit(1).to_list(1)
    if last and last[0].get("started_at"):
        try:
            age = (datetime.now(timezone.utc)
                   - datetime.fromisoformat(last[0]["started_at"])).total_seconds()
        except Exception:
            age = 1e9
        cd = TOOL_COOLDOWN[script]
        if age < cd:
            raise HTTPException(status_code=429,
                                detail=f"{script} ran {int(age)}s ago — wait {int(cd - age)}s")


async def _run_tool(run_id: str, script: str, argv: List[str]):
    import sys as _sys
    try:
        proc = await asyncio.create_subprocess_exec(
            _sys.executable, str(ROOT_DIR / TOOL_SCRIPTS[script]), *argv, cwd=str(ROOT_DIR),
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT)
        out, _ = await proc.communicate()
        text = out.decode("utf-8", "replace")
        await db.script_runs.update_one({"_id": run_id}, {"$set": {
            "status": "success" if proc.returncode == 0 else "failed",
            "exit_code": proc.returncode, "output": text[-TOOL_OUTPUT_CAP:],
            "truncated": len(text) > TOOL_OUTPUT_CAP,
            "finished_at": datetime.now(timezone.utc).isoformat()}})
    except Exception as e:
        logger.exception("tool %s failed", script)
        await db.script_runs.update_one({"_id": run_id}, {"$set": {
            "status": "failed", "exit_code": -1, "output": f"runner error: {e}",
            "finished_at": datetime.now(timezone.utc).isoformat()}})


async def _start_tool(script: str, argv: List[str], label: str) -> dict:
    await _tool_guard(script)
    run_id = f"run_{uuid.uuid4().hex[:12]}"
    doc = {"_id": run_id, "script": script, "label": label, "argv": argv, "status": "running",
           "started_at": datetime.now(timezone.utc).isoformat(), "finished_at": None,
           "output": "", "exit_code": None}
    await db.script_runs.insert_one(dict(doc))
    asyncio.create_task(_run_tool(run_id, script, argv))
    # keep the last 30 runs only
    old = await db.script_runs.find({}, {"_id": 1}).sort("started_at", -1).skip(30).to_list(500)
    if old:
        await db.script_runs.delete_many({"_id": {"$in": [o["_id"] for o in old]}})
    doc.pop("output", None)
    return {"started": True, **doc}


@api_router.post("/tools/backfill-shots")
async def tool_backfill_shots(token: Optional[str] = None, league_id: Optional[str] = None,
                              limit: int = 120, project_only: bool = False,
                              user: dict = Depends(get_current_user)):
    """Fill shot-volume features on this season's cached fixtures. SPENDS API CREDITS —
    one statistics call per un-filled fixture, capped by `limit` per league."""
    _check_tools_token(token)
    argv, parts = [], []
    if league_id and league_id != "all":
        if league_id not in MANAGED_LEAGUE_IDS:
            raise HTTPException(status_code=400, detail=f"unknown league_id {league_id}")
        argv.append(league_id)
        parts.append(league_id)
    argv += ["--limit", str(max(1, min(int(limit), 500)))]
    parts.append(f"limit={max(1, min(int(limit), 500))}")
    if project_only:
        argv.append("--project-only")
        parts.append("project-only")
    return await _start_tool("backfill_shots", argv, " ".join(parts) or "all leagues")


@api_router.post("/tools/backfill-goals")
async def tool_backfill_goals(token: Optional[str] = None, league_id: Optional[str] = None,
                              limit: int = 120, project_only: bool = False,
                              user: dict = Depends(get_current_user)):
    """Fill goal detail — scorers, minutes, and minutes spent trailing — onto cached
    fixtures, then project it onto team history.

    SPENDS API CREDITS on the fetch half: one `/fixtures/events` call per fixture not yet
    done, capped by `limit` per league and resumable, so the spend is yours to pace.
    `project_only` re-runs the cache -> teams half for free, which is what you want after
    a sync has added matches the cache already covers."""
    _check_tools_token(token)
    argv, parts = [], []
    if league_id and league_id != "all":
        if league_id not in MANAGED_LEAGUE_IDS:
            raise HTTPException(status_code=400, detail=f"unknown league_id {league_id}")
        argv.append(league_id)
        parts.append(league_id)
    capped = max(1, min(int(limit), 500))
    argv += ["--limit", str(capped)]
    parts.append(f"limit={capped}")
    if project_only:
        argv.append("--project-only")
        parts.append("project-only")
    return await _start_tool("backfill_goal_events", argv, " ".join(parts) or "all leagues")


@api_router.post("/tools/measure")
async def tool_measure(token: Optional[str] = None, mode: str = "features",
                       league_id: Optional[str] = None, user: dict = Depends(get_current_user)):
    """Run an offline tool. All of these touch the DATABASE ONLY — no API calls, so
    they cost nothing to run. (The one tool that does spend API credits, the half-split
    probe, has its own endpoint below so this promise stays true.)

    mode: features (blocked shots) | sweep (weights) | game_state (chase thesis)
        | chase_board (does the board's ranking pick better spots?)
        | backfill_fh (fill half-time goals onto team history from the fixture cache)"""
    _check_tools_token(token)
    if mode not in MEASURE_MODES:
        raise HTTPException(status_code=400,
                            detail=f"mode must be one of {'|'.join(MEASURE_MODES)}")
    script, fixed, takes_league = MEASURE_MODES[mode]
    argv, parts = list(fixed), [mode]
    if league_id and league_id != "all":
        if league_id not in MANAGED_LEAGUE_IDS:
            raise HTTPException(status_code=400, detail=f"unknown league_id {league_id}")
        if not takes_league:
            raise HTTPException(status_code=400,
                                detail=f"mode {mode} runs across all leagues; drop league_id")
        argv += ["--league", league_id]
        parts.append(league_id)
    return await _start_tool(script, argv, " ".join(parts))


@api_router.post("/tools/probe-halves")
async def tool_probe_halves(token: Optional[str] = None,
                            user: dict = Depends(get_current_user)):
    """Probe whether API-Football can give corners split by half.

    SPENDS API CREDITS — a handful of calls on a single fixture. Deliberately not a
    `measure` mode, because that endpoint promises no API calls and this one breaks it."""
    _check_tools_token(token)
    return await _start_tool("probe_corner_halves", [], "1H/2H availability")


@api_router.post("/tools/probe-stat-types")
async def tool_probe_stat_types(token: Optional[str] = None,
                                user: dict = Depends(get_current_user)):
    """List every statistic API-Football actually returns for our leagues.

    Answers "can we add crosses?" with evidence instead of a guess. SPENDS API CREDITS —
    roughly a dozen calls across a few leagues."""
    _check_tools_token(token)
    return await _start_tool("probe_stat_types", [], "available statistic types")


COUNTRY_RE = re.compile(r"^[A-Za-z][A-Za-z .'-]{1,39}$")


@api_router.post("/tools/probe-leagues")
async def tool_probe_leagues(token: Optional[str] = None, league_id: Optional[str] = None,
                             country: Optional[str] = None,
                             user: dict = Depends(get_current_user)):
    """Check a league is the competition we think it is, and that it carries corner data.

    SPENDS API CREDITS — about 6 calls per league, or 1 for a `country` listing.
    Deliberately its own endpoint rather than a `measure` mode, because that endpoint
    promises no API calls.

    `country` lists every league the provider has for that country, with ids. That is how
    you find the RIGHT id after a MISMATCH — guessing a second time is what put a wrong
    one in to begin with.

    Worth running before syncing any newly added league: 250 statistics calls spent on a
    competition with no Corner Kicks is the expensive way to find that out."""
    _check_tools_token(token)
    if country:
        # argv goes to create_subprocess_exec as a list — no shell, so metacharacters are
        # inert — but keep the pattern strict anyway so nothing odd reaches the provider.
        name = country.strip()
        if not COUNTRY_RE.match(name):
            raise HTTPException(status_code=400,
                                detail="country must be letters, spaces, . ' or - (max 40)")
        return await _start_tool("probe_leagues", ["--country", name], f"leagues in {name}")
    argv, label = [], "recently added leagues"
    if league_id and league_id != "all":
        if league_id not in MANAGED_LEAGUE_IDS:
            raise HTTPException(status_code=400, detail=f"unknown league_id {league_id}")
        argv.append(league_id)
        label = league_id
    return await _start_tool("probe_leagues", argv, label)


@api_router.get("/tools/runs")
async def tool_runs(token: Optional[str] = None, script: Optional[str] = None, limit: int = 5,
                    user: dict = Depends(get_current_user)):
    _check_tools_token(token)
    q = {"script": script} if script in TOOL_SCRIPTS else {}
    runs = await db.script_runs.find(q, {"_id": 0, "argv": 0}).sort("started_at", -1) \
        .limit(max(1, min(limit, 20))).to_list(20)
    return {"enabled": True, "runs": runs}


@api_router.get("/backtest")
async def backtest(league_id: str = "all", window: int = 10, min_games: int = 5,
                   model: str = "v1", blocked_weight: float = V3_BLOCKED_WEIGHT,
                   only_covered: bool = False, venue_form: bool = True,
                   user: dict = Depends(get_current_user)):
    """Walk-forward backtest over cached fixture stats: for each past match we predict
    team-corner probabilities from prior form only, then compare to what actually happened.

    VENUE FORM (`venue_form`, default true). Production prices from venue-split form:
    `expected_lambdas` calls `team_split(team, "home"|"away")`, and the shots and
    blocked-shots intent terms are venue-split too. This harness POOLED both venues until
    2026-08-27, so it was never describing production — and that gap is not academic: it
    is what made `venue_delta` look like a +9.1 edge on the chase-board rank test, when it
    was really correcting an error only the harness was making.

    Set `venue_form=false` to reproduce the old pooled basis. When venue_form is on and
    the model is not v3, `pooled_same_sample` returns the pooled basis scored on identical
    rows, so one call says what the fix was worth.

    Row eligibility is gated on POOLED history in both modes, deliberately: the sample
    must not move when the flag is toggled, or the comparison would be between two
    different sets of matches.

    A v3 run always also returns v2 scored on the SAME rows (`v2_same_sample`) —
    comparing a v3 run against a separate v2 run would compare two different samples.

    Two v3 questions, two modes:
    - default: every row is scored, v3 falling back to v2 where a team has no
      blocked-shots history. This is the SHIPPING question — how the model would
      behave in production, uneven coverage included. `rows_using_blocked` says how
      many rows actually got the new term.
    - only_covered=true: rows without blocked history are skipped instead. This is the
      FEATURE question — how much the blocked term is worth where it applies."""
    q = {} if league_id == "all" else {"league_id": league_id}
    matches = await db.fixture_stats.find(q, {"_id": 0}).to_list(30000)
    matches.sort(key=lambda m: m["date"])
    # league averages for the intent terms (blocked shots is None where uncovered)
    all_shots = [m.get("home_shots", 0) for m in matches] + [m.get("away_shots", 0) for m in matches]
    league_shots = (sum(all_shots) / len(all_shots)) if all_shots else 0.0
    all_blocked = [m[f"{side}_blocked_shots"] for m in matches for side in ("home", "away")
                   if m.get(f"{side}_blocked_shots") is not None]
    league_blocked = (sum(all_blocked) / len(all_blocked)) if all_blocked else 0.0

    hist_for = defaultdict(lambda: deque(maxlen=window))
    hist_against = defaultdict(lambda: deque(maxlen=window))
    hist_shots = defaultdict(lambda: deque(maxlen=window))
    hist_fh = defaultdict(lambda: deque(maxlen=window))
    hist_blocked = defaultdict(lambda: deque(maxlen=window))
    # ...and the same history keyed by (team, venue), because that is what production
    # actually prices from. Kept alongside the pooled deques rather than replacing them,
    # so both bases can be scored on identical rows in a single pass.
    hist_for_v = defaultdict(lambda: deque(maxlen=window))
    hist_against_v = defaultdict(lambda: deque(maxlen=window))
    hist_shots_v = defaultdict(lambda: deque(maxlen=window))
    hist_fh_v = defaultdict(lambda: deque(maxlen=window))
    hist_blocked_v = defaultdict(lambda: deque(maxlen=window))
    lines = [4, 5, 6, 7]
    stats = {L: {"n": 0, "pred": 0.0, "hit": 0, "brier": 0.0} for L in lines}
    alt_stats = {L: {"n": 0, "pred": 0.0, "hit": 0, "brier": 0.0} for L in lines}
    preds = skipped_no_blocked = fell_back = 0

    def avg(d):
        return sum(d) / len(d) if d else 0.0

    prob_fn = nb_ge if model in ("v2", "v3") else poisson_ge

    def form(pooled, by_venue):
        """The average production would use. Venue-split, falling back to pooled when
        this team has never played on this venue — which mirrors `expected_lambdas`,
        where `team_split(..., venue)` falls back to overall at played == 0."""
        if venue_form and by_venue:
            return avg(by_venue)
        return avg(pooled)

    for m in matches:
        h, a = m["home_id"], m["away_id"]
        sides = [
            ("home", "away", h, a, m["home_corners"],
             len(hist_for[h]) >= min_games and len(hist_against[a]) >= min_games),
            ("away", "home", a, h, m["away_corners"],
             len(hist_for[a]) >= min_games and len(hist_against[h]) >= min_games),
        ]
        for side, opp_side, team, opp, actual, can in sides:
            if not can:
                continue
            # Row eligibility stays on POOLED history on purpose: the sample must not
            # move when venue_form is toggled, or the two modes would be scored on
            # different rows and the comparison would mean nothing.
            tf_d, oa_d = hist_for[team], hist_against[opp]
            ts_d, fh_d, bl_d = hist_shots[team], hist_fh[team], hist_blocked[team]
            vf_d, voa_d = hist_for_v[(team, side)], hist_against_v[(opp, opp_side)]
            vts_d, vfh_d = hist_shots_v[(team, side)], hist_fh_v[(team, side)]
            vbl_d = hist_blocked_v[(team, side)]

            # blocked coverage follows whichever pool is actually being used
            bl_used = vbl_d if (venue_form and vbl_d) else bl_d
            has_blocked = len(bl_used) >= min_games
            if model == "v3" and not has_blocked:
                if only_covered:
                    skipped_no_blocked += 1
                    continue
                fell_back += 1               # thin history -> v3 prices as v2 would
            # a too-short window is passed as 0 so the fallback fires, rather than
            # letting two games of blocked data masquerade as form
            args = (form(tf_d, vf_d), form(oa_d, voa_d), form(ts_d, vts_d), league_shots,
                    form(fh_d, vfh_d))
            lam = model_lambda(model, *args, avg(bl_used) if has_blocked else 0.0,
                               league_blocked, blocked_weight)
            preds += 1
            for L in lines:
                p = prob_fn(L, lam)
                hit = 1 if actual >= L else 0
                s = stats[L]
                s["n"] += 1; s["pred"] += p; s["hit"] += hit; s["brier"] += (p - hit) ** 2
            # The comparison row. For v3 that is v2 on identical rows. Otherwise it is
            # THIS model with pooled form — the old harness's basis — so one call shows
            # what the fidelity fix was worth.
            if model == "v3":
                lam2 = model_lambda("v2", *args)
                alt_fn = nb_ge
            elif venue_form:
                lam2 = model_lambda(model, avg(tf_d), avg(oa_d), avg(ts_d), league_shots,
                                    avg(fh_d), avg(bl_d) if len(bl_d) >= min_games else 0.0,
                                    league_blocked, blocked_weight)
                alt_fn = prob_fn
            else:
                lam2 = alt_fn = None
            if lam2 is not None:
                for L in lines:
                    p = alt_fn(L, lam2)
                    hit = 1 if actual >= L else 0
                    s = alt_stats[L]
                    s["n"] += 1; s["pred"] += p; s["hit"] += hit; s["brier"] += (p - hit) ** 2
        # update rolling form AFTER predicting (no leakage)
        hist_for[h].append(m["home_corners"]); hist_against[h].append(m["away_corners"]); hist_shots[h].append(m.get("home_shots", 0)); hist_fh[h].append(1 if m.get("home_fh_goals", 0) >= 1 else 0)
        hist_for[a].append(m["away_corners"]); hist_against[a].append(m["home_corners"]); hist_shots[a].append(m.get("away_shots", 0)); hist_fh[a].append(1 if m.get("away_fh_goals", 0) >= 1 else 0)
        for tid, side, other in ((h, "home", "away"), (a, "away", "home")):
            hist_for_v[(tid, side)].append(m[f"{side}_corners"])
            hist_against_v[(tid, side)].append(m[f"{other}_corners"])
            hist_shots_v[(tid, side)].append(m.get(f"{side}_shots", 0))
            hist_fh_v[(tid, side)].append(1 if m.get(f"{side}_fh_goals", 0) >= 1 else 0)
            bl = m.get(f"{side}_blocked_shots")
            if bl is not None:              # uncovered fixtures never enter the window
                hist_blocked[tid].append(bl)
                hist_blocked_v[(tid, side)].append(bl)

    out = {"league_id": league_id, "model": model, "window": window, "min_games": min_games,
           "venue_form": venue_form,
           "matches": len(matches), "predictions": preds, **_backtest_summary(stats, lines)}
    if venue_form and model != "v3":
        out["pooled_same_sample"] = _backtest_summary(alt_stats, lines)
        out["note"] = ("venue_form=true mirrors production, which prices from venue-split "
                       "form. pooled_same_sample is the old harness basis on identical "
                       "rows — the difference is what the fidelity fix was worth.")
    if model == "v3":
        out["blocked_weight"] = blocked_weight
        out["only_covered"] = only_covered
        out["skipped_no_blocked_history"] = skipped_no_blocked
        out["rows_using_blocked"] = preds - fell_back
        out["rows_fell_back_to_v2"] = fell_back
        out["v2_same_sample"] = _backtest_summary(alt_stats, lines)
        out["note"] = ("v3 is a candidate, not live pricing. Compare against v2_same_sample, "
                       "not against a separate v2 run — that would be a different sample. "
                       + ("only_covered=true: scored only where blocked history exists (what the "
                          "feature is worth where it applies)."
                          if only_covered else
                          "Default mode: every row scored, falling back to v2 where blocked "
                          "history is short (what shipping this would actually do)."))
    return out


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
                    "total_avg": s["total_avg"], "season_total_avg": overall["total_avg"],
                    "features": team_features(src, split, window)})
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
        feats = team_features(real)
        out.append({"team_id": t["team_id"], "name": t["name"], "games": n,
                    "corners_won": round(won, 2), "corners_conceded": round(concd, 2),
                    "shots": round(shots, 1), "real_samples": t.get("real_samples", 0),
                    "shots_on_target": feats["shots_on_target_for"],
                    "blocked_shots": feats["blocked_shots_for"],
                    "dangerous_attacks": feats["dangerous_attacks_for"],
                    "features": feats})
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

    def features(team):
        return {sp: team_features(team.get("real_matches") or [], sp) for sp in ["home", "away", "overall"]}

    def states(team):
        return {sp: team_state_splits(team.get("real_matches") or [], sp)
                for sp in ["home", "away", "overall"]}

    def goals(team):
        return {sp: goal_profile(team.get("real_matches") or [], sp)
                for sp in ["home", "away", "overall"]}

    # Why the live model nudges this team's lambda, per split — the same call pricing
    # makes, so the panel and the price cannot disagree.
    league = await db.leagues.find_one({"league_id": fx["league_id"]}, {"_id": 0}) or {}
    ls, lb = league.get("avg_shots") or REF_SHOTS, league.get("avg_blocked") or 0.0

    def intent(team):
        return {sp: intent_breakdown(team, sp, ls, lb) for sp in ["home", "away", "overall"]}

    def recent(team):
        rms = team.get("real_matches") or []
        return [{"date": m["date"], "opponent": m["opponent"], "home": m["home"],
                 "won": m["corners_for"], "conceded": m["corners_against"],
                 "total": m["corners_for"] + m["corners_against"],
                 "gf": m.get("goals_for"), "ga": m.get("goals_against"),
                 "fh": (m["fh_goals_for"] >= 1) if m.get("fh_goals_for") is not None else None,
                 "ht_state": HT_LABELS.get(_match_state(m, "ht")),
                 "ft_state": FT_LABELS.get(_match_state(m, "ft")),
                 # goal detail — present only on matches the goal backfill has reached
                 "scorers": m.get("scorers"), "minutes_trailing": m.get("minutes_trailing"),
                 "first_goal_min": m.get("first_goal_min"),
                 "opp_first_goal_min": m.get("opp_first_goal_min"),
                 "scored_first": m.get("scored_first"),
                 # both sides of each feature: sync stores _for and _against, and the
                 # conceded half is what tells you whether a shot count was earned
                 # against a leaky defence or a solid one
                 **{f"{feat}_{side}": m.get(f"{feat}_{side}")
                    for feat in ("shots", "shots_on_target", "blocked_shots", "dangerous_attacks")
                    for side in ("for", "against")}}
                for m in reversed(rms)]

    return {"fixture": fx, "model": model,
            "home_team": {"name": home["name"], "splits": splits(home), "features": features(home),
                          "state_splits": states(home), "goal_profile": goals(home),
                          "intent": intent(home), "recent": recent(home),
                          "real_samples": home.get("real_samples", 0)},
            "away_team": {"name": away["name"], "splits": splits(away), "features": features(away),
                          "state_splits": states(away), "goal_profile": goals(away),
                          "intent": intent(away), "recent": recent(away),
                          "real_samples": away.get("real_samples", 0)}}


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


# A venue split needs this many games before it is trusted on its own. Below it the
# full history is used instead: a team promoted mid-table with one home game on record
# was previously handed a "home average" of that single match, and that number then
# drove its lambda, its projection and its place on every board.
MIN_VENUE_GAMES = 3


def _real_avg(team, side, field):
    rms = (team or {}).get("real_matches") or []
    if side == "home":
        pool = [m for m in rms if m["home"]]
    elif side == "away":
        pool = [m for m in rms if not m["home"]]
    else:
        pool = rms
    if len(pool) < MIN_VENUE_GAMES:
        pool = rms                      # too thin to mean anything — fall back to everything
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


# ----------------------------- Streak model -----------------------------
# One model, two directions. A streak is always described by a whole-number line
# plus a DIRECTION:
#   over  — the historic behaviour: "line+" corners, i.e. value >= line (= Over line-0.5).
#           A half-line can't land exactly, so an over leg never voids.
#   under — a laddered whole line: below it wins, EXACTLY on it is a void (stake back,
#           as books settle a whole corner line) and above it loses.
# A void is neutral: it neither extends nor breaks a run, and it is excluded from the
# hit-rate denominator instead of counting as a miss.
# SUBJECT picks what the line is measured against: the team's own corners, or the
# match total (team + opponent). Same model, same rows — no parallel collection.

WIN, VOID, LOSS = "win", "void", "loss"

# Laddered lines the auto-picker walks. Team corners top out far lower than match totals.
STREAK_LADDERS = {"team": list(range(1, 16)), "match": list(range(1, 31))}
# A run of one game is a result, not a streak. Two things could put one on the board:
#   - a line carried by VOIDS — four exact-line pushes and a single win cleared the old
#     `hits >= 1 and hits + voids >= min_hits` test, and showed as "streak: 1"
#   - a team with barely any history, so its whole record is one or two games
# Both are the same complaint: the row claims a pattern the sample cannot support.
MIN_STREAK_LEN = 2
# Default ceiling for under streaks: above these a line is true so often it says nothing.
UNDER_LINE_CAP = {"team": 8, "match": 12}


def settle_streak_leg(value: int, line: int, direction: str) -> str:
    """Settle one game against a streak line. Exact-line results void on unders."""
    if direction == "under":
        if value < line:
            return WIN
        return VOID if value == line else LOSS
    return WIN if value >= line else LOSS


def streak_value(match: dict, subject: str) -> int:
    """The number a streak line is measured against for one played match."""
    if subject == "match":
        return match["corners_for"] + match["corners_against"]
    return match["corners_for"]


def streak_legs(matches: List[dict], line: int, direction: str, subject: str) -> List[dict]:
    return [{"date": m.get("date"), "value": streak_value(m, subject),
             "result": settle_streak_leg(streak_value(m, subject), line, direction)}
            for m in matches]


def streak_runs(legs: List[dict]) -> dict:
    """Current and longest run over chronological (oldest-first) settled legs.

    The current run is the one still alive at the newest game — its length, the date it
    started and whether it is still active. Voids are skipped, so a run that goes
    win-win-void-win is three long and unbroken."""
    longest = {"length": 0, "start_date": None, "end_date": None, "voids": 0}
    length, voids, start, end = 0, 0, None, None
    for leg in legs:
        if leg["result"] == VOID:
            if length:
                voids += 1
            continue
        if leg["result"] == WIN:
            length += 1
            if length == 1:
                start, voids = leg["date"], 0
            end = leg["date"]
            if length > longest["length"]:
                longest = {"length": length, "start_date": start, "end_date": end, "voids": voids}
        else:
            length, start, end, voids = 0, None, None, 0
    current = {"length": length, "start_date": start, "last_date": end, "voids": voids,
               "status": "active" if length else "broken"}
    longest["is_current"] = bool(length) and longest["length"] == length and longest["end_date"] == end
    return {"current": current, "longest": longest}


def streak_qualifies(hits: int, voids: int, run_length: int, min_hits: int, floor: int) -> bool:
    """Is this a streak, or just a result that happened to fall the right way?

    Three separate hurdles, and a row has to clear all of them:
      - `hits >= floor`      — real WINS in the window, so voids can't carry a line
      - `hits + voids >= min_hits` — the coverage the user asked for, voids allowed
      - `run_length >= floor` — the run alive right now is actually a run
    The last one is what removes single-game streaks from a team with almost no history."""
    return hits >= floor and hits + voids >= min_hits and run_length >= floor


def streak_line_label(line: int, direction: str) -> str:
    return f"under {line}" if direction == "under" else f"{line}+"


def pick_streak_line(values: List[int], direction: str, subject: str, min_hits: int) -> int:
    """Best laddered line for this run: the highest line still cleared on an over,
    the tightest line still held on an under. Voids count towards min_hits (they are
    not misses) but a line carried entirely by voids is not a streak."""
    ladder = STREAK_LADDERS.get(subject, STREAK_LADDERS["team"])

    def qualifies(line: int) -> bool:
        legs = [settle_streak_leg(v, line, direction) for v in values]
        wins = legs.count(WIN)
        return wins >= 1 and wins + legs.count(VOID) >= min_hits

    hits = [x for x in ladder if qualifies(x)]
    if not hits:
        return 0
    return min(hits) if direction == "under" else max(hits)


def _streak_projection(team: dict, opp: Optional[dict], team_venue: str, opp_venue: str,
                       line: int, direction: str, subject: str, league_shots: float,
                       odds: Dict[str, float], league_blocked: float = 0.0) -> Optional[dict]:
    """Price the streak's own market on the team's next fixture.

    A whole-line under can push, so the fair price is taken over SETTLED outcomes
    (p_win / (p_win + p_loss)) and EV credits the void back at stake."""
    t_for = _real_avg(team, team_venue, "corners_for")
    o_against = _real_avg(opp, opp_venue, "corners_against") if opp else None
    if t_for is None or o_against is None:
        return None
    lam = live_lambda((t_for + o_against) / 2, team, team_venue, league_shots, league_blocked)
    ge, pmf, group = nb_ge, nb_pmf, team_venue
    extra = {}
    if subject == "match":
        o_for = _real_avg(opp, opp_venue, "corners_for")
        t_against = _real_avg(team, team_venue, "corners_against")
        if o_for is None or t_against is None:
            return None
        lam_opp = live_lambda((o_for + t_against) / 2, opp, opp_venue, league_shots, league_blocked)
        extra = {"opp_for": round(o_for, 2), "team_conceded": round(t_against, 2),
                 "lambda_team": lam, "lambda_opp": lam_opp}
        lam = round(lam + lam_opp, 2)
        ge, pmf, group = poisson_ge, poisson_pmf, "total"
    if direction == "under":
        p_void = pmf(line, lam)
        p = max(0.0, 1.0 - ge(line, lam))          # P(X <= line - 1)
        p_loss = max(0.0, 1.0 - p - p_void)
        settled = p + p_loss
        fo = fair_odds(p / settled) if settled > 0 else None
        mkey = f"{group}_under_{line}"
        book = odds.get(mkey)
        ev = round((book * p + p_void - 1) * 100, 2) if book else None
    else:
        p, p_void = ge(line, lam), 0.0
        fo = fair_odds(p)
        mkey = f"{group}_over_{line - 0.5}"
        book = odds.get(mkey)
        ev = round((book * p - 1) * 100, 2) if book else None
    return {"team_for": round(t_for, 2), "opp_conceded": round(o_against, 2), **extra,
            "lambda": lam, "line": line, "direction": direction, "subject": subject,
            "prob": round(p * 100, 1), "void_prob": round(p_void * 100, 1),
            "fair_odds": fo, "market_key": mkey, "book_odds": book, "ev": ev,
            "tier": tier_for_ev(ev) if ev is not None else None}


@api_router.get("/streaks")
async def streaks(league_id: Optional[str] = None, side: str = "overall", window: int = 5,
                  min_hits: int = 5, threshold: Optional[int] = None, min_line: int = 3,
                  within_days: Optional[int] = None, direction: str = "over",
                  subject: str = "team", max_line: Optional[int] = None,
                  min_streak: int = MIN_STREAK_LEN,
                  user: dict = Depends(get_current_user)):
    """Teams that keep landing the same side of a corner line over recent REAL games —
    e.g. 4+ team corners in 5/5 home games, or the match total under 10 in 8 of the last 10.

    direction:  over (line+) | under (below the line, exact line voids)
    subject:    team (team corners) | match (match total corners)
    min_streak: shortest run that counts as a streak (default 2 — one game is not one)"""
    if (_cache_ok() and league_id in (None, "all") and side == "home" and window == 5
            and min_hits == 5 and threshold is None and min_line == 3
            and within_days is None and direction == "over" and subject == "team"
            and max_line is None and min_streak == MIN_STREAK_LEN):
        return await _screen("streaks")
    q = {} if not league_id or league_id == "all" else {"league_id": league_id}
    teams = await db.teams.find(q, {"_id": 0}).to_list(5000)
    teams_by_id = {t["team_id"]: t for t in teams}
    ls_map = _league_shots_map(teams)
    bl_map = _league_blocked_map(teams)
    leagues = {l["league_id"]: l["name"] for l in await db.leagues.find({}, {"_id": 0}).to_list(100)}

    # earliest upcoming fixture per team
    fixtures = await db.fixtures.find(q, {"_id": 0}).to_list(5000)
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

    direction = "under" if direction == "under" else "over"
    subject = "match" if subject == "match" else "team"
    cap = max_line if max_line is not None else UNDER_LINE_CAP[subject]
    # never demand more wins than the window can supply, and never drop below 1
    floor = max(1, min(int(min_streak), min_hits))

    results = []
    for t in teams:
        rms = t.get("real_matches") or []
        if side == "home":
            history = [m for m in rms if m["home"]]
        elif side == "away":
            history = [m for m in rms if not m["home"]]
        else:
            history = list(rms)
        pool = history[-window:]
        if len(pool) < window:
            continue
        values = [streak_value(m, subject) for m in pool]
        line = int(threshold) if threshold is not None else pick_streak_line(values, direction, subject, min_hits)
        if line <= 0:
            continue
        # An under is impressive when the line is LOW, an over when it is HIGH.
        if direction == "under":
            if line > cap:
                continue
        elif line < min_line:
            continue
        legs = streak_legs(pool, line, direction, subject)
        hits = sum(1 for lg in legs if lg["result"] == WIN)
        voids = sum(1 for lg in legs if lg["result"] == VOID)
        misses = len(legs) - hits - voids
        runs = streak_runs(streak_legs(history, line, direction, subject))
        if not streak_qualifies(hits, voids, runs["current"]["length"], min_hits, floor):
            continue
        recent = [{"corners": lg["value"], "value": lg["value"], "result": lg["result"],
                   "opponent": m["opponent"], "home": m["home"], "date": m["date"]}
                  for m, lg in zip(reversed(pool), reversed(legs))]
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
            projection = _streak_projection(t, opp, team_venue, opp_venue, line, direction, subject,
                                            ls_map.get(t["league_id"], REF_SHOTS),
                                            odds_map.get(nf["fixture_id"], {}),
                                            bl_map.get(t["league_id"], 0.0))
        results.append({
            "team_id": t["team_id"], "name": t["name"], "league_id": t["league_id"],
            "league_name": leagues.get(t["league_id"], ""), "side": side, "window": window,
            "direction": direction, "subject": subject,
            "min_hits": min_hits, "hits": hits, "voids": voids, "misses": misses,
            "settled": hits + misses, "line": line,
            "line_label": streak_line_label(line, direction),
            "hit_rate": round(hits / (hits + misses) * 100, 1) if (hits + misses) else 0.0,
            "avg": round(sum(values) / len(values), 2), "min_won": min(values), "max_won": max(values),
            "streak": runs["current"], "longest": runs["longest"],
            "real_samples": t.get("real_samples", 0), "recent": recent,
            "next_fixture": nf, "projection": projection,
        })
    # tightest under / highest over first, then the most reliable and longest runs
    if direction == "under":
        results.sort(key=lambda x: (-x["line"], x["hits"], x["streak"]["length"], -x["avg"]), reverse=True)
    else:
        results.sort(key=lambda x: (x["line"], x["hits"], x["streak"]["length"], x["avg"]), reverse=True)
    return results


@api_router.get("/features/coverage")
async def feature_coverage(league_id: Optional[str] = None, user: dict = Depends(get_current_user)):
    """How much of the shot-volume data actually landed, per league.

    Providers cover these unevenly (dangerous attacks especially), so before reading
    anything into these features you need to know what fraction of fixtures carry them.
    Counts are over team-sides — two per cached fixture."""
    q = {} if not league_id or league_id == "all" else {"league_id": league_id}
    docs = await db.fixture_stats.find(q, {"_id": 0}).to_list(50000)
    leagues = {l["league_id"]: l["name"] for l in await db.leagues.find({}, {"_id": 0}).to_list(200)}
    per_league = {}
    for d in docs:
        lid = d.get("league_id", "")
        row = per_league.setdefault(lid, {"league_id": lid, "league_name": leagues.get(lid, lid),
                                          "fixtures": 0, "sides": 0, "goal_events": 0,
                                          **{f: 0 for f in SHOT_FEATURES}})
        row["fixtures"] += 1
        row["sides"] += 2
        # goal detail is per FIXTURE, not per side — one events call fills both teams
        row["goal_events"] += 2 if d.get("events_at") else 0
        for f in SHOT_FEATURES:
            row[f] += sum(1 for side in ("home", "away") if d.get(f"{side}_{f}") is not None)
    cols = list(SHOT_FEATURES) + ["goal_events"]
    for row in per_league.values():
        row["pct"] = {f: round(row[f] / row["sides"] * 100, 1) if row["sides"] else 0.0
                      for f in cols}
    totals = {"fixtures": sum(r["fixtures"] for r in per_league.values()),
              "sides": sum(r["sides"] for r in per_league.values())}
    for f in cols:
        totals[f] = sum(r[f] for r in per_league.values())
    totals["pct"] = {f: round(totals[f] / totals["sides"] * 100, 1) if totals["sides"] else 0.0
                     for f in cols}
    return {"features": cols, "totals": totals,
            "leagues": sorted(per_league.values(), key=lambda r: r["league_name"])}


@api_router.get("/leagues/{league_id}/state-splits")
async def league_state_splits(league_id: str, split: str = "overall",
                              user: dict = Depends(get_current_user)):
    """Corners won/conceded per team, grouped by half-time state and by final result.

    CAVEAT worth repeating at every call site: API-Football reports corners for the
    whole match only, so these are full-match corners in games where the team was in
    that state — not corners won while in it. A chase effect that lives in the second
    half reads diluted here. See probe_corner_halves.py."""
    teams = await db.teams.find({"league_id": league_id}, {"_id": 0}).to_list(200)
    league = await db.leagues.find_one({"league_id": league_id}, {"_id": 0}) or {}
    rows = []
    for t in teams:
        rows.append({"team_id": t["team_id"], "name": t["name"],
                     "real_samples": t.get("real_samples", 0),
                     **team_state_splits(t.get("real_matches") or [], split)})
    # league baseline: every team-game pooled, so a team's bucket has something to beat
    pooled = [m for t in teams for m in (t.get("real_matches") or [])]
    rows.sort(key=lambda r: (r["ht"]["trailing"]["won"] or 0), reverse=True)
    return {"league_id": league_id, "league_name": league.get("name", league_id),
            "split": split, "league_baseline": team_state_splits(pooled, split),
            "teams": rows}


@api_router.get("/leagues/{league_id}/matchups")
async def matchups(league_id: str, side: str = "overall", user: dict = Depends(get_current_user)):
    """Top corner-winning teams in a league (by venue) with their next fixture + opponent-concede mismatch."""
    teams = await db.teams.find({"league_id": league_id}, {"_id": 0}).to_list(200)
    teams_by_id = {t["team_id"]: t for t in teams}
    ls = _league_shots_map(teams).get(league_id, REF_SHOTS)
    lb = _league_blocked_map(teams).get(league_id, 0.0)
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
                lam = live_lambda((team_for + opp_conc) / 2, t, venue, ls, lb)
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
    bl_map = _league_blocked_map(teams)
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
        lam = live_lambda((team_for + opp_conc) / 2, t, venue,
                          ls_map.get(t["league_id"], REF_SHOTS), bl_map.get(t["league_id"], 0.0))
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
    if _cache_ok() and within_days == 7 and limit == 30:
        return await _screen("mismatches")
    return await _all_mismatches(within_days, limit)


def _venue_matches(team, venue):
    rms = (team or {}).get("real_matches") or []
    if venue == "home":
        pool = [m for m in rms if m["home"]]
    elif venue == "away":
        pool = [m for m in rms if not m["home"]]
    else:
        pool = list(rms)
    return pool or rms


async def _chase_board(within_days: int = 7, limit: int = 25, league_id: Optional[str] = None):
    """Weekly shortlist of the best team-corner chase spots, ranked by a composite of:
    corner dominance (team corners won + opponent corners conceded), a CHASE CATALYST
    (opponent scores a first-half goal → our team likely trails and chases), and CONSISTENCY
    (how reliably the team hits the line on this venue). No book odds needed."""
    q = {} if not league_id or league_id == "all" else {"league_id": league_id}
    teams = await db.teams.find(q, {"_id": 0}).to_list(2000)
    teams_by_id = {t["team_id"]: t for t in teams}
    ls_map = _league_shots_map(teams)
    bl_map = _league_blocked_map(teams)
    leagues = {l["league_id"]: l["name"] for l in await db.leagues.find({}, {"_id": 0}).to_list(200)}
    next_fx = await _next_fixtures(q)
    league_avgs = {}
    for t in teams:
        league_avgs.setdefault(t["league_id"], []).extend(m["corners_for"] for m in _src(t))
    league_avgs = {k: (sum(v) / len(v) if v else 5.0) for k, v in league_avgs.items()}
    fx_ids = list({v["fixture_id"] for v in next_fx.values()})
    odds_docs = await db.odds.find({"fixture_id": {"$in": fx_ids}}, {"_id": 0}).to_list(5000)
    odds_map = {o["fixture_id"]: o.get("odds", {}) for o in odds_docs}
    now = datetime.now(timezone.utc)
    out = []
    for t in teams:
        nf = next_fx.get(t["team_id"])
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
        venue = "home" if nf["is_home"] else "away"
        opp_venue = "away" if nf["is_home"] else "home"
        pool = _venue_matches(t, venue)
        if len(pool) < 4:
            continue
        team_for = sum(m["corners_for"] for m in pool) / len(pool)
        opp = teams_by_id.get(nf["opponent_team_id"])
        opp_pool = _venue_matches(opp, opp_venue) if opp else []
        if len(opp_pool) < 4:
            continue
        opp_conc = sum(m["corners_against"] for m in opp_pool) / len(opp_pool)
        opp_fh = sum(1 for m in opp_pool if m.get("fh_goals_for", 0) >= 1) / len(opp_pool)
        lam = live_lambda((team_for + opp_conc) / 2, t, venue,
                          ls_map.get(t["league_id"], REF_SHOTS), bl_map.get(t["league_id"], 0.0))
        line = max(3, round(lam) - 1)
        last5 = pool[-5:]
        hit = sum(1 for m in last5 if m["corners_for"] >= line)
        consistency = hit / len(last5)
        p = nb_ge(line, lam)
        avg = league_avgs.get(t["league_id"], 5.0)
        corner_edge = round(lam / avg, 2) if avg else 1.0
        # MEASURED AND FOUND NOT TO RANK. measure_chase_board.py replays this board
        # walk-forward and scores each ordering by residual (actual hit rate minus the
        # model's own probability) — i.e. does the order find spots the model UNDERRATES:
        #     chase_score  +0.02      lambda_only  +0.01
        #     no_opp_fh    +0.03      RANDOM       flat  <- control passed
        # All four are the same number. The control coming out flat is what makes that
        # trustworthy: the harness is not manufacturing gradients. So this ordering
        # carries no information the model did not already have, and no_opp_fh scoring
        # highest is noise, NOT evidence that dropping the term helped.
        #
        # The opponent first-half term is gone anyway — five tests have now failed to
        # find any effect from it, and keeping a falsified hypothesis in production code
        # meant the board displayed "opp scores 1H 62%" as though it were a reason.
        # `opp_fh_rate` is still returned as CONTEXT; it just no longer moves the order.
        #
        # This is simplification, not improvement. Ordering is still descriptive: use the
        # board as a filter (spots that clear the line reliably), not as a ranking.
        chase_score = round(lam * (0.6 + 0.4 * consistency), 3)
        mkey = f"{venue}_over_{line - 0.5}"
        book = odds_map.get(nf["fixture_id"], {}).get(mkey)
        ev = round((book * p - 1) * 100, 2) if book else None
        out.append({
            "team_id": t["team_id"], "name": t["name"], "league_id": t["league_id"],
            "league_name": leagues.get(t["league_id"], ""),
            "team_for": round(team_for, 2), "opp_conceded": round(opp_conc, 2),
            "opp_fh_rate": round(opp_fh * 100), "lambda": lam, "line": line,
            "consistency": hit, "consistency_of": len(last5),
            "prob": round(p * 100, 1), "fair_odds": fair_odds(p),
            "book_odds": book, "ev": ev, "tier": tier_for_ev(ev) if ev is not None else None,
            "market_key": mkey, "corner_edge": corner_edge, "chase_score": chase_score,
            "real_samples": t.get("real_samples", 0), "next_fixture": nf,
        })
    out.sort(key=lambda x: x["chase_score"], reverse=True)
    return out[:limit]


@api_router.get("/chase-board")
async def chase_board(within_days: int = 7, limit: int = 25, league_id: Optional[str] = None,
                      user: dict = Depends(get_current_user)):
    if _cache_ok() and within_days == 7 and limit == 25 and league_id in (None, "all"):
        return await _screen("chase")
    board = await _chase_board(within_days, min(max(limit, 1), 100), league_id)
    return {"within_days": within_days, "count": len(board), "board": board}


# ----------------------------- Fixture board (home page) -----------------------------
# Every other board on this site is TEAM-first: a row is a team, and the fixture rides
# along as `next_fixture`. That is the wrong shape for "what should I look at tonight",
# where the unit is the match. This one is fixture-first.
#
# HOW A FIXTURE IS RANKED, stated plainly because it matters:
#   - It must carry at least one live ANGLE (a chase spot or a streak). A big projected
#     total with nothing to bet on is not a pick, it is trivia.
#   - Those angles are then ordered by CORNER EDGE: the model's projected match total
#     divided by that league's actual average match total. Both halves are production
#     numbers — the projection is `expected_lambdas`, the same call the fixture page and
#     every price uses — so this ranks by model conviction, not by a new invented score.
#
# What it is NOT: a measured edge. Nothing here has been through the backtester as a
# ranking, so treat the order as triage — which matches to open first — and take the
# actual bet from the angle, which has been priced. `corner_edge` is also correlated
# with the chase board by construction (both are driven by the same lambda), so the
# angle count is corroboration, not independent confirmation.

FIXTURE_BOARD_PER_DAY = 5          # how many a day may show, IF they earn it
FIXTURE_BOARD_ANGLES = 6           # angles listed per fixture before it stops being readable

# The bar below is ABSOLUTE, and that is the whole point. `per_day` is a ceiling, not a
# quota: a quiet Tuesday with one fixture shows that fixture only if it would also have
# made a Saturday of ten. Ranking alone cannot do this — sort-and-take-N always promotes
# something, so the only game on gets crowned by default.
BOARD_MIN_GAMES = 6                # real matches behind EACH side before its numbers mean anything
BOARD_MIN_RUN = 3                  # a streak must be a run; 2 is merely the floor for being one
BOARD_MIN_CONSISTENCY = 0.8        # a chase spot must have hit 4 of its last 5
BOARD_MIN_EDGE = 1.0               # the model must expect an at-or-above-par corner game


def _angle_rank(a: dict) -> tuple:
    """Best angle first: strong ones above weak, then longest live run, most hits,
    tighter line."""
    return (1 if a.get("strong") else 0, a.get("streak_len") or 0,
            a.get("hits") or 0, -(a.get("line") or 0))


def angle_is_strong(a: dict, min_run: int = BOARD_MIN_RUN,
                    min_consistency: float = BOARD_MIN_CONSISTENCY) -> bool:
    """Is this angle evidence, or just a row that cleared a minimum?

    A chase spot is judged on how reliably the team has actually hit the line — the
    game-state catalyst (opponent scoring first-half goals) is what put it on the chase
    board, but reliability is what makes it worth acting on. A streak is judged on the
    run that is ALIVE, not on the window's hit count, because a 4/5 whose most recent
    game was the miss is a broken streak wearing a good record."""
    if a.get("kind") == "chase":
        return (a.get("consistency_rate") or 0.0) >= min_consistency
    return (a.get("streak_len") or 0) >= min_run


def fixture_qualifies(row: dict, min_games: int = BOARD_MIN_GAMES,
                      min_edge: float = BOARD_MIN_EDGE) -> bool:
    """Three hurdles, all absolute — nothing here depends on the rest of the day's card.

      CONTEXT    both sides have enough real matches for their averages to mean anything
      PROJECTION the model expects an at-or-above-par corner game for that league
      EVIDENCE   at least one angle that is actually strong, not merely present
    """
    if min(row.get("home_games", 0), row.get("away_games", 0)) < min_games:
        return False
    if (row.get("corner_edge") or 0) < min_edge:
        return False
    return any(a.get("strong") for a in row.get("angles") or [])


def board_days(rows: List[dict], per_day: int) -> List[dict]:
    """Group scored fixtures by kickoff day, keep the best `per_day` of each, and read
    each day back in KICKOFF order rather than in score order.

    The cap is the whole point of this board, so it is pure and tested: dropping the
    wrong fixture is silent — you would just never see the game you wanted."""
    by_day: Dict[str, List[dict]] = defaultdict(list)
    for r in rows:
        by_day[(r.get("date") or "")[:10]].append(r)
    out = []
    for day in sorted(k for k in by_day if k):
        ranked = sorted(by_day[day],
                        key=lambda r: (r["corner_edge"], r.get("angle_count") or 0),
                        reverse=True)
        picked = sorted(ranked[:per_day], key=lambda r: r.get("date") or "")
        out.append({"day": day, "considered": len(by_day[day]), "fixtures": picked})
    return out


async def _fixture_board(days: int = 7, per_day: int = FIXTURE_BOARD_PER_DAY,
                         league_id: Optional[str] = None, user: dict = None,
                         min_games: int = BOARD_MIN_GAMES, min_run: int = BOARD_MIN_RUN,
                         min_edge: float = BOARD_MIN_EDGE) -> dict:
    per_day = max(1, min(int(per_day), 20))
    days = max(1, min(int(days), 14))
    min_games = max(0, min(int(min_games), 30))
    min_run = max(1, min(int(min_run), 20))
    min_edge = max(0.0, min(float(min_edge), 3.0))
    lid = league_id or "all"
    q = {} if lid == "all" else {"league_id": lid}

    teams = await db.teams.find(q, {"_id": 0}).to_list(5000)
    teams_by_id = {t["team_id"]: t for t in teams}
    leagues = {l["league_id"]: l for l in await db.leagues.find({}, {"_id": 0}).to_list(200)}
    # what a normal match in this league actually produces, to judge the projection against
    league_totals = defaultdict(list)
    for t in teams:
        for m in _src(t):
            league_totals[t["league_id"]].append(m["corners_for"] + m["corners_against"])
    league_avg = {k: (sum(v) / len(v) if v else 10.0) for k, v in league_totals.items()}

    now = datetime.now(timezone.utc)
    horizon = now + timedelta(days=days)
    fixtures = await db.fixtures.find(q, {"_id": 0}).to_list(5000)

    rows: Dict[str, dict] = {}
    for fx in fixtures:
        try:
            dt = datetime.fromisoformat((fx.get("date") or "").replace("Z", "+00:00"))
        except Exception:
            continue
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        if dt < now or dt > horizon:
            continue
        home, away = teams_by_id.get(fx["home_team_id"]), teams_by_id.get(fx["away_team_id"])
        if not home or not away:
            continue
        lg = leagues.get(fx["league_id"], {})
        lam = expected_lambdas(home, away, lg.get("avg_shots") or REF_SHOTS,
                               lg.get("avg_blocked") or 0.0)
        avg = league_avg.get(fx["league_id"]) or 10.0
        rows[fx["fixture_id"]] = {
            "fixture_id": fx["fixture_id"], "date": fx["date"], "round": fx.get("round"),
            "league_id": fx["league_id"], "league_name": lg.get("name", fx["league_id"]),
            "home": fx["home_name"], "away": fx["away_name"],
            "lambda_home": lam["home"], "lambda_away": lam["away"], "lambda_total": lam["total"],
            "league_avg_total": round(avg, 2),
            "corner_edge": round(lam["total"] / avg, 3) if avg else 1.0,
            # sample behind each side — the CONTEXT hurdle, and shown so a thin row is
            # visibly thin rather than quietly thin
            "home_games": len(_src(home)), "away_games": len(_src(away)),
            "angles": [],
        }
    if not rows:
        return {"days": [], "per_day": per_day, "within_days": days, "fixtures": 0}

    def add(fid, angle):
        row = rows.get(fid)
        if row is not None:
            row["angles"].append(angle)

    for c in await _chase_board(within_days=days, limit=500, league_id=lid):
        nf = c.get("next_fixture") or {}
        rate = (c["consistency"] / c["consistency_of"]) if c.get("consistency_of") else 0.0
        add(nf.get("fixture_id"), {
            "kind": "chase", "team": c["name"], "label": f"{c['line']}+ corners",
            "detail": f"λ {c['lambda']} · hit {c['consistency']}/{c['consistency_of']}"
                      f" · opp scores 1H {c['opp_fh_rate']}%",
            "line": c["line"], "hits": c["consistency"], "streak_len": 0,
            "consistency_rate": round(rate, 3), "opp_fh_rate": c["opp_fh_rate"],
            "prob": c["prob"], "fair_odds": c["fair_odds"], "ev": c.get("ev")})

    # the same four grids the streaks export walks, so the board cannot disagree with it
    for direction, subject, min_line in (("over", "team", 3), ("under", "team", 3),
                                         ("over", "match", 7), ("under", "match", 3)):
        for s in await streaks(league_id=lid, side="overall", window=5, min_hits=5,
                               threshold=None, min_line=min_line, within_days=days,
                               direction=direction, subject=subject, user=user):
            nf = s.get("next_fixture") or {}
            run = (s.get("streak") or {}).get("length") or 0
            what = "match total" if subject == "match" else "corners"
            add(nf.get("fixture_id"), {
                "kind": f"{direction}_{subject}", "team": s["name"],
                "label": f"{s['line_label']} {what}",
                "detail": f"{s['hits']}/{s['settled'] or s['window']} · run {run}"
                          + (f" · {s['voids']} void" if s.get("voids") else ""),
                "line": s["line"], "hits": s["hits"], "streak_len": run,
                "prob": (s.get("projection") or {}).get("prob"),
                "fair_odds": (s.get("projection") or {}).get("fair_odds"),
                "ev": (s.get("projection") or {}).get("ev")})

    for r in rows.values():
        for a in r["angles"]:
            a["strong"] = angle_is_strong(a, min_run, BOARD_MIN_CONSISTENCY)
        r["angles"].sort(key=_angle_rank, reverse=True)
        r["angle_count"] = len(r["angles"])
        r["strong_angles"] = sum(1 for a in r["angles"] if a["strong"])
        r["angles"] = r["angles"][:FIXTURE_BOARD_ANGLES]
        r["best_angle"] = r["angles"][0] if r["angles"] else None

    # The bar, applied BEFORE the per-day ceiling — so a thin day shows fewer games, or
    # none, rather than promoting whatever happened to be on.
    live = [r for r in rows.values() if fixture_qualifies(r, min_games, min_edge)]
    out_days = board_days(live, per_day)
    seen = {d["day"] for d in out_days}
    # days that had fixtures but nothing that cleared the bar are reported, not hidden:
    # "nothing qualified" is information, an absent day looks like missing data
    for r in rows.values():
        day = (r.get("date") or "")[:10]
        if day and day not in seen:
            out_days.append({"day": day, "considered": 0, "fixtures": []})
            seen.add(day)
    for d in out_days:
        d["scanned"] = sum(1 for r in rows.values() if (r.get("date") or "")[:10] == d["day"])
    out_days.sort(key=lambda d: d["day"])
    return {"days": out_days, "per_day": per_day, "within_days": days,
            "min_games": min_games, "min_run": min_run, "min_edge": min_edge,
            "fixtures": sum(len(d["fixtures"]) for d in out_days)}


@api_router.get("/fixture-board")
async def fixture_board(days: int = 7, per_day: int = FIXTURE_BOARD_PER_DAY,
                        league_id: Optional[str] = None,
                        min_games: int = BOARD_MIN_GAMES, min_run: int = BOARD_MIN_RUN,
                        min_edge: float = BOARD_MIN_EDGE,
                        user: dict = Depends(get_current_user)):
    """The best upcoming fixtures, grouped by kickoff day, fixture-first.

    Served from the precomputed screen when called with defaults (the home page's
    request); any tuned parameter set computes live.

    `per_day` is a CEILING, not a quota. Every fixture must clear an absolute bar first
    — sample behind both sides, an at-or-above-par projection, and at least one angle
    that is strong rather than merely present — so a day with one fixture on shows it
    only if it would have made a busy day too. A day where nothing clears comes back
    with an empty list rather than being dropped.

    min_games / min_run / min_edge loosen or tighten that bar. See the notes above
    `_fixture_board` for how "best" is decided, and for what it has NOT been shown to be."""
    if (_cache_ok() and days == 3 and per_day == FIXTURE_BOARD_PER_DAY
            and league_id in (None, "all") and min_games == BOARD_MIN_GAMES
            and min_run == BOARD_MIN_RUN and min_edge == BOARD_MIN_EDGE):
        return await _screen("fixture_board")
    return await _fixture_board(days, per_day, league_id, user, min_games, min_run, min_edge)


@api_router.get("/top-corner-teams")
async def top_corner_teams(side: str = "overall", window: int = 0, limit: int = 40,
                           league_id: Optional[str] = None, user: dict = Depends(get_current_user)):
    """Best corner teams across leagues, ranked by average corners WON on a venue/window (real games)."""
    if (_cache_ok() and side == "overall" and window == 0 and limit == TOP_TEAMS_LIMIT
            and league_id in (None, "all")):
        return await _screen("top_teams")
    limit = min(max(limit, 1), 100)
    q = {} if not league_id or league_id == "all" else {"league_id": league_id}
    teams = await db.teams.find(q, {"_id": 0}).to_list(2000)
    leagues = {l["league_id"]: l["name"] for l in await db.leagues.find({}, {"_id": 0}).to_list(200)}
    next_fx = await _next_fixtures(q)
    out = []
    for t in teams:
        s = team_split(_src(t), side, window)
        if s["played"] < 3:
            continue
        out.append({"team_id": t["team_id"], "name": t["name"], "league_id": t["league_id"],
                    "league_name": leagues.get(t["league_id"], ""), "side": side, "window": window,
                    "games": s["played"], "won_avg": s["for_avg"], "conceded_avg": s["against_avg"],
                    "total_avg": s["total_avg"], "real_samples": t.get("real_samples", 0),
                    "shots_for_avg": s["shots_for_avg"], "shots_against_avg": s["shots_against_avg"],
                    "shots_games": s["shots_games"],
                    "sot_for_avg": s["sot_for_avg"], "sot_against_avg": s["sot_against_avg"],
                    "sot_games": s["sot_games"],
                    "next_fixture": next_fx.get(t["team_id"])})
    out.sort(key=lambda x: x["won_avg"], reverse=True)
    return out[:limit]


@api_router.get("/best-bets")
async def best_bets(user: dict = Depends(get_current_user)):
    # takes no parameters and runs three full team scans, so it is always served cached
    if _cache_ok():
        return await _screen("best_bets")
    chase = await _chase_board(within_days=7, limit=1)
    strk = await streaks(league_id="all", side="overall", window=5, min_hits=5,
                         threshold=None, min_line=3, within_days=None, user=user)
    mism = await _all_mismatches(within_days=None, limit=1)
    return {"chase": chase[0] if chase else None,
            "streak": strk[0] if strk else None,
            "mismatch": mism[0] if mism else None}


# Rows per section in the full markdown report. The old 40/60 caps silently dropped
# whole leagues off the bottom of globally-sorted tables.
EXPORT_ROWS = 250


def _streak_line_label(row: dict) -> str:
    """How the angle reads on a betting slip.

    A match-total angle is derived from ONE team's recent games, not from this
    fixture, so the source team is named. Without it the same fixture can show an
    over and an under total — each true of a different side — and read as the model
    contradicting itself."""
    if row["subject"] == "match":
        side = "match total"
    else:
        side = f"{row['name']} team corners"
    line = f"under {row['line']}" if row["direction"] == "under" else f"{row['line']}+"
    if row["subject"] == "match":
        return f"{side} {line} (via {row['name']}'s games)"
    return f"{side} {line}"


def _streak_record(row: dict) -> str:
    voids = f" +{row['voids']} void" if row.get("voids") else ""
    return f"{row['hits']}/{row.get('settled', row['window'])}{voids}"


@api_router.get("/export/streaks")
async def export_streaks(days: int = 7, window: int = 5, min_hits: int = 5,
                         side: str = "overall", league_id: Optional[str] = None,
                         user: dict = Depends(get_current_user)):
    """Every streak angle — overs and unders, team corners and match totals — on the
    fixtures kicking off in the next `days`, grouped by fixture. Markdown, built to be
    pasted straight into a chat.

    The main report (/api/export) also carries streak tables, but they are not tied to
    a fixture window and carry no kickoff or opponent, so you cannot tell which game an
    angle belongs to. This one is fixture-first."""
    from fastapi.responses import PlainTextResponse
    lid = league_id or "all"
    # match-total overs need a higher floor or every fixture qualifies at line 3
    grid = [("over", "team", 3), ("under", "team", 3),
            ("over", "match", 7), ("under", "match", 3)]
    by_fixture: Dict[str, dict] = {}
    counts = {f"{d}/{s}": 0 for d, s, _ in grid}

    for direction, subject, min_line in grid:
        rows = await streaks(league_id=lid, side=side, window=window, min_hits=min_hits,
                             threshold=None, min_line=min_line, within_days=days,
                             direction=direction, subject=subject, user=user)
        for r in rows:
            nf = r.get("next_fixture")
            if not nf:
                continue
            counts[f"{direction}/{subject}"] += 1
            slot = by_fixture.setdefault(nf["fixture_id"], {
                "date": nf["date"], "league": r["league_name"],
                "home": r["name"] if nf["is_home"] else nf["opponent"],
                "away": nf["opponent"] if nf["is_home"] else r["name"],
                "angles": [], "totals": []})
            entry = {**r, "is_home": nf["is_home"]}
            # a match total is the same bet from either team's side, so keep only the
            # strongest reading of it rather than printing two contradictory lines
            if subject == "match":
                slot["totals"].append(entry)
            else:
                slot["angles"].append(entry)

    for slot in by_fixture.values():
        best = {}
        for t in slot["totals"]:
            key = t["direction"]
            cur = best.get(key)
            better = cur is None or (
                (t["line"] < cur["line"]) if key == "under" else (t["line"] > cur["line"]))
            if better or (cur and t["line"] == cur["line"] and t["hits"] > cur["hits"]):
                best[key] = t
        slot["angles"] += list(best.values())
        slot["angles"].sort(key=lambda a: (a["subject"] != "team", a["direction"]))

    fixtures = sorted(by_fixture.values(), key=lambda f: f["date"])
    now = datetime.now(timezone.utc)
    out = [f"# Corner streaks — fixtures in the next {days} days",
           f"Generated {now.strftime('%Y-%m-%d %H:%M UTC')} · window {min_hits}/{window} · "
           f"side {side} · league {lid}",
           "",
           "Every team/match angle whose streak is live going into the fixture. Model prices are "
           "this app's own (v3); book odds and edge appear only where odds have been pasted in.",
           "An UNDER line is a whole number — landing exactly on it is a void, which does not "
           "break the streak and is excluded from the hit count.",
           "A match-total angle comes from one team's own recent games, so a fixture can show "
           "both an over and an under total — they describe the two sides' different histories, "
           "not a contradiction. The team is named on each.",
           "",
           f"**{len(fixtures)} fixtures** · " + " · ".join(f"{k} {v}" for k, v in counts.items()),
           ""]

    # Coverage, so "where are my other leagues?" is answerable from the export itself.
    # A league can be absent for two very different reasons and they need telling
    # apart: no fixtures stored in the window, or fixtures but nothing qualified.
    # Only the first is a data problem.
    all_leagues = {l["league_id"]: l["name"]
                   for l in await db.leagues.find({}, {"_id": 0}).to_list(500)}
    all_fx = await db.fixtures.find({} if lid == "all" else {"league_id": lid},
                                    {"_id": 0}).to_list(5000)
    horizon = now + timedelta(days=days)
    fx_by_league = defaultdict(int)
    for f in all_fx:
        try:
            dt = datetime.fromisoformat(f["date"].replace("Z", "+00:00"))
        except Exception:
            continue
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        if now <= dt <= horizon:
            fx_by_league[f["league_id"]] += 1
    with_angles = {f["league"] for f in fixtures}
    quiet = sorted(all_leagues.get(k, k) for k in fx_by_league
                   if all_leagues.get(k, k) not in with_angles)
    none_stored = sorted(n for k, n in all_leagues.items() if not fx_by_league.get(k))
    out += [f"Coverage: {sum(fx_by_league.values())} fixtures in this window across "
            f"{len(fx_by_league)} leagues; angles found in {len(with_angles)} of them.", ""]
    if quiet:
        out.append(f"- Fixtures but no qualifying streak ({len(quiet)}): {', '.join(quiet)}")
    if none_stored:
        out.append(f"- No fixtures stored in this window ({len(none_stored)}): "
                   f"{', '.join(none_stored)}")
        out.append("  (a league playing this week that appears here has not synced — "
                   "run a refresh)")
    out.append("")
    if not fixtures:
        out.append("_No streaks match this window. Try more days, a lower min_hits, or a wider "
                   "window._")
        return PlainTextResponse("\n".join(out))

    day = None
    for fx in fixtures:
        d = fx["date"][:10]
        if d != day:
            day = d
            try:
                pretty = datetime.fromisoformat(fx["date"].replace("Z", "+00:00")).strftime("%a %d %b")
            except Exception:
                pretty = d
            out.append(f"\n## {pretty}")
        out.append(f"\n### {fx['date'][11:16]} · {fx['league']} · {fx['home']} v {fx['away']}")
        for a in fx["angles"]:
            proj = a.get("projection") or {}
            bits = [f"{a['direction']}/{a['subject']}", _streak_record(a),
                    f"avg {a['avg']}",
                    f"streak {a['streak']['length']}" + (
                        f" since {a['streak']['start_date'][:10]}" if a['streak'].get('start_date') else ""),
                    f"best {a['longest']['length']}"]
            venue = "" if a["subject"] == "match" else f" ({'H' if a['is_home'] else 'A'})"
            out.append(f"- **{_streak_line_label(a)}**{venue} — " + " · ".join(bits))
            recent = ",".join(str(m["corners"]) for m in a["recent"])
            detail = [f"recent {recent}"]
            if proj.get("fair_odds"):
                detail.append(f"model {proj['fair_odds']} ({proj['prob']}%)")
            if proj.get("void_prob"):
                detail.append(f"void {proj['void_prob']}%")
            if proj.get("book_odds"):
                detail.append(f"book {proj['book_odds']} · edge {proj.get('ev')}%")
            if a["subject"] == "team" and proj.get("opp_conceded") is not None:
                detail.append(f"opp concedes {proj['opp_conceded']}")
            out.append(f"  {' · '.join(detail)}")
    return PlainTextResponse("\n".join(out))


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
    mism = await _all_mismatches(within_days=None, limit=EXPORT_ROWS)
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
    if len(trend) > EXPORT_ROWS:
        lines.append(f"_Showing the top {EXPORT_ROWS} of {len(trend)}._")
    for r in trend[:EXPORT_ROWS]:
        lines.append(f"| {r['name']} | {r['league_name']} | {r['recent_total']} | {r['season_total']} | +{r['delta']} |")

    strk = await streaks(league_id="all", side="overall", window=5, min_hits=5,
                         threshold=None, min_line=3, within_days=None, user=user)
    lines.append("\n## Consistency streaks — hit a team-corner line in all of last 5 games")
    lines.append("| Team | League | Line | Avg | Current | Longest | Recent (won) |")
    lines.append("|---|---|---|---|---|---|---|")
    if len(strk) > EXPORT_ROWS:
        lines.append(f"_Showing the top {EXPORT_ROWS} of {len(strk)}._")
    for r in strk[:EXPORT_ROWS]:
        rec = ",".join(str(m["corners"]) for m in r["recent"])
        lines.append(f"| {r['name']} | {r['league_name']} | {r['line']}+ (5/5) | {r['avg']} | "
                     f"{r['streak']['length']} | {r['longest']['length']} | {rec} |")

    for subj, title, unit in (("team", "team corners", "won"), ("match", "match total corners", "total")):
        unders = await streaks(league_id="all", side="overall", window=5, min_hits=5,
                               threshold=None, min_line=3, within_days=None,
                               direction="under", subject=subj, user=user)
        lines.append(f"\n## Under streaks — {title} stayed under the line in all of last 5 games")
        lines.append(f"| Team | League | Line | Avg | Current | Longest | Recent ({unit}) |")
        lines.append("|---|---|---|---|---|---|---|")
        if len(unders) > EXPORT_ROWS:
            lines.append(f"_Showing the top {EXPORT_ROWS} of {len(unders)}._")
        for r in unders[:EXPORT_ROWS]:
            rec = ",".join(str(m["corners"]) for m in r["recent"])
            voids = f" ({r['voids']} void)" if r["voids"] else ""
            lines.append(f"| {r['name']} | {r['league_name']} | under {r['line']} ({r['hits']}/{r['settled']}{voids}) | "
                         f"{r['avg']} | {r['streak']['length']} | {r['longest']['length']} | {rec} |")

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


# Derived, never re-typed. This used to be a hand-copied duplicate of sync_real's
# LEAGUE_META, and the boot cleanup below DELETES any league not in this set — so a
# league added to the sync alone had its data wiped on every restart, silently.
from leagues_meta import LEAGUE_META, MANAGED_LEAGUE_IDS  # noqa: E402,F401


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
    # lock in the day's two picks shortly after the morning sync, while games are unplayed
    scheduler.add_job(_snapshot_daily_picks, CronTrigger(hour=7, minute=30),
                      id="daily_picks", replace_existing=True)
    # settle hourly — most fixtures finish well after the twice-daily sync
    scheduler.add_job(_run_settlement, CronTrigger(minute=20), id="settle", replace_existing=True)
    # warm the screen cache after each sync has had time to finish. This is only a
    # warm-up: a screen also rebuilds on read once its data_version no longer matches,
    # so a sync that overruns self-heals on the next request rather than serving stale.
    scheduler.add_job(_rebuild_screens, CronTrigger(hour="8,20", minute=15),
                      id="screens", replace_existing=True)
    scheduler.start()
    app.state.scheduler = scheduler
    logger.info("Auto-refresh scheduler started (07:00 & 19:00 UTC daily; Daily 2 lock-in 07:30 UTC)")


@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()
