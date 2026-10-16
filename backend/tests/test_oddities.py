"""The oddity survey has to be surprising AND true, and the second one is the hard half.

WHAT THESE GUARD. Every finding in oddities.py ends up in a public post with a club's name
on it, so the failure that matters is not a crash — it is a confident sentence about a
match that never happened or a record nobody holds. The tests below are mostly about that:
synthetic games staying out, thin samples holding no records, and two findings never
describing the same game under different headings.

PURE MODULE, SO THESE ACTUALLY RUN. oddities.py imports nothing from server.py, which is
why this file can be executed in an environment where importing server panics the pydantic
core extension. That was a deliberate choice when splitting the module out, the same one
calibration.py made, and it is the only reason these assertions are checked rather than
reasoned about.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import oddities  # noqa: E402
from oddities import (MIN_GAMES, PUNCH_MIN_GAMES, all_corners_no_goals, games_of,  # noqa: E402
                      highest_floor,
                      league_extremes, league_table, leakiest, lowest_ceiling,
                      never_outcornered, punching_up, survey, widest_venue_gap,
                      _team_rows)

LEAGUES = {"eng-pl": "Premier League", "eng-l2": "League Two", "ita-sa": "Serie A"}
META = {
    "eng-pl": {"country": "England", "tier": 1, "name": "Premier League"},
    "eng-l2": {"country": "England", "tier": 4, "name": "League Two"},
    "ita-sa": {"country": "Italy", "tier": 1, "name": "Serie A"},
}


def game(cf, ca, home=True, opponent="Someone", date="2026-09-01", goals_for=1):
    return {"corners_for": cf, "corners_against": ca, "home": home,
            "opponent": opponent, "date": date, "goals_for": goals_for,
            "goals_against": 1}


def team(name, games, league_id="eng-pl", team_id=None):
    return {"name": name, "team_id": team_id or f"{league_id}-{name}",
            "league_id": league_id, "real_matches": list(games)}


def flat(name, cf, ca, n=12, league_id="eng-pl", goals_for=1):
    """A team with n identical games — the simplest fixture that clears MIN_GAMES."""
    return team(name, [game(cf, ca, home=(i % 2 == 0), goals_for=goals_for)
                       for i in range(n)], league_id)


class TestSyntheticGamesNeverGetIn:
    """RULE 2, AND THE ONE WITH TEETH. sync_real pads a thin team with gaussian noise in
    `matches`; publishing one of those as a real result would be inventing a match."""

    def test_games_of_reads_real_matches_only(self):
        t = {"name": "X", "real_matches": [game(5, 3)],
             "matches": [game(99, 0), game(98, 0)]}
        assert games_of(t) == [game(5, 3)]

    def test_a_team_with_only_synthetic_games_holds_nothing(self):
        t = {"name": "Ghost", "league_id": "eng-pl", "team_id": "g",
             "matches": [game(99, 0) for _ in range(30)]}
        out = survey([t], LEAGUES, META)
        assert out["findings"]["biggest_rout"] is None
        assert out["pool"]["games"] == 0

    def test_the_99_corner_synthetic_game_does_not_become_the_record(self):
        real = flat("Real", 6, 4, n=12)
        ghost = {"name": "Ghost", "league_id": "eng-pl", "team_id": "g",
                 "real_matches": [game(5, 5)],
                 "matches": [game(99, 0)]}
        out = survey([real, ghost], LEAGUES, META)
        assert out["findings"]["biggest_rout"]["corners_for"] <= 6


class TestThinSamplesHoldNoRecords:
    def test_below_min_games_is_excluded_from_team_rows(self):
        short = team("Short", [game(12, 0)] * (MIN_GAMES - 1))
        assert _team_rows([short], LEAGUES, META) == []

    def test_exactly_min_games_qualifies(self):
        ok = team("Ok", [game(7, 2)] * MIN_GAMES)
        rows = _team_rows([ok], LEAGUES, META)
        assert len(rows) == 1 and rows[0]["games"] == MIN_GAMES

    def test_a_thin_team_cannot_win_the_floor_record(self):
        """The whole point of MIN_GAMES: one enormous night is not a season."""
        thin = team("Thin", [game(11, 1)] * 3)
        deep = flat("Deep", 6, 3, n=20)
        rows = _team_rows([thin, deep], LEAGUES, META)
        assert highest_floor(rows)["team"] == "Deep"

    def test_games_missing_a_corner_count_are_skipped_not_zeroed(self):
        """A None read as 0 would hand this team the lowest-ceiling record on a
        measurement that was never taken."""
        partial = team("Partial", [game(8, 4)] * 11 + [{"corners_for": None,
                                                        "corners_against": None,
                                                        "home": True, "date": "x"}])
        rows = _team_rows([partial], LEAGUES, META)
        assert rows[0]["games"] == 11
        assert rows[0]["floor"] == 8


class TestTheMatchRecords:
    def test_the_rout_is_the_biggest_margin_not_the_biggest_count(self):
        a = team("Siege", [game(14, 1, opponent="Victim", date="2026-09-02")] + [game(5, 5)] * 11)
        b = team("Shootout", [game(15, 12, opponent="Other", date="2026-09-03")] + [game(5, 5)] * 11)
        out = survey([a, b], LEAGUES, META)
        rout = out["findings"]["biggest_rout"]
        assert rout["team"] == "Siege" and rout["margin"] == 13

    def test_the_haul_is_the_biggest_count(self):
        a = team("Siege", [game(14, 1, opponent="Victim", date="2026-09-02")] + [game(5, 5)] * 11)
        b = team("Shootout", [game(15, 12, opponent="Other", date="2026-09-03")] + [game(5, 5)] * 11)
        out = survey([a, b], LEAGUES, META)
        assert out["findings"]["biggest_haul"]["corners_for"] == 15

    def test_one_match_is_never_two_findings(self):
        """THE PADDING GUARD. A 16-1 is both the biggest rout and the biggest haul, and
        offering both is one fact under two headings — the exact failure this file was
        written to remove."""
        solo = team("Solo", [game(16, 1, opponent="Victim", date="2026-09-04")] + [game(4, 4)] * 11)
        out = survey([solo], LEAGUES, META)
        assert out["findings"]["biggest_rout"] is not None
        assert out["findings"]["biggest_haul"] is None

    def test_the_rout_keeps_the_game_when_they_collide(self):
        solo = team("Solo", [game(16, 1, opponent="V", date="2026-09-04")] + [game(4, 4)] * 11)
        out = survey([solo], LEAGUES, META)
        assert out["findings"]["biggest_rout"]["corners_for"] == 16

    def test_distinct_games_both_survive(self):
        a = team("Siege", [game(14, 1, opponent="V", date="2026-09-02")] + [game(5, 5)] * 11)
        b = team("Shootout", [game(15, 12, opponent="O", date="2026-09-03")] + [game(5, 5)] * 11)
        f = survey([a, b], LEAGUES, META)["findings"]
        assert f["biggest_rout"] is not None and f["biggest_haul"] is not None

    def test_the_wildest_game_is_the_combined_total(self):
        a = team("Siege", [game(14, 1, opponent="V", date="2026-09-02")] + [game(5, 5)] * 11)
        b = team("Shootout", [game(13, 12, opponent="O", date="2026-09-03")] + [game(5, 5)] * 11)
        out = survey([a, b], LEAGUES, META)
        assert out["findings"]["wildest_game"]["total"] == 25


class TestWhatTheFirstRunOnRealDataGotWrong:
    """Defects the hand-built fixtures could not produce and the live database did."""

    def test_a_short_record_cannot_out_floor_a_long_one_by_being_short(self):
        """THE BUG. A minimum is an extreme order statistic: the more games you play, the
        likelier one of them is quiet. So a ten-game side out-floored every twenty-game
        side on the first live run, and the comparison it won was not a fair one.

        Both are measured over their last MIN_GAMES here, so the denominators match.
        """
        # Twenty games, every one of them 7 corners. Floor over any window: 7.
        steady = flat("Steady", 7, 3, n=20)
        # Ten games at 6. Under the old rule its floor of 6 competed against a floor
        # drawn from twice as many chances to be low.
        short = flat("Short", 6, 3, n=10)
        rows = _team_rows([steady, short], LEAGUES, META)
        assert highest_floor(rows)["team"] == "Steady"

    def test_the_window_is_the_recent_games_not_the_whole_record(self):
        early_slump = team("Slump", [game(1, 9)] * 10 + [game(8, 3)] * 10)
        rows = _team_rows([early_slump], LEAGUES, META)
        # The old games are still counted in `games` and the average; the floor is not
        # drawn from them.
        assert rows[0]["games"] == 20
        assert rows[0]["floor"] == 8
        assert rows[0]["window"] == MIN_GAMES

    def test_a_tie_on_floor_goes_to_the_longer_record(self):
        short = flat("Short", 7, 3, n=10)
        long_ = flat("Long", 7, 3, n=20)
        rows = _team_rows([short, long_], LEAGUES, META)
        assert highest_floor(rows)["team"] == "Long"

    def test_the_punching_claim_needs_more_than_a_month_of_football(self):
        """It said a side would top 19 of 20 top flights, on ten games. That may well be
        true and ten games cannot show it."""
        thin = flat("Thin", 9, 4, n=10, league_id="eng-l2")
        top = [flat(f"I{i}", 5, 5, n=20, league_id="ita-sa") for i in range(6)]
        rows = _team_rows([thin] + top, LEAGUES, META)
        assert punching_up(rows, league_table([thin] + top, LEAGUES, META)) is None

    def test_the_same_claim_stands_once_the_record_is_long_enough(self):
        deep = flat("Deep", 9, 4, n=PUNCH_MIN_GAMES, league_id="eng-l2")
        top = [flat(f"I{i}", 5, 5, n=20, league_id="ita-sa") for i in range(6)]
        rows = _team_rows([deep] + top, LEAGUES, META)
        found = punching_up(rows, league_table([deep] + top, LEAGUES, META))
        assert found["team"]["team"] == "Deep"

    def test_a_thin_top_flight_leader_cannot_be_the_one_beaten(self):
        """Both sides of the comparison clear the bar. A 'league leader' with twelve games
        is as thin a number as the challenger, and the claim is about which is higher."""
        challenger = flat("Challenger", 8, 4, n=20, league_id="eng-l2")
        thin_leader = flat("Thin Leader", 7, 4, n=10, league_id="ita-sa")
        others = [flat(f"I{i}", 9, 5, n=20, league_id="ita-sa") for i in range(5)]
        teams = [challenger, thin_leader] + others
        rows = _team_rows(teams, LEAGUES, META)
        # Serie A's real leader among qualifying teams averages 9.0, above the
        # challenger's 8.0, so there is nothing to claim.
        assert punching_up(rows, league_table(teams, LEAGUES, META)) is None


class TestFloorAndCeiling:
    def test_the_floor_is_the_worst_game_not_the_average(self):
        """A 9-corner average with a 2-corner night loses to a 7-corner average that has
        never dropped below 6 — which is the whole reason this finding is not 'highest
        average' with extra words."""
        spiky = team("Spiky", [game(16, 2)] * 6 + [game(2, 2)] * 6)
        steady = team("Steady", [game(7, 3)] * 6 + [game(6, 3)] * 6)
        rows = _team_rows([spiky, steady], LEAGUES, META)
        assert highest_floor(rows)["team"] == "Steady"
        assert highest_floor(rows)["floor"] == 6

    def test_the_ceiling_finds_the_team_that_never_gets_going(self):
        quiet = team("Quiet", [game(3, 6)] * 8 + [game(4, 7)] * 4)
        normal = flat("Normal", 7, 5, n=12)
        rows = _team_rows([quiet, normal], LEAGUES, META)
        low = lowest_ceiling(rows)
        assert low["team"] == "Quiet" and low["ceiling"] == 4

    def test_every_record_carries_its_denominator(self):
        """Rule 4. A floor of 6 over 20 games is a story; over 10 it is a smaller one, and
        a post that cannot say which is making a claim it has not earned."""
        rows = _team_rows([flat("A", 7, 3, n=14)], LEAGUES, META)
        for finding in (highest_floor(rows), lowest_ceiling(rows), leakiest(rows)):
            assert finding["games"] == 14


