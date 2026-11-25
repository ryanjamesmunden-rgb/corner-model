"""The week card: one fixture, both sides, the bet and the evidence beside it.

The thing these tests are mostly about is the join between a PRICE and a RUN. Those come
from two different boards and are two different lines as often as not, and a card that
prints one under the other without checking is a card that credits a 6+ bet with a 5+
record. Everything else here is layout.
"""
import week_card


def rung(group, line, ev=None, book=None, cred="credible", fair=1.60, prob=62.5):
    return {"key": f"{group}_over_{line - 0.5}", "group": group, "line": line,
            "label": f"{line}+", "book_odds": book, "fair_odds": fair, "prob": prob,
            "ev": ev, "credibility": cred, "tier": "strong" if (ev or 0) > 5 else "none"}


def board_row(team_id="t1", fixture_id="fx1", line=5, hits=9, settled=10, floor=4,
              boards=("streaks",), warnings=()):
    return {"team_id": team_id, "name": "Bradford",
            "next_fixture": {"fixture_id": fixture_id, "opponent": "Barnsley",
                             "is_home": True, "date": "2026-11-24T19:45:00+00:00"},
            "boards": list(boards), "warnings": list(warnings),
            "streak": {"side": "home", "line": line, "line_label": f"{line}+",
                       "hits": hits, "settled": settled, "floor": floor, "length": 6}}


def value_row(ladder, fixture_id="fx1", status="ok"):
    return {"fixture_id": fixture_id, "date": "2026-11-24T19:45:00+00:00",
            "league_id": "eng-l1", "league_name": "League One", "tier": 3,
            "home_name": "Bradford", "away_name": "Barnsley",
            "home_team_id": "t1", "away_team_id": "t2",
            "status": status, "ladder": ladder, "lambda_total": 10.8}


# --- picking the rung -------------------------------------------------------------

def test_the_run_decides_the_line_even_when_another_rung_pays_more():
    # THE POINT OF THE WHOLE FILE. A 5+ run of 9/10 and a 6+ rung at +22% both exist.
    # Leading with 6+ puts the 9/10 under a bet it is not a record of.
    ladder = [rung("home", 5, ev=8.0, book=1.73), rung("home", 6, ev=22.0, book=2.10)]
    assert week_card.pick_rung(ladder, "home", run_line=5)["line"] == 5


def test_without_a_run_the_biggest_credible_edge_leads():
    ladder = [rung("home", 5, ev=8.0, book=1.73), rung("home", 6, ev=22.0, book=2.10)]
    assert week_card.pick_rung(ladder, "home", run_line=None)["line"] == 6


def test_a_broken_price_never_leads_a_card():
    # The value board demotes `implausible`; a card is read as a recommendation, so it
    # must not head one either — the quieter, believable rung wins.
    ladder = [rung("home", 5, ev=6.0, book=1.73),
              rung("home", 9, ev=310.0, book=9.0, cred="implausible")]
    assert week_card.pick_rung(ladder, "home")["line"] == 5


def test_a_broken_price_still_shows_when_it_is_the_only_one():
    # Hidden, it looks like no price exists. Shown, it is visibly wrong and can be fixed.
    ladder = [rung("home", 9, ev=310.0, book=9.0, cred="implausible")]
    assert week_card.pick_rung(ladder, "home")["line"] == 9


def test_the_run_cannot_drag_a_card_onto_a_broken_price():
    ladder = [rung("home", 5, ev=300.0, book=8.0, cred="implausible"),
              rung("home", 6, ev=9.0, book=1.90)]
    assert week_card.pick_rung(ladder, "home", run_line=5)["line"] == 6


def test_credibility_outranks_the_size_of_the_edge():
    ladder = [rung("home", 5, ev=9.0, book=1.90, cred="credible"),
              rung("home", 6, ev=28.0, book=2.60, cred="outlier")]
    assert week_card.pick_rung(ladder, "home")["line"] == 5


def test_an_unpriced_rung_is_offered_rather_than_nothing():
    # No book has quoted it. The model's fair price is still the answer to "what is this
    # bet worth", and "no price yet" is a fact about the book.
    pick = week_card.pick_rung([rung("home", 5, ev=None, book=None, prob=66.0)], "home")
    assert pick["line"] == 5 and pick["book_odds"] is None and pick["fair_odds"]


def test_a_priced_rung_beats_an_unpriced_one_whatever_the_probability():
    ladder = [rung("home", 4, ev=None, book=None, prob=88.0),
              rung("home", 6, ev=3.0, book=1.80, prob=57.0)]
    assert week_card.pick_rung(ladder, "home")["book_odds"] == 1.80


