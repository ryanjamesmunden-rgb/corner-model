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

# THE FREE TRIAL. `trialing` was already in ACTIVE_STATUSES above, so a trial has always
# granted access correctly — nothing downstream needed changing to add one. What was
# missing was anything that starts one.
#
# CARD UP FRONT, WHICH IS WHY THIS IS A TRIAL AND NOT A GIVEAWAY. Stripe collects the card
# at checkout, charges nothing for TRIAL_DAYS, then bills automatically unless the person
# cancels. A trial with no card is a mailing list: almost nobody comes back to enter one,
# and you cannot tell the people who decided to stay from the ones who simply forgot.
#
# Set TRIAL_DAYS=0 to turn it off without a deploy, or to any other length to change it.
# The default is the offer as advertised, so an unset variable is the right offer rather
# than a different one — a page and a checkout disagreeing about the length is the exact
# failure /api/config exists to prevent.
TRIAL_DAYS = max(0, int(os.environ.get("TRIAL_DAYS", "7") or 0))

MEMBER_SOURCE_STRIPE = "stripe"
MEMBER_SOURCE_CODE = "code"
MEMBER_SOURCE_LEGACY = "legacy"


def _present() -> bool:
    """Both variables filled in. Says nothing about whether the values are any good."""
    return bool(STRIPE_SECRET_KEY and STRIPE_PRICE_ID)


def configured() -> bool:
    """Whether checkout can run. Missing or malformed config is a 503, not a crash.

    THIS DECIDES WHAT THE JOIN PAGE OFFERS, via /api/config's `stripe_ready`, and that is
    why it is stricter than "the variable is non-empty". With a key of `sk_live_` and
    nothing after it, non-empty was true: the page advertised a free trial, sent people
    into a checkout that could not start, and gave them a red error over a payment form
    with no way forward. The fallback to the old payment link — which is right there, and
    works — was never reached, because the flag said everything was fine.
    So a key that cannot possibly work counts as not configured, and the page falls back on
    its own. When the real key is pasted in, it switches back on its own too.

    NO NETWORK CALL, DELIBERATELY. This runs on every page load, and a deterministic local
    test cannot flap: a blip at Stripe must never silently reshape the join page. It is a
    test of SHAPE, not of validity — a well-formed key that Stripe has since revoked passes
    here and fails at `check()`, which is the endpoint that asks Stripe and is run
    deliberately rather than by every visitor.
    """
    if not _present():
        return False
    shape = key_shape()
    return not (shape["truncated"] or shape["whitespace"])


# THE SHAPE OF A SECRET KEY, which is checkable without asking Stripe anything.
#
# FOUND LIVE, and it is worth being precise about the failure because the whole diagnostic
# had reported this setup as fine. The key in the environment was `sk_live_` and nothing
# else — a copy that took the visible prefix and left the secret behind, which is easy to
# do because the dashboard shows exactly that prefix next to a Reveal button. Every check
# that existed said "Stripe checkout: live", because every check that existed asked whether
# the variable was non-empty. It was non-empty. It was also eight characters long.
#
# A length test costs nothing, needs no network, and separates the two failures that want
# completely different fixes: "you have pasted the wrong thing" and "Stripe has rejected
# the right thing". Real keys are around a hundred characters; the floor is set far below
# that so it can only ever fire on something that is obviously not a key.
KEY_PREFIXES = ("sk_live_", "sk_test_", "rk_live_", "rk_test_")
MIN_KEY_LENGTH = 32

# AND THE SAME TEST FOR THE PRICE ID, because the same paste went wrong twice.
#
# The truncation check was written for the secret key and only for the secret key. So when
# STRIPE_PRICE_ID turned out to be `price_` — prefix kept, identifier lost, exactly the
# failure already diagnosed once — it sailed past every local check and had to be found by
# Stripe answering "No such price: 'price_'". A whole deploy cycle to learn a fact that was
# sitting in the variable all along.
#
# The lesson generalises: a check written against ONE instance of a mistake will not catch
# its twin in the next field along. Real price ids are around thirty characters.
MIN_PRICE_ID_LENGTH = 12


