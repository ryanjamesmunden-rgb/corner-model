"""When a positive-EV bet is worth sending, and when saying it again is noise.

WHY THIS IS A FILE OF ITS OWN. The value send hangs off the odds fetch, so every bet is
re-examined each time a price lands — several times on a matchday. Two opposite failures
sit either side of that, and both have happened in this repo: sending every row every
time is what produced "the bot sends me so many messages that are not value" (see
social_draft.yml's header), and suppressing a row for good is worse, because a bet whose
edge has doubled never gets mentioned and nothing reports that it did not.

So the rule is "new, or meaningfully better", and this pins the boundary.
"""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import bot_cards  # noqa: E402

GAIN = 4.0


# --- a bet nobody has been told about ----------------------------------------------

def test_a_bet_never_sent_goes_out():
    assert bot_cards.worth_sending(6.0, None, GAIN) is True


def test_zero_ev_is_still_a_number_not_a_missing_one():
    """0.0 is falsy, and `previous_ev or None` would read it as never sent. A bet sent at
    0% and still at 0% must stay quiet."""
    assert bot_cards.worth_sending(0.0, 0.0, GAIN) is False


def test_a_negative_previous_is_not_treated_as_unsent():
    assert bot_cards.worth_sending(-2.0, -2.0, GAIN) is False


# --- the re-send boundary ----------------------------------------------------------

def test_the_same_price_is_not_sent_twice():
    assert bot_cards.worth_sending(6.0, 6.0, GAIN) is False


def test_a_drift_below_the_step_stays_quiet():
    assert bot_cards.worth_sending(9.9, 6.0, GAIN) is False


def test_exactly_the_step_goes_out():
    """>= rather than >, so the documented four points is the threshold that sends and
    not the one just past it."""
    assert bot_cards.worth_sending(10.0, 6.0, GAIN) is True


def test_a_real_move_goes_out():
    assert bot_cards.worth_sending(15.0, 5.0, GAIN) is True


def test_a_shrinking_edge_is_never_re_sent():
    """The first message already made the claim. A worse price does not need announcing,
    and a second message about it would read as a second recommendation."""
    assert bot_cards.worth_sending(1.0, 12.0, GAIN) is False


def test_a_gain_of_zero_sends_any_improvement():
    assert bot_cards.worth_sending(6.1, 6.0, 0.0) is True
    assert bot_cards.worth_sending(6.0, 6.0, 0.0) is True
    assert bot_cards.worth_sending(5.9, 6.0, 0.0) is False


# --- numbers that are not numbers ---------------------------------------------------

def test_a_non_finite_ev_is_never_sent():
    """The reason _pct exists: a NaN sailing through a `>=` comparison is how "nanh old"
    reached a message once already. NaN >= anything is False, so a naive test would
    silently drop a live bet instead of reporting the bad value."""
    for bad in (float("nan"), float("inf"), float("-inf")):
        assert bot_cards.worth_sending(bad, None, GAIN) is False, bad


def test_a_missing_ev_is_never_sent():
    for bad in (None, "6.0", "", {}, [], True, False):
        assert bot_cards.worth_sending(bad, None, GAIN) is False, repr(bad)


def test_an_unreadable_previous_counts_as_never_sent():
    """One duplicate is recoverable; permanently silencing a live bet is not. So a stored
    value that cannot be read fails towards sending."""
    for bad in (float("nan"), "lots", {}, [], None, True):
        assert bot_cards.worth_sending(6.0, bad, GAIN) is True, repr(bad)


def test_an_unreadable_gain_falls_back_to_any_improvement():
    for bad in (None, "four", float("nan")):
        assert bot_cards.worth_sending(6.1, 6.0, bad) is True, repr(bad)
        assert bot_cards.worth_sending(5.9, 6.0, bad) is False, repr(bad)


def test_booleans_are_not_accepted_as_ev():
    """True == 1 in Python, so a bool reaching this would price a bet at 1% EV. _pct
    rejects it for the same reason everywhere else in this module."""
    assert bot_cards.worth_sending(True, None, GAIN) is False
    assert bot_cards.worth_sending(6.0, True, GAIN) is True


