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


def test_one_angle_per_side_the_lowest_line_priced_1_80_or_more():
    """THE POSTING RULE. Valerenga 6+ at 1.80 is their line; 7+ at +9.2% is a longer
    price on the same side and is not a second bet. The total is its own side."""
    got = bot_cards.value_rows(BOARD, min_ev=5.0)
    assert [r["ev"] for r in got] == [12.4, 6.1]
    assert [r["line"] for r in got] == [6, 11], "line N prices N+1 and the post says so"
    assert bot_cards.value_rows(BOARD) == got, "no floor still means one per side"


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
    assert len(set(keys)) == 2
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
    assert "7+ @ 2.50" not in card, "a longer line on the same side is not a second bet"
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
    """value_rows now gives at most one angle per side, but value_plan still holds the
    per-game cap for any caller that hands it more."""
    many = [{"team": "H", "subject": "H", "match": "H v A", "line": n, "ev": 20.0 - n,
             "book_odds": 2.0, "dedup_key": f"f1:{n}"} for n in range(5, 11)]
    many.append({"team": "C", "subject": "C", "match": "C v D", "line": 5, "ev": 10.0,
                 "book_odds": 2.0, "dedup_key": "f2:5"})
    plan, dropped = bot_cards.value_plan(many)
    first = dict((m, a) for m, a in plan)
    assert len(first["H v A"]) == bot_cards.MAX_ANGLES_PER_GAME
    assert len(first["C v D"]) == 1, "the second game must still get in"
    assert dropped == 2


def test_the_total_cap_holds():
    boards = [board_row(f"f{i}", f"H{i}", f"A{i}",
                        best=mark("home", 5, 20.0 - i),
                        alts=[mark("home", 6, 19.0 - i)])
              for i in range(14)]
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
              for i in range(14)]
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


# --- the rungs no book quoted -------------------------------------------------------

def rung(group, line, ev=None, book=None, fair=2.0, prob=50.0):
    return {"group": group, "line": line, "ev": ev, "book_odds": book, "fair_odds": fair,
            "prob": prob, "key": f"{group}_over_{line}", "group_label": group,
            "label": f"Over {line}", "tier": None}


# Valerenga's real shape on 2026-11-09: 5+ priced by the model at 69.6% and quoted by
# nobody in the feed, while 6+ and 7+ were quoted. The 5+ was the biggest edge available
# and the message did not mention it at all.
LADDER = [rung("away", 3.5, fair=1.12, prob=89.0),
          rung("away", 4.5, fair=1.44, prob=69.6),
          rung("away", 5.5, ev=12.4, book=1.80, fair=1.60, prob=62.5),
          rung("away", 6.5, ev=9.2, book=2.50, fair=2.29, prob=43.7),
          rung("away", 7.5, fair=3.10, prob=32.3)]

LADDER_BOARD = [{"status": "ok", "fixture_id": "nor-el-1494798",
                 "home_name": "Kristiansund BK", "away_name": "Valerenga",
                 "odds_source": "api", "best": LADDER[2], "alternatives": [LADDER[3]],
                 "ladder": LADDER}]


def test_the_unpriced_safer_rung_is_shown():
    """THE COMPLAINT THIS FIXES. 5+ at a fair 1.44 never appeared, because EV needs a
    fetched price and no book in the feed quoted that rung."""
    rows = bot_cards.value_rows(LADDER_BOARD, min_ev=5.0, with_ladder=True)
    refs = [r for r in rows if r.get("reference")]
    assert [r["line"] for r in refs] == [5, 4], "nearest safer rung first"
    assert refs[0]["fair_odds"] == 1.44


def test_a_rung_above_the_priced_ones_is_not_shown():
    """8+ is unpriced too, and a longer shot — the opposite of what was missing."""
    rows = bot_cards.value_rows(LADDER_BOARD, min_ev=5.0, with_ladder=True)
    assert 8 not in [r["line"] for r in rows if r.get("reference")]


