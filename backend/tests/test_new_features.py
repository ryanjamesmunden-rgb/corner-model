"""Backend tests for session-3 features: 27 leagues, top-mismatches pairings, corner-table endpoint."""
import os
import pytest
import requests
from dotenv import dotenv_values

frontend_env = dotenv_values("/app/frontend/.env")
base_url = os.environ.get("REACT_APP_BACKEND_URL") or frontend_env.get("REACT_APP_BACKEND_URL")
if not base_url:
    raise RuntimeError("REACT_APP_BACKEND_URL missing")
BASE_URL = base_url.rstrip("/")
TOKEN = "qa-test-token-123"


@pytest.fixture(scope="module")
def client():
    s = requests.Session()
    s.headers.update({"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"})
    return s


# --- auth ---
def test_auth_me(client):
    r = client.get(f"{BASE_URL}/api/auth/me", timeout=60)
    assert r.status_code == 200, r.text[:300]
    assert r.json().get("user_id") == "qa-user-1"


def test_unauthenticated_blocked():
    r = requests.get(f"{BASE_URL}/api/leagues", timeout=60)
    assert r.status_code in (401, 403), f"expected 401/403 got {r.status_code}"


# --- leagues: expect 27 across 20 countries ---
def test_leagues_count(client):
    r = client.get(f"{BASE_URL}/api/leagues", timeout=60)
    assert r.status_code == 200, r.text[:300]
    leagues = r.json()
    assert isinstance(leagues, list)
    ids = [l["league_id"] for l in leagues]
    countries = {l["country"] for l in leagues}
    print(f"leagues={len(leagues)} countries={len(countries)}")
    print(sorted(ids))
    assert "_id" not in leagues[0]
    for expected in ["ger-bl", "ger-bl2", "usa-ml", "jpn-j1", "arg-lp", "sco-pl", "por-pl", "bel-pl", "tur-sl", "den-sl", "sui-sl", "aut-bl", "gre-sl"]:
        assert expected in ids, f"missing league {expected}"
    assert len(leagues) == 27, f"expected 27 leagues got {len(leagues)}: {sorted(ids)}"
    assert len(countries) == 20, f"expected 20 countries got {len(countries)}: {sorted(countries)}"


# --- corner-table endpoint ---
@pytest.mark.parametrize("lid", ["ger-bl", "ned-ed", "usa-ml", "jpn-j1"])
def test_corner_table(client, lid):
    r = client.get(f"{BASE_URL}/api/leagues/{lid}/corner-table", timeout=60)
    assert r.status_code == 200, r.text[:300]
    d = r.json()
    assert "teams" in d and "league_name" in d
    teams = d["teams"]
    assert len(teams) > 0, f"no teams for {lid}"
    for t in teams:
        assert "corners_won" in t and "shots" in t and "team_id" in t and "name" in t
        assert isinstance(t["corners_won"], (int, float))
        assert isinstance(t["shots"], (int, float))
        assert "_id" not in t
    cw = [t["corners_won"] for t in teams]
    assert cw == sorted(cw, reverse=True), f"{lid} not sorted desc by corners_won: {cw}"
    assert max(cw) > 0, f"{lid} all corners_won zero"
    assert max(t["shots"] for t in teams) > 0, f"{lid} all shots zero"
    print(f"{lid}: {d['league_name']} top={teams[0]['name']} cw={teams[0]['corners_won']} sh={teams[0]['shots']} n={len(teams)}")


def test_corner_table_all_leagues_nonempty(client):
    leagues = client.get(f"{BASE_URL}/api/leagues", timeout=60).json()
    empty, zero_shots = [], []
    for l in leagues:
        r = client.get(f"{BASE_URL}/api/leagues/{l['league_id']}/corner-table", timeout=60)
        assert r.status_code == 200, f"{l['league_id']} -> {r.status_code}"
        teams = r.json().get("teams", [])
        if not teams:
            empty.append(l["league_id"])
        elif max(t["shots"] for t in teams) == 0:
            zero_shots.append(l["league_id"])
    print(f"empty={empty} zero_shots={zero_shots}")
    assert not empty, f"leagues with empty corner table: {empty}"
    assert not zero_shots, f"leagues with all-zero shots: {zero_shots}"


def test_corner_table_bad_league(client):
    r = client.get(f"{BASE_URL}/api/leagues/does-not-exist/corner-table", timeout=60)
    assert r.status_code in (200, 404), r.status_code
    if r.status_code == 200:
        assert r.json().get("teams") == []


# --- top mismatches (Quick Scan source) ---
@pytest.mark.parametrize("days", [3, 7, 14])
def test_top_mismatches(client, days):
    r = client.get(f"{BASE_URL}/api/top-mismatches", params={"within_days": days, "limit": 30}, timeout=90)
    assert r.status_code == 200, r.text[:300]
    rows = r.json()
    assert isinstance(rows, list)
    print(f"within_days={days} rows={len(rows)}")
    if days == 14:
        assert len(rows) > 0, "no mismatch rows within 14 days"
    for row in rows:
        for k in ["team_id", "name", "league_name", "team_for", "opp_conceded", "lambda", "line", "fair_odds", "prob", "next_fixture"]:
            assert k in row, f"missing {k} in {row}"
        nf = row["next_fixture"]
        assert nf and nf.get("fixture_id") and nf.get("opponent") and nf.get("date") is not None
        assert "is_home" in nf and "round" in nf
    lam = [r_["lambda"] for r_ in rows]
    assert lam == sorted(lam, reverse=True), "not sorted by lambda desc"


def test_top_mismatches_no_window(client):
    r = client.get(f"{BASE_URL}/api/top-mismatches", params={"limit": 30}, timeout=90)
    assert r.status_code == 200, r.text[:300]
    assert len(r.json()) > 0
