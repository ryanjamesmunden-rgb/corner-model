"""The rule this file exists to defend: a Stripe event must never revoke the wrong person.

Granting access wrongly costs money. Revoking it wrongly locks out someone who paid, who
then has no way to tell you what happened and every reason to charge back. The two are
not symmetrical, and `apply_subscription` is deliberately not symmetrical either — these
pin that asymmetry so a later tidy-up cannot "simplify" it away.
"""
import asyncio
import os
import sys

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "test_corner_model")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import billing  # noqa: E402


class FakeUsers:
    def __init__(self, rows):
        self.rows = rows

    async def find_one(self, query, projection=None):
        for r in self.rows:
            if all(r.get(k) == v for k, v in query.items()):
                return dict(r)
        return None

    async def update_one(self, query, update):
        for r in self.rows:
            if all(r.get(k) == v for k, v in query.items()):
                r.update(update["$set"])
                return
        raise AssertionError(f"update_one matched nothing: {query}")


class FakeDb:
    def __init__(self, rows):
        self.users = FakeUsers(rows)


def sub(status, user_id="u1", customer="cus_1", cancel_at_period_end=False):
    return {"id": "sub_1", "status": status, "customer": customer,
            "current_period_end": 1893456000, "cancel_at_period_end": cancel_at_period_end,
            "metadata": {"user_id": user_id}}


def run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def test_an_active_subscription_grants_membership():
    rows = [{"user_id": "u1", "member": False}]
    run(billing.apply_subscription(FakeDb(rows), sub("active")))
    assert rows[0]["member"] is True
    assert rows[0]["member_source"] == "stripe"
    assert rows[0]["stripe_customer_id"] == "cus_1"


def test_a_cancelled_subscription_revokes_a_stripe_member():
    rows = [{"user_id": "u1", "member": True, "member_source": "stripe"}]
    run(billing.apply_subscription(FakeDb(rows), sub("canceled")))
    assert rows[0]["member"] is False


def test_a_COMPED_member_is_never_revoked_by_stripe():
    """The failure that would hurt most: a comp with an old lapsed subscription."""
    rows = [{"user_id": "u1", "member": True, "member_source": "code"}]
    run(billing.apply_subscription(FakeDb(rows), sub("canceled")))
    assert rows[0]["member"] is True, "a comped member was revoked by a Stripe event"


def test_a_LEGACY_member_is_never_revoked_by_stripe():
    """Accounts that predate member_source have none. They must be left alone."""
    rows = [{"user_id": "u1", "member": True}]
    run(billing.apply_subscription(FakeDb(rows), sub("canceled")))
    assert rows[0]["member"] is True, "a legacy member was revoked by a Stripe event"


def test_past_due_keeps_access_while_stripe_retries():
    """A failed renewal is a retry window, not a cancellation. Locking someone out on
    the first failed charge turns a payment blip into a support ticket."""
    rows = [{"user_id": "u1", "member": True, "member_source": "stripe"}]
    run(billing.apply_subscription(FakeDb(rows), sub("past_due")))
    assert rows[0]["member"] is True
    assert rows[0]["subscription_status"] == "past_due"


def test_unpaid_ends_access():
    rows = [{"user_id": "u1", "member": True, "member_source": "stripe"}]
    run(billing.apply_subscription(FakeDb(rows), sub("unpaid")))
    assert rows[0]["member"] is False


def test_cancel_at_period_end_keeps_access_until_it_ends():
    """Cancelled but paid up. They keep what they bought, and the account page says so."""
    rows = [{"user_id": "u1", "member": True, "member_source": "stripe"}]
    run(billing.apply_subscription(FakeDb(rows), sub("active", cancel_at_period_end=True)))
    assert rows[0]["member"] is True
    assert rows[0]["cancel_at_period_end"] is True


def test_an_event_for_nobody_changes_nothing():
    """A test payment, or a customer deleted on our side. Logged, not applied."""
    rows = [{"user_id": "u1", "member": True, "member_source": "stripe"}]
    out = run(billing.apply_subscription(FakeDb(rows), sub("canceled", user_id="ghost",
                                                           customer="cus_other")))
    assert out["matched"] is False
    assert rows[0]["member"] is True


