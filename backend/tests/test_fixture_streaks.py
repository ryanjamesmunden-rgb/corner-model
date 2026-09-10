"""Streaks running INTO a fixture.

The streak board answers "which teams are on a run". This answers the other half —
"what is running into this game" — and it is what the fixture share posts. So what is
pinned here is that it describes the run it claims to: the right games, the right
direction, and nothing dressed up as a streak that is not one.
"""
import os
import sys

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "test_corner_model")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from server import live_streak, fixture_streaks, MIN_STREAK_LEN  # noqa: E402


def m(home, cf, ca, date):
    return {"home": home, "corners_for": cf, "corners_against": ca,
            "opponent": "X", "date": date}


def team(name, matches):
    return {"name": name, "team_id": "t-" + name, "real_matches": matches}


HOME_RUN = team("Derby", [
    m(True, 7, 3, "2026-08-01"),
    m(False, 2, 6, "2026-08-05"),      # an AWAY blank that must not break the home run
    m(True, 8, 4, "2026-08-10"),
    m(True, 6, 5, "2026-08-17"),
    m(True, 9, 2, "2026-08-24"),
])


def test_the_run_is_counted_on_the_venue_being_played():
    """"9 in a row" over a team's home games is a claim about its home games. Mixing the
    aways in would quietly describe a different streak from the one the board shows."""
    r = live_streak(HOME_RUN, "home", "team", "over")
    assert r["run"] == 4 and r["venue"] == "home"
    # The 2-corner away game sits in the middle of those four and is correctly ignored.
    assert live_streak(HOME_RUN, "away", "team", "over") is None


def test_it_keeps_the_most_demanding_line_at_the_same_run_length():
    """4 home games of 7, 8, 6, 9 all clear 3+ as well as 6+. Reporting 3+ would be true
    and worthless — the strongest true claim is the one worth posting."""
    assert live_streak(HOME_RUN, "home", "team", "over")["line"] == 6


def test_a_match_total_reads_both_teams_corners():
    r = live_streak(HOME_RUN, "home", "match", "over")
    assert r["subject"] == "match"
    assert r["line"] == 10          # totals were 10, 12, 11, 11


def test_a_broken_run_is_not_reported():
    """The current run has to be ALIVE. A team that cleared the line four times and then
    missed last week is not carrying anything into this game."""
    broken = team("X", [m(True, 8, 3, "2026-08-01"), m(True, 8, 3, "2026-08-08"),
                        m(True, 1, 3, "2026-08-15")])
    assert live_streak(broken, "home", "team", "over") is None


def test_a_single_game_is_not_a_streak():
    one = team("X", [m(True, 9, 3, "2026-08-01")])
    assert live_streak(one, "home", "team", "over") is None
    assert MIN_STREAK_LEN >= 2


def test_an_under_is_labelled_as_an_under():
    """A run of quiet games is the same kind of story as a run of busy ones, and posting
    it as an over would be a public, wrong claim about what is being suggested."""
    quiet = team("Y", [m(True, 1, 2, "2026-08-01"), m(True, 2, 1, "2026-08-08"),
                       m(True, 0, 2, "2026-08-15")])
    r = live_streak(quiet, "home", "team", "under")
    assert r["direction"] == "under"
    assert r["line_label"].startswith("under ")


def test_a_fixture_lists_both_sides_best_first():
    # A run long enough to be shareable — HOME_RUN's four games sit under SHARE_MIN_RUN,
    # which is the floor doing its job rather than a broken fixture.
    long_run = team("Long", [m(True, 8, 3, f"2026-08-{d:02d}") for d in (1, 4, 8, 11, 15, 18)])
    rows = fixture_streaks(long_run, long_run, "Derby", "West Brom")
    assert rows, "a fixture with live runs on both sides should return rows"
    assert [r["run"] for r in rows] == sorted([r["run"] for r in rows], reverse=True)
    # Trimming a share to fit drops the tail, so the tail has to be the weakest.
    assert {r["team"] for r in rows} <= {"Derby", "West Brom"}


def test_a_fixture_with_no_history_returns_nothing_rather_than_inventing_a_run():
    empty = team("New", [])
    assert fixture_streaks(empty, empty, "A", "B") == []


