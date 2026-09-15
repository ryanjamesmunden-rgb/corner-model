"""Stripe's objects are not dicts, and nothing past billing.py may find that out.

FOUND LIVE, TWICE. The diagnostic check reported a good key as rejected because
account.get("id") raised. It was fixed there and nowhere else — and the webhook handler,
which reads event["data"]["object"].get("client_reference_id") on its first line, had the
same failure the whole time. Every event Stripe sent was a 500. The first person to start
a trial sat on a "setting up your membership…" spinner over an account that never became
one, because the one event that would have made it one crashed on arrival.

So the conversion lives at the three places a Stripe resource enters the codebase — the
verified event, a fetched subscription, a modified subscription — and these tests use
objects that have to_dict and deliberately NO .get, which is the only shape that could
have caught it.
"""
import os
import sys
import importlib
from unittest.mock import MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

FULL_KEY = "sk_live_" + "51NqRvW" * 14


def _billing():
    os.environ["STRIPE_SECRET_KEY"] = FULL_KEY
    os.environ["STRIPE_PRICE_ID"] = "price_1ABCdef2GHIjkl3MNOpqr4ST"
    os.environ["STRIPE_WEBHOOK_SECRET"] = "whsec_1"
    os.environ["SITE_URL"] = "https://thecornermodel.com"
    import billing
    return importlib.reload(billing)


class Resource:
    """A stand-in for stripe.StripeObject on stripe-python 8+.

    Item access works, .get is absent, and to_dict() is SHALLOW — nested resources stay
    as objects — which is what stripe-python does and what made the first fix incomplete.
    to_dict_recursive() is the one that goes all the way down.
    """
    def __init__(self, data):
        self._data = data

    def __getitem__(self, k):
        return self._data[k]

    def to_dict(self):
        return dict(self._data)

    def to_dict_recursive(self):
        def conv(v):
            if isinstance(v, Resource):
                return v.to_dict_recursive()
            if isinstance(v, dict):
                return {k: conv(x) for k, x in v.items()}
            return v
        return {k: conv(v) for k, v in self._data.items()}


def _event():
    return Resource({
        "type": "checkout.session.completed",
        "data": {"object": Resource({
            "client_reference_id": "u1", "subscription": "sub_1",
            "customer_details": Resource({"name": "Karl"}),
        })},
    })


class TestTheVerifiedEvent:
    def test_it_comes_back_as_a_plain_dict_all_the_way_down(self, monkeypatch):
        # The handler's first read is event["data"]["object"].get(...). If the nested
        # object is still a Resource this raises exactly as it did live.
        b = _billing()
        mod = MagicMock()
        mod.Webhook.construct_event.return_value = _event()
        monkeypatch.setattr(b, "_stripe", lambda: mod)
        event = b.verify_event(b"{}", "sig")
        assert isinstance(event, dict)
        obj = event["data"]["object"]
        assert isinstance(obj, dict)
        assert obj.get("client_reference_id") == "u1"
        assert (obj.get("customer_details") or {}).get("name") == "Karl"

    def test_a_shallow_to_dict_is_not_trusted_on_its_own(self):
        # to_dict() leaves event["data"]["object"] as the very thing that raises, one
        # level down from where anybody looked. Recursive wins when it exists.
        b = _billing()
        out = b._as_dict(_event())
        assert isinstance(out["data"]["object"], dict)

    def test_an_object_with_only_to_dict_still_converts(self):
        class Shallow:
            def to_dict(self):
                return {"id": "x"}
        assert _billing()._as_dict(Shallow()) == {"id": "x"}

    def test_the_signature_check_still_stands(self, monkeypatch):
        # Converting the event must not have moved it in front of verification.
        b = _billing()
        mod = MagicMock()
        mod.Webhook.construct_event.side_effect = Exception("bad signature")
        monkeypatch.setattr(b, "_stripe", lambda: mod)
        try:
            b.verify_event(b"{}", "sig")
        except Exception as e:
            assert "bad signature" in str(e)
        else:
            raise AssertionError("an unverifiable event was accepted")


class TestFetchedAndModifiedSubscriptions:
    def test_a_fetched_subscription_is_a_dict(self, monkeypatch):
        # apply_subscription reads sub.get("customer") on its first line.
        b = _billing()
        mod = MagicMock()
        mod.Subscription.retrieve.return_value = Resource({
            "id": "sub_1", "status": "trialing", "customer": "cus_1",
            "metadata": Resource({"user_id": "u1"})})
        monkeypatch.setattr(b, "_stripe", lambda: mod)
        sub = b.fetch_subscription("sub_1")
        assert sub.get("status") == "trialing"
        assert sub["metadata"].get("user_id") == "u1"

    def test_cancelling_returns_a_dict_too(self, monkeypatch):
        # The account page's cancel button hands this straight to apply_subscription and
        # reads .get("cancel_at_period_end") off it. Same bug, second door.
        b = _billing()
        mod = MagicMock()
        mod.Subscription.modify.return_value = Resource({
            "id": "sub_1", "status": "active", "customer": "cus_1",
            "cancel_at_period_end": True, "metadata": Resource({"user_id": "u1"})})
        monkeypatch.setattr(b, "_stripe", lambda: mod)
        sub = b.set_cancel_at_period_end("sub_1", True)
        assert sub.get("cancel_at_period_end") is True

    def test_a_trial_grants_membership_once_the_event_can_be_read(self):
        # The end-to-end fact this whole file exists for: a `trialing` subscription, read
        # as a dict, makes a member. ACTIVE_STATUSES already said so; the event just
        # never got far enough to ask.
        import asyncio
        from test_billing import FakeDb
        b = _billing()
        db = FakeDb([{"user_id": "u1", "member": False}])
        sub = b._as_dict(Resource({"id": "sub_1", "status": "trialing", "customer": "cus_1",
                                   "current_period_end": 1893456000,
                                   "cancel_at_period_end": False,
                                   "metadata": Resource({"user_id": "u1"})}))
        res = asyncio.get_event_loop().run_until_complete(
            b.apply_subscription(db, sub, user_id="u1"))
        assert res["matched"] is True and res["member"] is True
        assert db.users.rows[0]["member"] is True
        assert db.users.rows[0]["member_source"] == "stripe"
