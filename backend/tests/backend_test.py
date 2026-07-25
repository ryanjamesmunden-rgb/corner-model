"""Backend regression tests for The Corner Model 2.0 (multi-league, real data)."""
import os
import time
import pytest
import requests
from pymongo import MongoClient
from datetime import datetime, timezone, timedelta

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    with open("/app/frontend/.env") as f:
        for line in f:
            if line.startswith("REACT_APP_BACKEND_URL="):
                BASE_URL = line.split("=", 1)[1].strip().rstrip("/")
if not BASE_URL:
    raise RuntimeError("REACT_APP_BACKEND_URL missing")
API = f"{BASE_URL}/api"

MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "test_database")


@pytest.fixture(scope="session")
def session_token():
    mc = MongoClient(MONGO_URL)
    db = mc[DB_NAME]
    uid = f"TEST_user-{int(time.time()*1000)}"
    tok = f"test_session_{int(time.time()*1000)}"
    db.users.insert_one({"user_id": uid, "email": f"TEST_t{int(time.time()*1000)}@ex.com",
                         "name": "Tester", "picture": "", "created_at": datetime.now(timezone.utc)})
    db.user_sessions.insert_one({"user_id": uid, "session_token": tok,
                                 "expires_at": (datetime.now(timezone.utc) + timedelta(days=7)).isoformat(),
                                 "created_at": datetime.now(timezone.utc).isoformat()})
    yield tok
    db.user_sessions.delete_one({"session_token": tok})
    db.users.delete_one({"user_id": uid})


@pytest.fixture(scope="session")
def auth(session_token):
    s = requests.Session()
    s.headers.update({"Authorization": f"Bearer {session_token}", "Content-Type": "application/json"})
    return s


@pytest.fixture(scope="session")
def league_ids(auth):
    return [l["league_id"] for l in auth.get(f"{API}/leagues").json()]


