"""One free week per account, when the customer is created before anyone subscribes.

WHAT CHANGED AND WHY IT IS DELICATE. The Stripe customer used to be minted by Stripe at
payment, and we learned its id from the webhook. So an account whose webhook never landed
had no customer id — and its next checkout created a SECOND Stripe customer with the same
email and another free trial attached. Three accounts were in exactly that state.

Creating the customer ourselves, before the redirect, fixes that and breaks two things on
the way past if nobody is looking:

  · `trial_days_for` keyed on `stripe_customer_id`, which now means "has opened checkout"
    rather than "has subscribed" — so every visitor would be refused a trial the moment
    they reached the payment page, including on their first ever visit.
  · the join page's offer read the same field through `has_billing`, so it would have
    advertised a free week to somebody the backend had already decided to charge.

These pin both, and the rule they protect: subscribe, cancel, subscribe again must not
yield a second free week.
"""
import os
import sys
import importlib
from unittest.mock import MagicMock

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "test_corner_model")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from test_billing import FakeDb, run  # noqa: E402


def _billing(days="7"):
    os.environ["TRIAL_DAYS"] = days
    os.environ["STRIPE_SECRET_KEY"] = "sk_live_" + "51NqRvW" * 14
    os.environ["STRIPE_PRICE_ID"] = "price_1ABCdef2GHIjkl3MNOpqr4ST"
    os.environ["SITE_URL"] = "https://thecornermodel.com"
    import billing
    return importlib.reload(billing)


class Resource:
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


class TestWhoGetsAFreeWeek:
    def test_a_brand_new_account(self):
        assert _billing().trial_days_for({"user_id": "u1"}) == 7

    def test_someone_who_opened_checkout_and_changed_their_mind_still_gets_one(self):
        # THE TRAP. They have a Stripe customer now — created when they reached the
        # payment page — and no subscription. Keying on the customer id, as this used to,
        # refuses a free week to somebody who has never had one.
        b = _billing()
        user = {"user_id": "u1", "stripe_customer_id": "cus_1"}
        assert b.trial_days_for(user, prior_subscription=False) == 7

    def test_someone_who_has_subscribed_before_gets_none(self):
        b = _billing()
        user = {"user_id": "u1", "stripe_customer_id": "cus_1"}
        assert b.trial_days_for(user, prior_subscription=True) == 0

    def test_a_cancelled_subscription_still_counts_as_having_had_one(self):
        # subscribe, cancel on day six, subscribe again is the whole thing this prevents.
        b = _billing()
        assert b.trial_days_for({"user_id": "u1", "had_subscription": True}) == 0

    def test_without_an_answer_from_stripe_it_falls_back_to_the_stored_flag(self):
        # The call failed. Refusing everyone would deny new visitors; granting everyone
        # would hand out free weeks. The flag is right far more often than either.
        b = _billing()
        assert b.trial_days_for({"user_id": "u1", "had_subscription": True}) == 0
        assert b.trial_days_for({"user_id": "u1"}) == 7

    def test_a_legacy_customer_id_still_blocks_a_trial_in_the_fallback(self):
        # Accounts that predate had_subscription got their customer id from the webhook,
        # which only ran after a real subscription. That meaning has to survive.
        b = _billing()
        assert b.trial_days_for({"user_id": "u1", "stripe_customer_id": "cus_old"}) == 0

    def test_trial_days_zero_switches_it_off_for_everyone(self):
        b = _billing(days="0")
        assert b.trial_days_for({"user_id": "u1"}, prior_subscription=False) == 0


class TestAskingStripe:
    def test_no_customer_means_no_call_and_no_prior_subscription(self, monkeypatch):
        b = _billing()
        stripe = MagicMock()
        monkeypatch.setattr(b, "_stripe", stripe)
        assert b.has_prior_subscription(None) is False
        assert b.has_prior_subscription("") is False
        stripe.assert_not_called()

    def test_it_counts_subscriptions_in_any_state(self, monkeypatch):
        # status="all", so a cancelled one is found. Listing only active subscriptions
        # would hand a second free week to everybody who had cancelled.
        b = _billing()
        mod = MagicMock()
        mod.Subscription.list.return_value = Resource({"data": [Resource({"id": "sub_1"})]})
        monkeypatch.setattr(b, "_stripe", lambda: mod)
        assert b.has_prior_subscription("cus_1") is True
        assert mod.Subscription.list.call_args.kwargs["status"] == "all"

    def test_a_customer_with_no_subscriptions_is_still_owed_a_trial(self, monkeypatch):
        b = _billing()
        mod = MagicMock()
        mod.Subscription.list.return_value = Resource({"data": []})
        monkeypatch.setattr(b, "_stripe", lambda: mod)
        assert b.has_prior_subscription("cus_1") is False


