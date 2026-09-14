"""The free trial.

Two failures matter. One is the trial being repeatable — subscribe, cancel on day nine,
subscribe again is an unlimited free subscription with a chore attached, and Stripe does
not dedupe it for us. The other is the join page promising days that checkout will not
grant, which is why the length is served from here rather than compiled into the bundle.
"""
import os
import sys
import importlib

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _billing(days="10"):
    """Freshly imported, so TRIAL_DAYS is read rather than inherited."""
    os.environ["TRIAL_DAYS"] = days
    import billing
    return importlib.reload(billing)


class TestEligibility:
    def test_a_new_account_gets_the_full_trial(self):
        assert _billing().trial_days_for({"user_id": "u1"}) == 10

    def test_an_account_that_has_subscribed_before_gets_none(self):
        # The repeat-trial hole. `stripe_customer_id` is set the first time they check out
        # and never cleared, so it outlives a cancellation — which is the point.
        b = _billing()
        assert b.trial_days_for({"user_id": "u1", "stripe_customer_id": "cus_123"}) == 0

    def test_zero_days_switches_it_off_everywhere(self):
        # Set on Render to end the promotion without a deploy.
        b = _billing(days="0")
        assert b.TRIAL_DAYS == 0
        assert b.trial_days_for({"user_id": "u1"}) == 0

    def test_a_negative_or_junk_setting_is_no_trial_rather_than_a_crash(self):
        assert _billing(days="-5").TRIAL_DAYS == 0
        assert _billing(days="").TRIAL_DAYS == 0

    def test_the_length_is_whatever_is_configured(self):
        assert _billing(days="14").trial_days_for({"user_id": "u1"}) == 14

    def test_missing_user_fields_do_not_throw(self):
        b = _billing()
        assert b.trial_days_for({}) == 10
        assert b.trial_days_for(None) == 10


class TestCheckout:
    def test_the_trial_reaches_stripe_on_a_first_subscription(self, monkeypatch):
        b = _billing()
        captured = {}

        class _Session:
            @staticmethod
            def create(**kw):
                captured.update(kw)
                return type("S", (), {"url": "https://stripe.test/session"})()

        monkeypatch.setattr(b, "_stripe", lambda: type(
            "S", (), {"checkout": type("C", (), {"Session": _Session})})())
        b.create_checkout_session({"user_id": "u1", "email": "a@b.c"})
        assert captured["subscription_data"]["trial_period_days"] == 10

    def test_and_is_omitted_entirely_for_a_returning_customer(self, monkeypatch):
        # Omitted rather than sent as 0 — Stripe rejects trial_period_days=0, so a returning
        # customer would hit an error at checkout instead of simply paying.
        b = _billing()
        captured = {}

        class _Session:
            @staticmethod
            def create(**kw):
                captured.update(kw)
                return type("S", (), {"url": "https://stripe.test/session"})()

        monkeypatch.setattr(b, "_stripe", lambda: type(
            "S", (), {"checkout": type("C", (), {"Session": _Session})})())
        b.create_checkout_session({"user_id": "u1", "stripe_customer_id": "cus_9"})
        assert "trial_period_days" not in captured["subscription_data"]
        # ...and the account id still rides along, which is what links the payment back.
        assert captured["subscription_data"]["metadata"]["user_id"] == "u1"


class TestAccessDuringTrial:
    def test_a_trialing_subscription_counts_as_a_member(self):
        # This already held before the trial existed — `trialing` was in ACTIVE_STATUSES
        # from the start — and it is the reason nothing downstream needed changing. Pinned
        # so a later tidy-up of that tuple cannot silently lock out every trial member.
        b = _billing()
        assert b.is_active("trialing") is True
        assert "trialing" in b.ACTIVE_STATUSES

    def test_a_cancelled_one_does_not(self):
        b = _billing()
        assert b.is_active("canceled") is False
        assert b.is_active("unpaid") is False
        assert b.is_active(None) is False
