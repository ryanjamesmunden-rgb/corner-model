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
    # LOUD PAST, QUIET RECENT GAMES, which is what an under streak now has to be: the line
    # must sit on the demanding side of this team's own average, so a side that is quiet
    # every week has no under to report — being held under 3 is not news about a team that
    # never wins 3.
    quiet = team("Y", [m(True, 9, 2, "2026-07-25"), m(True, 1, 2, "2026-08-01"),
                       m(True, 2, 1, "2026-08-08"), m(True, 1, 2, "2026-08-15")])
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


# --- what a SHARE is allowed to carry, and what the PANEL is ---
def test_the_panel_floor_is_five_and_the_board_keeps_its_own():
    """THE PANEL'S FLOOR WENT UP TO FIVE and it is no longer BOARD_MIN_RUN.

    It defaulted to the board's three on the reasoning that a reader can weigh a short run
    themselves where a post cannot be weighed. That was right when the panel held four or
    five rows; it now carries both directions, three subjects, both sides AND the overall
    pool beside each venue one, and a dozen rows of which half are three games long is not
    a richer panel, it is the useful ones buried in the rest.

    SEPARATE FROM BOARD_MIN_RUN rather than a change to it, because that constant has a
    second consumer — angle_is_strong, which decides what the BOARD publishes. Moving one
    number to fix a display would quietly have changed what gets posted."""
    from server import BOARD_MIN_RUN, PANEL_MIN_RUN, SHARE_MIN_RUN
    assert PANEL_MIN_RUN == 5
    assert BOARD_MIN_RUN == 3, "the board's own floor must not have moved with the panel's"
    assert SHARE_MIN_RUN == PANEL_MIN_RUN, "a post and the panel now agree"
    short = team("Z", [m(True, 9, 3, f"2026-08-{d:02d}") for d in (1, 8, 15)])   # 3 in a row
    assert fixture_streaks(short, short, "Z", "Z") == [], \
        "a three-game run is no longer enough for the panel"
    long_enough = team("Z", [m(True, 9, 3, f"2026-08-{d:02d}") for d in (1, 8, 15, 22, 29)])
    rows = fixture_streaks(long_enough, long_enough, "Z", "Z")
    assert rows, "five in a row has to reach it"
    assert all(r["run"] >= PANEL_MIN_RUN for r in rows)


def test_two_games_is_still_not_a_run():
    from server import PANEL_MIN_RUN
    pair = team("Z", [m(True, 9, 3, f"2026-08-{d:02d}") for d in (1, 8)])
    assert all(r["run"] >= PANEL_MIN_RUN
               for r in fixture_streaks(pair, pair, "Z", "Z"))


def test_a_conceded_run_reaches_the_panel_with_its_opponent():
    """The subject this change exists for. A side shipping corners in three straight is the
    angle; the bet is whoever plays them, so the row has to carry the other name."""
    leaky = team("Z", [m(True, 2, 7, f"2026-08-{d:02d}") for d in (1, 8, 15, 22, 29)])
    rows = fixture_streaks(leaky, leaky, "Leaky", "Sharp")
    conceded = [r for r in rows if r["subject"] == "conceded"]
    assert conceded, "no conceded run reached the panel"
    assert conceded[0]["opponent"]


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


# --- the overall run, beside the venue one ------------------------------------------
#
# The panel showed the VENUE run only. For most of a season exactly one of the two is
# worth anything and which one changes: in August a venue split is three games and the
# overall run is the only one long enough to mean anything; by April a side can be on a
# long home run that says nothing about its form generally. Showing one and calling it
# "the streak" picks the wrong half about half the time.

from server import _venue_and_overall  # noqa: E402

# Six league games, three at each venue — the shape that prompted this. The venue split
# is too short to say much; across both it is a run of six.
EARLY = team("Luton", [
    m(True, 7, 3, "2026-08-01"),
    m(False, 8, 4, "2026-08-05"),
    m(True, 6, 2, "2026-08-10"),
    m(False, 9, 5, "2026-08-15"),
    m(True, 7, 4, "2026-08-20"),
    m(False, 6, 3, "2026-08-25"),
])


