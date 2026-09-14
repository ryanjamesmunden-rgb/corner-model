"""The public record.

This page is the one thing on the site a stranger can read, and its whole value is that
it cannot be tidied. So what is pinned here is not that the numbers add up — it is that
the ways a record can quietly become an advertisement are all closed:

  - grading the survivors instead of the claim (survivorship bias)
  - dropping misses, pushes or unsettled games out of the count
  - reporting a rate before anything has settled
  - publishing a profit that was never priced
"""
import inspect
import os
import sys

import pytest

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "test_corner_model")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import server  # noqa: E402
from server import _grade_entries, _tally, WIN, LOSS, VOID  # noqa: E402


def entry(name="Ajax", line=4, direction="over", opponent="Sparta", **kw):
    return {"team_id": f"t-{name}", "name": name, "league_id": "ned-ed", "line": line,
            "direction": direction, "subject": "team", "opponent": opponent,
            "kickoff": "2026-09-12T12:30:00+00:00", "is_home": True,
            "fixture_id": "f1", "hits": 5, "window": 5, **kw}


def team_with(name="Ajax", opponent="Sparta", corners_for=7, date="2026-09-12"):
    return {f"t-{name}": {"team_id": f"t-{name}", "real_matches": [
        {"opponent": opponent, "date": date, "corners_for": corners_for, "corners_against": 4}]}}


# --- grading the claim, not the survivors ---
def test_a_miss_is_graded_as_a_miss_rather_than_disappearing():
    """The failure this whole design exists to prevent. A team that misses drops OFF the
    streak board, so grading the board afterwards would count only the survivors and
    report a near-perfect week forever."""
    rows = _grade_entries([entry(line=8)], team_with(corners_for=3))
    assert rows[0]["result"] == LOSS
    assert rows[0]["value"] == 3


def test_a_win_is_graded_from_the_frozen_line_not_a_fresh_scan():
    rows = _grade_entries([entry(line=4)], team_with(corners_for=7))
    assert rows[0]["result"] == WIN


def test_an_unplayed_game_stays_pending_instead_of_vanishing():
    """A partial weekend has to read as partial. Dropping the unplayed games would turn
    '3 of 6 so far' into a clean '3 of 3'."""
    rows = _grade_entries([entry()], {})
    assert rows[0]["result"] == "pending"
    assert rows[0]["value"] is None


def test_an_earlier_meeting_cannot_be_graded_in_place_of_the_real_one():
    """Two fixtures against the same opponent in a season. Settling against the earlier
    one would grade a game that was already played when the claim was made."""
    teams = team_with(corners_for=9, date="2026-03-01")     # before the kickoff recorded
    assert _grade_entries([entry()], teams)[0]["result"] == "pending"


def test_an_exact_line_on_an_under_is_a_push_not_a_win():
    rows = _grade_entries([entry(line=9, direction="under")], team_with(corners_for=9))
    assert rows[0]["result"] == VOID


# --- what the tally will and will not claim ---
def test_a_rate_does_not_exist_until_something_has_settled():
    """0% would be a claim about a record that has not been made. The page has to be
    able to tell 'nothing settled yet' apart from 'everything missed'."""
    assert _tally([])["hit_rate"] is None
    assert _tally([{"result": "pending"}] * 4)["hit_rate"] is None


def test_voids_and_pendings_are_counted_and_kept_out_of_the_rate():
    rows = [{"result": WIN}, {"result": WIN}, {"result": LOSS},
            {"result": VOID}, {"result": "pending"}]
    t = _tally(rows)
    assert (t["landed"], t["missed"], t["settled"]) == (2, 1, 3)
    assert t["voided"] == 1 and t["pending"] == 1
    assert t["hit_rate"] == pytest.approx(66.7)


def test_everything_missing_reads_as_zero_and_not_as_nothing():
    # The mirror of the empty case: a genuinely terrible week must show 0%, not "—".
    assert _tally([{"result": LOSS}, {"result": LOSS}])["hit_rate"] == 0.0


# --- what the public endpoint publishes, and what it must not ---
def test_a_signed_out_visitor_is_asked_to_sign_in():
    """This endpoint WAS open, and the reasoning was that evidence behind a login persuades
    nobody. That is still true and is now an accepted cost — the picks are the product, and
    signing in is free, so it is a door rather than a wall."""
    src = inspect.getsource(server.public_results)
    assert "PUBLIC_USER_ID" in src and "401" in src


