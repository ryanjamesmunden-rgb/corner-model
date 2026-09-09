"""Unit tests for the three things the fixture page now says out loud.

`corner_distribution` is the curve behind the headline percentage — it has to be the SAME
pmf the price uses, or the chart argues with the number printed beside it.

`team_profile` and `key_factors` turn measured averages into sentences. The risk with
generated prose is that it says something the data does not, so these pin the direction of
every claim and, above all, that both stay SILENT on a thin sample rather than guessing.
"""
import os
import sys

import pytest

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "test_corner_model")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from server import (  # noqa: E402
    PROFILE_MIN_GAMES, card_climate, corner_distribution, h2h_cards, key_factors, nb_ge,
    nb_pmf, poisson_ge, team_discipline, team_profile,
)

LG = 5.0        # league corners per team per game


def match(home=True, cf=5, ca=5, fh=0, fha=0, first_min=None, opp_first=None,
          scored_first=None, gf=1, ga=1, i=0):
    # `fh` / `fha` are the HALF-TIME goals either way, which is what the game-state split
    # classifies on — full-time goals do not decide the "ht" buckets.
    return {"home": home, "corners_for": cf, "corners_against": ca,
            "goals_for": gf, "goals_against": ga,
            "fh_goals_for": fh, "fh_goals_against": fha,
            "minutes_trailing": 20, "minutes_level": 40, "minutes_leading": 30,
            "first_goal_min": first_min, "opp_first_goal_min": opp_first,
            "scored_first": scored_first, "scorers": [],
            "opponent": "X", "date": f"2026-01-{i + 1:02d}"}


def team(n=10, home=True, cf=5, ca=5, **kw):
    return {"team_id": "t", "name": "T", "league_id": "lg",
            "real_matches": [match(home=home, cf=cf, ca=ca, i=i, **kw) for i in range(n)]}


# --- the distribution must be the model's own, not a lookalike ---
@pytest.mark.parametrize("group,ge", [("home", nb_ge), ("away", nb_ge), ("total", poisson_ge)])
def test_distribution_sums_to_the_same_probability_the_price_uses(group, ge):
    """Summing the bars at or above a line must reproduce the priced P(>= line).

    This is the invariant that stops the chart and the number disagreeing: if someone
    later swaps the pmf on one side only, the two stop matching and this fails."""
    lam = 6.4
    dist = corner_distribution(lam, group)
    for line in (4, 5, 6, 7):
        drawn = sum(r["p"] for r in dist if r["k"] >= line)
        assert drawn == pytest.approx(ge(line, lam), abs=0.005)


def test_distribution_is_trimmed_but_still_covers_the_mass():
    dist = corner_distribution(6.0, "home")
    assert sum(r["p"] for r in dist) > 0.98          # nothing meaningful cut off
    assert len(dist) < 25                            # but not a long flat tail either
    assert [r["k"] for r in dist] == sorted(r["k"] for r in dist)


def test_distribution_peaks_near_lambda():
    dist = corner_distribution(7.0, "home")
    peak = max(dist, key=lambda r: r["p"])["k"]
    assert 5 <= peak <= 9


def test_distribution_uses_nb_for_teams_and_poisson_for_totals():
    """The two differ on purpose; a single shared pmf here would silently change pricing."""
    lam = 10.0
    assert corner_distribution(lam, "home")[3]["p"] != corner_distribution(lam, "total")[3]["p"]
    team_row = next(r for r in corner_distribution(lam, "home") if r["k"] == 10)
    assert team_row["p"] == pytest.approx(round(nb_pmf(10, lam), 5))


# --- team_profile: never louder than the evidence ---
def test_profile_says_nothing_on_a_thin_sample():
    p = team_profile(team(n=PROFILE_MIN_GAMES - 1), "home", LG)
    assert p["traits"] == []
    assert "too few" in p["summary"]


def test_profile_flags_a_big_corner_threat():
    p = team_profile(team(cf=8, ca=5), "home", LG)
    attack = next(t for t in p["traits"] if t["key"] == "attack")
    assert attack["tone"] == "strong" and attack["delta_pct"] == 60
    assert "8.0 corners a game at home" in attack["text"]


