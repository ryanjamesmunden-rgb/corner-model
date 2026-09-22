"""Membership that does not depend on a webhook arriving.

FOUND LIVE, TWICE. Membership was granted by exactly one mechanism — an inbound Stripe
webhook — with nothing behind it. First every event 500'd on a library change; then none
arrived at all. Both times the symptom was the same: somebody who had paid sat in front of
a locked page, unable to add a price or join the channel, with no way to tell anyone.

This backend also SLEEPS. A cold start can outlast Stripe's delivery timeout, so a missed
webhook is a normal operating condition here rather than an incident — which makes a
single-mechanism grant the wrong design regardless of any particular bug.

These pin the sweep that fixes it: ask Stripe who is subscribed, and make the site agree.
"""
import os
import sys
import asyncio
import importlib
from unittest.mock import MagicMock

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "test_corner_model")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from test_billing import FakeDb, run  # noqa: E402


def _billing():
    os.environ["STRIPE_SECRET_KEY"] = "sk_live_" + "51NqRvW" * 14
    os.environ["STRIPE_PRICE_ID"] = "price_1ABCdef2GHIjkl3MNOpqr4ST"
    os.environ["STRIPE_WEBHOOK_SECRET"] = "whsec_1"
    os.environ["SITE_URL"] = "https://thecornermodel.com"
    import billing
    return importlib.reload(billing)


class Resource:
    """stripe-python 8+ shape: item access, no .get, shallow to_dict."""
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
            if isinstance(v, list):
                return [conv(x) for x in v]
            if isinstance(v, dict):
                return {k: conv(x) for k, x in v.items()}
            return v
        return {k: conv(v) for k, v in self._data.items()}


def sub(status="trialing", user_id="u1", sub_id="sub_1", customer="cus_1"):
    return Resource({"id": sub_id, "status": status, "customer": customer,
                     "current_period_end": 1893456000, "cancel_at_period_end": False,
                     "metadata": Resource({"user_id": user_id})})


class TestListingFromStripe:
    def test_it_starts_from_stripe_not_from_our_users(self, monkeypatch):
        # THE WHOLE POINT. The accounts needing this most are the ones no webhook ever
        # reached: no stripe_customer_id, no subscription id, nothing pointing outward.
        # A sweep over our own users would skip exactly them.
        b = _billing()
        mod = MagicMock()
        mod.Subscription.list.return_value = Resource(
            {"data": [sub()], "has_more": False})
        monkeypatch.setattr(b, "_stripe", lambda: mod)
        subs = b.list_subscriptions()
        assert len(subs) == 1
        assert subs[0]["metadata"]["user_id"] == "u1"

    def test_it_asks_for_every_status_not_just_active(self, monkeypatch):
        # A cancelled subscription is the one that has to REVOKE. Listing only active ones
        # would reconcile grants and silently never reconcile removals.
        b = _billing()
        mod = MagicMock()
        mod.Subscription.list.return_value = Resource({"data": [], "has_more": False})
        monkeypatch.setattr(b, "_stripe", lambda: mod)
        b.list_subscriptions()
        assert mod.Subscription.list.call_args.kwargs["status"] == "all"

    def test_it_pages_rather_than_stopping_at_the_first_hundred(self, monkeypatch):
        b = _billing()
        mod = MagicMock()
        first = Resource({"data": [sub(sub_id=f"sub_{i}") for i in range(100)],
                          "has_more": True})
        second = Resource({"data": [sub(sub_id="sub_last")], "has_more": False})
        mod.Subscription.list.side_effect = [first, second]
        monkeypatch.setattr(b, "_stripe", lambda: mod)
        assert len(b.list_subscriptions()) == 101

    def test_stripes_objects_are_converted_all_the_way_down(self, monkeypatch):
        # The nested metadata is where user_id lives, and a Resource there raises on .get
        # exactly as it did in the webhook.
        b = _billing()
        mod = MagicMock()
        mod.Subscription.list.return_value = Resource({"data": [sub()], "has_more": False})
        monkeypatch.setattr(b, "_stripe", lambda: mod)
        meta = b.list_subscriptions()[0]["metadata"]
        assert isinstance(meta, dict) and meta.get("user_id") == "u1"


class TestApplyingWhatStripeSays:
    """The sweep reuses apply_subscription, so the revocation rule comes with it."""

    def test_a_trial_that_no_webhook_reached_becomes_a_member(self):
        # THE LIVE CASE: they started a trial, Stripe took the card, the event never
        # landed, and the site showed them a locked page.
        b = _billing()
        db = FakeDb([{"user_id": "u1", "member": False}])
        res = run(b.apply_subscription(db, b._as_dict(sub("trialing")), user_id="u1"))
        assert res["member"] is True
        assert db.users.rows[0]["member"] is True
        # And the customer id lands, which is what stops a second free trial.
        assert db.users.rows[0]["stripe_customer_id"] == "cus_1"

    def test_a_cancelled_subscription_revokes_a_stripe_member(self):
        b = _billing()
        # STATED, because it is now load-bearing: revocation requires knowing the account
        # holds no OTHER live subscription. Without this the sweep asks the real Stripe,
        # cannot get an answer, and correctly declines to revoke — see
        # billing._surviving_subscription.
        b.active_subscriptions = lambda cid, exclude_id=None: []
        db = FakeDb([{"user_id": "u1", "member": True, "member_source": "stripe"}])
        res = run(b.apply_subscription(db, b._as_dict(sub("canceled")), user_id="u1"))
        assert res["member"] is False

    def test_a_comped_member_is_still_never_revoked(self):
        # The asymmetry the webhook obeys has to survive being reached a second way.
        b = _billing()
        db = FakeDb([{"user_id": "u1", "member": True, "member_source": "code"}])
        run(b.apply_subscription(db, b._as_dict(sub("canceled")), user_id="u1"))
        assert db.users.rows[0]["member"] is True

    def test_a_grandfathered_member_is_still_never_revoked(self):
        b = _billing()
        db = FakeDb([{"user_id": "u1", "member": True, "member_source": "stripe",
                      "grandfathered": True}])
        run(b.apply_subscription(db, b._as_dict(sub("canceled")), user_id="u1"))
        assert db.users.rows[0]["member"] is True

    def test_past_due_keeps_access_while_stripe_retries(self):
        b = _billing()
        db = FakeDb([{"user_id": "u1", "member": True, "member_source": "stripe"}])
        res = run(b.apply_subscription(db, b._as_dict(sub("past_due")), user_id="u1"))
        assert res["member"] is True

    def test_running_it_twice_changes_nothing_the_second_time(self):
        # It runs every fifteen minutes; anything not idempotent would churn the database
        # and the channel with it.
        b = _billing()
        db = FakeDb([{"user_id": "u1", "member": False}])
        first = run(b.apply_subscription(db, b._as_dict(sub()), user_id="u1"))
        since = db.users.rows[0]["member_since"]
        second = run(b.apply_subscription(db, b._as_dict(sub()), user_id="u1"))
        assert first["member"] is True and second["member"] is True
        # member_since is stamped once, not reset on every sweep.
        assert db.users.rows[0]["member_since"] == since

    def test_a_subscription_for_an_account_we_do_not_have_is_skipped(self):
        # A test payment, or a customer deleted on our side. Must not raise and must not
        # touch anybody else.
        b = _billing()
        db = FakeDb([{"user_id": "u1", "member": True, "member_source": "stripe"}])
        res = run(b.apply_subscription(db, b._as_dict(sub(user_id="ghost")),
                                       user_id="ghost"))
        assert res["matched"] is False
        assert db.users.rows[0]["member"] is True