class TestTheCustomerAndTheSession:
    def test_the_customer_carries_the_account_id(self, monkeypatch):
        # So a customer in the Stripe dashboard can be traced back here without going
        # through a subscription.
        b = _billing()
        mod = MagicMock()
        mod.Customer.create.return_value = Resource({"id": "cus_new"})
        monkeypatch.setattr(b, "_stripe", lambda: mod)
        cid = b.create_customer({"user_id": "u1", "email": "a@b.com", "name": "Ann"})
        assert cid == "cus_new"
        assert mod.Customer.create.call_args.kwargs["metadata"] == {"user_id": "u1"}

    def test_the_session_is_pinned_to_that_customer_and_never_to_an_email(self, monkeypatch):
        # customer_email is how Stripe minted a second customer for an account whose
        # webhook never landed. It must not come back.
        b = _billing()
        mod = MagicMock()
        mod.checkout.Session.create.return_value = Resource({"url": "https://pay"})
        monkeypatch.setattr(b, "_stripe", lambda: mod)
        b.create_checkout_session({"user_id": "u1", "email": "a@b.com"}, "cus_1", 7)
        kw = mod.checkout.Session.create.call_args.kwargs
        assert kw["customer"] == "cus_1"
        assert "customer_email" not in kw
        assert kw["subscription_data"]["trial_period_days"] == 7

    def test_no_trial_omits_the_field_rather_than_sending_zero(self, monkeypatch):
        # Stripe rejects trial_period_days=0.
        b = _billing()
        mod = MagicMock()
        mod.checkout.Session.create.return_value = Resource({"url": "https://pay"})
        monkeypatch.setattr(b, "_stripe", lambda: mod)
        b.create_checkout_session({"user_id": "u1"}, "cus_1", 0)
        assert "trial_period_days" not in \
            mod.checkout.Session.create.call_args.kwargs["subscription_data"]


class TestTheMarkThatBlocksASecondTrial:
    def test_a_subscription_stamps_had_subscription(self):
        b = _billing()
        db = FakeDb([{"user_id": "u1", "member": False}])
        run(b.apply_subscription(db, {"id": "sub_1", "status": "trialing",
                                      "customer": "cus_1",
                                      "metadata": {"user_id": "u1"}}, user_id="u1"))
        assert db.users.rows[0]["had_subscription"] is True

    def test_a_CANCELLED_subscription_stamps_it_too(self):
        # The case the flag exists for. A lapsed subscription has to leave the mark, or
        # cancelling is how you earn another free week.
        b = _billing()
        # No other live subscription — see the note in test_billing_reconcile.
        b.active_subscriptions = lambda cid, exclude_id=None: []
        db = FakeDb([{"user_id": "u1", "member": True, "member_source": "stripe"}])
        run(b.apply_subscription(db, {"id": "sub_1", "status": "canceled",
                                      "customer": "cus_1",
                                      "metadata": {"user_id": "u1"}}, user_id="u1"))
        assert db.users.rows[0]["had_subscription"] is True
        assert db.users.rows[0]["member"] is False


class TestTheBackfill:
    def test_existing_customers_are_marked_as_having_subscribed(self):
        # At deploy, `stripe_customer_id` could only have been written by the webhook —
        # i.e. only for an account that really subscribed. Without this, every returning
        # ex-subscriber is offered a free week the backend then refuses.
        b = _billing()
        db = FakeDb([{"user_id": "u1", "stripe_customer_id": "cus_1"},
                     {"user_id": "u2"}])
        run(b.backfill_had_subscription(db))
        assert db.users.rows[0]["had_subscription"] is True
        assert "had_subscription" not in db.users.rows[1]

    def test_it_does_not_touch_an_account_already_marked(self):
        b = _billing()
        db = FakeDb([{"user_id": "u1", "stripe_customer_id": "cus_1",
                      "had_subscription": True}])
        assert run(b.backfill_had_subscription(db)) == 0
