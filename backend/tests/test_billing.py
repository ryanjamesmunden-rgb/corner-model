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

    async def update_many(self, query, update):
        """Enough of Mongo's matcher for the backfill: equality plus $exists and $ne."""
        def matches(row, key, cond):
            if not isinstance(cond, dict):
                return row.get(key) == cond
            ok = True
            if "$exists" in cond:
                ok = ok and ((key in row) == cond["$exists"])
            if "$ne" in cond:
                ok = ok and row.get(key) != cond["$ne"]
            return ok

        n = 0
        for r in self.rows:
            if all(matches(r, k, v) for k, v in query.items()):
                r.update(update["$set"])
                n += 1
        return type("Res", (), {"modified_count": n})()


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


# ---------------------------------------------------------------------------
# One account, two subscriptions
# ---------------------------------------------------------------------------
# FOUND WHILE REFUNDING A DOUBLE CHARGE. Nothing stops a member subscribing twice — a
# second checkout on the same account is an ordinary Stripe subscription — but this module
# stores a single `stripe_subscription_id` and so cannot represent the pair. The damage
# lands on cancellation: the dead subscription's event arrives and revokes an account that
# is still being charged on the live one.
#
# It is not only the double-subscribe case. Cancel and immediately resubscribe produces the
# same two subscriptions, and there the old one's deletion event wipes the new membership.
#
# These pin the asymmetry this file exists for, one level further out: it is not enough to
# refuse to revoke comps and grandfathered accounts. A Stripe member with another live
# subscription must not be revoked either.

def sub2(status, sub_id="sub_2", user_id="u1", customer="cus_1"):
    return {"id": sub_id, "status": status, "customer": customer,
            "current_period_end": 1893456000, "cancel_at_period_end": False,
            "metadata": {"user_id": user_id}}


def with_other_subs(monkeypatch, others, configured=True):
    """Pretend Stripe holds `others` for the customer.

    Mirrors the real active_subscriptions, is_active filter included — a stub that
    returned cancelled siblings would let every revocation test pass by accident.
    """
    monkeypatch.setattr(billing, "configured", lambda: configured)
    monkeypatch.setattr(billing, "active_subscriptions",
                        lambda cid, exclude_id=None: [
                            s for s in others
                            if s.get("id") != exclude_id and billing.is_active(s.get("status"))])


def test_cancelling_one_of_two_subscriptions_keeps_access(monkeypatch):
    """The double-charge case. They are still paying on the other one."""
    live = sub2("active", "sub_live")
    with_other_subs(monkeypatch, [live])
    rows = [{"user_id": "u1", "member": True, "member_source": "stripe",
             "stripe_subscription_id": "sub_dead"}]
    run(billing.apply_subscription(FakeDb(rows), sub2("canceled", "sub_dead")))
    assert rows[0]["member"] is True


def test_the_account_then_describes_the_subscription_keeping_them_in(monkeypatch):
    """Not the one that ended.

    Leaving the dead id on the record shows a cancelled subscription on the account page of
    an active member — and hands the NEXT cancellation the wrong id to exclude itself by,
    so the check would compare the live subscription against itself and find no survivor.
    """
    live = sub2("active", "sub_live")
    with_other_subs(monkeypatch, [live])
    rows = [{"user_id": "u1", "member": True, "member_source": "stripe"}]
    run(billing.apply_subscription(FakeDb(rows), sub2("canceled", "sub_dead")))
    assert rows[0]["stripe_subscription_id"] == "sub_live"
    assert rows[0]["subscription_status"] == "active"


def test_a_past_due_sibling_still_counts(monkeypatch):
    """A card retrying is not a cancelled subscription.

    ACTIVE_STATUSES covers trialing and past_due, so asking Stripe for status="active"
    would revoke a member whose other payment is mid-retry.
    """
    with_other_subs(monkeypatch, [sub2("past_due", "sub_live")])
    rows = [{"user_id": "u1", "member": True, "member_source": "stripe"}]
    run(billing.apply_subscription(FakeDb(rows), sub2("canceled", "sub_dead")))
    assert rows[0]["member"] is True


def test_a_cancelled_sibling_does_not_rescue_them(monkeypatch):
    """Both ended. This is a genuine revocation and must still happen."""
    with_other_subs(monkeypatch, [sub2("canceled", "sub_older")])
    rows = [{"user_id": "u1", "member": True, "member_source": "stripe"}]
    run(billing.apply_subscription(FakeDb(rows), sub2("canceled", "sub_dead")))
    assert rows[0]["member"] is False
    assert rows[0]["member_ended_at"]


def test_the_ending_subscription_cannot_rescue_itself(monkeypatch):
    """It must be excluded from its own survivor check.

    Stripe lists a just-cancelled subscription among the customer's subscriptions. Without
    the exclusion the lookup finds it, reads its own status, and nobody is ever revoked.
    """
    dead = sub2("canceled", "sub_dead")
    with_other_subs(monkeypatch, [dead])
    rows = [{"user_id": "u1", "member": True, "member_source": "stripe"}]
    run(billing.apply_subscription(FakeDb(rows), dead))
    assert rows[0]["member"] is False


def test_stripe_being_unreachable_is_not_a_revocation(monkeypatch):
    """Granting is safe in a way revoking is not — the rule this file exists for.

    "Asked, and there is no other subscription" is a revocation. "Could not ask" is not.
    The quarter-hourly reconcile retries, so erring toward access self-corrects; erring
    the other way locks out someone who paid, during an outage they did not cause.
    """
    monkeypatch.setattr(billing, "configured", lambda: True)

    def boom(cid, exclude_id=None):
        raise RuntimeError("stripe is down")

    monkeypatch.setattr(billing, "active_subscriptions", boom)
    rows = [{"user_id": "u1", "member": True, "member_source": "stripe"}]
    run(billing.apply_subscription(FakeDb(rows), sub2("canceled", "sub_dead")))
    assert rows[0]["member"] is True
    assert "member_ended_at" not in rows[0]


def test_billing_switched_off_still_revokes(monkeypatch):
    """Not-configured is a real answer, not a failed check.

    With no Stripe there is no second subscription to find. Treating that as "unknown"
    would mean no Stripe member could ever be revoked in a deployment with billing off.
    """
    with_other_subs(monkeypatch, [], configured=False)
    rows = [{"user_id": "u1", "member": True, "member_source": "stripe"}]
    run(billing.apply_subscription(FakeDb(rows), sub2("canceled", "sub_dead")))
    assert rows[0]["member"] is False


def test_a_comp_with_two_subscriptions_is_still_never_revoked(monkeypatch):
    """The original asymmetry outranks all of this, and is checked first."""
    with_other_subs(monkeypatch, [])
    rows = [{"user_id": "u1", "member": True, "member_source": "comp"}]
    run(billing.apply_subscription(FakeDb(rows), sub2("canceled", "sub_dead")))
    assert rows[0]["member"] is True