def key_shape() -> dict:
    """What the configured key LOOKS like. Never the key itself.

    Returns the prefix, the length and the two ways a paste goes wrong. Length is safe to
    report — every Stripe key of a given kind is much the same length, so it identifies
    nothing — and it is the single most useful number when a key does not work.
    """
    key = STRIPE_SECRET_KEY
    prefix = next((p for p in KEY_PREFIXES if key.startswith(p)), "")
    return {
        "set": bool(key),
        # A key with no recognised prefix is reported by its first few characters so the
        # answer to "is that even a Stripe key" is visible without printing the value.
        "prefix": prefix or (key[:8] + "…" if key else ""),
        "mode": "live" if "_live_" in prefix else ("test" if "_test_" in prefix else ""),
        "restricted": prefix.startswith("rk_"),
        "length": len(key),
        # The one this session actually hit.
        "truncated": bool(key) and len(key) < MIN_KEY_LENGTH,
        # A value that picked up a line break on the way into the dashboard. Leading and
        # trailing space is already stripped at import, so anything left is in the middle,
        # where stripping cannot help and the key is simply wrong.
        "whitespace": any(c.isspace() for c in key),
    }


def _as_dict(obj) -> dict:
    """A Stripe resource as a plain dict.

    FOUND LIVE, AND IT ACCUSED THE WRONG THING. `account.get("id")` raises on recent
    stripe-python — its resources are objects, not dicts — and the except around it reported
    "Stripe rejected the key". The key was fine. A newly rotated, correctly pasted key was
    reported as refused by Stripe, which is the worst possible direction for this particular
    check to be wrong in: it sends somebody back to roll a key that already works.

    The tests missed it because they stand in plain dicts for Stripe's objects, and dicts
    have .get. So there is now a test using an object that has to_dict and NOT get.
    """
    if isinstance(obj, dict):  # older stripe-python subclasses dict
        return obj
    # RECURSIVE FIRST. to_dict() converts the top level and leaves nested resources as
    # objects — so an Event converted with it hands back event["data"]["object"] as the
    # very thing that raises on .get, one level down from where anybody looked. That is
    # precisely how the webhook handler was still crashing: the outer layer was a dict.
    for name in ("to_dict_recursive", "to_dict"):
        fn = getattr(obj, name, None)
        if callable(fn):
            try:
                return fn()
            except Exception:
                continue
    return {}


def fetch_subscription(subscription_id: str) -> dict:
    """One subscription, as a plain dict. The only way server.py should read one."""
    return _as_dict(_stripe().Subscription.retrieve(subscription_id))


def _money(amount, currency: str) -> str:
    """`2000`, `gbp` → `£20.00`. For a human reading a checklist, not for arithmetic."""
    if amount is None:
        return ""
    symbol = {"gbp": "£", "usd": "$", "eur": "€"}.get((currency or "").lower())
    return (f"{symbol}{amount / 100:.2f}" if symbol
            else f"{amount / 100:.2f} {(currency or '').upper()}")