def test_the_overall_run_is_on_the_fixture_now():
    rows = fixture_streaks(EARLY, team("Other", []), "Luton", "Other")
    venues = {r["venue"] for r in rows if r["team"] == "Luton"}
    assert "overall" in venues, "the overall run never reaches the fixture panel"


def test_early_in_a_season_the_overall_run_is_the_only_one_long_enough():
    """Six league games, three at each venue. Neither venue split can reach the panel's
    floor of five — only the pool that holds both can, which is the case the overall run
    was added for."""
    rows = [r for r in fixture_streaks(EARLY, team("Other", []), "Luton", "Other")
            if r["team"] == "Luton" and r["subject"] == "team" and r["direction"] == "over"]
    by_venue = {r["venue"]: r for r in rows}
    assert set(by_venue) == {"overall"}
    assert by_venue["overall"]["run"] == 6


def test_every_row_still_says_which_pool_it_came_from():
    """The chart looks identical either way — `venue` is the only thing distinguishing
    '6 in a row' from '6 in a row at home'."""
    rows = fixture_streaks(EARLY, team("Other", []), "Luton", "Other")
    assert all(r.get("venue") in ("home", "away", "overall") for r in rows)


class TestOnlyATrueDuplicateIsDropped:
    """THE FIRST VERSION OF THIS RULE DROPPED FAR TOO MUCH. It removed the overall row
    whenever it was "strictly no better" — same line, no longer — which was written when
    the two rows were indistinguishable on screen. They carry a Home/Away/Overall badge
    now, so the rule was only hiding things: a side 9-in-a-row at home whose overall run
    is 4 showed the home row alone, and the overall question had no row at all.

    What is dropped now is an actual duplicate, identified by the POOL rather than the
    claim: equal `games` means the venue pool is the whole history, so the two rows are
    the same matches counted twice."""

    def test_the_same_pool_is_one_finding_not_two(self):
        # A side that has only played at home so far: both runs read the same games.
        venue = {"line": 6, "run": 4, "venue": "home", "games": 4}
        same = {"line": 6, "run": 4, "venue": "overall", "games": 4}
        assert _venue_and_overall(venue, same) == [venue]

    def test_a_shorter_overall_run_is_KEPT_now(self):
        # The case the old rule hid. 9 at home, 4 across everything: those are two
        # different facts and the second is the one a reader cannot infer.
        venue = {"line": 6, "run": 9, "venue": "home", "games": 9}
        shorter = {"line": 6, "run": 4, "venue": "overall", "games": 18}
        assert _venue_and_overall(venue, shorter) == [venue, shorter]

    def test_a_longer_run_is_kept(self):
        venue = {"line": 6, "run": 4, "venue": "home", "games": 6}
        longer = {"line": 6, "run": 9, "venue": "overall", "games": 12}
        assert _venue_and_overall(venue, longer) == [venue, longer]

    def test_a_more_demanding_line_is_kept(self):
        venue = {"line": 4, "run": 5, "venue": "home", "games": 7}
        higher = {"line": 7, "run": 5, "venue": "overall", "games": 14}
        assert _venue_and_overall(venue, higher) == [venue, higher]

    def test_the_venue_row_survives_even_when_overall_is_bigger(self):
        # It is the pool the model prices this fixture against, and "9 in a row at home"
        # is the sentence the reader came for.
        venue = {"line": 5, "run": 3, "venue": "home", "games": 5}
        bigger = {"line": 5, "run": 11, "venue": "overall", "games": 11}
        assert _venue_and_overall(venue, bigger)[0] == venue

    def test_overall_alone_when_the_venue_split_has_no_run(self):
        over = {"line": 5, "run": 6, "venue": "overall", "games": 12}
        assert _venue_and_overall(None, over) == [over]

    def test_and_nothing_at_all_is_fine(self):
        assert _venue_and_overall(None, None) == []