class TestVenueGap:
    def test_it_finds_the_split_and_names_the_strong_end(self):
        t = team("Split", [game(10, 3, home=True)] * 6 + [game(3, 8, home=False)] * 6)
        rows = _team_rows([t], LEAGUES, META)
        gap = widest_venue_gap(rows)
        assert gap["gap"] == 7.0 and gap["stronger"] == "home"

    def test_a_team_better_away_is_reported_as_such(self):
        """RARER AND THEREFORE THE BETTER POST, so it must not be assumed away."""
        t = team("Traveller", [game(3, 8, home=True)] * 6 + [game(9, 3, home=False)] * 6)
        rows = _team_rows([t], LEAGUES, META)
        gap = widest_venue_gap(rows)
        assert gap["stronger"] == "away" and gap["gap"] == 6.0

    def test_a_team_short_of_games_at_one_venue_is_not_compared(self):
        lopsided = team("Lopsided", [game(10, 2, home=True)] * 10 + [game(1, 9, home=False)] * 2)
        rows = _team_rows([lopsided], LEAGUES, META)
        assert rows[0]["away_avg"] is None
        assert widest_venue_gap(rows) is None


class TestNeverOutcornered:
    def test_a_perfect_record_is_found(self):
        t = flat("Perfect", 8, 3, n=14)
        rows = _team_rows([t], LEAGUES, META)
        assert never_outcornered(rows)["team"] == "Perfect"

    def test_one_level_game_breaks_it(self):
        """A draw on corners is not a win, the same way a push is not a win anywhere else
        on this site."""
        t = team("Nearly", [game(8, 3)] * 11 + [game(5, 5)])
        rows = _team_rows([t], LEAGUES, META)
        assert never_outcornered(rows) is None

    def test_the_longer_record_wins(self):
        short = flat("Short", 9, 2, n=10)
        long_ = flat("Long", 7, 3, n=20)
        rows = _team_rows([short, long_], LEAGUES, META)
        assert never_outcornered(rows)["team"] == "Long"


