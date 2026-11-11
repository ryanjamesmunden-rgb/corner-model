"""Ranking the two lists together, and what a row is allowed to claim.

WHY ONE SCREEN OVER TWO STORES. Favourites and tracking are deliberately separate — the
promote endpoint untracks as it follows, so moving a team is a decision rather than a side
effect — but "which of mine is in the best shape" is a question about all of them at once.
Keeping them apart in the data and together on one screen is the arrangement that serves
both, and every row says which list it came from.

These tests cover the ranking, because an unstable sort reshuffles the list between
requests and the thing you were about to tap moves out from under you.
"""
import os
import sys
from datetime import datetime, timezone
from typing import Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _src():
    with open(os.path.join(HERE, "server.py")) as fh:
        return fh.read()


# server.py cannot be imported in this container — pymongo pulls in cryptography, which
# panics — so the pure ranking helpers come from a source slice, as test_value_snapshot
# and test_shot_streaks do.
def _load():
    src = _src()
    ns = {"datetime": datetime, "timezone": timezone, "Optional": Optional}
    body = src[src.index("MY_TEAMS_FIXTURES = "):src.index('@api_router.get("/my-teams")')]
    exec(compile(body, "sliced:my_teams", "exec"), ns)
    return ns


NS = _load()
key = NS["_my_teams_sort_key"]
date_rank = NS["_date_rank"]
SORTS = NS["MY_TEAMS_SORTS"]


def team(name="A", delta=0.0, run=0, sched=1.0, l5=5.0, date="2026-11-14T15:00:00+00:00"):
    return {"name": name, "form_delta": delta, "run": run, "schedule": sched,
            "l5": l5, "next": [{"date": date}]}


def order(rows, sort):
    return [r["name"] for r in sorted(rows, key=lambda o: key(o, sort), reverse=True)]


# --- each sort answers its own question -------------------------------------------------

def test_form_ranks_the_biggest_lift_first():
    rows = [team("cold", delta=-1.5), team("hot", delta=2.4), team("flat", delta=0.1)]
    assert order(rows, "form") == ["hot", "flat", "cold"]


def test_run_ranks_the_longest_streak_first():
    rows = [team("short", run=2), team("long", run=11), team("mid", run=6)]
    assert order(rows, "run") == ["long", "mid", "short"]


def test_schedule_ranks_the_softest_opponents_first():
    """A high ratio means the opponents concede MORE corners than their division does, so
    high is soft and high comes first."""
    rows = [team("tough", sched=0.82), team("soft", sched=1.31), team("avg", sched=1.0)]
    assert order(rows, "schedule") == ["soft", "avg", "tough"]


def test_average_ranks_the_highest_recent_level():
    """Different question from `form`, which is why it is its own sort: one is the level,
    the other is the change. A side averaging eight and steady beats one averaging four
    and climbing, on this sort and not on that one."""
    rows = [team("low", l5=3.8, delta=2.0), team("high", l5=8.2, delta=0.0)]
    assert order(rows, "average") == ["high", "low"]
    assert order(rows, "form") == ["low", "high"]


def test_next_ranks_the_soonest_kick_off_first():
    rows = [team("late", date="2026-11-20T15:00:00+00:00"),
            team("soon", date="2026-11-12T19:00:00+00:00"),
            team("mid", date="2026-11-15T13:00:00+00:00")]
    assert order(rows, "next") == ["soon", "mid", "late"]


def test_an_unknown_sort_falls_back_to_form():
    rows = [team("a", delta=0.2), team("b", delta=3.0)]
    assert order(rows, "nonsense") == order(rows, "form")


def test_every_offered_sort_is_handled():
    rows = [team("a", delta=1.0, run=3, sched=1.2, l5=6.0)]
    for s in SORTS:
        assert key(rows[0], s) is not None, s


# --- the order has to be stable ---------------------------------------------------------

def test_teams_level_on_the_sort_do_not_reshuffle():
    """THE REASON EVERY KEY ENDS WITH A NAME. Without a tie-break a list of sides all on
    the same run comes back in a different order each request, and the row somebody was
    about to tap moves."""
    rows = [team("Zulu", run=5), team("Alpha", run=5), team("Mike", run=5)]
    first = order(rows, "run")
    assert first == order(list(reversed(rows)), "run")
    # Descending sort, so the names come back reversed — what matters is that it is fixed.
    assert first == ["Zulu", "Mike", "Alpha"]