def test_but_the_tools_token_still_reads_it():
    """NOT a loophole — the reason the gate did not break the Monday post. social_draft.mjs
    builds the weekly picks review from here and holds no session, so gating on a user alone
    would have made Monday fall silently down its fallback chain with nothing in the log."""
    sig = inspect.signature(server.public_results)
    assert "token" in sig.parameters
    src = inspect.getsource(server.public_results)
    assert "_has_tools_token(token)" in src


def test_it_reads_snapshots_rather_than_rescanning_the_board():
    src = inspect.getsource(server.public_results)
    assert "streak_snapshots" in src
    # A fresh call to streaks() here would reintroduce survivorship bias.
    assert "await streaks(" not in src


def test_it_publishes_a_price_only_where_one_was_actually_recorded():
    """It used to publish no profit figure at all, because a snapshot stored the line and
    never the odds. Replying to the angle menu with "3 @ 1.80 1.5u" now captures the price
    as the angle is claimed, so the rows carrying one can be counted in units.

    What must NOT happen is the endpoint inventing the rest. It passes price and stake
    straight through — absent stays absent — rather than defaulting either to a number."""
    src = inspect.getsource(server.public_results)
    assert '"price": r.get("price")' in src
    assert '"stake": r.get("stake")' in src
    # A default here is the whole failure: `r.get("price", 2.0)` or `or 0` would turn "we
    # never wrote the odds down" into a units figure on a public graphic.
    for invention in ('r.get("price",', 'r.get("stake",',
                      'r.get("price") or', 'r.get("stake") or'):
        assert invention not in src, invention


def test_an_unpriced_row_is_counted_as_unpriced_rather_than_as_zero():
    """The guard that keeps the units figure honest. pick_profit answers None for a win at
    an unknown price rather than 0, and the tally has to publish how many rows it could not
    price — otherwise a week of unpriced winners reads as a week that made nothing."""
    t = _tally([{"result": WIN, "price": 1.8, "stake": 1.0},
                {"result": WIN},                                  # logged before capture
                {"result": LOSS, "price": 2.0, "stake": 1.0}])
    assert t["priced"] == 2 and t["unpriced"] == 1
    # 0.8 back on the winner, 1.0 down on the loser. The unpriced win contributes nothing
    # in either direction — it is not a 0 and it is not a guess.
    assert t["units"] == pytest.approx(-0.2)


def test_the_under_label_comes_from_the_backend_not_the_browser():
    """Same rule as the share text: an under rendered as "9+" would be a public, wrong
    claim about what was actually backed."""
    src = inspect.getsource(server.public_results)
    assert "streak_line_label(" in src


def test_one_settlement_implementation_serves_both_endpoints():
    """Two copies would eventually disagree, and the disagreement would be between what
    the tools report privately and what the site claims publicly."""
    assert "_grade_entries(" in inspect.getsource(server.snapshot_results)
    assert "_grade_entries(" in inspect.getsource(server.public_results)


# --- angles posted by hand ---
def test_the_before_kickoff_flag_is_computed_never_accepted():
    """The whole integrity mechanism. If a caller could send this, the record would be a
    record of whatever the caller felt like claiming."""
    fields = set(server.PostedAngleBody.model_fields)
    assert "before_kickoff" not in fields
    src = inspect.getsource(server.log_posted_angle)
    assert '"before_kickoff": now < ko' in src


def test_only_angles_claimed_before_kickoff_reach_the_headline_rate():
    """A hand-added winner must not move the percentage. Everything else about this page
    is worthless if it can."""
    src = inspect.getsource(server.public_results)
    assert "counted = everything + claimed" in src
    assert "_tally(counted)" in src
    # ...and the ones added afterwards are still PUBLISHED, just not counted.
    assert '"recalled"' in src


def test_angles_added_after_the_game_are_shown_rather_than_hidden():
    """Dropping them would be its own dishonesty — and would quietly delete the thing the
    owner actually asked to show."""
    src = inspect.getsource(server.public_results)
    assert "recalled = [r for r in posted_graded if not r.get(\"before_kickoff\")]" in src


def test_a_team_in_two_leagues_is_refused_not_guessed():
    """Grading reads that team's own match history, so picking the wrong club would
    settle a real game against the wrong side's corners — silently and plausibly."""
    src = inspect.getsource(server.log_posted_angle)
    assert "status_code=409" in src


def test_logging_the_same_angle_twice_cannot_pad_the_list():
    src = inspect.getsource(server.log_posted_angle)
    assert '"status": "exists"' in src


def test_posted_angles_are_graded_by_the_same_settlement_as_everything_else():
    assert "_grade_entries(posted" in inspect.getsource(server.public_results)
