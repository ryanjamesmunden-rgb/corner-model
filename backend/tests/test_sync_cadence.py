"""The staleness threshold and the cron schedule have to be read together.

They were set independently — cron at 07:00/19:00, STALE_HOURS at 12 — and met exactly
on the boundary. A sync launched at 07:02 finishes writing synced_at around 07:04, so at
the 19:02 tick the data is 11.97h old, which is not "older than 12". if-stale answered
"fresh", the tick did nothing, and the site refreshed once a day while the cron, the
workflow comments and the logs all said twice. Nothing was broken in a way anything
reported; the threshold was quietly rejecting half the schedule.

So the two constants are pinned against each other here rather than each looking correct
alone. If someone moves the cron to hourly, or nudges STALE_HOURS back up, this fails."""
import os
import re
import sys

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "test_corner_model")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from server import STALE_HOURS, SYNC_LOCK_MINUTES  # noqa: E402

WORKFLOW = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    ".github", "workflows", "sync.yml")


def _cron_hours():
    """The hours the sync workflow fires at, straight out of the YAML.

    Regex rather than a YAML parser so the test carries no dependency the backend does
    not already have — it only needs the one cron line."""
    with open(WORKFLOW) as fh:
        body = fh.read()
    m = re.search(r'^\s*-\s*cron:\s*["\']([^"\']+)["\']', body, re.M)
    assert m, "no cron line in sync.yml — has the schedule been removed?"
    minute, hour = m.group(1).split()[:2]
    assert minute == "0", f"cron fires at minute {minute}; the gap maths below assumes :00"
    return sorted(int(h) for h in hour.split(","))


def _min_gap_hours():
    """Smallest gap between consecutive fires, wrapping midnight."""
    hours = _cron_hours()
    assert len(hours) >= 2, f"only {len(hours)} fire(s) a day — cannot sync twice"
    gaps = [b - a for a, b in zip(hours, hours[1:])] + [24 - hours[-1] + hours[0]]
    return min(gaps)


def test_the_schedule_still_fires_twice_a_day():
    assert _cron_hours() == [7, 19]


def test_the_threshold_is_below_the_gap_between_runs():
    """The bug, pinned. At 12 and 12 the data was never quite old enough at tick time."""
    assert STALE_HOURS < _min_gap_hours(), (
        f"STALE_HOURS={STALE_HOURS} is not below the {_min_gap_hours()}h gap between "
        f"scheduled runs, so every other run will be rejected as fresh and the site will "
        f"refresh half as often as the schedule claims")


def test_there_is_real_slack_and_not_just_a_hair():
    """Under the gap is not enough on its own — 11.99 would pass the test above and still
    fail in practice, because a tick can land late and a sync takes minutes to write.
    An hour of margin absorbs both."""
    assert _min_gap_hours() - STALE_HOURS >= 1


def test_the_threshold_is_not_so_low_that_ordinary_traffic_syncs():
    """The other direction. Every visit calls the boot path, so a threshold far below the
    cadence would let ordinary traffic trigger syncs all day. It only needs to be under
    the gap, not near zero."""
    assert STALE_HOURS >= _min_gap_hours() - 3


def test_the_lock_is_shorter_than_the_gap_it_guards():
    """The lock exists to stop two syncs stacking, not to become a second staleness rule.
    Longer than the gap and it would start swallowing scheduled runs itself."""
    assert SYNC_LOCK_MINUTES < _min_gap_hours() * 60