class TestFutility:
    def test_it_picks_from_the_big_corner_winners_not_the_goalless(self):
        """THE TRAP THIS AVOIDS. A straight corners-per-goal ratio is won by whoever is
        goalless, however few corners they won — the denominator does all the work and the
        headline number stops meaning anything."""
        pool = [flat(f"Mid{i}", 5, 5, n=12, goals_for=2) for i in range(20)]
        barren = flat("Barren", 2, 9, n=12, goals_for=0)      # goalless, but no corners
        wasteful = flat("Wasteful", 9, 3, n=12, goals_for=0)  # corners AND goalless
        rows = _team_rows(pool + [barren, wasteful], LEAGUES, META)
        found = all_corners_no_goals(rows)
        assert found["team"] == "Wasteful"

    def test_it_reports_the_pool_it_chose_from(self):
        pool = [flat(f"Mid{i}", 5, 5, n=12, goals_for=2) for i in range(20)]
        wasteful = flat("Wasteful", 9, 3, n=12, goals_for=0)
        rows = _team_rows(pool + [wasteful], LEAGUES, META)
        found = all_corners_no_goals(rows)
        assert found["of"] == 21 and found["pool"] >= 3

    def test_too_small_a_pool_returns_nothing(self):
        rows = _team_rows([flat("A", 9, 2, n=12)], LEAGUES, META)
        assert all_corners_no_goals(rows) is None