def test_profile_flags_a_quiet_attack_as_a_negative():
    p = team_profile(team(cf=3, ca=5), "home", LG)
    attack = next(t for t in p["traits"] if t["key"] == "attack")
    assert attack["tone"] == "under"


def test_profile_reads_a_leaky_defence_as_an_opportunity_not_a_flaw():
    """Conceding corners is the half of a mismatch the OTHER team's price is built on, so
    it is toned as an edge rather than as a weakness."""
    d = next(t for t in team_profile(team(cf=5, ca=8), "home", LG)["traits"]
             if t["key"] == "defence")
    assert d["tone"] == "edge" and "Leaks corners" == d["label"]


def test_profile_flags_a_strong_defence():
    d = next(t for t in team_profile(team(cf=5, ca=3), "home", LG)["traits"]
             if t["key"] == "defence")
    assert d["tone"] == "strong"


def test_profile_compares_the_two_venues_only_when_both_have_games():
    mixed = {"team_id": "t", "name": "T", "league_id": "lg", "real_matches": (
        [match(home=True, cf=9, i=i) for i in range(6)]
        + [match(home=False, cf=4, i=i) for i in range(6)])}
    v = next(t for t in team_profile(mixed, "home", LG)["traits"] if t["key"] == "venue")
    assert v["tone"] == "strong" and "9.0" in v["text"] and "4.0" in v["text"]
    # one-venue team: no comparison claimed
    assert not [t for t in team_profile(team(cf=9), "home", LG)["traits"] if t["key"] == "venue"]


def test_profile_of_an_average_team_says_so_plainly():
    p = team_profile(team(cf=5, ca=5), "home", LG)
    assert p["traits"] == [] and "Nothing unusual" in p["summary"]


def test_profile_never_divides_by_a_missing_league_average():
    assert team_profile(team(cf=8), "home", 0.0)["traits"] == []


# --- key_factors: measured, or explicitly not ---
def carded(m, yellows=2, reds=0, fouls=12, against_y=2, against_r=0):
    """Attach collected card data to a match. A match WITHOUT these keys is one the
    backfill never reached, which is a different thing from a clean match."""
    m.update({"yellow_cards_for": yellows, "red_cards_for": reds, "fouls_for": fouls,
              "yellow_cards_against": against_y, "red_cards_against": against_r})
    return m


def league(n_teams=6, games=10, yellows=2, reds=0, fouls=12):
    """A league with enough team-matches behind it to support a rate."""
    return [{"team_id": f"t{i}", "name": f"T{i}", "league_id": "lg",
             "real_matches": [carded(match(home=j % 2 == 0, i=j), yellows, reds, fouls)
                              for j in range(games)]}
            for i in range(n_teams)]


def disciplined(name="T", n=10, yellows=2, reds=0, fouls=12, opponent="X", home=True,
                against_y=2, against_r=0):
    return {"team_id": name, "name": name, "league_id": "lg",
            "real_matches": [carded({**match(home=home, i=j), "opponent": opponent},
                                    yellows, reds, fouls, against_y, against_r)
                             for j in range(n)]}


# --- with no card data at all, the topic still gets said, without a number ---
def test_says_so_when_no_card_history_has_been_collected():
    fs = key_factors(team(), team(), "home", "Us", "Them", [])
    rc = next(f for f in fs if f["key"] == "red_card")
    assert rc["measured"] is False and "No card history collected yet" in rc["detail"]
    assert "Them" in rc["detail"]


# --- 1. the league's climate ---
def test_reports_the_leagues_card_rate_and_how_often_a_red_appears():
    lg = league(n_teams=6, games=10, yellows=2, reds=0)
    f = next(x for x in key_factors(disciplined(), team(), "home", "Us", "Them", lg)
             if x["key"] == "card_climate")
    assert f["measured"] is True and f["games"] == 60
    assert "4.0 cards a match" in f["detail"]      # 2 yellows per team, doubled
    assert "rare enough here" in f["detail"]


