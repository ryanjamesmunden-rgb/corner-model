"""Stripe subscriptions, and the one rule that matters: never revoke the wrong person.

WHY THIS EXISTS. Membership used to be a shared code posted in the Telegram, redeemed
once per account. That worked, but it left Stripe and the site with no link between them:
the site could not tell you whether you were subscribed, could not let you cancel, and —
because `member: True` was set once and never cleared — could not tell that you HAD
cancelled. People who stopped paying kept full access, and people who wanted to stop
paying had nowhere on the site to do it. The second half of that is a consumer-rights
problem as much as a product one; the first is a straight revenue leak.

THE MODEL. A subscription is bought through a Checkout Session created by us, so it
carries `client_reference_id` — the site's own user id. Stripe's webhook tells us when it
starts, renews, lapses or is cancelled, and Stripe's Billing Portal handles the
cancellation itself, which is why there is no "cancel" code here at all: card details and
cancellations stay on Stripe's pages, where they are already compliant.

MEMBERSHIP HAS A SOURCE, and this is the safety rule the whole module is built around.
`member_source` is "stripe" for a paid subscription, "code" for a comp, and missing for
the accounts that predate all of this. A webhook may only ever clear membership for an
account whose source is "stripe" AND whose customer id matches the event. A comped
account and a legacy account can never be revoked by a Stripe event, however that event
is shaped — because the alternative is a bad webhook silently locking out people who
paid you, and they would have no way to tell you what happened.
"""
import logging
import os
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)

STRIPE_SECRET_KEY = os.environ.get("STRIPE_SECRET_KEY", "").strip()
STRIPE_PRICE_ID = os.environ.get("STRIPE_PRICE_ID", "").strip()
STRIPE_WEBHOOK_SECRET = os.environ.get("STRIPE_WEBHOOK_SECRET", "").strip()
# Where Stripe sends people back to. The frontend origin, not the API's.
SITE_URL = os.environ.get("SITE_URL", "").strip().rstrip("/")

# Statuses Stripe considers a live, paid subscription. `past_due` is deliberately IN:
# a failed renewal starts a retry window, and locking someone out on the first failed
# charge — while Stripe is still retrying and may well succeed — turns a payment blip
# into a support ticket. Stripe moves it to `canceled` or `unpaid` when it gives up,
# and those are the ones that end access.
ACTIVE_STATUSES = ("active", "trialing", "past_due")

MEMBER_SOURCE_STRIPE = "stripe"
MEMBER_SOURCE_CODE = "code"
MEMBER_SOURCE_LEGACY = "legacy"


def configured() -> bool:
    """Whether checkout can run at all. Missing config is a 503, not a crash."""
    return bool(STRIPE_SECRET_KEY and STRIPE_PRICE_ID)


def _stripe():
    """Imported lazily so the app still boots with Stripe uninstalled or unconfigured.

    Everything else on the site is public and must keep working; a billing dependency
    that can take the whole API down on import is a bad trade for a paid extra."""
    import stripe
    stripe.api_key = STRIPE_SECRET_KEY
    return stripe


def is_active(status: Optional[str]) -> bool:
    return status in ACTIVE_STATUSES


def create_checkout_session(user: dict) -> str:
    """A Checkout Session tied to THIS account, and the reason sign-in comes first.

    `client_reference_id` carries our user id through Stripe and back on the webhook,
    which is what the old Payment Link could never do: it took the money and told us
    nothing about who had paid. `customer_email` prefills the form but is never used to
    match accounts — the address on the card is routinely not the one someone signs in
    with, and matching on it is how a paying member ends up locked out.
    """
    stripe = _stripe()
    existing = user.get("stripe_customer_id")
    session = stripe.checkout.Session.create(
        mode="subscription",
        line_items=[{"price": STRIPE_PRICE_ID, "quantity": 1}],
        client_reference_id=user["user_id"],
        # Reuse the customer when we already have one, so a resubscribe lands on the
        # same Stripe customer rather than creating a second one with the same email.
        **({"customer": existing} if existing else {"customer_email": user.get("email")}),
        success_url=f"{SITE_URL}/account?checkout=success",
        cancel_url=f"{SITE_URL}/join?checkout=cancelled",
        allow_promotion_codes=True,
        # So a cancellation made in the portal reaches us even if the customer never
        # returns to the site.
        subscription_data={"metadata": {"user_id": user["user_id"]}},
        metadata={"user_id": user["user_id"]},
    )
    return session.url