class TestLeagueTable:
    def test_it_reports_corners_per_match_not_per_side(self):
        """Each team-game already holds both sides' counts, so (for + against) averaged
        over team-games IS the per-match total. Halving it would be the per-side figure
        under the wrong name."""
        teams = [flat(f"T{i}", 6, 5, n=12) for i in range(6)]
        table = league_table(teams, LEAGUES, META)
        assert table[0]["per_match"] == 11.0

    def test_a_league_short_of_games_is_left_out(self):
        teams = [flat("Solo", 6, 5, n=12)]
        assert league_table(teams, LEAGUES, META) == []

    def test_extremes_report_both_ends_and_the_gap(self):
        busy = [flat(f"B{i}", 8, 7, n=12, league_id="eng-pl") for i in range(6)]
        quiet = [flat(f"Q{i}", 4, 4, n=12, league_id="ita-sa") for i in range(6)]
        ends = league_extremes(league_table(busy + quiet, LEAGUES, META))
        assert ends["top"]["league"] == "Premier League"
        assert ends["bottom"]["league"] == "Serie A"
        assert ends["gap"] == 7.0

    def test_one_league_has_no_extremes(self):
        teams = [flat(f"T{i}", 6, 5, n=12) for i in range(6)]
        assert league_extremes(league_table(teams, LEAGUES, META)) is None