# --- the card it feeds --------------------------------------------------------------

def test_the_card_still_renders_what_survives_the_filter():
    """worth_sending decides WHICH rows go; value_rows/value_card decide how they read.
    This is the join between them, on the shape value_board actually returns."""
    board = [
        {"status": "ok", "fixture_id": "nor-el-1", "home_name": "Kristiansund BK",
         "away_name": "Valerenga", "odds_source": "api",
         "best": {"group": "away", "line": 5, "ev": 12.4,
                  "book_odds": 1.8, "fair_odds": 1.6, "key": "away_over_5"}},
        {"status": "below_floor", "fixture_id": "nor-el-2", "home_name": "A",
         "away_name": "B", "best": {"group": "home", "line": 5, "ev": 0.4,
                                    "book_odds": 2.0, "fair_odds": 2.0,
                                    "key": "home_over_5"}},
    ]
    kept = [r for r in board
            if r["status"] == "ok"
            and bot_cards.worth_sending(r["best"]["ev"], None, GAIN)]
    assert len(kept) == 1
    card = bot_cards.value_card(bot_cards.value_rows(kept))
    assert "Valerenga" in card
    assert "1.80" in card, "the book price has to be in the message to be tweetable"
    assert "6+" in card, "a line of 5 prices P(X>=6) and the post says 6+"


def test_an_empty_send_is_not_built_as_a_card():
    """The endpoint returns early rather than rendering value_card's empty state. That
    text explains an empty BOARD to someone who asked; sending it unprompted on every
    quiet fetch is the noise this whole design avoids."""
    assert "No positive-EV rows" in bot_cards.value_card([])


# --- several angles from one game ---------------------------------------------------

def board_row(fid, home, away, best, alts=(), status="ok", source="api"):
    """One /value-board row, in the shape value_board really returns."""
    return {"status": status, "fixture_id": fid, "home_name": home, "away_name": away,
            "odds_source": source, "best": best, "alternatives": list(alts)}


def mark(group, line, ev, book=2.0, fair=1.9, key=None):
    return {"group": group, "line": line, "ev": ev, "book_odds": book,
            "fair_odds": fair, "key": key or f"{group}_over_{line}"}


BOARD = [board_row(
    "nor-el-1", "Kristiansund BK", "Valerenga",
    best=mark("away", 5, 12.4, 1.80, 1.60),
    alts=[mark("away", 6, 9.2, 2.50, 2.29),
          mark("total", 10, 6.1, 2.10, 1.98),
          mark("away", 7, -4.0, 3.60, 3.75)])]


def test_without_a_floor_only_the_best_angle_comes_back():
    """The digest's long-standing shape, unchanged by this."""
    got = bot_cards.value_rows(BOARD)
    assert len(got) == 1
    assert got[0]["line"] == 6 and got[0]["ev"] == 12.4


def test_with_a_floor_every_qualifying_angle_comes_back():
    got = bot_cards.value_rows(BOARD, min_ev=5.0)
    assert [r["ev"] for r in got] == [12.4, 9.2, 6.1]
    assert [r["line"] for r in got] == [6, 7, 11], "line N prices N+1 and the post says so"


def test_a_negative_alternative_is_not_sent_as_a_pick():
    """The board keeps the next three by EV whatever they are, so an unfiltered pass would
    print a -4% bet underneath a +12% one as though both were picks."""
    evs = [r["ev"] for r in bot_cards.value_rows(BOARD, min_ev=5.0)]
    assert -4.0 not in evs


def test_each_angle_is_remembered_separately():
    """Per market, not per fixture. A 6+ already sent must not silence a 7+ on the same
    game that has only just become value."""
    got = bot_cards.value_rows(BOARD, min_ev=5.0)
    keys = [r["dedup_key"] for r in got]
    assert len(set(keys)) == 3
    assert keys[0] == "nor-el-1:away_over_5"