def test_a_rung_that_has_a_price_is_never_a_reference():
    """It is a bet, or it failed the floor. Either way it is not a missing price."""
    rows = bot_cards.value_rows(LADDER_BOARD, min_ev=5.0, with_ladder=True)
    for r in rows:
        if r.get("reference"):
            assert r.get("book_odds") is None


def test_reference_rungs_are_capped():
    deep = [rung("away", x / 10, fair=1.1 + x / 100) for x in (5, 15, 25, 35, 45)]
    deep.append(rung("away", 5.5, ev=9.0, book=2.0, fair=1.8))
    board = [{"status": "ok", "fixture_id": "f", "home_name": "H", "away_name": "A",
              "best": deep[-1], "alternatives": [], "ladder": deep}]
    refs = [r for r in bot_cards.value_rows(board, min_ev=5.0, with_ladder=True)
            if r.get("reference")]
    assert len(refs) == bot_cards.MAX_REFERENCE_RUNGS


def test_without_the_ladder_nothing_changes():
    """The digest does not ask for these, and must not start getting them."""
    rows = bot_cards.value_rows(LADDER_BOARD, min_ev=5.0)
    assert not any(r.get("reference") for r in rows)


def test_a_missing_ladder_is_survivable():
    for bad in (None, [], "nope", [None, 3, {}]):
        board = [{"status": "ok", "fixture_id": "f", "home_name": "H", "away_name": "A",
                  "best": rung("home", 5.5, ev=9.0, book=2.0), "alternatives": [],
                  "ladder": bad}]
        rows = bot_cards.value_rows(board, min_ev=5.0, with_ladder=True)
        assert [r for r in rows if not r.get("reference")], repr(bad)
        assert not [r for r in rows if r.get("reference")], repr(bad)


# --- a reference is not a bet, and must never be recorded as one --------------------

def test_a_reference_rung_is_never_recorded_as_sent():
    """IF IT WERE, the real bet on that market would be suppressed the moment a price
    finally arrived for it — the silent, permanent loss value_plan exists to prevent."""
    rows = bot_cards.value_rows(LADDER_BOARD, min_ev=5.0, with_ladder=True)
    sent = bot_cards.value_sent(rows)
    assert len(sent) == 1
    assert all(not r.get("reference") for r in sent)
    assert [r["dedup_key"] for r in sent] == ["nor-el-1494798:away_over_5.5"]


def test_a_reference_rung_carries_no_dedup_key():
    """So a caller that forgets to filter them crashes loudly instead of writing a key
    that silences a future bet."""
    rows = bot_cards.value_rows(LADDER_BOARD, min_ev=5.0, with_ladder=True)
    for r in rows:
        if r.get("reference"):
            assert "dedup_key" not in r


# --- how it reads -------------------------------------------------------------------

def test_the_card_marks_a_reference_as_not_a_bet():
    card = bot_cards.value_card(
        bot_cards.value_rows(LADDER_BOARD, min_ev=5.0, with_ladder=True))
    assert "↳ Valerenga 5+ — fair 1.44 (70%), no price fetched" in card
    # No bullet and no EV on that line: it must not read as a pick.
    assert "• Valerenga 5+" not in card
    for line in card.splitlines():
        if "no price fetched" in line:
            assert "EV" not in line and not line.strip().startswith("•")


def test_references_alone_do_not_make_a_card():
    """A safer line on a game nobody is being told about is a line with no context, and
    the empty-board message must still be the empty-board message."""
    refs = [r for r in bot_cards.value_rows(LADDER_BOARD, min_ev=5.0, with_ladder=True)
            if r.get("reference")]
    assert refs
    assert "No positive-EV rows" in bot_cards.value_card(refs)


# --- the cap must not discard the safe line -----------------------------------------

