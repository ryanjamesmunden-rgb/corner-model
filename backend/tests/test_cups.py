"""A cup tie's two sides come from two different leagues, and almost everything the app
does assumed they did not.

WHAT THESE TESTS ARE FOR. Not "does the Champions League appear" — that is one line of
config. The failures worth guarding are the ones that produce a board that renders
perfectly and is wrong:

  - A cup synced as a LEAGUE creates a second Arsenal with six games on file, and every
    streak, average and projection for that row is computed from a fragment of a season.
  - A league reference read off the FIXTURE hands a cup — which has no teams of its own —
    a hardcoded default, and the edge calculation prices every European tie against 10.0
    total corners with nothing measured behind it.
  - An api id taken on trust syncs some other tournament under a Champions League name.
    This repo already has that scar (see the nor-d2 note in leagues_meta.py).
  - A tie where only one side is known looks like half a fixture. It is not: the missing
    side's conceded rate is an INPUT, and without it the projection is a default wearing a
    model's clothes.

Every assertion below is on one of those, not on the happy path.
"""
import os
import sys

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "test_corner_model")
os.environ.setdefault("API_FOOTBALL_KEY", "test-key")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import cups  # noqa: E402
from leagues_meta import COMPETITION_META, CUP_META, LEAGUE_META  # noqa: E402


def team(team_id, api_id, league_id, games=20, name=None):
    return {"team_id": team_id, "api_team_id": api_id, "league_id": league_id,
            "name": name or team_id, "real_samples": games}


ARSENAL = team("eng-pl-42", 42, "eng-pl")
BAYERN = team("ger-bl-157", 157, "ger-bl")
SPURS = team("eng-pl-47", 47, "eng-pl")


class TestTheIdIsNotTakenOnTrust:
    """The nor-d2 guard, automated. It was caught once by somebody remembering to run a
    probe by hand; a cup sync already makes the /leagues call, so this costs nothing and
    happens on every run instead of once before shipping."""

    def test_a_matching_competition_passes(self):
        entry = {"league": {"name": "UEFA Champions League", "type": "Cup"}}
        assert cups.verify_identity(entry, CUP_META["ucl"]) == ""

    def test_a_different_tournament_is_refused(self):
        # What a wrong id actually looks like: a real competition, real fixtures, real
        # teams, and nothing anywhere saying it is not the one we asked for.
        entry = {"league": {"name": "CONMEBOL Libertadores", "type": "Cup"}}
        complaint = cups.verify_identity(entry, CUP_META["ucl"])
        assert complaint
        assert "Libertadores" in complaint

    def test_a_league_where_a_cup_was_expected_is_refused(self):
        entry = {"league": {"name": "Champions League", "type": "League"}}
        assert "type" in cups.verify_identity(entry, CUP_META["ucl"])

    def test_an_empty_response_is_refused_rather_than_assumed_fine(self):
        # An id the provider does not know returns nothing. Treating "no complaint to
        # make" as "checks out" is how a guard passes on the exact input it exists for.
        assert cups.verify_identity(None, CUP_META["ucl"])
        assert cups.verify_identity({}, CUP_META["ucl"])

    def test_a_sponsor_rename_does_not_break_the_sync(self):
        """Matched on a substring on purpose. A sync that fails when a provider drops a
        'UEFA' prefix is a sync people learn to work around, and the check that matters —
        is this a completely different tournament — still fires."""
        for name in ("Champions League", "UEFA Champions League", "CHAMPIONS LEAGUE"):
            assert cups.verify_identity({"league": {"name": name, "type": "Cup"}},
                                        CUP_META["ucl"]) == ""


