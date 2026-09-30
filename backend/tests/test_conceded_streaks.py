"""Corners CONCEDED as a streak subject of its own.

WHY IT IS A SUBJECT AND NOT A DIRECTION. "Conceded 5+" is not the under of "won 5+" — it
counts the corners going the other way. A side can win two a game and ship eight, and only
one of those boards finds them. This is the fastest route to a leaky corner defence, which
is the angle the board could not previously express at all.

THE BET IS THE OTHER TEAM'S, AND THAT IS WHAT EVERY GUARD HERE IS ABOUT. The run belongs
to the defence; the slip is the opponent's team corners. Three places have to move with it
or the row prices the streaking side's own corners — a plausible number, a wrong fair
price, and an EV computed against a bookmaker's price for a different market:

  - the lambda, built from the opponent's attack against this defence;
  - the intent adjustment, which belongs to whoever is taking the corners;
  - the market key's venue, because home_over_4.5 and away_over_4.5 are two bets.

And one silent-failure guard: the streak board used to normalise any unrecognised subject
to "team", so a conceded request would have returned a full, plausible board of the WRONG
measurement under the right heading.
"""
import os
import sys

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "test_corner_model")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import server  # noqa: E402
from server import (  # noqa: E402
    OVER_LINE_FLOOR, STREAK_LADDERS, UNDER_LINE_CAP, _streak_line_label,
    _streak_projection, fixture_streaks, live_streak, streak_value,
)


def m(home, cf, ca, date, shots=14):
    return {"home": home, "corners_for": cf, "corners_against": ca,
            "shots_for": shots, "shots_against": shots,
            "blocked_shots_for": 4, "blocked_shots_against": 4,
            "opponent": "X", "date": date}


def team(name, matches):
    return {"name": name, "team_id": "t-" + name, "real_matches": matches,
            "matches": matches, "real_samples": len(matches)}


# WINS FEW, SHIPS MANY. The pair of numbers is the point: a side read on `team` looks
# ordinary and on `conceded` looks like a hole. One team document has to produce both.
LEAKY = team("Brighton", [
    m(True, 3, 6, "2026-08-01"),
    m(True, 2, 7, "2026-08-08"),
    m(True, 4, 6, "2026-08-15"),
    m(True, 3, 8, "2026-08-22"),
    m(True, 2, 5, "2026-08-29"),
])


class TestTheValueMeasured:
    def test_conceded_reads_the_other_end_of_the_match(self):
        match = m(True, 3, 7, "2026-08-01")
        assert streak_value(match, "team") == 3
        assert streak_value(match, "conceded") == 7
        assert streak_value(match, "match") == 10

    def test_it_is_not_the_under_of_the_team_board(self):
        """A side can be quiet AND leaky, and the two boards have to disagree about them.

        This side wins 2-4 corners a game and ships 5-8. The team-corner board finds no
        over run at all — their own attack never clears the floor five times running — and
        the conceded board finds a five-game run at 5+. Same team document, same games,
        opposite findings, which is the whole case for a separate subject."""
        assert live_streak(LEAKY, "home", "team", "over") is None
        assert live_streak(LEAKY, "home", "conceded", "over")["line"] >= 5

    def test_the_ladder_and_floors_exist_for_it(self):
        # A missing ladder entry falls back to "team" silently — same count, so nothing
        # would look wrong; a missing floor would offer "1+ conceded, 5 in a row".
        assert STREAK_LADDERS["conceded"] == STREAK_LADDERS["team"]
        assert OVER_LINE_FLOOR["conceded"] == 3
        assert UNDER_LINE_CAP["conceded"] == 8


class TestTheRun:
    def test_a_leaky_defence_produces_a_run_at_the_line_it_actually_clears(self):
        r = live_streak(LEAKY, "home", "conceded", "over")
        assert r["subject"] == "conceded"
        assert r["run"] == 5 and r["line"] == 5

    def test_a_solid_defence_produces_none(self):
        solid = team("Solid", [m(True, 6, 1, f"2026-08-0{i}") for i in range(1, 6)])
        assert live_streak(solid, "home", "conceded", "over") is None

    def test_the_under_direction_finds_the_solid_one_instead(self):
        solid = team("Solid", [m(True, 6, 1, f"2026-08-0{i}") for i in range(1, 6)])
        r = live_streak(solid, "home", "conceded", "under")
        assert r and r["run"] == 5