def test_a_card_heavy_league_is_called_out_as_one():
    lg = league(n_teams=6, games=10, yellows=3, reds=1)
    f = next(x for x in key_factors(disciplined(), team(), "home", "Us", "Them", lg)
             if x["key"] == "card_climate")
    assert "100% of them" in f["detail"] and "worth watching" in f["detail"]


def test_a_thin_league_sample_gets_no_rate_at_all():
    """Below CLIMATE_MIN_GAMES there is no league rate worth printing."""
    assert card_climate(league(n_teams=2, games=5)) is None


# --- 2. fouls and yellows, the dense signal ---
def test_a_fouling_side_is_flagged_as_the_risk():
    lg = league(fouls=11)
    hot = disciplined(name="Us", fouls=15)
    f = next(x for x in key_factors(hot, team(), "home", "Us", "Them", lg)
             if x["key"] == "discipline_team")
    assert f["kind"] == "risk"
    assert "15.0 fouls a game against a league 11.0" in f["detail"]
    assert "their man off is what kills the bet" in f["detail"]


def test_the_opponent_fouling_is_the_good_news_not_the_bad():
    """Their discipline points the other way: their card is the gift."""
    lg = league(fouls=11)
    f = next(x for x in key_factors(disciplined(), disciplined(name="Them", fouls=15),
                                    "home", "Us", "Them", lg)
             if x["key"] == "discipline_opp")
    assert f["kind"] == "boost" and "Them and the referee" == f["title"]
    # The two sides must not share a sentence: they point opposite ways.
    assert "THEIR man off that makes this bet" in f["detail"]


def test_an_ordinary_fouling_side_is_not_dressed_up_as_a_signal():
    lg = league(fouls=11)
    f = next(x for x in key_factors(disciplined(fouls=11), team(), "home", "Us", "Them", lg)
             if x["key"] == "discipline_team")
    assert f["kind"] == "watch" and "luck rather than a pattern" in f["detail"]


def test_discipline_falls_back_to_yellows_when_fouls_are_not_collected_yet():
    """Fouls only arrive with the next sync; yellows are already there."""
    t = disciplined()
    for m in t["real_matches"]:
        m["fouls_for"] = None
    lg = league()
    for team_doc in lg:
        for m in team_doc["real_matches"]:
            m["fouls_for"] = None
    f = next(x for x in key_factors(t, team(), "home", "Us", "Them", lg)
             if x["key"] == "discipline_team")
    assert "yellows" in f["detail"] and "fouls a game" not in f["detail"]


# --- 3. the head-to-head, which is free ---
def test_the_last_meeting_between_these_two_is_reported():
    t = disciplined(opponent="Them", yellows=3, against_y=3, reds=1)
    f = next(x for x in key_factors(t, team(), "home", "Us", "Them", league())
             if x["key"] == "h2h_cards")
    assert f["measured"] is True
    assert "7 cards" in f["detail"] and "sending-off" in f["detail"]
    assert "produces another" in f["detail"]


def test_no_head_to_head_row_when_these_two_have_not_met():
    t = disciplined(opponent="Someone Else")
    assert not [x for x in key_factors(t, team(), "home", "Us", "Them", league())
                if x["key"] == "h2h_cards"]


def test_the_head_to_head_matches_the_name_case_insensitively():
    t = disciplined(opponent="them fc")
    assert h2h_cards(t, "Them FC") is not None


def test_a_quiet_head_to_head_is_not_talked_up():
    t = disciplined(opponent="Them", yellows=1, against_y=1)
    f = next(x for x in key_factors(t, team(), "home", "Us", "Them", league())
             if x["key"] == "h2h_cards")
    assert "quiet one" in f["detail"]