def test_the_other_side_of_the_game_is_never_picked():
    ladder = [rung("home", 5, ev=4.0, book=1.70), rung("away", 7, ev=40.0, book=3.0)]
    assert week_card.pick_rung(ladder, "home")["group"] == "home"
    assert week_card.pick_rung(ladder, "away")["group"] == "away"


def test_a_side_with_no_rung_at_all_is_none():
    assert week_card.pick_rung([rung("away", 5, ev=4.0, book=1.7)], "home") is None
    assert week_card.pick_rung([], "home") is None
    assert week_card.pick_rung(None, "home") is None


# --- one side ---------------------------------------------------------------------

def test_a_side_says_when_its_run_is_at_a_different_line_from_its_bet():
    ladder = [rung("home", 6, ev=12.0, book=1.95)]          # no 5+ rung priced
    side = week_card.side_card("Bradford", "t1", "home", ladder, board_row(line=5))
    assert side["pick"]["line"] == 6
    assert side["run"]["line"] == 5
    assert side["run_matches_pick"] is False


def test_a_side_whose_run_and_bet_agree_says_so():
    ladder = [rung("home", 5, ev=12.0, book=1.95)]
    side = week_card.side_card("Bradford", "t1", "home", ladder, board_row(line=5))
    assert side["run_matches_pick"] is True


def test_a_side_on_no_board_is_still_a_side():
    # Most sides are on no board. A card with one interesting half is still a card.
    side = week_card.side_card("Barnsley", "t2", "away",
                               [rung("away", 4, ev=2.0, book=1.60)], None)
    assert side["run"] is None and side["boards"] == []
    assert side["pick"]["line"] == 4
    assert side["run_matches_pick"] is False


def test_a_side_carries_its_boards_and_its_warnings():
    side = week_card.side_card("Bradford", "t1", "home", [rung("home", 5, ev=2.0, book=1.6)],
                               board_row(boards=("quick_scan", "streaks"),
                                         warnings=("opponent has only 9 games",)))
    assert side["boards"] == ["quick_scan", "streaks"]
    assert side["warnings"] == ["opponent has only 9 games"]


# --- the card ---------------------------------------------------------------------

def test_a_card_has_both_sides_and_the_match_line():
    ladder = [rung("home", 5, ev=9.0, book=1.80), rung("away", 4, ev=3.0, book=1.70),
              rung("total", 11, ev=6.0, book=1.83)]
    card = week_card.build_card(value_row(ladder), {"home": board_row()})
    assert card["home"]["name"] == "Bradford" and card["away"]["name"] == "Barnsley"
    assert card["home"]["pick"]["line"] == 5 and card["away"]["pick"]["line"] == 4
    assert card["total"]["line"] == 11
    assert card["run_count"] == 1 and card["pick_count"] == 2


def test_a_card_with_no_match_line_simply_has_none():
    ladder = [rung("home", 5, ev=9.0, book=1.80)]
    assert week_card.build_card(value_row(ladder), {})["total"] is None


def test_the_boards_on_a_card_are_both_sides_merged_without_repeats():
    card = week_card.build_card(
        value_row([rung("home", 5, ev=1.0, book=1.6), rung("away", 5, ev=1.0, book=1.6)]),
        {"home": board_row(boards=("streaks", "quick_scan")),
         "away": board_row(team_id="t2", boards=("streaks", "perfect_games"))})
    assert card["boards"] == ["perfect_games", "quick_scan", "streaks"]


def test_a_card_keeps_the_rows_status_so_a_thin_game_reads_as_thin():
    card = week_card.build_card(value_row([], status="below_floor"), {})
    assert card["status"] == "below_floor"
    assert card["pick_count"] == 0 and card["run_count"] == 0


# --- the day ----------------------------------------------------------------------

def test_cards_come_back_in_kick_off_order_not_by_edge():
    # A diary, not a ranking. The boards already rank by edge; this is read down the day.
    late = {**value_row([rung("home", 5, ev=40.0, book=2.5)], fixture_id="late"),
            "date": "2026-11-24T20:00:00+00:00"}
    early = {**value_row([rung("home", 5, ev=2.0, book=1.6)], fixture_id="early"),
             "date": "2026-11-24T12:30:00+00:00"}
    out = week_card.build_cards([late, early], [])
    assert [c["fixture_id"] for c in out] == ["early", "late"]


def test_a_board_row_reaches_only_its_own_team_and_its_own_fixture():
    # The join is (team, fixture). A team's run from LAST week's game must not attach to
    # this one, and the away side's row must not land on the home side.
    rows = [value_row([rung("home", 5, ev=1.0, book=1.6), rung("away", 5, ev=1.0, book=1.6)])]
    stale = board_row(team_id="t1", fixture_id="an-older-game")
    theirs = board_row(team_id="t2", fixture_id="fx1", line=6)
    out = week_card.build_cards(rows, [stale, theirs])
    assert out[0]["home"]["run"] is None
    assert out[0]["away"]["run"]["line"] == 6