def test_a_long_home_run_and_a_shorter_overall_one_BOTH_reach_the_panel():
    """The shape the old rule hid, end to end.

    Four home games all clearing the line, with one bad away game in between: the home run
    is four, the overall run is three because the away game broke it. Those are two
    different facts about the same side and the panel has to carry both — the second is
    the one a reader cannot work out from the first.
    """
    side = team("Luton", [
        m(True, 7, 3, "2026-07-04"),
        m(True, 8, 4, "2026-07-11"),
        m(True, 9, 2, "2026-07-18"),
        m(True, 7, 5, "2026-07-25"),
        m(True, 8, 3, "2026-08-01"),
        m(False, 2, 6, "2026-08-05"),      # the away blank that breaks the overall run
        m(True, 7, 3, "2026-08-10"),
        m(True, 8, 4, "2026-08-17"),
        m(True, 9, 2, "2026-08-24"),
        m(True, 7, 5, "2026-08-31"),
        m(True, 8, 3, "2026-09-07"),
    ])
    rows = [r for r in fixture_streaks(side, team("Other", []), "Luton", "Other")
            if r["team"] == "Luton" and r["subject"] == "team" and r["direction"] == "over"]
    by_venue = {r["venue"]: r for r in rows}
    assert set(by_venue) == {"home", "overall"}
    assert by_venue["home"]["run"] == 10
    assert by_venue["overall"]["run"] == 5
    # And they are measured over different pools, which is what makes them two findings.
    assert by_venue["home"]["games"] != by_venue["overall"]["games"]


# --- a line has to be demanding FOR THIS TEAM ---------------------------------------
#
# "UNDER 8 TEAM CORNERS IN 8 GAMES" was the complaint, and it is a true sentence that says
# nothing: a side averaging five corners is under eight almost every week, so the run
# describes the sport rather than the team. UNDER_LINE_CAP cannot see it — 8 is inside the
# cap by one — because it is the same rung for a side winning nine a game and one winning
# three. The team's own average is the yardstick that adapts.

def test_an_under_above_the_teams_own_average_is_not_an_angle():
    """The exact shape reported. Eight straight games under 8, from a side that averages
    about five: true, and worth nobody's attention."""
    ordinary = team("Mid", [m(True, c, 4, f"2026-08-{d:02d}")
                            for d, c in zip(range(1, 25, 3), [5, 4, 6, 5, 4, 6, 5, 4])])
    r = live_streak(ordinary, "home", "team", "under")
    # par is 4.875, so nothing above 5 is offered — and 7 and 8, the lines that prompted
    # this, cannot appear however long the run at them is.
    assert r is None or r["line"] <= 5, \
        "an under well above the team's own par is not a claim about the team"


def test_but_a_genuinely_tight_run_still_counts():
    """A side that normally wins six being held under three for five straight is the same
    kind of story as a long over — and it survives, because the line is on the demanding
    side of what this team usually does."""
    throttled = team("Quiet", [
        m(True, 9, 3, "2026-07-04"), m(True, 8, 4, "2026-07-11"),
        m(True, 7, 2, "2026-07-18"), m(True, 2, 5, "2026-07-25"),
        m(True, 1, 6, "2026-08-01"), m(True, 2, 4, "2026-08-08"),
        m(True, 1, 5, "2026-08-15"), m(True, 2, 6, "2026-08-22"),
    ])
    r = live_streak(throttled, "home", "team", "under")
    assert r is not None, "a run well under this team's own par has to survive"
    assert r["run"] >= 5
    assert r["line"] <= 3


def test_an_elite_record_is_not_deleted_by_the_same_rule():
    """The allowance of one rung, and why it is there. A side conceding exactly one corner
    a week has a par of 1, so a strict `line <= par` would offer nothing at all — deleting
    the best defensive records on the board, which are the ones worth having."""
    solid = team("Solid", [m(True, 6, 1, f"2026-08-{d:02d}") for d in (1, 8, 15, 22, 29)])
    r = live_streak(solid, "home", "conceded", "under")
    assert r is not None and r["run"] == 5 and r["line"] == 2


def test_the_over_side_is_deliberately_untouched():
    """Applied to overs the same rule did harm: ranking is (length, line), so an over a
    rung below par is beaten only on the line and still wins on LENGTH. Cutting those
    turned a four-game run at one line into a three-game run at the next one up — a
    shorter run for a marginally harder line, which is not a trade to make for a reader."""
    r = live_streak(HOME_RUN, "home", "match", "over")
    assert r["line"] == 10 and r["run"] == 4