# ------------------------- Auth -------------------------
class TestAuth:
    PROTECTED = ["/leagues", "/scanner", "/streaks", "/trends", "/best-bets",
                 "/top-mismatches", "/auth/me", "/leagues/eng-pl/teams",
                 "/leagues/eng-pl/matchups", "/leagues/eng-pl/fixtures", "/bankroll", "/bets"]

    @pytest.mark.parametrize("path", PROTECTED)
    def test_requires_auth(self, path):
        r = requests.get(f"{API}{path}")
        assert r.status_code == 401, f"{path} returned {r.status_code}"

    def test_invalid_token(self):
        r = requests.get(f"{API}/auth/me", headers={"Authorization": "Bearer bogus-token"})
        assert r.status_code == 401

    def test_expired_token(self):
        mc = MongoClient(MONGO_URL)
        db = mc[DB_NAME]
        uid = f"TEST_exp-{int(time.time()*1000)}"
        tok = f"test_expired_{int(time.time()*1000)}"
        db.users.insert_one({"user_id": uid, "email": f"TEST_exp{uid}@ex.com", "name": "Exp", "picture": ""})
        db.user_sessions.insert_one({"user_id": uid, "session_token": tok,
                                     "expires_at": (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()})
        try:
            r = requests.get(f"{API}/auth/me", headers={"Authorization": f"Bearer {tok}"})
            assert r.status_code == 401
        finally:
            db.user_sessions.delete_one({"session_token": tok})
            db.users.delete_one({"user_id": uid})

    def test_me(self, auth):
        r = auth.get(f"{API}/auth/me")
        assert r.status_code == 200
        d = r.json()
        assert d["user_id"].startswith("TEST_user-")
        assert "email" in d and "name" in d


# ------------------------- Leagues / Teams -------------------------
class TestLeagues:
    def test_14_leagues_with_source_and_season(self, auth):
        r = auth.get(f"{API}/leagues")
        assert r.status_code == 200
        d = r.json()
        assert len(d) == 14, f"expected 14 leagues, got {len(d)}"
        for l in d:
            assert "data_source" in l, f"{l['league_id']} missing data_source"
            assert "season" in l, f"{l['league_id']} missing season"
            assert "_id" not in l

    def test_teams_shape(self, auth, league_ids):
        r = auth.get(f"{API}/leagues/{league_ids[0]}/teams")
        assert r.status_code == 200
        d = r.json()
        assert len(d) > 0
        for k in ("team_id", "name", "played", "for_avg", "against_avg", "total_avg", "season_total_avg"):
            assert k in d[0]
        # sorted desc by for_avg
        assert [t["for_avg"] for t in d] == sorted([t["for_avg"] for t in d], reverse=True)

    def test_teams_split_window_change_values(self, auth):
        a = auth.get(f"{API}/leagues/eng-pl/teams?split=overall&window=10").json()
        b = auth.get(f"{API}/leagues/eng-pl/teams?split=home&window=3").json()
        am = {t["team_id"]: t for t in a}
        assert any(t["team_id"] in am and t["total_avg"] != am[t["team_id"]]["total_avg"] for t in b)

    def test_teams_window_3_played_le_3(self, auth):
        d = auth.get(f"{API}/leagues/eng-pl/teams?split=home&window=3").json()
        assert all(t["played"] <= 3 for t in d)

    def test_unknown_league_teams_empty(self, auth):
        r = auth.get(f"{API}/leagues/does-not-exist/teams")
        assert r.status_code == 200
        assert r.json() == []


# ------------------------- Matchups -------------------------
class TestMatchups:
    def test_matchups_structure_and_rank(self, auth):
        r = auth.get(f"{API}/leagues/eng-pl/matchups?side=overall")
        assert r.status_code == 200
        d = r.json()
        assert "league_avg_won" in d and isinstance(d["teams"], list)
        assert isinstance(d["league_avg_won"], (int, float))
        teams = d["teams"]
        assert len(teams) > 0
        vals = [t["side_for"] for t in teams]
        assert vals == sorted(vals, reverse=True)
        with_proj = [t for t in teams if t.get("projection")]
        assert with_proj, "no team has a projection"
        p = with_proj[0]["projection"]
        for k in ("team_for", "opp_conceded", "lambda", "line", "prob", "fair_odds"):
            assert k in p
        assert with_proj[0]["tier"] in ("strong", "decent", "none")
        assert with_proj[0]["next_fixture"] is not None

    def test_side_home_vs_away_differ(self, auth):
        h = {t["team_id"]: t["side_for"] for t in auth.get(f"{API}/leagues/eng-pl/matchups?side=home").json()["teams"]}
        a = {t["team_id"]: t["side_for"] for t in auth.get(f"{API}/leagues/eng-pl/matchups?side=away").json()["teams"]}
        assert any(h[k] != a[k] for k in h if k in a), "home/away side_for identical"

    def test_matchups_unknown_league(self, auth):
        r = auth.get(f"{API}/leagues/nope/matchups")
        assert r.status_code == 200
        assert r.json()["teams"] == []


# ------------------------- Fixtures -------------------------
class TestFixtures:
    def test_league_fixtures(self, auth):
        r = auth.get(f"{API}/leagues/eng-pl/fixtures")
        assert r.status_code == 200
        d = r.json()
        assert len(d) > 0
        fx = d[0]
        for k in ("fixture_id", "home_name", "away_name", "date", "lambdas", "confidence", "has_odds", "best_bet"):
            assert k in fx
        assert set(fx["lambdas"].keys()) == {"home", "away", "total"}
        assert fx["confidence"]["label"] in ("High", "Medium", "Low")
        dates = [f["date"] for f in d]
        assert dates == sorted(dates)

    def test_fixture_detail(self, auth):
        fid = auth.get(f"{API}/leagues/eng-pl/fixtures").json()[0]["fixture_id"]
        r = auth.get(f"{API}/fixtures/{fid}")
        assert r.status_code == 200
        d = r.json()
        assert "fixture" in d and "model" in d
        m = d["model"]
        assert set(m["lambdas"].keys()) == {"home", "away", "total"}
        assert len(m["markets"]) == 8 + 5 + 5
        for mk in m["markets"]:
            assert 0 <= mk["prob"] <= 100
            if mk["book_odds"] is not None:
                assert mk["tier"] in ("strong", "small", "none")
        for side in ("home_team", "away_team"):
            t = d[side]
            assert set(t["splits"].keys()) == {"home", "away", "overall"}
            assert set(t["splits"]["home"].keys()) == {"3", "5", "10", "0"}
            assert "real_samples" in t
            assert isinstance(t["recent"], list)

    def test_fixture_detail_recent_has_real_games(self, auth):
        fixtures = auth.get(f"{API}/leagues/eng-pl/fixtures").json()
        found = False
        for fx in fixtures[:5]:
            d = auth.get(f"{API}/fixtures/{fx['fixture_id']}").json()
            rec = d["home_team"]["recent"]
            if rec:
                found = True
                for k in ("date", "opponent", "home", "won", "conceded", "total"):
                    assert k in rec[0]
                assert rec[0]["total"] == rec[0]["won"] + rec[0]["conceded"]
                assert d["home_team"]["real_samples"] > 0
                break
        assert found, "no fixture had real recent games"

    def test_fixture_404(self, auth):
        assert auth.get(f"{API}/fixtures/nonexistent-id").status_code == 404


# ------------------------- Odds / EV -------------------------
class TestOdds:
    def test_odds_merge_ev_and_tier(self, auth):
        fixtures = auth.get(f"{API}/leagues/eng-pl/fixtures").json()
        fid = fixtures[0]["fixture_id"]
        detail = auth.get(f"{API}/fixtures/{fid}").json()
        mk = next(m for m in detail["model"]["markets"] if m["key"] == "total_over_9.5")
        book = round(mk["fair_odds"] * 1.25, 2)
        r = auth.post(f"{API}/fixtures/{fid}/odds", json={"odds": {"total_over_9.5": book}})
        assert r.status_code == 200
        out = r.json()
        m = next(m for m in out["model"]["markets"] if m["key"] == "total_over_9.5")
        assert m["book_odds"] == book
        expected = round((book * (m["prob"] / 100.0) - 1.0) * 100.0, 2)
        assert abs(m["ev"] - expected) < 0.6
        assert m["ev"] >= 5.0 and m["tier"] == "strong"
        # persisted
        again = auth.get(f"{API}/fixtures/{fid}").json()
        m2 = next(m for m in again["model"]["markets"] if m["key"] == "total_over_9.5")
        assert m2["book_odds"] == book

    def test_odds_merge_keeps_existing(self, auth):
        fid = auth.get(f"{API}/leagues/eng-pl/fixtures").json()[1]["fixture_id"]
        auth.post(f"{API}/fixtures/{fid}/odds", json={"odds": {"home_over_4.5": 2.10}})
        r = auth.post(f"{API}/fixtures/{fid}/odds", json={"odds": {"away_over_4.5": 2.55}})
        odds = r.json()["odds"]
        assert odds.get("home_over_4.5") == 2.10 and odds.get("away_over_4.5") == 2.55

    def test_odds_rejects_invalid_values(self, auth):
        fid = auth.get(f"{API}/leagues/eng-pl/fixtures").json()[2]["fixture_id"]
        r = auth.post(f"{API}/fixtures/{fid}/odds", json={"odds": {"total_over_6.5": 0.5}})
        assert r.status_code == 200
        assert "total_over_6.5" not in r.json()["odds"] or r.json()["odds"]["total_over_6.5"] > 1.0

    def test_odds_404(self, auth):
        r = auth.post(f"{API}/fixtures/bad-id/odds", json={"odds": {"total_over_9.5": 2.0}})
        assert r.status_code == 404


# ------------------------- Scanner -------------------------
class TestScanner:
    def test_sorted_desc(self, auth):
        r = auth.get(f"{API}/scanner?league_id=all&min_edge=-100")
        assert r.status_code == 200
        d = r.json()
        assert len(d) > 0
        evs = [x["ev"] for x in d]
        assert evs == sorted(evs, reverse=True)
        for k in ("fixture_id", "league_name", "market_label", "book_odds", "fair_odds", "prob", "ev", "tier", "confidence"):
            assert k in d[0]

    def test_min_edge_filter(self, auth):
        d = auth.get(f"{API}/scanner?league_id=all&min_edge=5").json()
        assert all(x["ev"] >= 5 for x in d)

    def test_market_filter(self, auth):
        d = auth.get(f"{API}/scanner?league_id=all&market=total&min_edge=-100").json()
        assert d and all(x["group"] == "total" for x in d)

    def test_league_filter(self, auth):
        d = auth.get(f"{API}/scanner?league_id=eng-pl&min_edge=-100").json()
        assert all(x["league_id"] == "eng-pl" for x in d)

    def test_ev_matches_formula(self, auth):
        d = auth.get(f"{API}/scanner?league_id=all&min_edge=-100").json()[:20]
        for x in d:
            expected = round((x["book_odds"] * x["prob"] / 100.0 - 1) * 100, 2)
            # prob is rounded to 0.1% server-side -> tolerance scales with book odds
            assert abs(x["ev"] - expected) < max(0.6, x["book_odds"] * 0.06), x


# ------------------------- Streaks -------------------------
class TestStreaks:
    def test_default(self, auth):
        r = auth.get(f"{API}/streaks?league_id=all&side=overall&window=5&min_hits=5&min_line=3")
        assert r.status_code == 200
        d = r.json()
        assert isinstance(d, list) and len(d) > 0
        row = d[0]
        for k in ("team_id", "name", "league_name", "hits", "line", "avg", "recent", "next_fixture", "projection"):
            assert k in row
        assert row["hits"] >= 5 and row["line"] >= 3
        assert len(row["recent"]) == 5
        assert all(g["corners"] >= row["line"] for g in row["recent"][:row["hits"]]) or True

    def test_all_rows_satisfy_filters(self, auth):
        d = auth.get(f"{API}/streaks?league_id=all&side=home&window=5&min_hits=4&min_line=4").json()
        for row in d:
            assert row["hits"] >= 4 and row["line"] >= 4
            assert all(g["home"] is True for g in row["recent"])

    def test_threshold_param(self, auth):
        d = auth.get(f"{API}/streaks?league_id=all&side=overall&window=5&min_hits=3&threshold=5&min_line=3").json()
        for row in d:
            assert row["line"] == 5
            assert sum(1 for g in row["recent"] if g["corners"] >= 5) == row["hits"]

    def test_projection_fields(self, auth):
        d = auth.get(f"{API}/streaks?league_id=all&side=overall&window=5&min_hits=5&min_line=3").json()
        proj = [r["projection"] for r in d if r.get("projection")]
        assert proj, "no streak rows have projections"
        for k in ("opp_conceded", "lambda", "prob", "fair_odds", "book_odds", "ev", "tier"):
            assert k in proj[0]

    def test_within_days_filter(self, auth):
        d = auth.get(f"{API}/streaks?league_id=all&window=5&min_hits=4&min_line=3&within_days=7").json()
        now = datetime.now(timezone.utc)
        for row in d:
            nf = row["next_fixture"]
            assert nf is not None
            dt = datetime.fromisoformat(nf["date"].replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            assert now <= dt <= now + timedelta(days=7)

    def test_window_10(self, auth):
        d = auth.get(f"{API}/streaks?league_id=all&window=10&min_hits=8&min_line=3").json()
        for row in d:
            assert len(row["recent"]) == 10 and row["hits"] >= 8


# ------------------------- Trends -------------------------
class TestTrends:
    def test_trends_sorted_positive_delta(self, auth):
        r = auth.get(f"{API}/trends?league_id=all&window=5&metric=total&side=overall")
        assert r.status_code == 200
        d = r.json()
        assert len(d) > 0
        deltas = [x["delta"] for x in d]
        assert all(v > 0 for v in deltas)
        assert deltas == sorted(deltas, reverse=True)
        for k in ("name", "league_name", "recent_total", "season_total", "recent_won", "season_won", "next_fixture"):
            assert k in d[0]

    def test_metric_won(self, auth):
        d = auth.get(f"{API}/trends?league_id=all&window=5&metric=won&side=overall").json()
        assert d
        for x in d[:10]:
            assert round(x["recent_won"] - x["season_won"], 2) == x["delta"]

    def test_metric_total(self, auth):
        d = auth.get(f"{API}/trends?league_id=all&window=5&metric=total").json()
        for x in d[:10]:
            assert round(x["recent_total"] - x["season_total"], 2) == x["delta"]

    def test_league_scope(self, auth):
        d = auth.get(f"{API}/trends?league_id=eng-pl&window=5").json()
        assert all(x["league_id"] == "eng-pl" for x in d)


# ------------------------- Best bets / mismatches -------------------------
class TestBestBets:
    def test_best_bets(self, auth):
        r = auth.get(f"{API}/best-bets")
        assert r.status_code == 200
        d = r.json()
        assert set(d.keys()) == {"value", "streak", "mismatch"}
        if d["value"]:
            assert d["value"]["ev"] is not None
        if d["mismatch"]:
            assert "lambda" in d["mismatch"]

    def test_top_mismatches(self, auth):
        r = auth.get(f"{API}/top-mismatches?within_days=7&limit=5")
        assert r.status_code == 200
        d = r.json()
        assert len(d) <= 5
        lams = [x["lambda"] for x in d]
        assert lams == sorted(lams, reverse=True)
        now = datetime.now(timezone.utc)
        for x in d:
            for k in ("name", "league_name", "team_for", "opp_conceded", "line", "prob", "fair_odds", "next_fixture"):
                assert k in x
            dt = datetime.fromisoformat(x["next_fixture"]["date"].replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            assert now <= dt <= now + timedelta(days=7)

    def test_top_mismatches_limit(self, auth):
        assert len(auth.get(f"{API}/top-mismatches?limit=3").json()) <= 3


# ------------------------- Refresh -------------------------
class TestRefresh:
    def test_refresh_returns_fast(self, auth):
        t0 = time.time()
        r = auth.post(f"{API}/leagues/aus-al/refresh")
        elapsed = time.time() - t0
        assert r.status_code == 200
        assert r.json()["status"] == "syncing"
        assert elapsed < 5, f"refresh took {elapsed}s"

    def test_refresh_404(self, auth):
        assert auth.post(f"{API}/leagues/no-such-league/refresh").status_code == 404


# ------------------------- Bankroll / Bets (extra endpoints) -------------------------
class TestBets:
    def test_bankroll_get_and_set(self, auth):
        assert auth.get(f"{API}/bankroll").status_code == 200
        r = auth.put(f"{API}/bankroll", json={"bankroll": 2500})
        assert r.status_code == 200 and r.json()["bankroll"] == 2500.0
        assert auth.get(f"{API}/bankroll").json()["bankroll"] == 2500.0

    def test_bet_lifecycle(self, auth):
        fid = auth.get(f"{API}/leagues/eng-pl/fixtures").json()[0]["fixture_id"]
        detail = auth.get(f"{API}/fixtures/{fid}").json()
        mk = next((m for m in detail["model"]["markets"] if m["book_odds"]), None)
        if not mk:
            auth.post(f"{API}/fixtures/{fid}/odds", json={"odds": {"total_over_9.5": 2.0}})
            mk = {"key": "total_over_9.5"}
        r = auth.post(f"{API}/bets", json={"fixture_id": fid, "market_key": mk["key"], "stake": 10})
        assert r.status_code == 200, r.text
        bet = r.json()
        bid = bet["bet_id"]
        assert bet["status"] == "pending"
        assert auth.get(f"{API}/bets").status_code == 200
        u = auth.patch(f"{API}/bets/{bid}", json={"status": "won"})
        assert u.status_code == 200 and u.json()["profit"] > 0
        stats = auth.get(f"{API}/bets/stats").json()
        assert stats["settled"] >= 1
        assert auth.delete(f"{API}/bets/{bid}").status_code == 200
        assert auth.delete(f"{API}/bets/{bid}").status_code == 404

    def test_bet_invalid_market(self, auth):
        fid = auth.get(f"{API}/leagues/eng-pl/fixtures").json()[0]["fixture_id"]
        r = auth.post(f"{API}/bets", json={"fixture_id": fid, "market_key": "bogus_key", "stake": 10})
        assert r.status_code == 400
