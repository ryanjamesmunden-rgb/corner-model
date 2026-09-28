"""Offline: did anybody try to subscribe and fail to get through?

THE QUESTION THIS ANSWERS, and the two very different reasons the answer can be yes.

REASON ONE, BY DESIGN. signup.py runs a weekly window: SIGNUP_DAY defaults to 1 (Monday)
and SIGNUP_SCOPE defaults to "trial". A brand-new visitor is always offered a trial —
trial_days_for returns TRIAL_DAYS for an account with no prior subscription, and there is
no way for them to decline one — so under the defaults A NEW VISITOR CAN ONLY SUBSCRIBE ON
A MONDAY. Six days a week the join page hides the button and the endpoint answers 409.

That is the cohort window working, not a fault. But it is the single likeliest answer to
"somebody could not check out", it is on by default, and nothing about it is visible from
the outside — so this prints the setting first, in words, before anything else.

REASON TWO, A REAL FAILURE. A misconfigured key, a Stripe outage, a card declined at their
end. Those raise 502/503 and are LOGGED AND NOT STORED, so there is no ledger of them to
read — Render's logs are the only record and they rotate.

WHAT IS STORED, AND WHY IT IS THE USEFUL SIGNAL. The Stripe customer is created and
written to the account BEFORE the redirect, deliberately, so a retry cannot mint a second
one. That makes `stripe_customer_id` mean "has opened checkout at least once" — its own
docstring says so. An account carrying one and NOT carrying a membership is therefore
somebody who reached the payment page and did not come back. That is not proof of a fault:
most of them are people who thought better of it. But it is the population a fault would
hide in, and it is countable.

db.billing_events is the other half: one row per Stripe event received, with `error` set
when handling it raised. A subscription that Stripe created and we failed to apply shows
up there and nowhere else.

READS ONLY. No Stripe calls, no writes — it reports what the database already knows.

Run: python audit_signups.py
     python audit_signups.py --days 30
"""
import asyncio
import os
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

import billing
import signup

ROOT = Path(__file__).parent
load_dotenv(ROOT / ".env")
db = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]

DEFAULT_DAYS = 60
# Below this, an unfinished checkout is somebody still deciding rather than somebody stuck.
# Stripe's own session expires in 24h, so a day is the point after which they are not
# coming back to that one.
STALE_HOURS = 24


def parse_dt(iso):
    if not iso:
        return None
    try:
        d = datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
    except ValueError:
        return None
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def hours_since(iso, now):
    d = parse_dt(iso)
    return None if d is None else (now - d).total_seconds() / 3600.0


def window_report():
    """The signup window, in words, because it is the likeliest answer and it is invisible."""
    lines = []
    if not signup.SIGNUP_DAY:
        lines.append("  The weekly window is OFF (SIGNUP_DAY=0). Anyone can subscribe any day.")
        return lines, False
    day = signup.DAY_NAMES.get(signup.SIGNUP_DAY, str(signup.SIGNUP_DAY))
    scope = signup.SIGNUP_SCOPE
    open_now = signup.is_open()
    lines.append(f"  SIGNUP_DAY={signup.SIGNUP_DAY} ({day})   SIGNUP_SCOPE={scope}   "
                 f"TRIAL_DAYS={billing.TRIAL_DAYS}")
    lines.append(f"  open right now: {'YES' if open_now else 'NO'}")
    # WHO THIS ACTUALLY STOPS, spelled out, because the obvious reading of "trial" is wrong.
    if billing.TRIAL_DAYS and scope != "all":
        lines.append(f"  A NEW visitor is always offered a trial, so under scope=trial they")
        lines.append(f"  can only subscribe on {day}. Returning ex-subscribers get through")
        lines.append(f"  any day, because they are offered no trial to align with a cohort.")
    elif scope == "all":
        lines.append(f"  scope=all: NOBODY subscribes except on {day}.")
    else:
        lines.append(f"  TRIAL_DAYS=0, so no checkout starts a trial and scope=trial blocks")
        lines.append(f"  nobody. The window is effectively off.")
    return lines, not open_now


def classify(users, now):
    """Split accounts by how far through subscribing they got."""
    out = {"members": [], "unfinished": [], "lapsed": [], "never_started": []}
    for u in users:
        member = bool(u.get("member"))
        src = u.get("member_source")
        has_customer = bool(u.get("stripe_customer_id"))
        had = bool(u.get("had_subscription"))
        if member and src == billing.MEMBER_SOURCE_STRIPE:
            out["members"].append(u)
        elif member:
            continue          # comped: not a checkout at all, and not this file's question
        elif had:
            out["lapsed"].append(u)
        elif has_customer:
            # OPENED CHECKOUT, NEVER COMPLETED. See the note at the top: the customer is
            # written before the redirect, so this field means exactly that.
            out["unfinished"].append(u)
        else:
            out["never_started"].append(u)
    return out


