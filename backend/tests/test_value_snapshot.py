"""Freezing a positive-EV claim so it can be graded later.

WHY THIS BOARD NEEDED A SNAPSHOT AT ALL. Streaks, mismatches, perfect games and
projections all freeze before kick-off and are graded afterwards. The value board had
none of that, so no positive-EV claim this site has made has ever been graded as a board
claim — and it is the board whose output gets published.

A value row also cannot be replayed, and less so than any of the others: it exists only
while the price does. Prices move, the feed drops them after twelve hours, and the
provider serves pre-match markets only, so once the game kicks off the number the claim
was made against is gone. Written down before, or not knowable.

THESE TESTS GUARD THE SHAPE, not the plumbing. _grade_entries settles on four fields —
team_id, opponent, line, subject — and every one of them has a way of being wrong that
produces a plausible-looking record rather than an error.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import bot_cards  # noqa: E402


def angle(group, line, **kw):
    """One row as value_rows emits it, with `line` ALREADY the plus-line.

    `line` is used to build the market key, so it is formatted defensively — a test that
    passes None or a float is testing the shaper, and the helper must reach it rather
    than blowing up first.
    """
    key_line = f"{line - 1}.5" if isinstance(line, (int, float)) \
        and not isinstance(line, bool) else line
    base = {"group": group, "line": line, "ev": 12.0, "book_odds": 1.80,
            "fair_odds": 1.60, "prob": 61.0, "key": f"{group}_over_{key_line}",
            "fixture_id": "eng-l1-1", "kickoff": "2026-11-14T15:00:00+00:00",
            "home_name": "Colchester", "away_name": "Gillingham",
            "home_team_id": "eng-l2-colch", "away_team_id": "eng-l2-gill",
            "match": "Colchester v Gillingham", "league_id": "eng-l2",
            "league_name": "League Two", "odds_source": "api",
            "subject": "Colchester" if group == "home" else
                       "Gillingham" if group == "away" else "Match total"}
    base.update(kw)
    return base


# server.py cannot be imported in this container — pymongo pulls in cryptography, which
# panics here. So the pure shaper is exercised through a slice of the source, the same
# technique test_upcoming_status uses for sync_real.
def _shaper():
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    src = open(os.path.join(here, "server.py")).read()
    start = src.index("VALUE_GROUP_SUBJECT = ")
    end = src.index("class ValueSnapshotBody")
    ns = {"bot_cards": bot_cards, "Optional": __import__("typing").Optional}
    exec(compile(src[start:end], "sliced", "exec"), ns)
    return ns["value_snapshot_entry"], ns["VALUE_GROUP_SUBJECT"]


SHAPE, GROUPS = _shaper()


# --- which team the claim settles against -------------------------------------------

def test_a_home_claim_anchors_on_the_home_team():
    e = SHAPE(angle("home", 5))
    assert e["team_id"] == "eng-l2-colch"
    assert e["opponent"] == "Gillingham"
    assert e["is_home"] is True
    assert e["subject"] == "team"


def test_an_away_claim_anchors_on_the_away_team():
    """THE ONE THAT WOULD SILENTLY GRADE THE WRONG SIDE. _grade_entries reads the played
    game out of this team's history, so an away claim stored against the home id settles
    a real game against the wrong team's corners and looks entirely normal doing it."""
    e = SHAPE(angle("away", 5))
    assert e["team_id"] == "eng-l2-gill"
    assert e["opponent"] == "Colchester"
    assert e["is_home"] is False
    assert e["subject"] == "team"


def test_a_match_total_settles_as_subject_match():
    """streak_value(m, "match") is corners_for + corners_against, so either side gives the
    same number — but it still needs A team to find the game in."""
    e = SHAPE(angle("total", 11))
    assert e["subject"] == "match"
    assert e["team_id"] == "eng-l2-colch", "anchored on home, not left to chance"
    assert e["opponent"] == "Gillingham"


