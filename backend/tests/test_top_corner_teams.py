"""Tests for /api/top-corner-teams (new) + regressions: chase-board, best-bets, picks."""
import os
import pytest
import requests
from dotenv import dotenv_values

frontend_env = dotenv_values("/app/frontend/.env")
base_url = os.environ.get("REACT_APP_BACKEND_URL") or frontend_env.get("REACT_APP_BACKEND_URL")
if not base_url:
    raise RuntimeError("REACT_APP_BACKEND_URL missing")
BASE_URL = base_url.rstrip("/")
API = f"{BASE_URL}/api"
TOKEN = "qa-test-token-123"


@pytest.fixture(scope="module")
def client():
    s = requests.Session()
    s.headers.update({"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"})
    return s


# --- top-corner-teams ---
class TestTopCornerTeams:
    def test_requires_auth(self):
        r = requests.get(f"{API}/top-corner-teams", timeout=30)
        assert r.status_code in (401, 403), r.text

    def test_default_shape_and_sorting(self, client):
        r = client.get(f"{API}/top-corner-teams", params={"side": "overall", "window": 0, "limit": 40}, timeout=60)
        assert r.status_code == 200, r.text
        data = r.json()
        assert isinstance(data, list)
        assert 0 < len(data) <= 40
        keys = {"team_id", "name", "league_name", "side", "window", "games",
                "won_avg", "conceded_avg", "total_avg", "real_samples", "next_fixture"}
        for it in data:
            assert keys.issubset(it.keys()), set(keys) - set(it.keys())
            assert "_id" not in it
            assert it["games"] >= 3
            assert it["side"] == "overall"
            assert it["window"] == 0
            assert isinstance(it["won_avg"], (int, float))
            assert isinstance(it["name"], str) and it["name"]
            if it["next_fixture"] is not None:
                assert "fixture_id" in it["next_fixture"]
                assert "opponent" in it["next_fixture"]
                assert "date" in it["next_fixture"]
                assert "is_home" in it["next_fixture"]
        avgs = [x["won_avg"] for x in data]
        assert avgs == sorted(avgs, reverse=True), avgs

    @pytest.mark.parametrize("side", ["home", "away", "overall"])
    def test_sides(self, client, side):
        r = client.get(f"{API}/top-corner-teams", params={"side": side, "window": 0, "limit": 10}, timeout=60)
        assert r.status_code == 200, r.text
        data = r.json()
        assert all(x["side"] == side for x in data)
        avgs = [x["won_avg"] for x in data]
        assert avgs == sorted(avgs, reverse=True)

    @pytest.mark.parametrize("window", [0, 5, 10])
    def test_windows(self, client, window):
        r = client.get(f"{API}/top-corner-teams", params={"side": "overall", "window": window, "limit": 10}, timeout=60)
        assert r.status_code == 200, r.text
        data = r.json()
        assert all(x["window"] == window for x in data)
        if window:
            assert all(x["games"] <= window for x in data), [x["games"] for x in data]

    def test_side_changes_ordering(self, client):
        h = client.get(f"{API}/top-corner-teams", params={"side": "home", "limit": 20}, timeout=60).json()
        a = client.get(f"{API}/top-corner-teams", params={"side": "away", "limit": 20}, timeout=60).json()
        assert [x["team_id"] for x in h] != [x["team_id"] for x in a]

    def test_league_filter_narrows(self, client):
        all_r = client.get(f"{API}/top-corner-teams", params={"league_id": "all", "limit": 40}, timeout=60).json()
        assert all_r
        lid = all_r[0]["league_id"] if "league_id" in all_r[0] else None
        leagues = client.get(f"{API}/leagues", timeout=60).json()
        target = lid or leagues[0]["league_id"]
        one = client.get(f"{API}/top-corner-teams", params={"league_id": target, "limit": 40}, timeout=60).json()
        assert one
        assert len(one) <= len(all_r)
        assert all(x.get("league_id") == target for x in one)

    def test_limit_respected(self, client):
        r = client.get(f"{API}/top-corner-teams", params={"limit": 5}, timeout=60)
        assert r.status_code == 200
        assert len(r.json()) <= 5


# --- regressions ---
class TestRegressions:
    def test_chase_board(self, client):
        r = client.get(f"{API}/chase-board", params={"league_id": "all", "within_days": 7, "limit": 25}, timeout=60)
        assert r.status_code == 200, r.text
        payload = r.json()
        assert isinstance(payload, dict) and "board" in payload
        data = payload["board"]
        assert isinstance(data, list) and len(data) == 25
        assert payload.get("count") == 25
        for it in data:
            assert "_id" not in it
            assert it.get("opp_fh_rate") is not None
        scores = [it.get("chase_score", it.get("score")) for it in data]
        assert all(s is not None for s in scores)
        assert scores == sorted(scores, reverse=True), scores

    def test_best_bets(self, client):
        r = client.get(f"{API}/best-bets", timeout=60)
        assert r.status_code == 200, r.text
        d = r.json()
        assert set(["chase", "streak", "mismatch"]).issubset(d.keys())
        assert d["chase"] is not None

    def test_picks_record(self, client):
        r = client.get(f"{API}/picks", timeout=60)
        assert r.status_code == 200, r.text
        d = r.json()
        rec = d.get("record") if isinstance(d, dict) else None
        assert rec is not None, d
        for k in ("won", "lost", "pending", "win_rate"):
            assert k in rec, rec
        picks = d.get("picks")
        assert isinstance(picks, list) and len(picks) >= 7, picks
        assert rec["won"] + rec["lost"] + rec["pending"] == rec.get("total", len(picks))
        assert isinstance(rec["win_rate"], (int, float))

    def test_streaks(self, client):
        r = client.get(f"{API}/streaks", params={"league_id": "all", "side": "overall", "window": 5, "min_hits": 5}, timeout=60)
        assert r.status_code == 200, r.text
        assert isinstance(r.json(), list)

    def test_trends(self, client):
        r = client.get(f"{API}/trends", timeout=60)
        assert r.status_code == 200, r.text
        assert isinstance(r.json(), list)
