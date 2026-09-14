"""The weekly signup window.

The rule is simple; the ways it goes quietly wrong are not. Two in particular:

  · the weekday read in UTC rather than London, which turns away the first hour of every
    British Summer Time Monday — a real closed door nobody would ever diagnose
  · "the next window" computed as always-seven-days-ahead, so a visitor arriving at 9am ON
    the open Monday is told to come back next week, in front of a signup that works
"""
import os
import sys
import importlib
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

MONDAY = 1


def _signup(day="1", scope="all"):
    os.environ["SIGNUP_DAY"] = day
    os.environ["SIGNUP_SCOPE"] = scope
    import signup
    return importlib.reload(signup)


def utc(y, m, d, hh=12, mm=0):
    return datetime(y, m, d, hh, mm, tzinfo=timezone.utc)


class TestTheDay:
    def test_open_on_the_configured_day_and_shut_otherwise(self):
        s = _signup()
        assert s.is_open(utc(2026, 9, 14)) is True      # Monday
        assert s.is_open(utc(2026, 9, 15)) is False     # Tuesday
        assert s.is_open(utc(2026, 9, 20)) is False     # Sunday

    def test_no_window_configured_means_always_open(self):
        # An unset variable has to mean what the shop was doing before anyone configured
        # anything, which is opening every day.
        s = _signup(day="0")
        assert s.enabled() is False
        for d in range(14, 21):
            assert s.is_open(utc(2026, 9, d)) is True

    def test_the_day_is_configurable_rather_than_hardcoded_to_monday(self):
        s = _signup(day="4")
        assert s.day_name() == "Thursday"
        assert s.is_open(utc(2026, 9, 17)) is True      # Thursday
        assert s.is_open(utc(2026, 9, 14)) is False

    def test_the_default_is_monday_rather_than_off(self):
        # A feature that does nothing until somebody remembers to set a variable is a
        # feature that quietly is not running — the same reason TRIAL_DAYS defaults to the
        # advertised length rather than to zero.
        import importlib
        os.environ.pop("SIGNUP_DAY", None)
        import signup
        s = importlib.reload(signup)
        assert s.SIGNUP_DAY == MONDAY
        assert s.day_name() == "Monday"

    def test_a_junk_setting_does_not_lock_the_door(self):
        # A shop that cannot be opened because of a typo in an env var is worse than one
        # with no window at all.
        assert _signup(day="").enabled() is False
        assert _signup(day="99").SIGNUP_DAY == 7
        assert _signup(day="-3").SIGNUP_DAY == 0


class TestTheClockItReads:
    def test_the_first_hour_of_a_summer_monday_is_open(self):
        # 00:30 London on Monday 14 September is 23:30 UTC on SUNDAY. Reading the weekday
        # in UTC would shut the door for the first hour of every BST Monday, and the cause
        # would be invisible from the outside.
        s = _signup()
        assert s.is_open(utc(2026, 9, 13, 23, 30)) is True

    def test_and_the_last_hour_of_a_summer_sunday_is_shut(self):
        # The mirror: 23:30 UTC Saturday is 00:30 London Sunday — still shut.
        s = _signup()
        assert s.is_open(utc(2026, 9, 12, 23, 30)) is False

    def test_in_winter_when_london_is_utc_nothing_shifts(self):
        s = _signup()
        assert s.is_open(utc(2026, 1, 12, 0, 30)) is True     # Monday 12 Jan
        assert s.is_open(utc(2026, 1, 11, 23, 30)) is False   # Sunday


class TestNextOpen:
    def test_on_the_open_day_the_next_window_is_today(self):
        # THE COUNTDOWN MUST NOT SKIP A WEEK. A visitor at 9am on the open Monday being
        # told to come back in seven days is a working signup turned away by its own copy.
        s = _signup()
        assert s.next_open(utc(2026, 9, 14, 9)).date().isoformat() == "2026-09-14"

    def test_from_a_tuesday_it_is_the_following_monday(self):
        s = _signup()
        assert s.next_open(utc(2026, 9, 15)).date().isoformat() == "2026-09-21"

    def test_from_a_sunday_it_is_the_very_next_day(self):
        s = _signup()
        assert s.next_open(utc(2026, 9, 20)).date().isoformat() == "2026-09-21"

    def test_it_is_the_start_of_the_day_not_the_current_time_a_week_on(self):
        s = _signup()
        nxt = s.next_open(utc(2026, 9, 15, 17, 43))
        assert (nxt.hour, nxt.minute, nxt.second) == (0, 0, 0)


class TestWhatItTells_Somebody:
    def test_a_sunday_visitor_is_told_tomorrow(self):
        # "Signups open Monday" on a Sunday evening is ambiguous about whether that means
        # tomorrow, and a reader working it out is a reader deciding whether to bother.
        s = _signup()
        assert "tomorrow" in s.closed_message(utc(2026, 9, 20, 19))

    def test_anyone_further_out_gets_the_actual_date(self):
        s = _signup()
        msg = s.closed_message(utc(2026, 9, 15))
        assert "Monday 21 September" in msg

    def test_it_says_why_rather_than_only_no(self):
        # The reason is the only thing that makes waiting six days feel like a policy
        # rather than a fault.
        s = _signup()
        assert "week" in s.closed_message(utc(2026, 9, 15)).lower()

    def test_an_open_day_has_nothing_to_say(self):
        s = _signup()
        assert s.closed_message(utc(2026, 9, 14)) == ""


class TestScope:
    def test_all_turns_everybody_away_on_a_closed_day(self):
        s = _signup(scope="all")
        assert s.blocks(is_trial=True, now=utc(2026, 9, 15)) is True
        assert s.blocks(is_trial=False, now=utc(2026, 9, 15)) is True

    def test_trial_only_lets_a_paying_customer_through(self):
        # The weekly tracking comes from trials starting together. Somebody paying full
        # price on a Wednesday does not affect it, and turning them away is £20 a month
        # refused for no measurement at all.
        s = _signup(scope="trial")
        assert s.blocks(is_trial=True, now=utc(2026, 9, 15)) is True
        assert s.blocks(is_trial=False, now=utc(2026, 9, 15)) is False

    def test_nothing_is_blocked_on_the_open_day_under_either_scope(self):
        for scope in ("all", "trial"):
            s = _signup(scope=scope)
            assert s.blocks(is_trial=True, now=utc(2026, 9, 14)) is False
            assert s.blocks(is_trial=False, now=utc(2026, 9, 14)) is False

    def test_an_unknown_scope_falls_back_to_gating_the_trial_only(self):
        # The safer direction of the two: a typo costs a cohort, not a month's revenue.
        s = _signup(scope="nonsense")
        assert s.blocks(is_trial=False, now=utc(2026, 9, 15)) is False


class TestEnforcedServerSide:
    def test_checkout_refuses_on_a_closed_day(self):
        # A page hiding a button stops nobody who calls the endpoint, and this endpoint
        # starts a subscription.
        import inspect
        os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
        os.environ.setdefault("DB_NAME", "test_corner_model")
        import server
        src = inspect.getsource(server.billing_checkout)
        assert "signup.blocks" in src

    def test_the_window_reaches_the_page_from_the_backend(self):
        import inspect
        import server
        assert "signup.state()" in inspect.getsource(server.public_config)