def test_a_below_floor_fixture_contributes_no_angles():
    rows = [board_row("x", "A", "B", best=mark("home", 5, 1.0), status="below_floor")]
    assert bot_cards.value_rows(rows, min_ev=5.0) == []


# --- how the message reads ----------------------------------------------------------

def test_angles_on_one_game_group_under_it():
    card = bot_cards.value_card(bot_cards.value_rows(BOARD, min_ev=5.0))
    assert "Kristiansund BK v Valerenga" in card
    # The side is named per line; the fixture is not repeated on each one.
    assert card.count("Kristiansund BK v Valerenga") == 1
    assert "• Valerenga 6+ @ 1.80" in card
    assert "• Valerenga 7+ @ 2.50" in card
    assert "• Match total 11+ @ 2.10" in card


def test_rows_with_no_match_still_render_flat():
    """The digest passes rows built before grouping existed. Nothing that worked changes.

    `line` here is ALREADY the plus-line: value_rows does the plus_line() conversion, so a
    row handed straight to the card carries the number the post says and the card must not
    add one again."""
    card = bot_cards.value_card([{"team": "Cambridge United", "line": 5, "ev": 7.0,
                                  "book_odds": 2.0, "fair_odds": 1.9}])
    assert "• Cambridge United 5+ @ 2.00" in card


# --- the caps, and the record agreeing with them ------------------------------------

def test_one_game_cannot_fill_the_whole_message():
    many = [board_row("f1", "H", "A", best=mark("home", 5, 20.0),
                      alts=[mark("home", 6, 19.0), mark("home", 7, 18.0),
                            mark("home", 8, 17.0), mark("total", 10, 16.0),
                            mark("total", 11, 15.0)]),
            board_row("f2", "C", "D", best=mark("away", 5, 10.0))]
    plan, dropped = bot_cards.value_plan(bot_cards.value_rows(many, min_ev=5.0))
    first = dict((m, a) for m, a in plan)
    assert len(first["H v A"]) == bot_cards.MAX_ANGLES_PER_GAME
    assert len(first["C v D"]) == 1, "the second game must still get in"
    assert dropped == 2


def test_the_total_cap_holds():
    boards = [board_row(f"f{i}", f"H{i}", f"A{i}",
                        best=mark("home", 5, 20.0 - i),
                        alts=[mark("home", 6, 19.0 - i)])
              for i in range(8)]
    rows = bot_cards.value_rows(boards, min_ev=5.0)
    plan, dropped = bot_cards.value_plan(rows)
    shown = sum(len(a) for _m, a in plan)
    assert shown == bot_cards.MAX_VALUE_ANGLES
    assert shown + dropped == len(rows)


def test_what_is_recorded_is_exactly_what_was_printed():
    """THE BUG THIS EXISTS TO STOP. The sender records what it sent so it does not repeat
    itself, and a recorded angle stays suppressed until its EV improves. Recording an
    angle the card dropped loses it silently and permanently."""
    boards = [board_row(f"f{i}", f"H{i}", f"A{i}", best=mark("home", 5, 20.0 - i),
                        alts=[mark("home", 6, 19.0 - i), mark("home", 7, 18.0 - i)])
              for i in range(6)]
    rows = bot_cards.value_rows(boards, min_ev=5.0)
    sent = bot_cards.value_sent(rows)
    card = bot_cards.value_card(rows)
    assert len(sent) == bot_cards.MAX_VALUE_ANGLES
    assert len(sent) < len(rows), "this case must actually drop something"
    # Every angle recorded appears in the message, and every one that does not, does not.
    for r in sent:
        assert f"{r['subject']} {r['line']}+" in card
    dropped_keys = {r["dedup_key"] for r in rows} - {r["dedup_key"] for r in sent}
    assert dropped_keys, "and some were genuinely left out"


def test_the_plan_and_the_card_agree_on_the_empty_case():
    assert bot_cards.value_plan([]) == ([], 0)
    assert bot_cards.value_sent([]) == []
    assert "No positive-EV rows" in bot_cards.value_card([])