def check() -> dict:
    """Ask Stripe whether this configuration actually works. For the diagnostic only.

    NOT ON /api/config. This makes two live API calls, and /api/config is fetched by every
    visitor on every page load; wiring a Stripe round trip into that would put an outage at
    Stripe in the path of the whole site to answer a question that changes when somebody
    edits an environment variable. It is gated behind the tools token instead, where it is
    run deliberately.
    """
    out = {
        "key": key_shape(),
        "price_id_set": bool(STRIPE_PRICE_ID),
        "webhook_secret_set": bool(STRIPE_WEBHOOK_SECRET),
        "site_url": SITE_URL,
        # SET BEFORE ANY EARLY RETURN, and this needed fixing the day it was written. The
        # SITE_URL test lived below the key checks, so while the key was broken the field
        # was never populated and the checklist could not print the row at all — meaning
        # the exact sequential discovery it was added to prevent: fix the key, redeploy,
        # find out about SITE_URL, redeploy again.
        "site_url_ok": SITE_URL.startswith(("http://", "https://")),
        "trial_days": TRIAL_DAYS,
        "ok": False,
    }
    # `_present`, not `configured`, because configured() now also rejects a malformed key —
    # and "not set" is the wrong thing to tell somebody whose key IS set and is eight
    # characters long. The shape checks below say that properly.
    if not _present():
        missing = [n for n, v in (("STRIPE_SECRET_KEY", STRIPE_SECRET_KEY),
                                  ("STRIPE_PRICE_ID", STRIPE_PRICE_ID)) if not v]
        out["error"] = f"not set: {', '.join(missing)}"
        return out
    # SAID BEFORE ANY NETWORK CALL, because a key that is eight characters long will come
    # back from Stripe as "Invalid API Key" — which reads as "wrong key, get another one"
    # and sends somebody to roll a perfectly good key instead of pasting all of it.
    if out["key"]["truncated"]:
        out["error"] = (f"the key is only {out['key']['length']} characters — it has been "
                        "cut off in the paste. Reveal the full key in Stripe and copy all "
                        "of it.")
        return out
    if out["key"]["whitespace"]:
        out["error"] = "the key has a space or line break inside it — re-copy it in one piece"
        return out
    # The price id, tested the same way and for the same reason. Unlike the key this one is
    # not secret and is always visible in the dashboard, so it can be named in full here.
    out["price_id_truncated"] = len(STRIPE_PRICE_ID) < MIN_PRICE_ID_LENGTH
    if out["price_id_truncated"]:
        out["error"] = (f"STRIPE_PRICE_ID is '{STRIPE_PRICE_ID}' — that is the prefix "
                        "without the id. Copy the whole thing from Stripe → Product "
                        "catalogue → your product → the price; it looks like "
                        "price_1ABCdef2GHIjkl3MNOpqr4ST")
        return out
    # WHERE STRIPE SENDS PEOPLE BACK TO, which has no default and is not optional.
    #
    # create_checkout_session builds `success_url` as f"{SITE_URL}/account?checkout=success".
    # With SITE_URL unset that is "/account?checkout=success" — a relative path, which Stripe
    # rejects outright. Checkout then fails for a reason that has nothing to do with the key
    # or the price, which is precisely the kind of thing that only gets discovered by the
    # next person to try and pay.
    #
    # CHECKED HERE RATHER THAN AFTER THE KEY IS FIXED, because finding one blocker at a time
    # is how a ten-minute job takes three days.
    if not out["site_url_ok"]:
        out["error"] = ("SITE_URL is " + (f"'{SITE_URL}'" if SITE_URL else "not set")
                        + " — it must be the full site address, like "
                        "https://thecornermodel.com. Stripe refuses a checkout whose return "
                        "address is not an absolute URL.")
        return out
    try:
        stripe = _stripe()
    except Exception as e:  # the library is optional; the rest of the site runs without it
        out["error"] = f"the stripe library is not installed on this backend: {e}"
        return out

    try:
        # The cheapest call that proves the key works, and it names the account — which
        # answers the question after "is it valid": is it the RIGHT Stripe account.
        account = _as_dict(stripe.Account.retrieve())
        out["account"] = {
            "id": account.get("id"),
            "name": ((account.get("settings") or {}).get("dashboard") or {}).get("display_name")
                    or account.get("business_profile", {}).get("name") or "",
        }
    except Exception as e:
        out["key_valid"] = False
        out["error"] = f"Stripe rejected the key: {e}"
        return out
    out["key_valid"] = True

    try:
        price = _as_dict(stripe.Price.retrieve(STRIPE_PRICE_ID))
    except Exception as e:
        out["price_valid"] = False
        out["error"] = f"Stripe does not have that price: {e}"
        return out
    out["price_valid"] = True
    recurring = price.get("recurring") or {}
    out["price"] = {
        "amount": _money(price.get("unit_amount"), price.get("currency")),
        "interval": recurring.get("interval") or "one-off",
        "active": bool(price.get("active", True)),
        "livemode": bool(price.get("livemode")),
    }
    # A LIVE KEY WITH A TEST PRICE, which Stripe refuses at checkout with a message about
    # the price not existing — sending you to look at the price, which is fine, rather than
    # at the pair of them. Caught here because both halves are visible in one place.
    if out["key"]["mode"] and out["price"]["livemode"] != (out["key"]["mode"] == "live"):
        out["error"] = (f"the key is in {out['key']['mode']} mode but the price is a "
                        f"{'live' if out['price']['livemode'] else 'test'} price — they "
                        "must match")
        return out
    if not out["price"]["active"]:
        out["error"] = "that price is archived in Stripe — checkout cannot use it"
        return out
    # A ONE-OFF PRICE ON A SUBSCRIPTION, which fails at checkout rather than charging once.
    if not recurring.get("interval"):
        out["error"] = "that price is not recurring — a subscription needs a recurring price"
        return out
    out["ok"] = True
    return out


