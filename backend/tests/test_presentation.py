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
    PROFILE_MIN_GAMES, corner_distribution, key_factors, nb_ge, nb_pmf, poisson_ge,
    team_profile,
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
def test_red_card_factor_says_so_when_there_is_no_card_history():
    """The scenario still matters with no data, so the row stays — but it must not look
    like a stat. `measured` is the flag the UI uses to label it."""
    rc = next(f for f in key_factors(team(), team(), "home", "Us", "Them") if f["key"] == "red_card")
    assert rc["measured"] is False
    assert "Them" in rc["detail"] and "Not enough card history" in rc["detail"]


def test_red_card_factor_reports_the_drop_when_the_history_is_there():
    # Six clean games at 5 corners, three with a red at 3 — a real, measurable drop.
    ms = ([match(home=True, cf=5, i=i) for i in range(6)]
          + [match(home=True, cf=3, i=i + 6) for i in range(3)])
    for m in ms[:6]:
        m["red_cards_for"], m["red_cards_against"] = 0, 0
    for m in ms[6:]:
        m["red_cards_for"], m["red_cards_against"] = 1, 0
    t = {"team_id": "t", "name": "T", "league_id": "lg", "real_matches": ms}
    rc = next(f for f in key_factors(t, team(), "home", "Us", "Them") if f["key"] == "red_card")
    assert rc["measured"] is True and rc["kind"] == "risk" and rc["games"] == 9
    assert "3 of 9" in rc["detail"] and "main way this bet dies" in rc["detail"]


def test_a_team_that_never_goes_down_to_ten_is_reported_as_a_positive():
    ms = [match(home=True, cf=5, i=i) for i in range(8)]
    for m in ms:
        m["red_cards_for"], m["red_cards_against"] = 0, 0
    t = {"team_id": "t", "name": "T", "league_id": "lg", "real_matches": ms}
    rc = next(f for f in key_factors(t, team(), "home", "Us", "Them") if f["key"] == "red_card")
    assert rc["kind"] == "boost" and rc["measured"] is True
    assert "keep eleven" in rc["title"]


def test_the_opponents_sendings_off_are_reported_as_the_good_news():
    """The half the site leads with: THEIR red is the gift, and it is measured from their
    games, in corners CONCEDED rather than won."""
    ms = ([match(home=False, cf=4, ca=5, i=i) for i in range(6)]
          + [match(home=False, cf=4, ca=9, i=i + 6) for i in range(2)])
    for m in ms[:6]:
        m["red_cards_for"], m["red_cards_against"] = 0, 0
    for m in ms[6:]:
        m["red_cards_for"], m["red_cards_against"] = 1, 0
    opp = {"team_id": "o", "name": "O", "league_id": "lg", "real_matches": ms}
    f = next(x for x in key_factors(team(), opp, "home", "Us", "Them") if x["key"] == "opp_red")
    assert f["kind"] == "boost" and f["measured"] is True
    assert "2 of 8" in f["detail"] and "9.0 corners" in f["detail"]


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