class TestPunchingUp:
    def _world(self):
        # A League Two side winning 9 a game, a Serie A whose best wins 7. Every record
        # is 20 games long: PUNCH_MIN_GAMES applies to BOTH sides of the comparison, so a
        # 12-game fixture here would be testing the bar rather than the finding.
        lower = [flat(f"L{i}", 4, 5, n=20, league_id="eng-l2") for i in range(5)]
        lower.append(flat("Hammers", 9, 4, n=20, league_id="eng-l2"))
        top = [flat(f"I{i}", 5, 5, n=20, league_id="ita-sa") for i in range(5)]
        top.append(flat("Best Italians", 7, 4, n=20, league_id="ita-sa"))
        return lower + top

    def test_it_names_the_lower_tier_side_and_the_league_it_tops(self):
        teams = self._world()
        rows = _team_rows(teams, LEAGUES, META)
        found = punching_up(rows, league_table(teams, LEAGUES, META))
        assert found["team"]["team"] == "Hammers"
        assert found["beats"]["league"] == "Serie A"
        assert found["beats"]["team"] == "Best Italians"

    def test_it_picks_the_strongest_league_it_can_still_top(self):
        """NOT ANY LEAGUE IT BEATS. Choosing the weakest top flight would land the joke on
        a league nobody has heard of and waste the comparison."""
        teams = self._world()
        weak = [flat(f"W{i}", 3, 3, n=20, league_id="eng-pl") for i in range(6)]
        rows = _team_rows(teams + weak, LEAGUES, META)
        found = punching_up(rows, league_table(teams + weak, LEAGUES, META))
        assert found["beats"]["league"] == "Serie A"

    def test_nothing_when_no_lower_tier_side_beats_a_top_flight(self):
        lower = [flat(f"L{i}", 4, 5, n=20, league_id="eng-l2") for i in range(6)]
        top = [flat(f"I{i}", 8, 5, n=20, league_id="ita-sa") for i in range(6)]
        rows = _team_rows(lower + top, LEAGUES, META)
        assert punching_up(rows, league_table(lower + top, LEAGUES, META)) is None


class TestTheSurveyAsAWhole:
    def test_an_empty_database_returns_findings_that_are_all_none(self):
        """NONE IS A REAL ANSWER. Early in a season almost nothing clears MIN_GAMES, and a
        thin pool that still produced a confident superlative is the dishonest outcome."""
        out = survey([], LEAGUES, META)
        assert out["pool"]["teams"] == 0
        assert set(out["findings"].values()) == {None}

    def test_the_pool_is_reported_so_a_post_can_bound_its_claim(self):
        teams = [flat(f"T{i}", 6, 5, n=12) for i in range(6)]
        out = survey(teams, LEAGUES, META)
        assert out["pool"]["teams"] == 6
        assert out["pool"]["games"] == 72
        assert out["pool"]["min_games"] == MIN_GAMES

    def test_findings_carry_league_and_country_for_the_unfamiliar_clubs(self):
        """Across 28 leagues most clubs are unknown to most readers, so a bare name is not
        a fact anyone can place."""
        teams = [flat(f"T{i}", 6, 5, n=12, league_id="ita-sa") for i in range(6)]
        found = survey(teams, LEAGUES, META)["findings"]["highest_floor"]
        assert found["league"] == "Serie A" and found["country"] == "Italy"

    def test_no_finding_is_about_an_upcoming_fixture(self):
        """Rule 1, asserted structurally. The moment a projection or a next fixture
        appears in one of these records, a historical fact has become a tip."""
        teams = [flat(f"T{i}", 6, 5, n=12) for i in range(6)]
        for found in survey(teams, LEAGUES, META)["findings"].values():
            if isinstance(found, dict):
                assert "next_fixture" not in found
                assert "projection" not in found
                assert "prob" not in found

    def test_the_findings_keys_are_stable(self):
        """The wording module has a builder per key; a rename here that is not made there
        silently drops a post rather than failing."""
        out = survey([], LEAGUES, META)
        assert set(out["findings"]) == {
            "biggest_rout", "biggest_haul", "wildest_game", "highest_floor",
            "lowest_ceiling", "widest_venue_gap", "never_outcornered",
            "all_corners_no_goals", "leakiest", "league_extremes", "punching_up"}

    def test_match_findings_names_match_the_keys_they_describe(self):
        assert set(oddities.MATCH_FINDINGS) <= set(survey([], LEAGUES, META)["findings"])