# --- 4. reds as a count, never a rate ---
def test_reds_are_reported_as_a_count_with_their_window():
    t = disciplined(n=18, reds=0)
    t["real_matches"][0]["red_cards_for"] = 1
    f = next(x for x in key_factors(t, team(), "home", "Us", "Them", league())
             if x["key"] == "red_card")
    assert "1 in their last 18 games" in f["detail"]
    assert "not a claim about how likely" in f["detail"]


def test_the_red_card_row_never_prints_a_percentage():
    """The whole reason this was rewritten: 1 red in 9 games is a 2%-44% interval, so any
    percentage here would be a number the sample cannot support."""
    t = disciplined(n=9)
    t["real_matches"][0]["red_cards_for"] = 1
    f = next(x for x in key_factors(t, team(), "home", "Us", "Them", league())
             if x["key"] == "red_card")
    assert "%" not in f["detail"]


def test_a_clean_record_says_none_rather_than_claiming_discipline():
    t = disciplined(n=12, reds=0)
    f = next(x for x in key_factors(t, team(), "home", "Us", "Them", league())
             if x["key"] == "red_card")
    assert "None in their last 12 games" in f["detail"] and f["kind"] == "boost"


def test_matches_the_backfill_never_reached_are_not_counted_as_clean():
    """A missing key means "we don't know", not "no cards". Treating it as zero would put
    every un-backfilled game in the denominator and dilute the rate toward nothing."""
    ms = [match(home=True, cf=5, i=i) for i in range(9)]      # no card keys at all
    t = {"team_id": "t", "name": "T", "league_id": "lg", "real_matches": ms}
    rc = next(f for f in key_factors(t, team(), "home", "Us", "Them") if f["key"] == "red_card")
    assert rc["measured"] is False


def test_early_goal_risk_is_reported_with_its_sample():
    t = team(n=10, first_min=25, scored_first=True)
    f = next(x for x in key_factors(t, team(), "home", "Us", "Them") if x["key"] == "early_goal")
    assert f["kind"] == "risk" and f["games"] == 10 and "100%" in f["detail"]


def test_early_goal_risk_is_omitted_without_goal_coverage():
    """`goal_profile` only covers matches the goal backfill reached; no coverage, no claim."""
    bare = {"team_id": "t", "name": "T", "league_id": "lg", "real_matches": [
        {"home": True, "corners_for": 5, "corners_against": 5, "opponent": "X",
         "date": f"2026-01-{i + 1:02d}"} for i in range(10)]}
    assert not [f for f in key_factors(bare, bare, "home", "Us", "Them")
                if f["key"] == "early_goal"]


def test_a_team_that_wins_corners_when_behind_reads_as_a_boost():
    ms = ([match(home=True, cf=9, fh=0, fha=1, i=i) for i in range(4)]         # trailing at HT
          + [match(home=True, cf=4, fh=2, fha=0, i=i + 4) for i in range(4)])  # leading at HT
    t = {"team_id": "t", "name": "T", "league_id": "lg", "real_matches": ms}
    f = next(x for x in key_factors(t, team(), "home", "Us", "Them") if x["key"] == "chase")
    assert f["kind"] == "boost" and "good news for this bet" in f["detail"]


def test_the_chase_factor_needs_games_in_both_states():
    """All-leading history cannot support a claim about what happens when behind."""
    t = {"team_id": "t", "name": "T", "league_id": "lg",
         "real_matches": [match(home=True, cf=4, fh=2, fha=0, i=i) for i in range(8)]}
    assert not [f for f in key_factors(t, team(), "home", "Us", "Them") if f["key"] == "chase"]


def test_a_passive_opponent_is_surfaced_as_a_boost():
    slow = team(n=8, home=False, scored_first=False)
    f = next(x for x in key_factors(team(), slow, "home", "Us", "Them") if x["key"] == "opp_slow")
    assert f["kind"] == "boost" and "Them" in f["title"] and "0%" in f["detail"]


def test_every_factor_carries_a_title_and_a_kind():
    for f in key_factors(team(n=10, first_min=25, scored_first=True), team(), "home", "Us", "Them"):
        assert f["title"] and f["kind"] in {"risk", "boost", "watch"} and f["detail"]
