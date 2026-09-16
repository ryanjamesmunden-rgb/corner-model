"""What the cup sync writes, and — mostly — what it refuses to.

THE SHAPE OF THE DOCUMENTS IS THE WHOLE FEATURE. A cup stores fixtures pointing at the
DOMESTIC team rows, so `home_team_id` reading "eng-pl-42" rather than "ucl-42" is not a
formatting detail: it is the difference between Arsenal's twenty-game season and a
six-game fragment invented by the competition. Nothing downstream would report the
mistake — the board would render, the streaks would compute, and every number on a
European game would be drawn from a third of a season.
"""
import os
import sys

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "test_corner_model")
os.environ.setdefault("API_FOOTBALL_KEY", "test-key")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import cups  # noqa: E402
import sync_real  # noqa: E402
from leagues_meta import CUP_META  # noqa: E402


def team(tid, api, lid, games=20):
    return {"team_id": tid, "api_team_id": api, "league_id": lid, "name": tid,
            "real_samples": games}


ARSENAL = team("eng-pl-42", 42, "eng-pl")
BAYERN = team("ger-bl-157", 157, "ger-bl")
SPURS = team("eng-pl-47", 47, "eng-pl")
BY_API = cups.index_by_api_id([ARSENAL, BAYERN, SPURS])


def af_fixture(fid, home_api, away_api, date="2026-09-30T19:00:00+00:00",
               rnd="Group Stage - 1"):
    """One entry as API-Football returns it."""
    return {"fixture": {"id": fid, "date": date, "status": {"short": "NS"}},
            "league": {"round": rnd},
            "teams": {"home": {"id": home_api, "name": f"T{home_api}"},
                      "away": {"id": away_api, "name": f"T{away_api}"}}}


class TestTheDocumentsPointAtDomesticTeams:
    def test_the_team_ids_are_the_leagues_not_the_cups(self):
        """THE ONE THAT MATTERS. `ucl-42` here would be a second Arsenal with a handful of
        games on file, and every average, streak and projection on that row would be
        computed from it without a word of complaint anywhere."""
        docs, skipped = sync_real.cup_fixture_docs("ucl", [af_fixture(1, 42, 157)], BY_API)
        assert skipped == {}
        assert [d["home_team_id"] for d in docs] == ["eng-pl-42"]
        assert [d["away_team_id"] for d in docs] == ["ger-bl-157"]
        assert not any(d["home_team_id"].startswith("ucl-") for d in docs)

    def test_the_fixture_id_is_derived_from_the_provider_id(self):
        """Fixtures are deleted and re-inserted on every sync, so a random id would strand
        every price somebody typed in and every starred game — see the long note in
        sync_league where this was fixed for the leagues."""
        docs, _ = sync_real.cup_fixture_docs("ucl", [af_fixture(12345, 42, 157)], BY_API)
        assert docs[0]["fixture_id"] == "ucl-12345"
        assert docs[0]["api_fixture_id"] == 12345

    def test_the_league_id_is_the_cup_so_boot_cleanup_and_filters_find_it(self):
        docs, _ = sync_real.cup_fixture_docs("ucl", [af_fixture(1, 42, 157)], BY_API)
        assert docs[0]["league_id"] == "ucl"

    def test_the_round_label_survives(self):
        docs, _ = sync_real.cup_fixture_docs(
            "ucl", [af_fixture(1, 42, 157, rnd="Round of 16")], BY_API)
        assert docs[0]["round"] == "Round of 16"

    def test_a_missing_round_does_not_produce_a_blank(self):
        f = af_fixture(1, 42, 157)
        f["league"] = {}
        docs, _ = sync_real.cup_fixture_docs("ucl", [f], BY_API)
        assert docs[0]["round"] == "Upcoming"

    def test_each_sides_league_rides_along(self):
        docs, _ = sync_real.cup_fixture_docs("ucl", [af_fixture(1, 42, 157)], BY_API)
        assert docs[0]["home_league_id"] == "eng-pl"
        assert docs[0]["away_league_id"] == "ger-bl"


class TestWhatItRefusesToStore:
    def test_a_tie_with_an_unknown_side_is_skipped_and_counted(self):
        """Counted, not silently dropped: "the round had thirty-two ties and we stored
        eleven" is a sentence somebody will need explained, and the alternative is a board
        that is quietly short with nothing to point at."""
        docs, skipped = sync_real.cup_fixture_docs(
            "ucl", [af_fixture(1, 42, 157), af_fixture(2, 42, 999)], BY_API)
        assert len(docs) == 1
        assert skipped == {"unknown_side": 1}

    def test_a_thin_side_is_skipped(self):
        thin = team("gre-sl-3", 3, "gre-sl", games=2)
        by_api = cups.index_by_api_id([ARSENAL, thin])
        docs, skipped = sync_real.cup_fixture_docs("ucl", [af_fixture(1, 42, 3)], by_api)
        assert docs == []
        assert skipped == {"thin_history": 1}

    def test_the_bar_is_a_parameter_so_the_rule_is_not_buried(self):
        thin = team("gre-sl-3", 3, "gre-sl", games=2)
        by_api = cups.index_by_api_id([ARSENAL, thin])
        docs, _ = sync_real.cup_fixture_docs("ucl", [af_fixture(1, 42, 3)], by_api,
                                             min_games=1)
        assert len(docs) == 1

    def test_nothing_resolvable_produces_an_empty_list_rather_than_an_error(self):
        docs, skipped = sync_real.cup_fixture_docs("ucl", [af_fixture(1, 900, 901)], {})
        assert docs == []
        assert skipped == {"unknown_side": 1}