def checkout_error_message(exc: Exception) -> str:
    """What a VISITOR is told when checkout will not start.

    Stripe's own message went straight into a toast on the join page, so the failure the
    owner saw was `Invalid API Key provided: sk_live_`. For him that was the whole
    diagnosis. For everybody else it is a stranger's backend internals in front of a
    payment they were trying to make, and it reads like the site has been compromised.

    So the detail goes to the log and to `check()`, which says it better anyway, and the
    person gets the two facts that concern them: it is not their fault, and they have not
    been charged.
    """
    logger.error("stripe: checkout refused — %s", exc)
    return ("Subscriptions are temporarily unavailable — nothing has been charged. "
            "Please try again in a few minutes.")


def trial_days_for(user: dict) -> int:
    """How many free days THIS account gets. Zero once they have subscribed before.

    ONE TRIAL PER CUSTOMER, and the check is "have we ever created a Stripe customer for
    them" rather than anything about their current status. Without it the trial is an
    unlimited free subscription with a weekly chore attached: subscribe, cancel on day
    six, subscribe again. Stripe does not dedupe this for us — `trial_period_days` is
    honoured on every session it is passed on, however many the same customer has had.
    """
    if not TRIAL_DAYS:
        return 0
    return 0 if (user or {}).get("stripe_customer_id") else TRIAL_DAYS


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
        subscription_data={
            "metadata": {"user_id": user["user_id"]},
            # Only on a first subscription — see trial_days_for. Omitted entirely rather
            # than sent as 0, because Stripe rejects trial_period_days=0.
            **({"trial_period_days": trial} if (trial := trial_days_for(user)) else {}),
        },
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
    # Returned as a dict, because the caller hands it straight to apply_subscription and
    # reads .get("cancel_at_period_end") off it — both of which raise on a Stripe object.
    # Cancelling from the account page was broken by the same bug as the webhook.
    return _as_dict(_stripe().Subscription.modify(subscription_id,
                                                  cancel_at_period_end=cancelling))


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
    # A PLAIN DICT, ALL THE WAY DOWN. construct_event returns a stripe.Event, and on
    # stripe-python 8+ its nested objects raise TypeError on .get — so the handler's very
    # first read, obj.get("client_reference_id"), was a 500. Every webhook Stripe sent was
    # failing, Stripe was retrying them, and the first person to start a trial sat on a
    # "setting up your membership…" spinner over an account that never became one.
    #
    # Converted HERE, at the one place events enter, rather than defensively at each read:
    # a handler written against dicts is then correct by construction.
    return _as_dict(stripe.Webhook.construct_event(payload, signature, STRIPE_WEBHOOK_SECRET))


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