def test_each_side_gets_its_own_game_state_verdict():
    # _game_state_for reads the side off the headline market, which on a two-sided card
    # would give both halves the same verdict. Each side is asked separately.
    seen = []

    def states_for(row, group):
        seen.append(group)
        return {"verdict": "chase_spot" if group == "away" else "caution"}

    out = week_card.build_cards([value_row([rung("home", 5, ev=1.0, book=1.6)])], [],
                                states_for)
    assert seen == ["home", "away"]
    assert out[0]["home"]["game_state"]["verdict"] == "caution"
    assert out[0]["away"]["game_state"]["verdict"] == "chase_spot"


def test_no_game_state_source_leaves_the_field_empty_rather_than_guessing():
    out = week_card.build_cards([value_row([rung("home", 5, ev=1.0, book=1.6)])], [])
    assert out[0]["home"]["game_state"] is None


def test_nothing_in_means_nothing_out():
    assert week_card.build_cards([], []) == []
    assert week_card.build_cards(None, None) == []


# --- a line the run cannot reach ------------------------------------------------------
#
# A real card led with "VfB Stuttgart 8+ at 13.00" under a 4+ record. Nothing was broken:
# the model gave 8+ a 10.3% chance, 13.00 x 0.103 is +34%, and +34% beat the 4+ rung's
# +13%. But the whole of that +34% sits inside two points of model error at a price that
# long, and the run — the one measured thing on the card — reached 4+ and no further.

def test_the_card_will_not_lead_with_a_line_the_run_cannot_reach():
    # The Stuttgart card, with its own numbers.
    ladder = [rung("home", 3, ev=3.2, book=1.37), rung("home", 4, ev=13.4, book=1.94),
              rung("home", 8, ev=34.2, book=13.0)]
    assert week_card.pick_rung(ladder, "home", run_line=4)["line"] == 4


def test_a_rung_below_the_run_outranks_a_long_shot_above_it():
    # The run's line is not priced at all. A record of 4+ in nine of ten is also a record
    # of 3+ in nine of ten; it is no record of 8+, so the short one leads.
    ladder = [rung("home", 3, ev=3.2, book=1.37), rung("home", 8, ev=34.2, book=13.0)]
    assert week_card.pick_rung(ladder, "home", run_line=4)["line"] == 3


def test_the_edge_still_decides_between_rungs_the_run_reaches():
    # Both are at or under the run, so neither is a stretch and the bigger edge wins.
    ladder = [rung("home", 3, ev=3.0, book=1.37), rung("home", 4, ev=13.0, book=1.94)]
    assert week_card.pick_rung(ladder, "home", run_line=5)["line"] == 4


def test_credibility_still_comes_before_reach():
    # A credible rung two lines above the run beats an OUTLIER one line above it. The
    # reach rule reorders rungs the card is willing to lead with; it does not promote one
    # it already distrusts.
    ladder = [rung("home", 5, ev=70.0, book=3.0, cred="outlier"),
              rung("home", 6, ev=9.0, book=1.9)]
    assert week_card.pick_rung(ladder, "home", run_line=4)["line"] == 6


def test_with_no_run_the_biggest_edge_still_leads():
    # Nothing measured to correct against, so the sort is unchanged.
    ladder = [rung("home", 4, ev=13.4, book=1.94), rung("home", 8, ev=34.2, book=13.0)]
    assert week_card.pick_rung(ladder, "home", run_line=None)["line"] == 8


def test_a_long_shot_still_shows_when_it_is_the_only_price():
    # "No price at the line your record covers" is a fact about the book. Hiding the one
    # quote there is would leave the side blank and say nothing at all.
    ladder = [rung("home", 8, ev=34.2, book=13.0)]
    assert week_card.pick_rung(ladder, "home", run_line=4)["line"] == 8


def test_a_side_carries_what_its_opponent_gives_up():
    # The half a run cannot see: five games against five other opponents say nothing
    # about the one in front of it.
    row = board_row()
    row["quick_scan"] = {"opp_conceded": 3.1, "lambda": 4.3}
    side = week_card.side_card("Bradford", "t1", "home",
                               [rung("home", 5, ev=8.0, book=1.73)], row)
    assert side["opp_conceded"] == 3.1


def test_an_opponent_with_no_measured_leak_is_none_rather_than_zero():
    # Zero conceded is a real number and "we never measured it" is not.
    side = week_card.side_card("Bradford", "t1", "home",
                               [rung("home", 5, ev=8.0, book=1.73)], board_row())
    assert side["opp_conceded"] is None
