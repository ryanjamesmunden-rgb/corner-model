"""When the door is open.

WHY A WEEKLY WINDOW AT ALL. Everyone who starts on the same day sees the same week, so the
week's published record IS the week they experienced — no explaining that their trial
straddled a good Tuesday and a bad Friday from two different reporting periods. A cohort
also makes the trial measurable: seven people who started on the 15th either converted or
did not, and that is a number, where a trickle of individually-timed trials is an anecdote.

WHAT IT COSTS, STATED HERE BECAUSE IT IS REAL. Somebody who reads the pitch on a Tuesday
has to come back in six days, and most people do not come back. That is the trade, and it
is why the closed state on the join page has to do actual work rather than saying "no".

SERVER-SIDE, BECAUSE A CLIENT-SIDE GATE IS NOT A GATE. The page hiding a button stops
nobody who calls the endpoint directly, and this one starts a subscription. The page reads
the same values only so that it can explain the closed door rather than discover it.

LONDON, NOT THE SERVER'S CLOCK. The backend runs in UTC, and at 00:30 on a British Summer
Time Monday it is still Sunday in UTC — so a UTC weekday check would turn away the first
hour of every Monday in summer, and nobody would ever work out why.
"""
import logging
import os
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

TZ = ZoneInfo("Europe/London")

# 1 = Monday … 7 = Sunday, matching date.isoweekday(). 0 turns the window off entirely.
#
# THE DEFAULT IS THE POLICY, for the same reason TRIAL_DAYS defaults to the advertised
# length: a feature that does nothing until somebody remembers to set a variable is a
# feature that quietly is not running. Setting SIGNUP_DAY=0 is how you turn it off, and
# that is a decision somebody makes rather than one they forget to make.
#
# A junk value falls back to 0 rather than to a day, because a shop that cannot be opened
# because of a typo in an environment variable is worse than one with no window at all.
SIGNUP_DAY = max(0, min(7, int(os.environ.get("SIGNUP_DAY", "1") or 0)))

# WHAT THE WINDOW APPLIES TO.
#
#   "trial" — only a checkout that WOULD START A TRIAL waits for the open day
#   "all"   — nobody subscribes at all except on the open day
#
# WHO THIS ACTUALLY DIFFERS FOR, stated precisely because the obvious reading is wrong.
# It is tempting to describe "trial" as "somebody willing to pay full price can join any
# day". That is not what it does. A brand-new visitor is offered a trial and has no way to
# decline one, so billing.trial_days_for answers 7 for them and they wait for the open day
# under either setting.
#
# The people it lets through are RETURNING EX-SUBSCRIBERS — trial_days_for answers 0 once
# an account has a Stripe customer — and that is exactly right. Somebody who cancelled in
# March and wants back in on a Wednesday is not forming a cohort; there is no free week of
# theirs to align with anybody else's, and the weekly record is unaffected by when they
# rejoin. Making them wait is friction that buys no measurement and costs a month.
#
# So the default is "trial": the window covers the cohort it exists for, and nothing else.
# Anything unrecognised lands here too, which is the safer direction to be wrong in — a
# typo costs a returning customer's convenience, where the other way round it costs revenue.
SIGNUP_SCOPE = os.environ.get("SIGNUP_SCOPE", "").strip().lower() or "trial"

DAY_NAMES = {1: "Monday", 2: "Tuesday", 3: "Wednesday", 4: "Thursday",
             5: "Friday", 6: "Saturday", 7: "Sunday"}


def _local(now=None) -> datetime:
    """Now, in the zone the window is defined in."""
    if now is None:
        return datetime.now(TZ)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    return now.astimezone(TZ)


def enabled() -> bool:
    return SIGNUP_DAY != 0


def day_name() -> str:
    return DAY_NAMES.get(SIGNUP_DAY, "")


def is_open(now=None) -> bool:
    """Is the door open right now? Always, when no window is configured."""
    if not enabled():
        return True
    return _local(now).isoweekday() == SIGNUP_DAY


def next_open(now=None) -> datetime:
    """The start of the next open day, in London.

    RETURNS TODAY WHEN TODAY IS THE DAY, rather than skipping a week. A visitor arriving at
    9am on the open Monday must not be told the next window is in seven days — that is a
    working signup turned away by its own countdown.
    """
    local = _local(now)
    if not enabled():
        return local
    ahead = (SIGNUP_DAY - local.isoweekday()) % 7
    return (local + timedelta(days=ahead)).replace(hour=0, minute=0, second=0, microsecond=0)


def closed_message(now=None) -> str:
    """What to tell somebody who arrived on the wrong day.

    NAMES THE DAY AND THE DATE. "Signups open Monday" on a Sunday evening is ambiguous
    about whether that means tomorrow, and a reader who has to work it out is a reader
    deciding whether to bother.
    """
    if is_open(now):
        return ""
    nxt = next_open(now)
    tomorrow = (_local(now) + timedelta(days=1)).date() == nxt.date()
    when = "tomorrow" if tomorrow else f"{day_name()} {nxt.day} {nxt.strftime('%B')}"
    return (f"Signups open on {day_name()}s, so the whole group starts the week together "
            f"and the week's results are the week you actually saw. Next window: {when}.")


def state(now=None) -> dict:
    """The whole window, for /api/config. Shaped so the page can render the closed state
    without recomputing any of the rule."""
    nxt = next_open(now)
    return {
        "enabled": enabled(),
        "open": is_open(now),
        "day": SIGNUP_DAY,
        "day_name": day_name(),
        "scope": SIGNUP_SCOPE,
        "next_open": nxt.isoformat() if enabled() else None,
        "message": closed_message(now),
    }


def blocks(is_trial: bool, now=None) -> bool:
    """Should this particular checkout be refused?

    THE SCOPE IS CHECKED HERE rather than at the call site, so "trial-only" cannot be
    honoured by the page and forgotten by the endpoint — which would leave the door open
    to anyone who noticed.
    """
    if is_open(now):
        return False
    return True if SIGNUP_SCOPE == "all" else bool(is_trial)