def test_form_breaks_a_tie_on_every_other_sort():
    rows = [team("dull", run=4, delta=0.0), team("rising", run=4, delta=2.2)]
    assert order(rows, "run") == ["rising", "dull"]


# --- missing numbers must not win, and must not raise -----------------------------------

def test_a_team_with_no_form_sorts_last_rather_than_first():
    """None is not zero and must not read as average. A side with no form at all sorting
    above a side in form would put the least evidenced row at the top of a ranking."""
    rows = [team("known", delta=-0.5), team("unknown", delta=None)]
    assert order(rows, "form") == ["known", "unknown"]


def test_missing_run_and_schedule_are_treated_as_nothing():
    rows = [team("has", run=3), {"name": "none", "next": []}]
    assert order(rows, "run") == ["has", "none"]
    assert order(rows, "schedule") == ["has", "none"]


def test_a_team_with_no_fixture_sorts_after_one_that_has_a_date():
    rows = [team("playing", date="2026-11-12T19:00:00+00:00"), {"name": "idle", "next": []}]
    assert order(rows, "next") == ["playing", "idle"]


def test_an_unreadable_date_sorts_last_instead_of_raising():
    assert date_rank("not a date") == 9e18
    rows = [team("good", date="2026-11-12T19:00:00+00:00"), team("bad", date="whenever")]
    assert order(rows, "next") == ["good", "bad"]


def test_a_naive_date_is_read_as_utc():
    assert date_rank("2026-11-12T19:00:00") == date_rank("2026-11-12T19:00:00+00:00")


# --- the endpoint's own rules, asserted on the source -----------------------------------

def _endpoint():
    src = _src()
    fn = src[src.index('@api_router.get("/my-teams")'):]
    return fn[:fn.index('@api_router.get("/tracking/teams")')]


def test_a_team_on_both_lists_counts_once_as_a_favourite():
    """The promote endpoint untracks as it follows, so this should not happen — but if it
    ever does, showing the side twice would double it in every count and in the flattened
    fixture list."""
    fn = _endpoint()
    assert 'wanted = {tid: "favourites" for tid in fav_ids}' in fn
    assert "setdefault(tid, \"tracking\")" in fn


def test_the_tracking_count_excludes_anything_already_followed():
    fn = _endpoint()
    assert "len(trk_ids - fav_ids)" in fn


def test_a_follow_whose_team_has_gone_is_reported_not_dropped():
    """Same rule the favourites endpoint already applies: a list that has gone quiet has
    to be visible instead of looking empty."""
    fn = _endpoint()
    assert '"missing": True' in fn


def test_missing_follows_are_not_ranked_among_the_live_rows():
    fn = _endpoint()
    assert 'live = [r for r in rows if not r.get("missing")]' in fn
    assert 'rows = live + [r for r in rows if r.get("missing")]' in fn


def test_the_price_comes_from_the_same_function_the_streak_board_uses():
    """So a number here and a number there cannot disagree. Writing a second projection
    for this screen is how two parts of one site start quoting different fair prices for
    the same bet."""
    fn = _endpoint()
    assert "_streak_projection(" in fn
    assert "_odds_for_many(" in fn


def test_both_shapes_are_returned_from_one_request():
    """They share the whole computation, and a page that can switch instantly is the
    point — two endpoints would do the work twice and could drift."""
    fn = _endpoint()
    assert '"teams": rows' in fn and '"fixtures": flat' in fn


def test_the_fixture_list_is_in_kick_off_order():
    fn = _endpoint()
    assert "flat.sort(key=lambda g: _date_rank(" in fn


def test_the_window_and_fixture_count_are_clamped():
    """An unbounded `fixtures` would let one request ask for every game of the season per
    team, and an unbounded window the same."""
    fn = _endpoint()
    assert "min(within_days, 60)" in fn
    assert "min(fixtures, 10)" in fn
