"""Backend tests for The Corner Model 2.0."""
import os
import time
import pytest
import requests
from pymongo import MongoClient
from datetime import datetime, timezone, timedelta

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    # fallback: read frontend .env
    with open("/app/frontend/.env") as f:
        for line in f:
            if line.startswith("REACT_APP_BACKEND_URL="):
                BASE_URL = line.split("=", 1)[1].strip().rstrip("/")
API = f"{BASE_URL}/api"

MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "test_database")


@pytest.fixture(scope="session")
def session_token():
    mc = MongoClient(MONGO_URL)
    db = mc[DB_NAME]
    uid = f"test-user-{int(time.time()*1000)}"
    tok = f"test_session_{int(time.time()*1000)}"
    db.users.insert_one({"user_id": uid, "email": f"t{int(time.time()*1000)}@ex.com",
                         "name": "Tester", "picture": "", "created_at": datetime.now(timezone.utc)})
    db.user_sessions.insert_one({"user_id": uid, "session_token": tok,
                                 "expires_at": (datetime.now(timezone.utc) + timedelta(days=7)).isoformat(),
                                 "created_at": datetime.now(timezone.utc).isoformat()})
    yield tok
    db.user_sessions.delete_one({"session_token": tok})
    db.users.delete_one({"user_id": uid})


@pytest.fixture
def auth(session_token):
    s = requests.Session()
    s.headers.update({"Authorization": f"Bearer {session_token}", "Content-Type": "application/json"})
    return s


# --- Auth ---
class TestAuth:
    def test_me_no_token(self):
        r = requests.get(f"{API}/auth/me")
        assert r.status_code == 401

    def test_me_with_token(self, auth):
        r = auth.get(f"{API}/auth/me")
        assert r.status_code == 200
        d = r.json()
        assert "user_id" in d and "email" in d

    def test_protected_requires_auth(self):
        assert requests.get(f"{API}/leagues").status_code == 401
        assert requests.get(f"{API}/scanner").status_code == 401


# --- Leagues ---
class TestLeagues:
    def test_seven_leagues(self, auth):
        r = auth.get(f"{API}/leagues")
        assert r.status_code == 200
        d = r.json()
        assert len(d) == 7
        ids = {l["league_id"] for l in d}
        assert "eng-pl" in ids

    def test_teams_default(self, auth):
        r = auth.get(f"{API}/leagues/eng-pl/teams")
        assert r.status_code == 200
        d = r.json()
        assert len(d) == 10
        row = d[0]
        for k in ("for_avg", "against_avg", "total_avg"):
            assert k in row

    def test_teams_splits_windows_differ(self, auth):
        a = auth.get(f"{API}/leagues/eng-pl/teams?split=overall&window=10").json()
        b = auth.get(f"{API}/leagues/eng-pl/teams?split=home&window=3").json()
        # find same team in both, verify numbers differ (very likely)
        am = {t["team_id"]: t for t in a}
        differ = False
        for t in b:
            if t["team_id"] in am and t["total_avg"] != am[t["team_id"]]["total_avg"]:
                differ = True
                break
        assert differ, "splits/windows should change numbers"


# --- Fixtures ---
class TestFixtures:
    def test_league_fixtures(self, auth):
        r = auth.get(f"{API}/leagues/eng-pl/fixtures")
        assert r.status_code == 200
        d = r.json()
        assert len(d) > 0
        fx = d[0]
        assert "lambdas" in fx and "confidence" in fx and "has_odds" in fx
        assert "best_bet" in fx

    def test_fixture_detail(self, auth):
        fx_list = auth.get(f"{API}/leagues/eng-pl/fixtures").json()
        fid = fx_list[0]["fixture_id"]
        r = auth.get(f"{API}/fixtures/{fid}")
        assert r.status_code == 200
        d = r.json()
        assert "model" in d and "home_team" in d and "away_team" in d
        assert "lambdas" in d["model"] and "markets" in d["model"]
        splits = d["home_team"]["splits"]
        assert set(splits.keys()) == {"home", "away", "overall"}
        for sp in splits.values():
            assert set(sp.keys()) == {"3", "5", "10", "0"}


# --- Odds and EV ---
class TestOdds:
    def test_odds_merge_and_ev(self, auth):
        fx_list = auth.get(f"{API}/leagues/eng-pl/fixtures").json()
        fid = fx_list[0]["fixture_id"]
        # Get fair odds from model
        detail = auth.get(f"{API}/fixtures/{fid}").json()
        total_market = [m for m in detail["model"]["markets"] if m["key"] == "total_over_9.5"][0]
        fair = total_market["fair_odds"]
        # book higher => positive EV
        book_high = round(fair * 1.10, 2)
        r = auth.post(f"{API}/fixtures/{fid}/odds", json={"odds": {"total_over_9.5": book_high}})
        assert r.status_code == 200
        d = r.json()
        m = [m for m in d["model"]["markets"] if m["key"] == "total_over_9.5"][0]
        assert m["book_odds"] == book_high
        # EV% = book*prob - 1
        expected_ev = round((book_high * (m["prob"] / 100.0) - 1.0) * 100.0, 2)
        assert abs(m["ev"] - expected_ev) < 0.5, f"got {m['ev']} expected ~{expected_ev}"
        assert m["ev"] > 0

    def test_ev_tier_strong(self, auth):
        fx_list = auth.get(f"{API}/leagues/eng-pl/fixtures").json()
        fid = fx_list[1]["fixture_id"]
        detail = auth.get(f"{API}/fixtures/{fid}").json()
        m0 = [m for m in detail["model"]["markets"] if m["key"] == "total_over_9.5"][0]
        big = round(m0["fair_odds"] * 1.25, 2)  # ~+25% -> EV > 5 => strong
        r = auth.post(f"{API}/fixtures/{fid}/odds", json={"odds": {"total_over_9.5": big}})
        m = [m for m in r.json()["model"]["markets"] if m["key"] == "total_over_9.5"][0]
        assert m["ev"] >= 5.0
        assert m["tier"] == "strong"


# --- Scanner ---
class TestScanner:
    def test_scanner_sorted(self, auth):
        r = auth.get(f"{API}/scanner?league_id=all&min_edge=-100")
        assert r.status_code == 200
        d = r.json()
        assert len(d) > 0
        evs = [x["ev"] for x in d]
        assert evs == sorted(evs, reverse=True)

    def test_scanner_min_edge(self, auth):
        d = auth.get(f"{API}/scanner?league_id=all&min_edge=5").json()
        assert all(x["ev"] >= 5 for x in d)

    def test_scanner_market_filter(self, auth):
        d = auth.get(f"{API}/scanner?league_id=all&market=total&min_edge=-100").json()
        assert all(x["group"] == "total" for x in d)

    def test_scanner_league_filter(self, auth):
        d = auth.get(f"{API}/scanner?league_id=eng-pl&min_edge=-100").json()
        assert all(x["league_id"] == "eng-pl" for x in d)