def test_a_line_too_low_to_mean_anything_is_never_suggested():
    """Every side clears "1+ corners" most weeks. A run at the bottom of the ladder is
    technically true and reads as a joke, so the same floor the streak board uses applies
    here — this test is what caught it being missing."""
    from server import OVER_LINE_FLOOR
    broken = team("X", [m(True, 8, 3, "2026-08-01"), m(True, 8, 3, "2026-08-08"),
                        m(True, 1, 3, "2026-08-15")])
    r = live_streak(broken, "home", "team", "over")
    assert r is None, f"suggested {r and r['line_label']} — below the floor"
    assert OVER_LINE_FLOOR["team"] >= 3


def test_an_under_too_loose_to_mean_anything_is_never_suggested():
    """The mirror: "under 15 corners" lands nearly every week for everyone."""
    from server import UNDER_LINE_CAP
    quiet = team("Y", [m(True, 1, 2, "2026-08-01"), m(True, 2, 1, "2026-08-08")])
    r = live_streak(quiet, "home", "team", "under")
    assert r is None or r["line"] <= UNDER_LINE_CAP["team"]


# --- what a SHARE is allowed to carry ---
def test_a_short_run_stays_on_the_site_and_out_of_the_post():
    """The board can show a 3-game run because on screen you can weigh it yourself. A post
    is read once and scrolled, so only runs worth someone's attention go out."""
    from server import SHARE_MIN_RUN
    assert SHARE_MIN_RUN >= 5
    short = team("Z", [m(True, 9, 3, f"2026-08-{d:02d}") for d in (1, 8, 15)])   # 3 in a row
    assert fixture_streaks(short, short, "Z", "Z") == []


def test_a_long_run_still_goes_out():
    long_run = team("Z", [m(True, 9, 3, f"2026-08-{d:02d}") for d in (1, 4, 8, 11, 15, 18)])
    rows = fixture_streaks(long_run, long_run, "Z", "Z")
    assert rows and all(r["run"] >= 5 for r in rows)


# --- the opponent's own record ---
def test_leak_counts_games_rather_than_averaging_them():
    """An average hides the shape: 9, 9, 1, 1 averages the same as 5, 5, 5, 5 and only the
    second is a matchup worth backing. The count is what tells them apart."""
    from server import opp_leak
    spiky = team("Spiky", [m(False, 3, 9, "2026-08-01"), m(False, 3, 9, "2026-08-08"),
                           m(False, 3, 1, "2026-08-15"), m(False, 3, 1, "2026-08-22")])
    steady = team("Steady", [m(False, 3, 5, f"2026-08-{d:02d}") for d in (1, 8, 15, 22)])
    a, b = opp_leak(spiky, "away"), opp_leak(steady, "away")
    assert a["avg"] == b["avg"]                 # identical averages...
    assert a["hits"]["5"] == 2 and b["hits"]["5"] == 4   # ...and a different story


def test_leak_is_read_at_the_venue_the_opponent_is_playing():
    from server import opp_leak
    t = team("T", [m(False, 2, 8, "2026-08-01"), m(True, 2, 0, "2026-08-08"),
                   m(False, 2, 7, "2026-08-15")])
    assert opp_leak(t, "away")["hits"]["6"] == 2      # the home clean sheet is not theirs to carry


# --- form, as game state ---
def g(home, gf, ga, date):
    return {"home": home, "goals_for": gf, "goals_against": ga,
            "corners_for": 6, "corners_against": 4, "opponent": "X", "date": date}


def test_form_is_read_at_the_venue_being_played_with_no_fallback():
    """_venue_matches quietly returns the WHOLE history when a venue pool is empty. That
    is harmless for an average and a lie here — "unbeaten in 5 at home" has to be about
    home games or it is a false sentence."""
    from server import team_form
    t = team("T", [g(True, 2, 1, "1"), g(True, 1, 1, "2"), g(False, 0, 3, "3"),
                   g(True, 3, 0, "4"), g(True, 2, 2, "5")])
    home = team_form(t, "home")
    assert home["marks"] == ["D", "W", "D", "W"]      # the away defeat is not in it
    assert home["label"] == "unbeaten in 4"
    away = team_form(t, "away")
    assert away["marks"] == ["L"] and away["losses"] == 1


def test_a_side_that_cannot_win_is_named_as_such():
    """Chasing produces corners too, so a bad run is as much a signal as a good one."""
    from server import team_form
    t = team("T", [g(True, 0, 1, "1"), g(True, 1, 1, "2"), g(True, 0, 2, "3")])
    assert team_form(t, "home")["label"] == "without a win in 3"


def test_a_short_run_reports_the_record_rather_than_claiming_a_run():
    from server import team_form
    t = team("T", [g(True, 3, 0, "1"), g(True, 0, 2, "2"), g(True, 2, 0, "3")])
    assert team_form(t, "home")["label"] == "2W 0D 1L"


