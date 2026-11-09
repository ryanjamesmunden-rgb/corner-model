"""Which fixtures the sync is willing to call "upcoming".

WHY THIS FILE EXISTS. The filter was the literal tuple ("NS", "TBD"), written out twice,
and it was blind to PST. That is not a cosmetic gap: the sync REPLACES a league's
upcoming fixtures with what it fetched, so a postponed match did not merely show a stale
kick-off — it was deleted, and every board, projection and price for it vanished with no
error. Kristiansund v Vålerenga, moved from Saturday 7 November 2026 to the Monday after
an illness outbreak in the Vålerenga squad, was simply not in the database.

THE INTERESTING CASE IS NOT "DOES PST PASS". It is that PST means two different things —
moved to a new date, and called off with no new date — and only the first is a game worth
pricing. The provider distinguishes them by whether the date has moved into the future,
so that is what `is_upcoming` reads, and most of what is below pins down that boundary
rather than the statuses either side of it.
"""
import os
import sys
from datetime import datetime, timedelta, timezone

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "test_corner_model")
os.environ.setdefault("API_FOOTBALL_KEY", "test-key")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import sync_real  # noqa: E402

NOW = datetime(2026, 11, 9, 9, 55, tzinfo=timezone.utc)


def fx(status, date="2026-11-09T19:00:00+00:00"):
    """One entry in the shape API-Football's /fixtures response uses."""
    f = {"fixture": {"id": 1, "status": {"short": status}},
         "teams": {"home": {"id": 320, "name": "Kristiansund"},
                   "away": {"id": 767, "name": "Valerenga"}}}
    if date is not None:
        f["fixture"]["date"] = date
    return f


# --- the statuses that pass on their own ------------------------------------------

def test_ns_is_upcoming():
    assert sync_real.is_upcoming(fx("NS"), NOW) is True


def test_tbd_is_upcoming():
    assert sync_real.is_upcoming(fx("TBD"), NOW) is True


def test_ns_in_the_past_still_passes():
    """UNCHANGED ON PURPOSE. A kicked-off game the provider has not relabelled yet is
    still NS, and every reader downstream filters on the date. Adding a date test here
    would change behaviour nobody asked about, for games this fix is not about."""
    assert sync_real.is_upcoming(fx("NS", "2026-10-01T19:00:00+00:00"), NOW) is True


# --- PST, which is the whole point -------------------------------------------------

def test_postponed_to_a_new_date_is_upcoming():
    """THE FIXTURE THAT FOUND THIS. Kick-off eight hours away, status still PST."""
    assert sync_real.is_upcoming(fx("PST"), NOW) is True


def test_postponed_with_no_new_date_is_not_upcoming():
    """Called off and left on the round it was meant to be played in. Storing this would
    put a game that is not going to be played onto the board."""
    assert sync_real.is_upcoming(fx("PST", "2026-11-07T15:00:00+00:00"), NOW) is False


def test_postponed_exactly_now_is_not_upcoming():
    """The boundary is strictly future. A fixture whose kick-off is this instant has
    nothing left to price."""
    assert sync_real.is_upcoming(fx("PST", NOW.isoformat()), NOW) is False


def test_postponed_one_minute_from_now_is_upcoming():
    soon = (NOW + timedelta(minutes=1)).isoformat()
    assert sync_real.is_upcoming(fx("PST", soon), NOW) is True


def test_postponed_with_no_date_at_all_is_not_upcoming():
    """Cannot tell a reschedule from a cancellation without a date, so it does not pass."""
    assert sync_real.is_upcoming(fx("PST", None), NOW) is False


def test_postponed_with_an_unreadable_date_is_not_upcoming():
    assert sync_real.is_upcoming(fx("PST", "next Tuesday"), NOW) is False


# --- everything that must stay out -------------------------------------------------

def test_statuses_that_are_over_or_in_progress_never_pass():
    """SUSP and INT are matches already under way, so part of the corner count has
    already been taken and pricing them from zero would be wrong. The rest are finished,
    however they finished. All of these are correctly deleted today and must stay so,
    even with a future date on them."""
    for status in ("FT", "AET", "PEN", "SUSP", "INT", "ABD", "CANC", "AWD", "WO", "LIVE"):
        assert sync_real.is_upcoming(fx(status), NOW) is False, status


def test_unknown_status_does_not_pass():
    assert sync_real.is_upcoming(fx("WHAT"), NOW) is False


def test_missing_status_does_not_crash():
    assert sync_real.is_upcoming({"fixture": {"date": "2026-12-01T19:00:00+00:00"}},
                                 NOW) is False
    assert sync_real.is_upcoming({}, NOW) is False
    assert sync_real.is_upcoming(None, NOW) is False


# --- date reading -------------------------------------------------------------------

def test_zulu_suffix_parses():
    """fromisoformat refuses a trailing Z on older Pythons, and the provider sends it."""
    assert sync_real.fixture_dt(fx("PST", "2026-12-01T19:00:00Z")) == \
        datetime(2026, 12, 1, 19, 0, tzinfo=timezone.utc)


def test_naive_date_is_read_as_utc():
    """Not as local time: the runner's clock is UTC and Render's is not guaranteed to be,
    so a naive string must not mean two different instants in two places."""
    assert sync_real.fixture_dt(fx("PST", "2026-12-01T19:00:00")) == \
        datetime(2026, 12, 1, 19, 0, tzinfo=timezone.utc)


def test_offset_date_is_converted_not_truncated():
    """19:00 in Oslo is 18:00 UTC. Dropping the offset would move a kick-off an hour and
    is exactly the sort of error that only shows up on a fixture near midnight."""
    got = sync_real.fixture_dt(fx("PST", "2026-11-09T19:00:00+01:00"))
    assert got == datetime(2026, 11, 9, 18, 0, tzinfo=timezone.utc)


def test_fixture_dt_survives_rubbish():
    for bad in (None, {}, {"fixture": {}}, {"fixture": {"date": None}},
                {"fixture": {"date": ""}}, {"fixture": {"date": 20261109}},
                {"fixture": {"date": "not a date"}}):
        assert sync_real.fixture_dt(bad) is None


# --- the default clock --------------------------------------------------------------

def test_now_defaults_to_the_real_clock():
    """Called with no `now` at both sync sites, so the default has to work."""
    far = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()
    gone = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
    assert sync_real.is_upcoming(fx("PST", far)) is True
    assert sync_real.is_upcoming(fx("PST", gone)) is False


def test_the_two_sync_sites_use_the_helper():
    """Both filters were the same literal tuple and only one of them got fixed in an
    earlier pass of a different list. Written out again, the next edit updates one."""
    src = open(os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "sync_real.py")).read()
    body = src.split("UPCOMING_STATUSES = ", 1)[1]
    assert '("NS", "TBD")' not in body.split("def fixture_dt", 1)[1], \
        "a status filter is still written out by hand instead of calling is_upcoming"
    assert body.count("if is_upcoming(f)") == 2