class TestTheCrossLeagueFlagIsWrittenNotInferredLater:
    def test_a_cross_border_tie_is_marked(self):
        docs, _ = sync_real.cup_fixture_docs("ucl", [af_fixture(1, 42, 157)], BY_API)
        assert docs[0]["cup"] is True
        assert docs[0]["cross_league"] is True

    def test_an_all_english_tie_is_not(self):
        docs, _ = sync_real.cup_fixture_docs("ucl", [af_fixture(1, 42, 47)], BY_API)
        assert docs[0]["cup"] is True
        assert docs[0]["cross_league"] is False


class TestTheSyncDispatchesCupsSeparately:
    def test_the_default_target_list_covers_both_and_puts_cups_last(self):
        """Cups resolve their sides out of db.teams, so they have to run AFTER the leagues
        that populate it. On a fresh database the other order stores no cup fixtures at
        all and presents as "the cup has no games on"."""
        import inspect
        src = inspect.getsource(sync_real.main)
        assert "list(LEAGUE_META.keys()) + list(CUP_META.keys())" in src

    def test_a_cup_id_does_not_go_down_the_league_path(self):
        """sync_league would build `ucl-<id>` team documents, which is the second-Arsenal
        bug — and it would look like a successful sync."""
        import inspect
        src = inspect.getsource(sync_real.main)
        assert "sync_cup(hc, lid) if lid in CUP_META" in src

    def test_the_cup_sync_verifies_the_id_before_it_writes(self):
        """The identity check is worth nothing if the deletes and inserts happen first."""
        import inspect
        src = inspect.getsource(sync_real.sync_cup)
        verify = src.index("verify_identity")
        assert verify < src.index("delete_many")
        assert verify < src.index("insert_many")

    def test_the_cup_league_document_carries_no_shot_averages(self):
        """A cup has no teams to compute them from. Writing a number there would be the
        hardcoded-default bug moved into the database, where it would look measured."""
        import inspect
        src = inspect.getsource(sync_real.sync_cup)
        set_block = src[src.index('"league_id": cup_id, "name": meta["name"]'):]
        assert "avg_shots" not in set_block
        assert "avg_blocked" not in set_block

    def test_the_cap_is_applied_after_resolution_not_before(self):
        """With three European competitions this is the difference between the feature
        working and not. The Conference League's league phase is over a hundred fixtures,
        a large share involving sides from leagues this app does not sync — so a cap taken
        off the front of the FETCHED list spends the allowance on ties that get thrown
        away, and usable games two matchdays later (still inside the board's month-long
        horizon) are never looked at. It presents as "that competition barely has any
        games on", which is indistinguishable from a quiet week."""
        import inspect
        src = inspect.getsource(sync_real.sync_cup)
        assert "docs = docs[:UPCOMING_FIXTURES]" in src
        # And the fetched list is NOT pre-trimmed, which is what would silently undo it.
        fetched = src[src.index("ns = sorted"):src.index("teams = await")]
        assert "UPCOMING_FIXTURES" not in fetched

    def test_everything_is_fetched_before_the_existing_round_is_deleted(self):
        """A failed request must leave the previous round standing rather than empty the
        competition and then fall over."""
        import inspect
        src = inspect.getsource(sync_real.sync_cup)
        assert src.index("cup_fixture_docs") < src.index("delete_many")


class TestTheSeasonHelper:
    def test_the_current_season_is_preferred(self):
        entry = {"seasons": [{"year": 2024, "current": False},
                             {"year": 2025, "current": True},
                             {"year": 2026, "current": False}]}
        assert sync_real.season_from(entry) == 2025

    def test_the_newest_is_the_fallback_when_none_is_current(self):
        entry = {"seasons": [{"year": 2024, "current": False}, {"year": 2025}]}
        assert sync_real.season_from(entry) == 2025

    def test_no_entry_at_all_does_not_raise(self):
        assert isinstance(sync_real.season_from(None), int)


def test_the_cup_is_configured_with_something_to_verify_against():
    """Belt and braces with test_leagues_meta: if this ever empties, sync_cup's guard
    becomes a no-op and an id typed from memory syncs unchallenged."""
    assert all(m.get("verify_name") for m in CUP_META.values())