def test_unsynced_scores_read_as_unknown_rather_than_as_a_blank_record():
    """A team whose goals were never synced must not be published as having no form."""
    from server import team_form
    assert team_form(team("T", [{"home": True, "corners_for": 5}]), "home") is None


# --- the ladders a posted pick quotes ---
def test_the_won_ladder_counts_rungs_rather_than_averaging_them():
    """The whole reason the post quotes counts: 12,12,1,1 and 6,6,6,6 average the same
    and are not the same bet. Only one of them is a side that keeps winning 6."""
    from server import corner_counts
    spiky = team("Spiky", [m(True, 12, 3, "1"), m(True, 12, 3, "2"),
                           m(True, 1, 3, "3"), m(True, 1, 3, "4"),
                           m(True, 6, 3, "5")])
    steady = team("Steady", [m(True, 6, 3, "1"), m(True, 7, 3, "2"),
                             m(True, 6, 3, "3"), m(True, 7, 3, "4"),
                             m(True, 6, 3, "5")])
    a, b = corner_counts(spiky, "home", "corners_for"), corner_counts(steady, "home", "corners_for")
    assert a["avg"] == b["avg"] == 6.4          # identical averages
    assert a["hits"]["6"] == 3 and b["hits"]["6"] == 5   # and a different bet


def test_the_conceded_ladder_is_the_same_function_pointed_the_other_way():
    from server import corner_counts
    t = team("Leaky", [m(True, 2, 7, "1"), m(True, 2, 8, "2"), m(True, 2, 6, "3"),
                       m(True, 2, 3, "4"), m(True, 2, 9, "5")])
    got = corner_counts(t, "home", "corners_against")
    assert got["hits"] == {"4": 4, "5": 4, "6": 4}
    assert got["hits"]["4"] == 4                 # the 3 is the only rung it misses


def test_a_thin_venue_split_widens_the_pool_and_says_so():
    """Four home games is not a home record. Quoting "6+ in 4/4 at home" would invite a
    confidence four games cannot carry, so the ladder widens — and reports that it did,
    because the caller is about to name a venue in a sentence."""
    from server import corner_counts
    t = team("Thin", [m(True, 7, 3, "1"), m(True, 7, 3, "2"), m(True, 7, 3, "3"),
                      m(True, 7, 3, "4"),
                      m(False, 2, 3, "5"), m(False, 2, 3, "6"), m(False, 2, 3, "7")])
    got = corner_counts(t, "home", "corners_for")
    assert got["scope"] == "overall" and got["games"] == 7
    assert got["hits"]["6"] == 4                 # counted over every game, not just home

    fat = team("Fat", [m(True, 7, 3, str(i)) for i in range(6)])
    assert corner_counts(fat, "home", "corners_for")["scope"] == "home"


def test_an_unmeasured_first_half_is_not_a_side_that_never_scores_early():
    """fh_goals_for is absent on leagues the sync has not covered. Reporting 0 hits over
    0 games as a rate would publish "scores in the first half in 0/10", which is a claim
    about the team rather than about the data."""
    from server import fh_rate
    blank = team("Blank", [m(True, 6, 4, str(i)) for i in range(6)])
    assert fh_rate(blank, "home") == {"games": 0, "hits": 0, "scope": "home"}

    scored = team("Early", [{**m(True, 6, 4, str(i)), "fh_goals_for": 1 if i < 4 else 0}
                            for i in range(6)])
    got = fh_rate(scored, "home")
    assert got["games"] == 6 and got["hits"] == 4


def test_the_card_meets_each_side_with_the_defence_it_actually_faces():
    """The home side is met by an AWAY defence and vice versa. Reading the opponent at
    the wrong venue is the single easiest way to publish a true-looking false number."""
    from server import fixture_card
    home = team("H", [m(True, 8, 3, str(i)) for i in range(6)])
    # Leaky away, tight at home — the card must quote the away half against H.
    away = team("A", [m(False, 3, 9, f"a{i}") for i in range(6)]
                     + [m(True, 3, 1, f"h{i}") for i in range(6)])
    card = fixture_card(home, away, "H", "A")
    assert card["home"]["opp_conceded"]["scope"] == "away"
    assert card["home"]["opp_conceded"]["hits"]["6"] == 6     # the away leak, not the home tightness
    assert card["home"]["opponent"] == "A"
    assert card["away"]["team"] == "A" and card["away"]["venue"] == "away"