def test_matching_falls_back_to_customer_id_when_metadata_is_missing():
    """Subscriptions created before the metadata was added still have to resolve."""
    rows = [{"user_id": "u1", "member": True, "member_source": "stripe",
             "stripe_customer_id": "cus_1"}]
    s = sub("canceled")
    s["metadata"] = {}
    run(billing.apply_subscription(FakeDb(rows), s))
    assert rows[0]["member"] is False


def test_active_statuses_are_the_ones_documented():
    assert billing.is_active("active") and billing.is_active("trialing")
    assert billing.is_active("past_due")
    assert not billing.is_active("canceled")
    assert not billing.is_active("unpaid")
    assert not billing.is_active("incomplete_expired")


class FakeUsersMany(FakeUsers):
    """update_many and count_documents, for the grandfathering migration."""

    async def count_documents(self, query):
        n = 0
        for r in self.rows:
            if all(r.get(k) == v for k, v in query.items()):
                n += 1
        return n

    async def update_many(self, query, update):
        n = 0
        for r in self.rows:
            ok = True
            for k, v in query.items():
                if isinstance(v, dict) and "$exists" in v:
                    if (k in r) != v["$exists"]:
                        ok = False
                elif r.get(k) != v:
                    ok = False
            if ok:
                r.update(update["$set"])
                n += 1
        return type("R", (), {"modified_count": n})()


class FakeDbMany(FakeDb):
    def __init__(self, rows):
        self.users = FakeUsersMany(rows)


def test_grandfathering_marks_existing_members_and_skips_everyone_else():
    rows = [
        {"user_id": "old", "member": True},                                  # pre-existing
        {"user_id": "comp", "member": True, "member_source": "code"},        # already tagged
        {"user_id": "none", "member": False},                                # not a member
    ]
    out = run(billing.grandfather_existing_members(FakeDbMany(rows)))
    assert out["grandfathered"] == 1
    assert rows[0]["grandfathered"] is True and rows[0]["member_source"] == "legacy"
    assert "grandfathered" not in rows[1]
    assert "grandfathered" not in rows[2]


def test_grandfathering_is_idempotent():
    """It runs on every boot. The second run must do nothing."""
    rows = [{"user_id": "old", "member": True}]
    db = FakeDbMany(rows)
    assert run(billing.grandfather_existing_members(db))["grandfathered"] == 1
    assert run(billing.grandfather_existing_members(db))["grandfathered"] == 0


def test_it_reports_how_many_are_protected_even_when_it_changed_nothing():
    """The boot log is what an operator reads before enabling the Stripe webhook. A run
    that changed nothing still has to say how many accounts are covered, or "no line in
    the log" cannot be told apart from "the migration never ran"."""
    rows = [{"user_id": "old", "member": True}]
    db = FakeDbMany(rows)
    run(billing.grandfather_existing_members(db))
    second = run(billing.grandfather_existing_members(db))
    assert second["grandfathered"] == 0
    assert second["protected"] == 1 and second["members"] == 1


def test_a_grandfathered_member_survives_a_cancellation():
    rows = [{"user_id": "u1", "member": True, "member_source": "legacy", "grandfathered": True}]
    run(billing.apply_subscription(FakeDb(rows), sub("canceled")))
    assert rows[0]["member"] is True


def test_a_grandfathered_member_who_subscribes_then_cancels_keeps_their_old_access():
    """The case that would be cruellest to get wrong: they had it for free, they paid you
    anyway, they stopped paying — they must land back where they started, not locked out."""
    rows = [{"user_id": "u1", "member": True, "member_source": "legacy", "grandfathered": True}]
    db = FakeDb(rows)
    run(billing.apply_subscription(db, sub("active")))
    assert rows[0]["member_source"] == "stripe"
    assert rows[0]["grandfathered"] is True, "the mark was cleared by subscribing"
    run(billing.apply_subscription(db, sub("canceled")))
    assert rows[0]["member"] is True, "a grandfathered member lost access after cancelling"