def unfinished_rows(users, now, stale_hours=STALE_HOURS):
    """The abandoned checkouts, oldest attempt first, with how long ago it was."""
    rows = []
    for u in users:
        age = hours_since(u.get("stripe_customer_at") or u.get("created_at"), now)
        rows.append({"user_id": u.get("user_id"), "email": u.get("email"),
                     "name": u.get("name"), "age_h": age,
                     "stale": age is None or age >= stale_hours})
    rows.sort(key=lambda r: (r["age_h"] is None, -(r["age_h"] or 0)))
    return rows


async def run(days=DEFAULT_DAYS):
    now = datetime.now(timezone.utc)
    print("SIGNUP AUDIT — did anybody try to subscribe and not get through?")
    print("(reads the database only; no Stripe calls, no writes)\n")

    print("THE WEEKLY WINDOW — the likeliest reason somebody could not check out")
    lines, closed_now = window_report()
    for line in lines:
        print(line)

    users = await db.users.find({}, {"_id": 0}).to_list(20000)
    groups = classify(users, now)
    print(f"\naccounts: {len(users)}")
    print(f"  paying members            {len(groups['members']):5}")
    print(f"  lapsed (subscribed once)  {len(groups['lapsed']):5}")
    print(f"  OPENED CHECKOUT, NEVER FINISHED {len(groups['unfinished']):5}")
    print(f"  never started a checkout  {len(groups['never_started']):5}")

    rows = unfinished_rows(groups["unfinished"], now)
    stale = [r for r in rows if r["stale"]]
    if rows:
        print(f"\nUNFINISHED CHECKOUTS ({len(rows)}, of which {len(stale)} older than "
              f"{STALE_HOURS}h)")
        print("A Stripe customer exists for these accounts and no subscription does. Most")
        print("will be people who thought better of it — this is the population a real")
        print("failure would be hiding in, not a list of failures.")
        for r in rows[:20]:
            when = f"{r['age_h']:.0f}h ago" if r["age_h"] is not None else "unknown"
            print(f"  {when:>12}  {r.get('name') or '(no name)':<24} {r.get('email') or ''}")
        if len(rows) > 20:
            print(f"  ... and {len(rows) - 20} more")
    else:
        print("\nNo account has a Stripe customer without a subscription. Nobody has reached")
        print("the payment page and failed to come back.")

    # THE OTHER HALF: events Stripe sent that we failed to handle. A subscription that
    # exists at Stripe and not here shows up only in this ledger.
    since = (now - timedelta(days=days)).isoformat()
    events = await db.billing_events.find({"received_at": {"$gte": since}},
                                          {"_id": 0}).to_list(5000)
    errored = [e for e in events if e.get("error")]
    unmatched = [e for e in events if not e.get("matched") and not e.get("error")]
    print(f"\nSTRIPE EVENTS in the last {days} days: {len(events)}")
    if events:
        by_type = Counter(e.get("type") or "?" for e in events)
        for t, n in by_type.most_common(8):
            print(f"  {n:4}  {t}")
    if errored:
        print(f"\n  !! {len(errored)} event(s) FAILED to apply. A subscription can exist at")
        print("  !! Stripe and not here, which looks to the customer like paying for nothing.")
        for e in errored[:10]:
            print(f"      {(e.get('received_at') or '')[:19]}  {e.get('type')}  "
                  f"{str(e.get('error'))[:80]}")
    if unmatched:
        print(f"\n  {len(unmatched)} event(s) matched no account. Usually a payment made")
        print("  outside the signed-in flow — the old payment link did exactly this.")
        for e in unmatched[:5]:
            print(f"      {(e.get('received_at') or '')[:19]}  {e.get('type')}")

    print(f"\n{'=' * 78}\nVERDICT\n{'=' * 78}")
    if errored:
        print(f"  {len(errored)} Stripe event(s) failed to apply — somebody may have paid and")
        print("  not been let in. Read those rows first; everything else here is secondary.")
    elif closed_now and billing.TRIAL_DAYS and signup.SIGNUP_SCOPE != "all":
        day = signup.DAY_NAMES.get(signup.SIGNUP_DAY, "?")
        print(f"  THE WINDOW IS SHUT TODAY. Any new visitor trying to subscribe right now is")
        print(f"  turned away until {day} — by design, but it is the answer to the question")
        print(f"  far more often than a bug is. {len(stale)} account(s) opened a checkout and")
        print(f"  never finished; if any of those tried on a closed day, this is why.")
    elif stale:
        print(f"  Nothing is failing that leaves a trace. {len(stale)} checkout(s) were")
        print("  started and abandoned, which is ordinary — the shop is open and the")
        print("  plumbing is working.")
    else:
        print("  No failed events, no abandoned checkouts, window open. Nothing to report,")
        print("  which on this question is the answer rather than an absence of one.")


def main():
    args = sys.argv[1:]

    def opt(flag, default=None, cast=str):
        return cast(args[args.index(flag) + 1]) if flag in args else default

    asyncio.run(run(days=opt("--days", DEFAULT_DAYS, int)))


if __name__ == "__main__":
    main()
