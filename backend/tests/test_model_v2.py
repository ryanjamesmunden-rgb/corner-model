"""Backend tests for session-4: model v2 (NB dispersion + shots/form) and /api/backtest v1-vs-v2."""
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


def _avg_gap(d):
    ls = d["lines"]
    return sum(l["calibration_gap"] for l in ls) / len(ls)


# --- /api/backtest ---
@pytest.mark.parametrize("model", ["v1", "v2"])
def test_backtest_contract(client, model):
    r = client.get(f"{BASE_URL}/api/backtest", params={"league_id": "all", "model": model}, timeout=180)
    assert r.status_code == 200, r.text[:300]
    d = r.json()
    assert d["model"] == model
    assert isinstance(d["overall_brier"], float) and 0 < d["overall_brier"] < 1
    assert isinstance(d["lines"], list) and len(d["lines"]) > 0
    assert d["matches"] > 0 and d["predictions"] > 0
    for l in d["lines"]:
        for k in ["line", "n", "model_prob", "actual_hit_rate", "calibration_gap", "brier"]:
            assert k in l, f"missing {k}"
        assert l["n"] > 0
        assert 0 <= l["model_prob"] <= 100 and 0 <= l["actual_hit_rate"] <= 100
    print(f"{model}: brier={d['overall_brier']} avg_gap={_avg_gap(d):.2f} lines={[l['line'] for l in d['lines']]}")


def test_backtest_v2_better_than_v1(client):
    v1 = client.get(f"{BASE_URL}/api/backtest", params={"league_id": "all", "model": "v1"}, timeout=180).json()
    v2 = client.get(f"{BASE_URL}/api/backtest", params={"league_id": "all", "model": "v2"}, timeout=180).json()
    g1, g2 = _avg_gap(v1), _avg_gap(v2)
    print(f"v1 brier={v1['overall_brier']} gap={g1:.2f} | v2 brier={v2['overall_brier']} gap={g2:.2f}")
    assert v2["overall_brier"] <= v1["overall_brier"], f"v2 brier {v2['overall_brier']} > v1 {v1['overall_brier']}"
    assert g2 < g1, f"v2 avg gap {g2:.2f} not lower than v1 {g1:.2f}"
    # same actual hit rates / samples (model change must not alter ground truth)
    a1 = {l["line"]: (l["n"], l["actual_hit_rate"]) for l in v1["lines"]}
    a2 = {l["line"]: (l["n"], l["actual_hit_rate"]) for l in v2["lines"]}
    assert a1 == a2, f"ground truth differs: {a1} vs {a2}"


def test_backtest_single_league(client):
    r = client.get(f"{BASE_URL}/api/backtest", params={"league_id": "eng-pl", "model": "v2"}, timeout=180)
    assert r.status_code == 200, r.text[:300]
    d = r.json()
    assert d["league_id"] == "eng-pl"
    assert isinstance(d["lines"], list)
    print(f"eng-pl v2: matches={d['matches']} brier={d['overall_brier']} lines={len(d['lines'])}")


def test_backtest_unknown_league_graceful(client):
    r = client.get(f"{BASE_URL}/api/backtest", params={"league_id": "does-not-exist", "model": "v2"}, timeout=120)
    assert r.status_code == 200, r.text[:300]
    d = r.json()
    assert d["lines"] == [] and d["overall_brier"] is None


def test_backtest_requires_auth():
    r = requests.get(f"{BASE_URL}/api/backtest", params={"league_id": "all"}, timeout=120)
    assert r.status_code in (401, 403), r.status_code


# --- regression: surfaces that now consume v2 ---
def test_scanner(client):
    r = client.get(f"{BASE_URL}/api/scanner", params={"league_id": "all", "min_edge": 0}, timeout=180)
    assert r.status_code == 200, r.text[:300]
    rows = r.json()
    assert isinstance(rows, list) and len(rows) > 0
    for row in rows[:20]:
        for k in ["fixture_id", "home_name", "away_name", "date", "round", "market_label",
                  "group", "book_odds", "fair_odds", "prob", "ev", "tier", "confidence"]:
            assert k in row, f"missing {k} in scanner row keys={list(row)}"
        assert 0 <= row["prob"] <= 100
        assert "_id" not in row
    print(f"scanner rows={len(rows)} top={rows[0]['home_name']} vs {rows[0]['away_name']} ev={rows[0]['ev']}")


def test_top_mismatches_v2(client):
    r = client.get(f"{BASE_URL}/api/top-mismatches", params={"limit": 20}, timeout=180)
    assert r.status_code == 200, r.text[:300]
    rows = r.json()
    assert len(rows) > 0
    for row in rows:
        assert row["lambda"] > 0 and 0 <= row["prob"] <= 100 and row["fair_odds"] > 1
    print(f"mismatches={len(rows)} top lambda={rows[0]['lambda']} prob={rows[0]['prob']}")


def test_matchups_eng_pl(client):
    r = client.get(f"{BASE_URL}/api/leagues/eng-pl/matchups", timeout=120)
    assert r.status_code == 200, r.text[:300]
    d = r.json()
    assert "teams" in d and "league_avg_won" in d
    rows = d["teams"]
    assert isinstance(rows, list) and len(rows) > 0
    for row in rows[:10]:
        assert "_id" not in row
        assert row["name"] and row["side_for"] >= 0
    print(f"eng-pl matchups teams={len(rows)} avg={d['league_avg_won']} sample_keys={list(rows[0])}")


def test_streaks(client):
    r = client.get(f"{BASE_URL}/api/streaks", params={"league_id": "all"}, timeout=180)
    assert r.status_code == 200, r.text[:300]
    assert isinstance(r.json(), list)
    print(f"streaks rows={len(r.json())}")


def test_fixture_detail_markets(client):
    rows = client.get(f"{BASE_URL}/api/scanner", params={"league_id": "all", "min_edge": 0}, timeout=180).json()
    fid = rows[0]["fixture_id"]
    r = client.get(f"{BASE_URL}/api/fixtures/{fid}", timeout=120)
    assert r.status_code == 200, r.text[:300]
    d = r.json()
    markets = d["model"]["markets"]
    assert len(markets) > 0
    groups = {m["group"] for m in markets}
    assert {"total", "home", "away"} <= groups, groups
    for m in markets:
        assert 0 <= m["prob"] <= 100 and m["fair_odds"] > 1
    lam = d["model"]["lambdas"]
    assert lam["total"] > 0 and lam["home"] > 0 and lam["away"] > 0
    print(f"fixture {fid}: markets={len(markets)} lambdas={lam} keys={list(d)}")
