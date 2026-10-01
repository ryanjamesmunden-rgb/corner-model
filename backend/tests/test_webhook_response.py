"""What the Stripe webhook is allowed to answer, and why it matters more than it looks.

STRIPE DISABLED THIS ENDPOINT ON 2026-10-01, after nine consecutive days of failures. Its
rule is simple: anything outside 200-299 is a failed delivery, it retries for days, and
enough of them turn the endpoint off. Losing it removes the fast path that tells this app
somebody has paid.

TWO FAILURES LOOK THE SAME TO STRIPE AND NEED OPPOSITE ANSWERS:

  - A BAD SIGNATURE is not our event. 400, every time, and no ledger entry pretending we
    handled it. Retrying is pointless but harmless, and answering 200 to an unverified
    payload would mean anyone who finds the URL can grant themselves access.

  - A VERIFIED EVENT WE COULD NOT APPLY is our bug. Past the signature check the handler
    calls Stripe, writes to Mongo and talks to Telegram, and any of those raising used to
    return a 500. Stripe reads that as "try again" — but a retry hits the same bug with the
    same payload, so a deterministic failure buys nothing and costs the endpoint.

That second case is what these pin. The event is accepted, the error is recorded so
signup_audit can surface it, and _reconcile_billing re-applies from Stripe inside fifteen
minutes. Answering 200 is only safe BECAUSE that sweep exists; if it is ever removed, this
has to be reconsidered with it.
"""
import asyncio
import os
import sys

import pytest

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "test_corner_model")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import billing  # noqa: E402
import server  # noqa: E402
from fastapi import HTTPException  # noqa: E402


def run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


class FakeRequest:
    def __init__(self, sig="whsec-sig"):
        self.headers = {"stripe-signature": sig}

    async def body(self):
        return b"{}"


EVENT = {"type": "customer.subscription.updated", "data": {"object": {"id": "sub_1"}}}


@pytest.fixture
def recorded(monkeypatch):
    """Capture the ledger rows the handler writes, without a database."""
    rows = []

    async def fake_record(kind, result, error=None):
        rows.append({"type": kind, "result": result, "error": error})

    monkeypatch.setattr(server, "_record_webhook", fake_record)
    return rows


def verified(monkeypatch):
    monkeypatch.setattr(billing, "verify_event", lambda payload, sig: EVENT)


class TestAVerifiedEventIsAlwaysAccepted:
    def test_a_handled_event_answers_200_and_says_it_applied(self, monkeypatch, recorded):
        verified(monkeypatch)

        async def ok(db, obj, user_id=None):
            return {"matched": True, "user_id": "u1", "member": True, "status": "active"}

        monkeypatch.setattr(billing, "apply_subscription", ok)
        out = run(server.billing_webhook(FakeRequest()))
        assert out["received"] is True and out["applied"] is True
        assert recorded[0]["error"] is None

    def test_an_event_we_could_not_apply_STILL_answers_200(self, monkeypatch, recorded):
        """THE ONE THAT COST THE ENDPOINT. This used to raise out of the handler as a 500,
        Stripe retried it for nine days and then disabled the webhook."""
        verified(monkeypatch)

        async def boom(db, obj, user_id=None):
            raise RuntimeError("mongo is having a moment")

        monkeypatch.setattr(billing, "apply_subscription", boom)
        out = run(server.billing_webhook(FakeRequest()))
        assert out["received"] is True
        assert out["applied"] is False

    def test_and_the_failure_is_recorded_rather_than_swallowed(self, monkeypatch, recorded):
        # 200 with no trace would be a silent drop. signup_audit reads this ledger and
        # reports errored rows first.
        verified(monkeypatch)

        async def boom(db, obj, user_id=None):
            raise RuntimeError("mongo is having a moment")

        monkeypatch.setattr(billing, "apply_subscription", boom)
        run(server.billing_webhook(FakeRequest()))
        assert "RuntimeError" in recorded[0]["error"]
        assert "mongo is having a moment" in recorded[0]["error"]

    def test_a_failure_in_the_channel_removal_does_not_fail_the_delivery(
            self, monkeypatch, recorded):
        # Telegram being down is not a reason for Stripe to retry a payment event.
        verified(monkeypatch)

        async def lapsed(db, obj, user_id=None):
            return {"matched": True, "user_id": "u1", "member": False, "status": "canceled"}

        async def telegram_down(uid):
            raise RuntimeError("telegram timeout")

        monkeypatch.setattr(billing, "apply_subscription", lapsed)
        monkeypatch.setattr(server, "_revoke_channel_access", telegram_down)
        out = run(server.billing_webhook(FakeRequest()))
        assert out["applied"] is False
        assert "telegram timeout" in recorded[0]["error"]

    def test_an_event_type_we_ignore_is_still_a_success(self, monkeypatch, recorded):
        verified(monkeypatch)
        monkeypatch.setattr(billing, "verify_event",
                            lambda p, s: {"type": "invoice.paid", "data": {"object": {}}})
        out = run(server.billing_webhook(FakeRequest()))
        assert out["applied"] is True and out["matched"] is False


class TestSignatureFailuresAreNotSoftened:
    def test_a_bad_signature_is_a_400(self, monkeypatch, recorded):
        """NOT softened by any of the above. An unverified payload is not our event, and
        answering 200 to one would let anyone who finds the URL grant themselves access."""
        def bad(payload, sig):
            raise ValueError("no match")

        monkeypatch.setattr(billing, "verify_event", bad)
        with pytest.raises(HTTPException) as e:
            run(server.billing_webhook(FakeRequest()))
        assert e.value.status_code == 400

    def test_a_missing_secret_is_a_503_and_says_so_in_the_ledger(self, monkeypatch, recorded):
        # 503 rather than 400: the request may well be genuine and the fault is ours, so
        # the two need different entries in the diagnostic.
        def unset(payload, sig):
            raise RuntimeError("STRIPE_WEBHOOK_SECRET is not set")

        monkeypatch.setattr(billing, "verify_event", unset)
        with pytest.raises(HTTPException) as e:
            run(server.billing_webhook(FakeRequest()))
        assert e.value.status_code == 503
        assert recorded[0]["error"] == "STRIPE_WEBHOOK_SECRET is not set"

    def test_a_rejected_delivery_is_still_written_down(self, monkeypatch, recorded):
        # "Stripe has never called" and "Stripe calls and every one is refused" are the same
        # silence without this row, and they need opposite fixes.
        monkeypatch.setattr(billing, "verify_event",
                            lambda p, s: (_ for _ in ()).throw(ValueError("nope")))
        with pytest.raises(HTTPException):
            run(server.billing_webhook(FakeRequest()))
        assert recorded[0]["type"] == "rejected"
        assert "signature rejected" in recorded[0]["error"]