def test_every_group_the_board_emits_has_a_subject():
    assert set(GROUPS) == {"home", "away", "total"}


# --- the line, which must not be converted twice ------------------------------------

def test_the_plus_line_is_stored_unchanged():
    """value_rows already ran plus_line: 4.5 became 5. settle_streak_leg compares
    `value >= line`, so 5 settles 5+. Converting again grades every claim one corner
    adrift, in the direction that flatters it."""
    assert SHAPE(angle("home", 5))["line"] == 5
    assert SHAPE(angle("total", 11))["line"] == 11


def test_an_unconverted_market_line_is_refused():
    """A float here is the raw 4.5 that should have been converted upstream. Refused
    rather than rounded, because rounding produces a plausible-looking wrong record."""
    assert SHAPE(angle("home", 4.5)) is None


def test_a_boolean_line_is_refused():
    """True == 1 in Python and isinstance(True, int) is True, so a bool would sail in and
    settle as a 1+ claim that always wins."""
    assert SHAPE(angle("home", True)) is None


def test_a_missing_line_is_refused():
    assert SHAPE(angle("home", None)) is None


# --- the price, which is this board's whole claim -----------------------------------

def test_the_price_is_frozen_with_the_claim():
    """EVERY OTHER SNAPSHOT OMITS IT and reports units as unavailable. A value claim is
    "this price is wrong", so the price IS the claim — and freezing it is what lets this
    board's record carry units at all. _tally reads r["price"] and r["stake"]."""
    e = SHAPE(angle("home", 5, book_odds=1.73, ev=27.6))
    assert e["price"] == 1.73
    assert e["ev"] == 27.6
    assert e["stake"] == 1.0
    assert e["fair_odds"] == 1.60 and e["prob"] == 61.0


def test_the_direction_is_over():
    """settle_streak_leg voids an exact-line result on unders only. Every value claim here
    is an over, and saying so explicitly is what keeps that true."""
    assert SHAPE(angle("home", 5))["direction"] == "over"


# --- rows that cannot be settled are refused, not stored ----------------------------

def test_an_unknown_group_is_refused():
    row = angle("home", 5)
    row["group"] = "sideways"
    assert SHAPE(row) is None


def test_a_claim_with_no_team_id_is_refused():
    """Nothing to look the played game up in, so it could only ever read pending."""
    assert SHAPE(angle("home", 5, home_team_id=None)) is None
    assert SHAPE(angle("away", 5, away_team_id=None)) is None


def test_a_claim_with_no_fixture_is_refused():
    assert SHAPE(angle("home", 5, fixture_id=None)) is None


def test_the_market_key_rides_along():
    """So a frozen claim can be traced back to the exact stored price it was made against."""
    assert SHAPE(angle("home", 5))["market_key"] == "home_over_4.5"


# --- the join with value_rows -------------------------------------------------------

def test_value_rows_emits_everything_the_shaper_needs():
    """The two are written apart and have to agree. A field renamed on one side would
    produce entries that look complete and grade as pending for ever."""
    board = [{"status": "ok", "fixture_id": "eng-l2-1",
              "home_name": "Colchester", "away_name": "Gillingham",
              "home_team_id": "eng-l2-colch", "away_team_id": "eng-l2-gill",
              "league_id": "eng-l2", "league_name": "League Two",
              "date": "2026-11-14T15:00:00+00:00", "odds_source": "api",
              "best": {"group": "home", "line": 4.5, "ev": 27.6, "book_odds": 1.73,
                       "fair_odds": 1.36, "prob": 73.8, "key": "home_over_4.5"},
              "alternatives": [], "ladder": []}]
    rows = bot_cards.value_rows(board, min_ev=5.0)
    assert len(rows) == 1
    e = SHAPE(rows[0])
    assert e is not None, "value_rows output must be shapeable without translation"
    assert e["line"] == 5 and e["team_id"] == "eng-l2-colch"
    assert e["price"] == 1.73 and e["subject"] == "team"
    assert e["market_key"] == "home_over_4.5"