class TestResolvingASideToItsDomesticRow:
    def test_both_sides_resolve_to_their_league_teams(self):
        by_api = cups.index_by_api_id([ARSENAL, BAYERN])
        home, away, reason = cups.resolve_tie(42, 157, by_api)
        assert reason == ""
        # THE POINT OF THE WHOLE DESIGN: the ids are domestic, so twenty games of form
        # come with them. A cup-as-a-league would have produced `ucl-42` here.
        assert home["team_id"] == "eng-pl-42"
        assert away["team_id"] == "ger-bl-157"

    def test_an_unknown_side_drops_the_whole_fixture(self):
        """Half a tie is worse than none. The opponent's conceded rate is an input to the
        projection, not decoration — without it the model falls back to a league default
        and prints a number that looks exactly like a measured one."""
        by_api = cups.index_by_api_id([ARSENAL])
        home, away, reason = cups.resolve_tie(42, 157, by_api)
        assert (home, away) == (None, None)
        assert reason == "unknown_side"

    def test_a_thin_side_drops_the_fixture_too(self):
        thin = team("gre-sl-9", 9, "gre-sl", games=3)
        by_api = cups.index_by_api_id([ARSENAL, thin])
        _, _, reason = cups.resolve_tie(42, 9, by_api)
        assert reason == "thin_history"

    def test_the_bar_reads_real_games_not_padded_ones(self):
        """`matches` is padded with SYNTHETIC games for sparse teams so the maths has
        something to work on. A bar read off it would pass a side with three real games
        and five invented ones — which is the precise shape of 'looks like evidence'."""
        padded = {"team_id": "x-1", "api_team_id": 1, "league_id": "gre-sl",
                  "name": "X", "real_samples": 3,
                  "matches": [{}] * 20, "real_matches": [{}] * 3}
        assert cups.real_games(padded) == 3
        by_api = cups.index_by_api_id([ARSENAL, padded])
        assert cups.resolve_tie(42, 1, by_api)[2] == "thin_history"

    def test_real_samples_falls_back_to_counting_real_matches(self):
        """Older team documents predate the stored count."""
        old = {"team_id": "x-2", "api_team_id": 2, "league_id": "eng-ch",
               "name": "Y", "real_matches": [{}] * 11}
        assert cups.real_games(old) == 11

    def test_a_team_drawn_against_itself_is_refused(self):
        """Not hypothetical: a provider placeholder for an undecided tie can carry the
        same id on both sides, and `expected_lambdas` on one team twice returns a
        perfectly plausible projection for a game that does not exist."""
        by_api = cups.index_by_api_id([ARSENAL])
        assert cups.resolve_tie(42, 42, by_api)[2] == "same_team"

    def test_exactly_one_of_a_pair_and_a_reason_comes_back(self):
        """So a caller cannot half-use the result."""
        by_api = cups.index_by_api_id([ARSENAL, BAYERN])
        for args in ((42, 157), (42, 999), (42, 42)):
            home, away, reason = cups.resolve_tie(*args, by_api)
            assert bool(reason) != bool(home and away)


class TestTheIndexIsDeterministic:
    def test_a_duplicated_api_id_resolves_the_same_way_every_time(self):
        """It should not happen — a club plays in one league a season and each league's
        teams are rebuilt wholesale — but a half-finished sync leaves rows behind, and
        'whichever Mongo returned last' would produce a different board per request."""
        a = team("eng-ch-42", 42, "eng-ch", games=20)
        b = team("eng-pl-42", 42, "eng-pl", games=20)
        assert cups.index_by_api_id([a, b])[42]["team_id"] == \
               cups.index_by_api_id([b, a])[42]["team_id"]

    def test_the_row_with_more_real_games_wins(self):
        thin = team("eng-ch-42", 42, "eng-ch", games=4)
        full = team("eng-pl-42", 42, "eng-pl", games=20)
        assert cups.index_by_api_id([full, thin])[42]["team_id"] == "eng-pl-42"

    def test_the_higher_division_breaks_a_tie_on_games(self):
        second = team("eng-ch-42", 42, "eng-ch", games=20)
        top = team("eng-pl-42", 42, "eng-pl", games=20)
        assert cups.index_by_api_id([second, top])[42]["league_id"] == "eng-pl"

    def test_a_team_with_no_api_id_is_skipped_not_keyed_on_none(self):
        """Mock/seed teams have no api_team_id. Keying them under None would make every
        unknown cup side resolve to whichever one landed there."""
        idx = cups.index_by_api_id([{"team_id": "mock-1", "league_id": "x", "name": "M"}])
        assert idx == {}


