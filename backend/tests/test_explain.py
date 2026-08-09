"""Phase 3: Claude explainer endpoint — POST /api/explain"""
import os
import time
import uuid

import pytest
import requests
from dotenv import dotenv_values

frontend_env = dotenv_values("/app/frontend/.env")
base_url = os.environ.get("REACT_APP_BACKEND_URL") or frontend_env.get("REACT_APP_BACKEND_URL")
if not base_url:
    raise RuntimeError("REACT_APP_BACKEND_URL missing")
BASE_URL = base_url.rstrip("/")
TOKEN = "qa-test-token-123"

PAYLOAD = {
    "key": "qa-test-city-6",
    "team": "Manchester City",
    "opponent": "Bournemouth",
    "league": "Premier League",
    "is_home": True,
    "line": 6,
    "team_for": 7.5,
    "opp_conceded": 5.8,
    "lam": 7.2,
    "prob": 64,
    "fair_odds": 1.55,
}


@pytest.fixture(scope="module")
def client():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json", "Authorization": f"Bearer {TOKEN}"})
    return s


@pytest.fixture(scope="module")
def created_keys():
    keys = []
    yield keys
    # cleanup via mongo (endpoint has no delete) — best effort
    import subprocess
    for k in keys:
        subprocess.run(
            ["mongosh", "--quiet", "--eval",
             f'db.explanations.deleteOne({{_id:"{k}"}})'],
            capture_output=True)


class TestExplainAuth:
    def test_requires_auth(self):
        r = requests.post(f"{BASE_URL}/api/explain", json=PAYLOAD)
        assert r.status_code in (401, 403), r.text

    def test_validation_error_on_missing_fields(self, client):
        r = client.post(f"{BASE_URL}/api/explain", json={"key": "x"})
        assert r.status_code == 422, r.text


class TestExplainLLM:
    def test_explain_then_cached(self, client, created_keys):
        key = f"qa-test-city-6-{uuid.uuid4().hex[:8]}"
        payload = dict(PAYLOAD, key=key)
        created_keys.append(key)

        t0 = time.time()
        r1 = client.post(f"{BASE_URL}/api/explain", json=payload, timeout=120)
        assert r1.status_code == 200, r1.text
        d1 = r1.json()
        assert isinstance(d1.get("explanation"), str)
        assert len(d1["explanation"].strip()) > 20, d1
        assert d1.get("cached") is False, d1
        print(f"first call {time.time()-t0:.1f}s -> {d1['explanation']}")

        # numbers referenced
        text = d1["explanation"]
        assert "Manchester City" in text or "City" in text
        assert any(tok in text for tok in ["7.5", "5.8", "7.2", "64", "1.55", "6+"]), text

        r2 = client.post(f"{BASE_URL}/api/explain", json=payload, timeout=60)
        assert r2.status_code == 200, r2.text
        d2 = r2.json()
        assert d2.get("cached") is True, d2
        assert d2["explanation"] == d1["explanation"]

    def test_no_mongo_id_leak(self, client, created_keys):
        key = created_keys[0] if created_keys else PAYLOAD["key"]
        r = client.post(f"{BASE_URL}/api/explain", json=dict(PAYLOAD, key=key), timeout=60)
        assert r.status_code == 200
        assert "_id" not in r.json()
