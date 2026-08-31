"""Session tokens and the sign-in guardrails.

The Google half needs a real token from Google, so it cannot be tested offline — but the
things that would actually let someone in as somebody else CAN be, and are:
a token we did not sign, a token whose expiry has passed, and a token for another app.
"""
import os
import sys
import time

import jwt
import pytest

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "test_corner_model")
os.environ.setdefault("SESSION_SECRET", "test-secret-not-the-real-one")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import auth  # noqa: E402


def test_a_session_round_trips():
    assert auth.read_session(auth.issue_session("u-123")) == "u-123"


def test_a_token_we_did_not_sign_is_refused():
    """The whole point of signing. Anyone can write {"sub": "someone-else"}."""
    forged = jwt.encode({"sub": "victim", "exp": int(time.time()) + 999},
                        "not-our-secret", algorithm="HS256")
    assert auth.read_session(forged) is None


def test_an_expired_session_is_refused():
    stale = jwt.encode({"sub": "u-1", "iat": 0, "exp": int(time.time()) - 60},
                       auth.SESSION_SECRET, algorithm="HS256")
    assert auth.read_session(stale) is None


def test_the_algorithm_cannot_be_swapped_for_none():
    """The classic JWT attack: re-sign with alg=none and hope the reader accepts it."""
    payload = {"sub": "victim", "exp": int(time.time()) + 999}
    none_alg = jwt.encode(payload, key="", algorithm="none")
    assert auth.read_session(none_alg) is None


def test_rubbish_is_not_signed_in_rather_than_an_error():
    """On a public site "not signed in" is an ordinary state, not a failure."""
    for bad in (None, "", "abc", "a.b.c", "Bearer x"):
        assert auth.read_session(bad) is None


def test_bearer_header_parsing():
    assert auth.bearer("Bearer abc123") == "abc123"
    assert auth.bearer("bearer abc123") == "abc123"       # case-insensitive scheme
    assert auth.bearer("Bearer   abc123  ") == "abc123"


def test_a_header_that_is_not_a_bearer_token_yields_nothing():
    for bad in (None, "", "abc123", "Basic abc123", "Bearer", "Bearer "):
        assert auth.bearer(bad) is None


def test_sign_in_refuses_when_the_server_is_not_configured():
    """Better a clear message than verifying against an empty audience, which would
    accept tokens minted for any app at all."""
    with pytest.raises(auth.AuthError) as e:
        auth.verify_google_token("anything", client_id="")
    assert "not configured" in str(e.value)


def test_a_google_token_is_never_trusted_without_verification():
    """A Google ID token is just a JWT — anyone can mint one that LOOKS right. This one
    is well-formed and completely fake, and must be rejected."""
    fake = jwt.encode({"sub": "attacker", "email": "a@b.c", "aud": "our-client-id",
                       "iss": "https://accounts.google.com", "exp": int(time.time()) + 999},
                      "attackers-own-key", algorithm="HS256")
    with pytest.raises(auth.AuthError):
        auth.verify_google_token(fake, client_id="our-client-id")


def test_session_length_is_set_deliberately():
    assert auth.SESSION_DAYS == 30


# --------------------------------------------------------------------------------------
# The dependencies. The site is PUBLIC, so the rule that matters most is that being
# signed out is an ordinary state and never an error — every screen that worked before
# sign-in existed has to keep working without one.

import asyncio  # noqa: E402

import pytest  # noqa: E402,F811
from fastapi import HTTPException  # noqa: E402

import server  # noqa: E402


class _Req:
    def __init__(self, header=None):
        self.headers = {"authorization": header} if header else {}


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


@pytest.fixture
def fake_users(monkeypatch):
    """A stand-in users collection, so these run with no database."""
    rows = {}

    class Users:
        async def find_one(self, q, *a, **k):
            for r in rows.values():
                if all(r.get(key) == val for key, val in q.items()):
                    return dict(r)
            return None

        async def insert_one(self, doc):
            rows[doc["user_id"]] = dict(doc)

        async def update_one(self, q, upd, **k):
            for r in rows.values():
                if all(r.get(key) == val for key, val in q.items()):
                    r.update(upd.get("$set", {}))

    monkeypatch.setattr(server.db, "users", Users())
    return rows


def test_no_token_is_the_guest_not_a_refusal(fake_users):
    u = _run(server.get_current_user(_Req()))
    assert u["user_id"] == server.PUBLIC_USER_ID


def test_a_forged_token_falls_back_to_guest_rather_than_erroring(fake_users):
    forged = jwt.encode({"sub": "someone", "exp": int(time.time()) + 99},
                        "not-our-secret", algorithm="HS256")
    u = _run(server.get_current_user(_Req(f"Bearer {forged}")))
    assert u["user_id"] == server.PUBLIC_USER_ID


def test_a_valid_session_resolves_to_that_member(fake_users):
    fake_users["u-1"] = {"user_id": "u-1", "name": "Ryan", "email": "r@x.com"}
    u = _run(server.get_current_user(_Req(f"Bearer {auth.issue_session('u-1')}")))
    assert u["user_id"] == "u-1" and u["name"] == "Ryan"


def test_a_session_for_a_deleted_account_becomes_the_guest(fake_users):
    """The row is re-read rather than trusted from the token, so a deleted account
    cannot be carried back to life by an old session."""
    token = auth.issue_session("u-gone")
    u = _run(server.get_current_user(_Req(f"Bearer {token}")))
    assert u["user_id"] == server.PUBLIC_USER_ID


def test_require_user_refuses_the_guest(fake_users):
    with pytest.raises(HTTPException) as e:
        _run(server.require_user(_Req()))
    assert e.value.status_code == 401


def test_require_user_admits_a_member(fake_users):
    fake_users["u-2"] = {"user_id": "u-2", "name": "Member"}
    u = _run(server.require_user(_Req(f"Bearer {auth.issue_session('u-2')}")))
    assert u["user_id"] == "u-2"


def test_whoami_is_null_signed_out_rather_than_401(fake_users):
    """Signed out is the ordinary state on a public site."""
    assert _run(server.whoami(user=_run(server.get_current_user(_Req())))) == {"user": None}


def test_the_browser_never_receives_the_google_account_id(fake_users):
    """google_sub identifies the account; it has no business in a client payload."""
    out = server._public_user({"user_id": "u-3", "name": "N", "email": "e", "picture": "p",
                               "google_sub": "SECRET-SUB"})
    assert "google_sub" not in out and "SECRET-SUB" not in str(out)