def create_portal_session(customer_id: str) -> str:
    """Stripe's own billing portal: cancel, change card, download invoices.

    Cancellation is not implemented here on purpose. Stripe's portal is hosted, already
    handles the confirmation flow and the proration rules, and keeps card details off
    this codebase entirely. Writing our own cancel button would mean owning all of that
    to end up somewhere worse.
    """
    return _stripe().billing_portal.Session.create(
        customer=customer_id,
        return_url=f"{SITE_URL}/account",
    ).url


def set_cancel_at_period_end(subscription_id: str, cancelling: bool) -> dict:
    """Schedule a cancellation, or call one off. Returns the updated subscription.

    AT PERIOD END, NEVER IMMEDIATELY. Someone cancelling on day 2 of a month they have
    paid for should keep the other 28 days — ending it there and then would be taking
    money for nothing and would turn every cancellation into a refund conversation.
    Stripe stops billing at the end of the period and access follows.

    Reversible on purpose: `cancelling=False` puts the subscription back. A cancellation
    that cannot be undone without contacting you is the same trap as a cancellation that
    cannot be done without contacting you, only pointed the other way.
    """
    return _stripe().Subscription.modify(subscription_id, cancel_at_period_end=cancelling)


def verify_event(payload: bytes, signature: Optional[str]) -> dict:
    """Parse a webhook, or raise.

    The signature check is not optional and there is no unsigned fallback. This endpoint
    grants and revokes paid access and is open to the internet by necessity — Stripe
    cannot authenticate to us. Without verification, anyone who finds the URL can post
    themselves a subscription, or post one that cancels somebody else's.
    """
    if not STRIPE_WEBHOOK_SECRET:
        raise RuntimeError("STRIPE_WEBHOOK_SECRET is not set — refusing to trust a webhook")
    stripe = _stripe()
    return stripe.Webhook.construct_event(payload, signature, STRIPE_WEBHOOK_SECRET)


def _sub_fields(sub: dict) -> dict:
    status = sub.get("status")
    period_end = sub.get("current_period_end")
    return {
        "stripe_subscription_id": sub.get("id"),
        "subscription_status": status,
        "subscription_ends_at": (
            datetime.fromtimestamp(period_end, tz=timezone.utc).isoformat() if period_end else None
        ),
        # Set when someone cancels but has paid to the end of the period — they keep
        # access until then, and the account page says so rather than implying they were
        # cut off early.
        "cancel_at_period_end": bool(sub.get("cancel_at_period_end")),
    }