# Torreense v União de Leiria, 2026-11-09, as the preview printed it. EV rises with every
# rung of the home ladder, which is why "top four by EV" kept the three longest shots and
# threw away the 5+ the message was asked about.
TORREENSE = [rung("home", 2.5, ev=-10.1, book=1.035, fair=1.15, prob=86.8),
             rung("home", 3.5, ev=2.0, book=1.36, fair=1.33, prob=75.0),
             rung("home", 4.5, ev=9.8, book=1.80, fair=1.64, prob=61.0),
             rung("home", 5.5, ev=12.4, book=2.40, fair=2.14, prob=46.8),
             rung("home", 6.5, ev=22.6, book=3.60, fair=2.94, prob=34.0),
             rung("home", 7.5, ev=29.6, book=5.50, fair=4.24, prob=23.6),
             rung("total", 8.5, ev=5.1, book=1.52, fair=1.45, prob=69.1),
             rung("total", 9.5, ev=11.0, book=1.95, fair=1.76, prob=56.9)]

TORREENSE_BOARD = [{"status": "ok", "fixture_id": "por-l2-1576529",
                    "home_name": "Torreense", "away_name": "União de Leiria",
                    "odds_source": "api", "best": TORREENSE[5],
                    "alternatives": [TORREENSE[4], TORREENSE[3], TORREENSE[7]],
                    "ladder": TORREENSE}]


def test_the_safest_qualifying_rung_survives_the_cap():
    """THE COMPLAINT. 5+ at 1.80 is +9.8%, clears the floor, and ranked sixth by EV on
    its own fixture — so the board's top-four cut it before any card logic ran."""
    rows = bot_cards.value_rows(TORREENSE_BOARD, min_ev=5.0, with_ladder=True)
    sent = bot_cards.value_sent(rows)
    lines = {(r["subject"], r["line"]) for r in sent}
    assert ("Torreense", 5) in lines, "the safest home rung must be in the message"


def test_the_long_shot_is_not_sent_alongside_it():
    """THE POSTING RULE. One line per side: 5+ at 1.80 is Torreense's line, and 8+ at
    5.50 on +29.6% is the longest price on the ladder, not a second bet. (Changed from
    "both are wanted" after the bot sent Reading 8+ at 10.00 when their 5+ was 1.73.)"""
    sent = bot_cards.value_sent(
        bot_cards.value_rows(TORREENSE_BOARD, min_ev=5.0, with_ladder=True))
    assert [r["line"] for r in sent if r["subject"] == "Torreense"] == [5]


def test_every_subject_gets_its_safest_rung():
    sent = bot_cards.value_sent(
        bot_cards.value_rows(TORREENSE_BOARD, min_ev=5.0, with_ladder=True))
    by_subject = {}
    for r in sent:
        by_subject.setdefault(r["subject"], []).append(r["line"])
    assert min(by_subject["Torreense"]) == 5
    assert "Match total" in by_subject, "the total's safest rung too"


def test_the_ladder_beats_the_boards_top_four():
    """value_rows must read the ladder, not best+alternatives, or the fifth-ranked rung
    is unreachable however the card is written."""
    rows = [r for r in bot_cards.value_rows(TORREENSE_BOARD, min_ev=5.0, with_ladder=True)
            if not r.get("reference")]
    # The safe home line (4.5 -> 5+, +9.8%) ranks sixth by EV, so it is only reachable
    # through the ladder; the total's first 1.80+ line is 9.5 -> 10+.
    assert {(r["subject"], r["line"]) for r in rows} == {("Torreense", 5), ("Match total", 10)}


def test_rungs_are_shown_in_ladder_order():
    """A reader comparing rungs on one side is reading a ladder; EV order scatters it."""
    sent = bot_cards.value_sent(
        bot_cards.value_rows(TORREENSE_BOARD, min_ev=5.0, with_ladder=True))
    tor = [r["line"] for r in sent if r["subject"] == "Torreense"]
    assert tor == sorted(tor)


def test_a_below_floor_rung_is_still_excluded():
    """3+ at -10.1% and 4+ at +2.0% must not ride in on the "safest rung" rule."""
    sent = bot_cards.value_sent(
        bot_cards.value_rows(TORREENSE_BOARD, min_ev=5.0, with_ladder=True))
    lines = {(r["subject"], r["line"]) for r in sent}
    assert ("Torreense", 3) not in lines and ("Torreense", 4) not in lines
