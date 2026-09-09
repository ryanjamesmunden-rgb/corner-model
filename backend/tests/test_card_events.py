"""Unit tests for card parsing.

The expensive mistake here is UNDERCOUNTING sendings-off, because the whole point of the
feature is "what happens when a side goes down to ten" — and a match where that is missed
is silently filed as an ordinary one, which drags the effect toward zero. So most of these
are about the ways the provider hides a dismissal.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from card_events import (  # noqa: E402
    OFF, RED, SECOND_YELLOW, YELLOW, card_summary, parse_card_events, team_card_sample,
)

HOME, AWAY = 10, 20


def ev(kind_detail, team, minute, player="A. Player", type_="Card", extra=None):
    return {"type": type_, "detail": kind_detail, "team": {"id": team},
            "time": {"elapsed": minute, "extra": extra},
            "player": {"name": player}}


def test_reads_reds_and_yellows_with_minutes_and_sides():
    cards = parse_card_events([
        ev("Yellow Card", HOME, 12, "H One"),
        ev("Red Card", AWAY, 66, "A One"),
    ], HOME, AWAY)
    assert [(c["kind"], c["side"], c["minute"]) for c in cards] == [
        (YELLOW, "home", 12), (RED, "away", 66)]


def test_ignores_goals_and_substitutions_in_the_same_feed():
    """The events response carries everything; only cards are ours."""
    cards = parse_card_events([
        ev("Normal Goal", HOME, 20, type_="Goal"),
        ev("Substitution 1", HOME, 60, type_="subst"),
        ev("Yellow Card", HOME, 70),
    ], HOME, AWAY)
    assert len(cards) == 1 and cards[0]["kind"] == YELLOW


def test_a_labelled_second_yellow_is_a_sending_off():
    cards = parse_card_events([ev("Second Yellow card", HOME, 80, "H One")], HOME, AWAY)
    assert cards[0]["kind"] == SECOND_YELLOW
    assert card_summary(cards)["home_reds"] == 1


def test_two_plain_yellows_for_one_player_are_a_sending_off():
    """The provider often reports the second as an ordinary yellow. Taking that at face
    value loses the dismissal in exactly the matches most likely to have one."""
    cards = parse_card_events([
        ev("Yellow Card", HOME, 30, "H One"),
        ev("Yellow Card", HOME, 75, "H One"),
    ], HOME, AWAY)
    assert [c["kind"] for c in cards] == [YELLOW, SECOND_YELLOW]
    assert card_summary(cards)["home_reds"] == 1


def test_two_yellows_for_DIFFERENT_players_are_not_a_sending_off():
    cards = parse_card_events([
        ev("Yellow Card", HOME, 30, "H One"),
        ev("Yellow Card", HOME, 75, "H Two"),
    ], HOME, AWAY)
    assert [c["kind"] for c in cards] == [YELLOW, YELLOW]
    assert card_summary(cards)["home_reds"] == 0


def test_the_same_player_name_on_opposing_sides_is_not_conflated():
    cards = parse_card_events([
        ev("Yellow Card", HOME, 30, "J Smith"),
        ev("Yellow Card", AWAY, 75, "J Smith"),
    ], HOME, AWAY)
    assert [c["kind"] for c in cards] == [YELLOW, YELLOW]


def test_an_unnamed_second_yellow_is_left_as_a_yellow():
    """Two unnamed yellows cannot be shown to be the same player, and inventing a
    dismissal is worse than missing one — it would put a fake red in the record."""
    cards = parse_card_events([
        ev("Yellow Card", HOME, 30, None),
        ev("Yellow Card", HOME, 75, None),
    ], HOME, AWAY)
    assert [c["kind"] for c in cards] == [YELLOW, YELLOW]


def test_cards_are_sorted_by_minute_including_stoppage_time():
    cards = parse_card_events([
        ev("Red Card", AWAY, 90, "Late", extra=4),
        ev("Yellow Card", HOME, 90, "Early"),
        ev("Yellow Card", HOME, 45, "First"),
    ], HOME, AWAY)
    assert [c["player"] for c in cards] == ["First", "Early", "Late"]


def test_events_without_a_minute_or_a_known_team_are_dropped():
    cards = parse_card_events([
        {"type": "Card", "detail": "Red Card", "team": {"id": HOME}, "time": {"elapsed": None}},
        ev("Red Card", 999, 40),          # a team not in this fixture
    ], HOME, AWAY)
    assert cards == []


def test_summary_counts_each_side_and_the_first_dismissal_minute():
    s = card_summary(parse_card_events([
        ev("Yellow Card", HOME, 10, "H1"),
        ev("Red Card", HOME, 55, "H2"),
        ev("Red Card", HOME, 70, "H3"),
        ev("Yellow Card", AWAY, 80, "A1"),
    ], HOME, AWAY))
    assert s["home_reds"] == 2 and s["home_yellows"] == 1 and s["home_first_red_min"] == 55
    assert s["away_reds"] == 0 and s["away_yellows"] == 1 and s["away_first_red_min"] is None


def test_a_second_yellow_does_not_also_count_as_a_yellow():
    """Otherwise a dismissal inflates the yellow count as well as the red one."""
    s = card_summary(parse_card_events([
        ev("Yellow Card", HOME, 30, "H One"),
        ev("Yellow Card", HOME, 75, "H One"),
    ], HOME, AWAY))
    assert s["home_reds"] == 1 and s["home_yellows"] == 1


def test_the_team_sample_keeps_both_directions():
    """A team's own red is the risk; the opponent's is the gift. One-sided storage would
    lose the half the site actually leads with."""
    s = card_summary(parse_card_events([
        ev("Red Card", AWAY, 33, "A1"), ev("Yellow Card", HOME, 60, "H1"),
    ], HOME, AWAY))
    home = team_card_sample(s, "home")
    assert home["red_cards_for"] == 0 and home["red_cards_against"] == 1
    assert home["first_red_min_against"] == 33 and home["first_red_min_for"] is None
    away = team_card_sample(s, "away")
    assert away["red_cards_for"] == 1 and away["red_cards_against"] == 0
    assert away["yellow_cards_against"] == 1


def test_a_clean_match_records_zeros_not_blanks():
    """Zero cards is a FACT about the match. It has to be distinguishable from a fixture
    the backfill never reached, which carries no keys at all."""
    s = card_summary(parse_card_events([ev("Normal Goal", HOME, 5, type_="Goal")], HOME, AWAY))
    sample = team_card_sample(s, "home")
    assert sample["red_cards_for"] == 0 and sample["red_cards_against"] == 0
    assert sample["first_red_min_for"] is None


def test_empty_and_missing_feeds_do_not_throw():
    for feed in ([], None):
        assert parse_card_events(feed, HOME, AWAY) == []
    assert card_summary([])["home_reds"] == 0


def test_off_covers_both_ways_a_player_is_dismissed():
    assert set(OFF) == {RED, SECOND_YELLOW}