async def grandfather_existing_members(db) -> dict:
    """Stamp everyone who already had access, once, so a later change cannot take it.

    Before this, membership was a flag with no provenance. That was survivable while
    nothing could clear the flag; it stops being survivable the moment a webhook can.
    Someone who paid last year and has no Stripe subscription must not be revoked by an
    event, and "has no member_source" is too fragile a thing to rest that on — one later
    code path setting the field for an unrelated reason would quietly remove the
    protection from every one of them.

    So they are marked explicitly, and `grandfathered` is checked directly by
    apply_subscription rather than being inferred from what a document lacks.

    Runs on boot and is idempotent: the query matches only members not yet stamped, so
    the second and every subsequent boot is a no-op. On boot rather than in a script
    because a migration you have to remember to run is a migration that gets forgotten,
    and the cost of forgetting this one is locking out paying customers.
    """
    res = await db.users.update_many(
        {"member": True, "member_source": {"$exists": False}},
        {"$set": {"member_source": MEMBER_SOURCE_LEGACY, "grandfathered": True,
                  "grandfathered_at": datetime.now(timezone.utc).isoformat()}},
    )
    # ALWAYS LOGGED, including when it changed nothing.
    #
    # This line is what an operator reads to decide whether it is safe to point Stripe's
    # webhook at this deploy. Logging only when modified_count > 0 made "no line in the
    # log" mean either "ran fine, nothing to do" or "never ran at all" — and those want
    # opposite responses, one of them being "do not enable the webhook yet". A check
    # whose negative result is ambiguous is not a check.
    protected = await db.users.count_documents({"member": True, "grandfathered": True})
    members = await db.users.count_documents({"member": True})
    logger.info("billing: grandfathering complete — %d newly marked, %d of %d member(s) "
                "now protected from Stripe revocation", res.modified_count, protected, members)
    return {"grandfathered": res.modified_count, "protected": protected, "members": members}


async def apply_subscription(db, sub: dict, user_id: Optional[str] = None) -> dict:
    """Bring one account's membership into line with one Stripe subscription.

    Finds the account by the subscription's metadata, then its customer id — never by
    email, for the reason given in create_checkout_session.

    THE REVOCATION RULE. Membership is only ever taken away from an account whose
    `member_source` is "stripe" AND which is not grandfathered. A comp, a legacy account,
    and anyone who had access before billing existed are left alone even when a Stripe
    event says otherwise, because a wrongly-matched event must not be able to lock out
    someone who paid. Granting is safe in a way revoking is not, so the two are not
    symmetrical here and should not be made so.

    Grandfathering outranks the source deliberately. Someone who had access before, then
    later subscribes, keeps what they already had if they cancel — they are not made
    worse off by having paid you.
    """
    customer_id = sub.get("customer")
    uid = user_id or (sub.get("metadata") or {}).get("user_id")
    query = {"user_id": uid} if uid else {"stripe_customer_id": customer_id}
    account = await db.users.find_one(query, {"_id": 0})
    if not account and customer_id:
        account = await db.users.find_one({"stripe_customer_id": customer_id}, {"_id": 0})
    if not account:
        logger.warning("stripe: no account for subscription %s (customer %s)",
                       sub.get("id"), customer_id)
        return {"matched": False}

    fields = {**_sub_fields(sub), "stripe_customer_id": customer_id}
    active = is_active(sub.get("status"))

    if active:
        fields["member"] = True
        # The source becomes "stripe" because that is now true, but `grandfathered` is
        # never unset — see the revocation rule above.
        fields["member_source"] = MEMBER_SOURCE_STRIPE
        if not account.get("member_since"):
            fields["member_since"] = datetime.now(timezone.utc).isoformat()
    elif account.get("grandfathered"):
        # Had access before any of this existed. Nothing Stripe says can take it away —
        # including a cancellation of a subscription they took out later.
        logger.info("stripe: subscription %s ended but %s is grandfathered — access kept",
                    sub.get("id"), account["user_id"])
    elif account.get("member_source") == MEMBER_SOURCE_STRIPE:
        # Their access came from this subscription, and the subscription has ended.
        fields["member"] = False
        fields["member_ended_at"] = datetime.now(timezone.utc).isoformat()
    else:
        # A comp that also happens to have a lapsed subscription. Record the subscription
        # state, change nothing about their access.
        logger.info("stripe: subscription %s lapsed but %s is a %s member — access kept",
                    sub.get("id"), account["user_id"], account.get("member_source") or "legacy")

    await db.users.update_one({"user_id": account["user_id"]}, {"$set": fields})
    return {"matched": True, "user_id": account["user_id"],
            "member": fields.get("member", account.get("member")), "status": sub.get("status")}