class TestTheBoardDoesNotSilentlySwallowIt:
    def test_an_unknown_subject_still_falls_back_but_a_known_one_passes_through(self):
        """THE SILENT FAILURE THIS REPLACED. `"match" if subject == "match" else "team"`
        answered a conceded request with the team-corner board: every row real, every
        number right for a measurement nobody asked for, under a heading saying
        otherwise."""
        import inspect
        src = inspect.getsource(server.streaks)
        assert 'subject = "match" if subject == "match" else "team"' not in src, \
            "the two-way normalisation is back — a new subject now answers as 'team'"
        assert "subject if subject in STREAK_LADDERS" in src


class TestTheSlipNamesTheOtherTeam:
    def test_the_label_is_the_opponents_corners(self):
        row = {"name": "Brighton", "subject": "conceded", "line": 5, "direction": "over",
               "opponent": "Arsenal"}
        label = _streak_line_label(row)
        assert "Arsenal team corners 5+" in label
        assert "Brighton" in label            # named as the defence being attacked

    def test_it_never_reads_as_the_streaking_sides_own_corners(self):
        # THE COSTLY MISREADING: backing the side that has been kept quiet.
        row = {"name": "Brighton", "subject": "conceded", "line": 5, "direction": "over",
               "opponent": "Arsenal"}
        assert not _streak_line_label(row).startswith("Brighton team corners")

    def test_a_missing_opponent_degrades_to_a_word_rather_than_a_wrong_name(self):
        row = {"name": "Brighton", "subject": "conceded", "line": 5, "direction": "over"}
        assert "opponent team corners 5+" in _streak_line_label(row)

    def test_the_other_subjects_are_untouched(self):
        assert _streak_line_label(
            {"name": "Derby", "subject": "team", "line": 6, "direction": "over"}
        ) == "Derby team corners 6+"
        assert "match total 10+" in _streak_line_label(
            {"name": "Derby", "subject": "match", "line": 10, "direction": "over"})


class TestThePrice:
    # A busy attack meeting the leaky defence above.
    SHARP = team("Arsenal", [m(False, 7, 4, f"2026-08-0{i}") for i in range(1, 6)])

    def proj(self, subject):
        return _streak_projection(LEAKY, self.SHARP, "home", "away", 5, "over", subject,
                                  league_shots=14.0, odds={}, league_blocked=4.0)

    def test_it_prices_the_opponents_corners_not_the_streaking_teams(self):
        """THE LOAD-BEARING CASE. Brighton win 2-4 a game; Arsenal take 7. A conceded
        projection built on Brighton's own attack would come back near their line and
        read as a perfectly reasonable price for the wrong bet."""
        conceded = self.proj("conceded")
        own = self.proj("team")
        assert conceded["lambda"] > own["lambda"]
        # The two inputs must be the pair that averages to the lambda beside them.
        assert conceded["team_for"] == conceded["opp_for"]
        assert conceded["opp_conceded"] == conceded["team_conceded"]

    def test_the_market_key_is_the_opponents_venue(self):
        # home_over_4.5 and away_over_4.5 are two different bets, and the book price is
        # looked up by this key. Brighton are at home, so the bet is the AWAY side's.
        assert self.proj("conceded")["market_key"] == "away_over_4.5"
        assert self.proj("team")["market_key"] == "home_over_4.5"

    def test_it_says_whose_corners_it_priced(self):
        assert self.proj("conceded")["attacker"] == "opponent"
        assert self.proj("team")["attacker"] == "team"

    def test_the_ev_is_computed_against_the_opponents_market(self):
        odds = {"away_over_4.5": 2.0, "home_over_4.5": 50.0}
        p = _streak_projection(LEAKY, self.SHARP, "home", "away", 5, "over", "conceded",
                              league_shots=14.0, odds=odds, league_blocked=4.0)
        assert p["book_odds"] == 2.0, "priced against the streaking team's own market"

    def test_no_opponent_means_no_price_rather_than_a_guess(self):
        assert _streak_projection(LEAKY, None, "home", "away", 5, "over", "conceded",
                                  league_shots=14.0, odds={}) is None


class TestOnTheFixturePage:
    def test_a_conceded_run_reaches_the_fixture_panel_with_the_opponent_on_it(self):
        rows = fixture_streaks(LEAKY, TestThePrice.SHARP, "Brighton", "Arsenal", min_run=5)
        conceded = [r for r in rows if r["subject"] == "conceded"]
        assert conceded, "the fixture panel never asks for the conceded subject"
        assert conceded[0]["team"] == "Brighton"
        # Without this the panel cannot say whose bet it is — see fixtureStreaks.js.
        assert conceded[0]["opponent"] == "Arsenal"

    def test_the_other_subjects_carry_no_opponent(self):
        rows = fixture_streaks(LEAKY, TestThePrice.SHARP, "Brighton", "Arsenal", min_run=5)
        for r in rows:
            if r["subject"] != "conceded":
                assert "opponent" not in r