class TestTheCrossLeagueCaveat:
    def test_two_sides_from_different_leagues_are_flagged(self):
        assert cups.cross_league(ARSENAL, BAYERN) is True

    def test_an_all_english_tie_in_europe_is_not(self):
        """The caveat is about two records earned against different opposition, NOT about
        the badge on the fixture. Arsenal v Spurs in a European tie is Premier League form
        on both sides, directly comparable, and labelling it 'form from different leagues'
        would be a warning about nothing that teaches people to ignore the real ones."""
        assert cups.cross_league(ARSENAL, SPURS) is False
        assert cups.transfer_note(ARSENAL, SPURS) == ""

    def test_the_note_names_both_leagues_and_the_rotation_risk(self):
        note = cups.transfer_note(ARSENAL, BAYERN)
        assert "Premier League" in note and "Bundesliga" in note
        # Rotation is the limit no corner count can see, so it is said rather than modelled.
        assert "rotation" in note.lower()

    def test_a_missing_side_is_not_reported_as_crossed(self):
        assert cups.cross_league(None, BAYERN) is False


class TestTheBlendedYardstick:
    def test_two_leagues_average_to_their_midpoint(self):
        assert cups.blend(9.6, 11.4, 10.0) == 10.5

    def test_one_league_is_unchanged(self):
        """EVERY DOMESTIC FIXTURE TAKES THIS PATH, so if it were not an identity the cup
        work would have quietly re-priced all 27 leagues."""
        assert cups.blend(9.6, 9.6, 10.0) == 9.6

    def test_a_missing_side_falls_back_to_the_one_present(self):
        assert cups.blend(None, 11.4, 10.0) == 11.4
        assert cups.blend(9.6, None, 10.0) == 9.6

    def test_both_missing_reaches_the_callers_default(self):
        """The same default those call sites already used — `or 10.0` and `, 5.0`."""
        assert cups.blend(None, None, 10.0) == 10.0
        assert cups.blend(None, None, 5.0) == 5.0

    def test_a_zero_average_is_kept_rather_than_treated_as_missing(self):
        """`or` would swallow it. It cannot happen with real corner data, and the day it
        does the honest answer is 0, not a silent 10.0 that hides an empty league."""
        assert cups.blend(0.0, 10.0, 99.0) == 5.0


class TestTheConfigItself:
    def test_the_cup_is_not_in_the_league_list(self):
        """If it ever is, the sync builds `ucl-42` team documents and the second Arsenal
        problem is back — see the long note above CUP_META."""
        for cid in CUP_META:
            assert cid not in LEAGUE_META

    def test_is_cup_only_says_yes_to_cups(self):
        assert cups.is_cup("ucl") is True
        for lid in LEAGUE_META:
            assert cups.is_cup(lid) is False
        assert cups.is_cup(None) is False
        assert cups.is_cup("all") is False

    def test_the_written_bar_is_higher_than_nothing_and_is_real_games(self):
        assert cups.CUP_MIN_GAMES >= 5

    def test_a_cup_pick_can_be_settled(self):
        """THE SILENT ONE. Settlement looks a pick's competition up to fetch the fixture
        window it was played in. A league-only lookup returns nothing for a cup pick and
        does not raise — it logs "no league meta" and leaves the pick pending for ever, so
        the published record simply shows fewer games than were actually posted. That is
        the record the money-back guarantee is measured against."""
        for cid, meta in CUP_META.items():
            assert COMPETITION_META.get(cid) is meta
            assert isinstance(COMPETITION_META[cid]["api"], int)

    def test_the_combined_map_still_holds_every_league(self):
        for lid, meta in LEAGUE_META.items():
            assert COMPETITION_META[lid] is meta

    def test_settlement_resolves_through_the_combined_map(self):
        """Both settlement paths. A pick logged on a cup tie has to reach a result by the
        same route as a league one, and the failure mode is a ledger that looks short
        rather than an error anybody sees."""
        import inspect

        import settle_picks
        import settlement
        for mod in (settlement, settle_picks):
            src = inspect.getsource(mod)
            assert "COMPETITION_META" in src, mod.__name__

    def test_competition_name_covers_both_kinds(self):
        assert cups.competition_name("ucl") == CUP_META["ucl"]["name"]
        assert cups.competition_name("eng-pl") == "Premier League"
        assert cups.competition_name("nonsense") == "nonsense"
