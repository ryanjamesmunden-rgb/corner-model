"""Did anybody try to subscribe and not get through?

WHY THE CLASSIFICATION HAS TO BE EXACT. The whole audit rests on one field meaning one
thing: `stripe_customer_id` is written BEFORE the redirect to Stripe, so it means "has
opened checkout at least once" and NOT "has subscribed". billing.trial_days_for carries the
same warning for the same reason — keying a trial on that field once denied a free week to
everybody who started a checkout and thought better of it.

Read it the old way and this file answers the opposite question: every abandoned checkout
becomes a member and every real failure disappears.

WHAT THESE GUARD:

  - An account that opened checkout and never finished is counted as exactly that — not as
    a member, not as lapsed, not as somebody who never tried.
  - A comped member is not counted as a checkout at all. They never went near Stripe.
  - A lapsed subscriber is not an unfinished checkout. They got through once; that is the
    opposite finding.
  - The window report says who is actually blocked, which is the part everybody reads
    wrongly: "scope=trial" sounds like "anyone willing to pay may join any day", and what it
    really means is that only RETURNING ex-subscribers may.
"""
import os
import sys
from datetime import datetime, timedelta, timezone

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "test_corner_model")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import audit_signups as audit  # noqa: E402
import billing  # noqa: E402
import signup  # noqa: E402

NOW = datetime(2026, 9, 28, 12, 0, tzinfo=timezone.utc)


def user(**kw):
    base = {"user_id": "u1", "email": "a@b.c", "name": "A"}
    return {**base, **kw}


def ago(hours):
    return (NOW - timedelta(hours=hours)).isoformat()


class TestWhoGotHowFar:
    def test_a_paying_member_is_a_member(self):
        u = user(member=True, member_source=billing.MEMBER_SOURCE_STRIPE,
                 stripe_customer_id="cus_1", had_subscription=True)
        assert audit.classify([u], NOW)["members"] == [u]

    def test_an_opened_checkout_that_never_finished_is_its_own_group(self):
        # THE LOAD-BEARING CASE. The customer is written before the redirect, so this is
        # somebody who reached the payment page and did not come back.
        u = user(stripe_customer_id="cus_2")
        g = audit.classify([u], NOW)
        assert g["unfinished"] == [u]
        assert g["members"] == [] and g["lapsed"] == []

    def test_a_lapsed_subscriber_is_not_an_unfinished_checkout(self):
        # They got through once. Counting them here would turn a success into a failure.
        u = user(stripe_customer_id="cus_3", had_subscription=True)
        g = audit.classify([u], NOW)
        assert g["lapsed"] == [u]
        assert g["unfinished"] == []

    def test_somebody_who_never_opened_checkout_is_not_a_failure(self):
        g = audit.classify([user()], NOW)
        assert len(g["never_started"]) == 1
        assert g["unfinished"] == []

    def test_a_comped_member_is_not_a_checkout_at_all(self):
        # member_source "code" never went near Stripe, so they belong in no bucket here.
        u = user(member=True, member_source="code")
        g = audit.classify([u], NOW)
        assert all(u not in rows for rows in g.values())

    def test_every_account_lands_somewhere_or_is_deliberately_dropped(self):
        rows = [user(user_id="a", member=True, member_source=billing.MEMBER_SOURCE_STRIPE),
                user(user_id="b", stripe_customer_id="c"),
                user(user_id="c", stripe_customer_id="c", had_subscription=True),
                user(user_id="d")]
        g = audit.classify(rows, NOW)
        assert sum(len(v) for v in g.values()) == 4


class TestHowLongAgoTheyTried:
    def test_the_oldest_attempt_is_listed_first(self):
        rows = audit.unfinished_rows(
            [user(user_id="new", stripe_customer_id="c", created_at=ago(2)),
             user(user_id="old", stripe_customer_id="c", created_at=ago(200))], NOW)
        assert [r["user_id"] for r in rows] == ["old", "new"]

    def test_a_checkout_within_the_day_is_not_called_stale(self):
        # Stripe's own session lives 24h. Before that they may simply still be deciding.
        rows = audit.unfinished_rows(
            [user(stripe_customer_id="c", created_at=ago(3))], NOW)
        assert rows[0]["stale"] is False

    def test_and_one_older_than_a_day_is(self):
        rows = audit.unfinished_rows(
            [user(stripe_customer_id="c", created_at=ago(30))], NOW)
        assert rows[0]["stale"] is True

    def test_an_account_with_no_date_is_treated_as_stale_rather_than_dropped(self):
        # Unknown age must not read as "just now", which would hide the oldest cases.
        rows = audit.unfinished_rows([user(stripe_customer_id="c")], NOW)
        assert rows[0]["stale"] is True
        assert rows[0]["age_h"] is None


class TestTheWindowIsExplained:
    def test_an_open_door_is_reported_as_open(self, monkeypatch):
        # The shipped default. The audit's first job is to say plainly that nobody is being
        # turned away, because "is the window shutting people out" is the question it exists
        # to answer and the expensive wrong answer is a shrug.
        monkeypatch.setattr(signup, "SIGNUP_DAY", 0)
        lines, closed = audit.window_report()
        assert "OFF" in lines[0] and "any day" in lines[0]
        assert closed is False

    def test_it_names_the_day_and_the_scope_when_there_is_one(self, monkeypatch):
        monkeypatch.setattr(signup, "SIGNUP_DAY", 1)
        text = " ".join(audit.window_report()[0])
        assert "SIGNUP_DAY=1" in text
        assert f"SIGNUP_SCOPE={signup.SIGNUP_SCOPE}" in text

    def test_it_says_a_new_visitor_is_limited_to_the_open_day(self, monkeypatch):
        # THE SENTENCE THAT MATTERS. "scope=trial" reads as "anyone paying full price may
        # join any day", and that is not what it does: a new visitor cannot decline a trial,
        # so they wait. Only returning ex-subscribers get through.
        monkeypatch.setattr(signup, "SIGNUP_DAY", 1)
        monkeypatch.setattr(signup, "SIGNUP_SCOPE", "trial")
        monkeypatch.setattr(billing, "TRIAL_DAYS", 7)
        text = " ".join(audit.window_report()[0])
        assert "only subscribe on Monday" in text
        assert "Returning ex-subscribers" in text

    def test_scope_all_is_reported_as_blocking_everybody(self, monkeypatch):
        monkeypatch.setattr(signup, "SIGNUP_DAY", 3)
        monkeypatch.setattr(signup, "SIGNUP_SCOPE", "all")
        text = " ".join(audit.window_report()[0])
        assert "NOBODY subscribes except on Wednesday" in text

    def test_no_trial_means_the_window_blocks_nobody(self, monkeypatch):
        # scope=trial with TRIAL_DAYS=0 is a window that cannot fire. Reporting it as open
        # for business is the honest reading.
        monkeypatch.setattr(signup, "SIGNUP_DAY", 1)
        monkeypatch.setattr(signup, "SIGNUP_SCOPE", "trial")
        monkeypatch.setattr(billing, "TRIAL_DAYS", 0)
        assert "effectively off" in " ".join(audit.window_report()[0])

    def test_a_disabled_window_says_so_and_stops(self, monkeypatch):
        monkeypatch.setattr(signup, "SIGNUP_DAY", 0)
        lines, closed = audit.window_report()
        assert "OFF" in lines[0]
        assert closed is False
