"""Backend tests for session-4 features: Weekly Chase Board, best-bets chase card,
fixture odds paste -> EV recalculation, and /api/picks regression."""
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


@pytest.fixture(scope="module")
def board(client):
    r = client.get(f"{BASE_URL}/api/chase-board?within_days=7&limit=25", timeout=120)
    assert r.status_code == 200, r.text[:300]
    return r.json()


# --- /api/chase-board shape ---
def test_chase_board_shape(board):
    assert set(["within_days", "count", "board"]).issubset(board.keys())
    assert board["within_days"] == 7
    assert isinstance(board["board"], list)
    assert board["count"] == len(board["board"])
    assert 0 < len(board["board"]) <= 25, f"got {len(board['board'])} rows"


def test_chase_board_row_fields(board):
    required = ["name", "next_fixture", "team_for", "opp_conceded", "opp_fh_rate",
                "consistency", "consistency_of", "lambda", "line", "prob",
                "fair_odds", "chase_score", "market_key"]
    for row in board["board"]:
        missing = [k for k in required if k not in row]
        assert not missing, f"{row.get('name')} missing {missing}"
        nf = row["next_fixture"]
        for k in ("opponent", "is_home", "fixture_id", "date"):
            assert k in nf, f"next_fixture missing {k}"
        assert 0 <= row["opp_fh_rate"] <= 100
        assert row["line"] >= 3
        assert row["consistency_of"] > 0
        assert row["fair_odds"] and row["fair_odds"] > 1.0
        assert row["market_key"] == f"{'home' if nf['is_home'] else 'away'}_over_{row['line'] - 0.5}"


def test_chase_board_sorted_desc(board):
    scores = [r["chase_score"] for r in board["board"]]
    assert scores == sorted(scores, reverse=True), scores


def test_opp_fh_rate_not_all_zero(board):
    rates = [r["opp_fh_rate"] for r in board["board"]]
    nonzero = [x for x in rates if x > 0]
    assert len(nonzero) > 0, f"all opp_fh_rate are zero: {rates}"


def test_no_mongo_id_leak(board):
    for r in board["board"]:
        assert "_id" not in r
        assert "_id" not in r["next_fixture"]


# --- filters ---
def test_chase_board_limit(client):
    r = client.get(f"{BASE_URL}/api/chase-board?within_days=14&limit=15", timeout=120)
    assert r.status_code == 200
    assert len(r.json()["board"]) <= 15


def test_chase_board_window_widening(client):
    r3 = client.get(f"{BASE_URL}/api/chase-board?within_days=3&limit=200", timeout=120).json()
    r14 = client.get(f"{BASE_URL}/api/chase-board?within_days=14&limit=200", timeout=120).json()
    assert r3["count"] <= r14["count"], f"3d={r3['count']} 14d={r14['count']}"


def test_chase_board_league_filter(client, board):
    lid = board["board"][0]["league_id"]
    r = client.get(f"{BASE_URL}/api/chase-board?within_days=7&limit=200&league_id={lid}", timeout=120)
    assert r.status_code == 200
    rows = r.json()["board"]
    assert rows, "league-filtered board empty"
    assert all(x["league_id"] == lid for x in rows)
    allr = client.get(f"{BASE_URL}/api/chase-board?within_days=7&limit=200&league_id=all", timeout=120).json()
    assert len(rows) <= allr["count"]


def test_chase_board_requires_auth():
    r = requests.get(f"{BASE_URL}/api/chase-board", timeout=60)
    assert r.status_code in (401, 403)


# --- /api/best-bets ---
def test_best_bets(client):
    r = client.get(f"{BASE_URL}/api/best-bets", timeout=120)
    assert r.status_code == 200, r.text[:300]
    d = r.json()
    assert set(["chase", "streak", "mismatch"]).issubset(d.keys())
    assert d["chase"] is not None, "chase card is null"
    c = d["chase"]
    assert c["next_fixture"] and c["next_fixture"].get("fixture_id")
    assert "opp_fh_rate" in c and 0 <= c["opp_fh_rate"] <= 100
    assert c["line"] >= 3 and c["fair_odds"] > 1


# --- paste odds -> EV recalculation on chase board ---
def test_paste_odds_updates_chase_board_ev(client, board):
    row = board["board"][0]
    fid = row["next_fixture"]["fixture_id"]
    mkey = row["market_key"]
    payload = {"odds": {mkey: 2.20}}
    r = client.post(f"{BASE_URL}/api/fixtures/{fid}/odds", json=payload, timeout=60)
    assert r.status_code in (200, 201), r.text[:300]

    assert r.json().get("odds", {}).get(mkey) == 2.20, r.text[:300]

    # fixture detail model must reflect the pasted book odds on that market
    fx = client.get(f"{BASE_URL}/api/fixtures/{fid}", timeout=60)
    assert fx.status_code == 200
    mkts = fx.json()["model"]["markets"]
    target = [m for m in mkts if m["key"] == mkey]
    assert target, f"market {mkey} not in fixture model keys={[m['key'] for m in mkts][:20]}"
    assert target[0].get("book_odds") == 2.20, target[0]
    assert target[0].get("ev") is not None, target[0]

    nb = client.get(f"{BASE_URL}/api/chase-board?within_days=7&limit=200", timeout=120).json()["board"]
    match = [x for x in nb if x["team_id"] == row["team_id"] and x["market_key"] == mkey]
    assert match, "row disappeared from board after odds paste"
    m = match[0]
    assert m["book_odds"] == 2.20, m
    assert m["ev"] is not None, "EV still null after real odds pasted"
    expected = round((2.20 * m["prob"] / 100 - 1) * 100, 1)
    assert abs(m["ev"] - expected) < 1.5, f"ev={m['ev']} expected≈{expected}"

    # cleanup: remove the odds doc we created (no clear-odds API exists; POST merges)
    _clear_odds(fid)


def _clear_odds(fixture_id: str):
    from pymongo import MongoClient
    env = dotenv_values("/app/backend/.env")
    mc = MongoClient(env["MONGO_URL"])
    mc[env["DB_NAME"]].odds.delete_one({"fixture_id": fixture_id})
    mc.close()


# --- /api/picks regression ---
def test_picks_record_and_manual_picks(client):
    r = client.get(f"{BASE_URL}/api/picks", timeout=60)
    assert r.status_code == 200, r.text[:300]
    d = r.json()
    rec = d["record"]
    for k in ("won", "lost", "pending", "win_rate"):
        assert k in rec, f"record missing {k}"
    picks = d["picks"]
    assert isinstance(picks, list) and picks
    manual = [p for p in picks if p.get("source") == "manual"]
    assert len(manual) >= 7, f"expected >=7 manual picks, got {len(manual)}"
    assert all(p.get("date") is None for p in manual), "manual picks should have date null"
    assert any(p.get("odds") for p in manual), "no manual picks carry odds"
    assert rec["won"] + rec["lost"] == rec["settled"]
