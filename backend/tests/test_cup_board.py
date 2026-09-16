"""A cup tie on the board, over a database small enough to read.

test_cups covers the rules. This covers the four places that looked up a league reference
with the FIXTURE's id and used it for both sides — correct for as long as every fixture in
the database was domestic, and silently wrong the first time one was not.

WHY THESE FAILURES ARE THE DANGEROUS KIND. None of them raises. A cup has no teams, so:

  - `league_avg.get(fx["league_id"]) or 10.0` returns the HARDCODED 10.0, and every
    European tie is judged busy-or-quiet against a number nobody measured. The board still
    sorts, still ranks, still prints a `corner_edge` to three decimal places.
  - `leagues.get(fx["league_id"]).get("avg_shots") or REF_SHOTS` prices both sides off the
    reference constant, so the intent term — the whole v3 model — is switched off for
    European games and nothing says so.
  - filtering `db.teams` by the requested league returns nothing for a cup, every fixture
    falls out at the `if not home or not away` guard, and the board renders an empty
    competition that looks exactly like a quiet week.

Each test below asserts against the wrong number specifically, not merely that a number
came back.
"""
import asyncio
import os
import sys
from datetime import datetime, timedelta, timezone

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "test_corner_model")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import server  # noqa: E402

NOW = datetime.now(timezone.utc)


def iso(hours):
    return (NOW + timedelta(hours=hours)).isoformat().replace("+00:00", "Z")


def matches(n, won, conceded, shots, blocked=4):
    """n real games, alternating venue, with the features the v3 lambda reads."""
    return [{"home": i % 2 == 0, "corners_for": won, "corners_against": conceded,
             "shots_for": shots, "shots_against": shots,
             "blocked_shots_for": blocked, "blocked_shots_against": blocked,
             "goals_for": 1, "goals_against": 1, "fh_goals_for": 1, "fh_goals_against": 0,
             "date": (NOW - timedelta(days=n - i)).isoformat(), "opponent": "Someone"}
            for i in range(n)]


def team(tid, api, lid, won=6, conceded=5, shots=14, n=20):
    return {"team_id": tid, "api_team_id": api, "league_id": lid, "name": tid,
            "real_samples": n, "real_matches": matches(n, won, conceded, shots),
            "matches": matches(n, won, conceded, shots)}


# TWO LEAGUES THAT PRODUCE VISIBLY DIFFERENT CORNER COUNTS, so a blended yardstick, a
# per-league one and the hardcoded 10.0 are all distinguishable in an assertion. If they
# averaged the same, every version of this code would pass.
BUSY = team("eng-pl-42", 42, "eng-pl", won=7, conceded=6, shots=16)      # 13/game
QUIET = team("ger-bl-157", 157, "ger-bl", won=4, conceded=3, shots=10)   # 7/game
BUSY2 = team("eng-pl-47", 47, "eng-pl", won=7, conceded=6, shots=16)

LEAGUES = [
    {"league_id": "eng-pl", "name": "Premier League", "avg_shots": 16.0, "avg_blocked": 4.0},
    {"league_id": "ger-bl", "name": "Bundesliga", "avg_shots": 10.0, "avg_blocked": 4.0},
    # WHAT sync_cup ACTUALLY WRITES: a name, and no averages at all, because a cup has no
    # teams to compute them from. Every failure this file guards starts here.
    {"league_id": "ucl", "name": "Champions League", "is_cup": True,
     "teams_from": "domestic"},
]


def fixture(fid, lid, home, away, hours=48, **extra):
    return {"fixture_id": fid, "league_id": lid, "date": iso(hours), "round": "Round 1",
            "home_team_id": home["team_id"], "away_team_id": away["team_id"],
            "home_name": home["team_id"], "away_name": away["team_id"],
            "status": "upcoming", **extra}


class FakeCursor:
    def __init__(self, docs):
        self._docs = list(docs)

    def sort(self, field, direction=1):
        self._docs.sort(key=lambda d: d.get(field) or "", reverse=direction < 0)
        return self

    async def to_list(self, n):
        return [dict(d) for d in self._docs[:n]]


class FakeCollection:
    """Honours the league filter, because the filter is the thing under test.

    A fake that ignored the query would pass whether `_fixture_projections` filtered teams
    by the requested league or not — which is exactly the bug."""

    def __init__(self, docs):
        self._docs = list(docs)

    def find(self, q=None, proj=None):
        return FakeCursor([d for d in self._docs if self._match(d, q or {})])

    async def find_one(self, q=None, proj=None):
        rows = [d for d in self._docs if self._match(d, q or {})]
        return dict(rows[0]) if rows else None

    @staticmethod
    def _match(doc, q):
        for key, want in q.items():
            if isinstance(want, dict) and "$in" in want:
                if doc.get(key) not in want["$in"]:
                    return False
            elif doc.get(key) != want:
                return False
        return True


class FakeDB:
    def __init__(self, teams, fixtures, leagues=LEAGUES):
        self.teams = FakeCollection(teams)
        self.fixtures = FakeCollection(fixtures)
        self.leagues = FakeCollection(leagues)
        self.odds = FakeCollection([])


def run(coro):
    """Sync runner — the repo has no async pytest plugin, and asyncio.run() would close
    the loop other modules in the suite hold on to."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def projections(monkeypatch, teams, fixtures, **kwargs):
    monkeypatch.setattr(server, "db", FakeDB(teams, fixtures))
    return run(server._fixture_projections(**kwargs))


CUP_TIE = "ucl-1"
DOMESTIC = "eng-pl-1"


class TestTheYardstickIsNotAHardcodedDefault:
    def test_a_cup_tie_is_judged_against_the_two_leagues_and_not_10(self, monkeypatch):
        rows = projections(monkeypatch, [BUSY, QUIET],
                           [fixture(CUP_TIE, "ucl", BUSY, QUIET)], days=7)
        row = rows[CUP_TIE]
        # eng-pl produces 13 corners a game, ger-bl 7. The midpoint is 10.0 — which is
        # ALSO the hardcoded default, so that pair cannot tell the two apart. Asserted
        # against a deliberately lopsided pair below instead; here just pin the blend.
        assert row["league_avg_total"] == 10.0
        assert row["is_cup"] is True and row["cross_league"] is True

    def test_the_blend_moves_with_the_leagues_rather_than_sitting_on_10(self, monkeypatch):
        """THE ASSERTION THAT ACTUALLY SEPARATES THE TWO IMPLEMENTATIONS. Two busy
        leagues must not come back at 10.0, because 10.0 is what the bug returns."""
        busier = team("ita-sa-1", 1, "ita-sa", won=8, conceded=7, shots=16)   # 15/game
        leagues = LEAGUES + [{"league_id": "ita-sa", "name": "Serie A",
                              "avg_shots": 16.0, "avg_blocked": 4.0}]
        monkeypatch.setattr(server, "db", FakeDB([BUSY, busier],
                                                 [fixture(CUP_TIE, "ucl", BUSY, busier)],
                                                 leagues))
        row = run(server._fixture_projections(days=7))[CUP_TIE]
        assert row["league_avg_total"] == 14.0        # (13 + 15) / 2
        assert row["league_avg_total"] != 10.0

    def test_a_domestic_fixture_is_completely_unchanged(self, monkeypatch):
        """The blend degrades to the single league's own average when both sides share
        one — which is every fixture in all 27 leagues. If this ever fails, the cup work
        has quietly re-priced the entire board."""
        rows = projections(monkeypatch, [BUSY, BUSY2],
                           [fixture(DOMESTIC, "eng-pl", BUSY, BUSY2)], days=7)
        row = rows[DOMESTIC]
        assert row["league_avg_total"] == 13.0
        assert row["is_cup"] is False and row["cross_league"] is False
        assert row["transfer_note"] == ""


class TestEachSideIsPricedAgainstItsOwnLeague:
    def test_the_two_sides_get_different_shot_references(self, monkeypatch):
        """Bayern's shot volume judged against the Premier League's average measures the
        difference between two competitions, not the team's intent. The cup league
        document carries no averages at all, so the broken version prices BOTH sides off
        REF_SHOTS — and the giveaway is that the tie then matches a fixture where the
        references really were identical."""
        cup = projections(monkeypatch, [BUSY, QUIET],
                          [fixture(CUP_TIE, "ucl", BUSY, QUIET)], days=7)[CUP_TIE]
        # The same two teams, priced with one shared reference (what the bug does).
        wrong = server.expected_lambdas(BUSY, QUIET, server.REF_SHOTS, 0.0)
        assert (cup["lambda_home"], cup["lambda_away"]) != (wrong["home"], wrong["away"])
        # And it matches the per-side call, which is the intended behaviour spelled out.
        right = server.expected_lambdas(BUSY, QUIET, 16.0, 4.0, 10.0, 4.0)
        assert cup["lambda_home"] == right["home"]
        assert cup["lambda_away"] == right["away"]

    def test_a_domestic_fixture_still_uses_one_reference_for_both(self, monkeypatch):
        row = projections(monkeypatch, [BUSY, BUSY2],
                          [fixture(DOMESTIC, "eng-pl", BUSY, BUSY2)], days=7)[DOMESTIC]
        same = server.expected_lambdas(BUSY, BUSY2, 16.0, 4.0)
        assert (row["lambda_home"], row["lambda_away"]) == (same["home"], same["away"])


class TestAskingForTheCupReturnsItsFixtures:
    def test_filtering_by_the_cup_id_does_not_come_back_empty(self, monkeypatch):
        """The failure this exists for renders as a perfectly normal, empty competition.
        Teams filtered by `ucl` find nothing, both sides fail to resolve, and every
        fixture is dropped by the guard that exists for deleted teams."""
        rows = projections(monkeypatch, [BUSY, QUIET],
                           [fixture(CUP_TIE, "ucl", BUSY, QUIET)], days=7, league_id="ucl")
        assert set(rows) == {CUP_TIE}

    def test_filtering_by_a_league_still_excludes_other_leagues_fixtures(self, monkeypatch):
        """Loading every team must not become loading every fixture — a request for the
        Premier League board that also returned Bundesliga games would be a regression
        hiding inside the fix."""
        rows = projections(monkeypatch, [BUSY, QUIET, BUSY2],
                           [fixture(CUP_TIE, "ucl", BUSY, QUIET),
                            fixture(DOMESTIC, "eng-pl", BUSY, BUSY2)],
                           days=7, league_id="eng-pl")
        assert set(rows) == {DOMESTIC}

    def test_the_competition_name_is_the_cups_not_a_sides_league(self, monkeypatch):
        """`league_name` is what a posted pick prints. "Premier League" on an
        Arsenal v Bayern tie would be wrong in a way nobody notices until it is published."""
        row = projections(monkeypatch, [BUSY, QUIET],
                          [fixture(CUP_TIE, "ucl", BUSY, QUIET)], days=7)[CUP_TIE]
        assert row["league_name"] == "Champions League"
        assert row["home_league_name"] == "Premier League"
        assert row["away_league_name"] == "Bundesliga"


class TestTheTransferCaveatRidesOnTheRow:
    def test_a_cross_league_tie_carries_a_note_naming_both_leagues(self, monkeypatch):
        row = projections(monkeypatch, [BUSY, QUIET],
                          [fixture(CUP_TIE, "ucl", BUSY, QUIET)], days=7)[CUP_TIE]
        assert "Premier League" in row["transfer_note"]
        assert "Bundesliga" in row["transfer_note"]

    def test_an_all_english_tie_in_europe_carries_none(self, monkeypatch):
        """Both records are Premier League records, directly comparable. A warning here
        would be a warning about nothing, which teaches people to ignore the real ones."""
        row = projections(monkeypatch, [BUSY, BUSY2],
                          [fixture("ucl-2", "ucl", BUSY, BUSY2)], days=7)["ucl-2"]
        assert row["is_cup"] is True
        assert row["cross_league"] is False
        assert row["transfer_note"] == ""

    def test_a_mismatch_angle_on_a_cup_tie_is_flagged(self, monkeypatch):
        leaky = team("ger-bl-9", 9, "ger-bl", won=3, conceded=9, shots=10)
        row = projections(monkeypatch, [BUSY, leaky],
                          [fixture(CUP_TIE, "ucl", BUSY, leaky)], days=7)[CUP_TIE]
        mm = [a for a in row["angles"] if a["kind"] == "mismatch"]
        assert mm, "a 7-corner side against a defence conceding 9 should be a mismatch"
        assert all(a.get("cross_league") for a in mm)


class TestTheMismatchBarIsBlendedAndTheLambdaIsNot:
    def test_the_bar_comes_from_both_leagues(self, monkeypatch):
        """Whether a side wins unusually many corners is a question about the TIE, so it
        is asked against the midpoint of the two leagues. Against the busy league alone a
        genuinely strong Bundesliga side would be judged by English standards and never
        qualify; against the quiet one alone every English side would."""
        # ger-bl averages 4.0 corners won per team-game here, eng-pl 5.67. The blend is
        # 4.83, so the bar (x MISMATCH_EDGE) is 5.32 — which a Bundesliga side winning 6
        # clears. Against eng-pl's own average the bar would be 6.23 and the same side
        # would not qualify, which is the whole point.
        strong_de = team("ger-bl-5", 5, "ger-bl", won=6, conceded=3, shots=10)
        leaky_en = team("eng-pl-9", 9, "eng-pl", won=7, conceded=9, shots=16)
        rest = [team("ger-bl-6", 6, "ger-bl", won=3, conceded=3, shots=10),
                team("ger-bl-7", 7, "ger-bl", won=3, conceded=3, shots=10),
                team("eng-pl-10", 10, "eng-pl", won=5, conceded=5, shots=16),
                team("eng-pl-11", 11, "eng-pl", won=5, conceded=5, shots=16)]
        row = projections(monkeypatch, [strong_de, leaky_en] + rest,
                          [fixture(CUP_TIE, "ucl", strong_de, leaky_en)], days=7)[CUP_TIE]
        teams = [a["team"] for a in row["angles"] if a["kind"] == "mismatch"]
        assert "ger-bl-5" in teams
        # The contrast, spelled out: 6.0 would have failed the busy league's own bar.
        assert 6.0 < (5 + 5 + 7) / 3 * server.MISMATCH_EDGE


class TestTheIdIsAcceptedWhereItWorksAndRefusedWhereItDoesNot:
    """MANAGED_LEAGUE_IDS had to widen to include cups, or boot cleanup would delete every
    cup fixture on restart. That widening reaches four tool endpoints that were validating
    against it — and those tools sync teams, backfill per-fixture statistics and probe api
    ids, none of which a cup has. Accepted there, they would launch a subprocess that exits
    with "unknown league key" into a log nobody reads, while the endpoint reported that it
    had started fine."""

    def test_the_per_league_tools_refuse_a_cup_and_say_why(self):
        msg = server._not_a_league("ucl")
        assert "cup" in msg.lower()
        # Not "unknown": the id is perfectly well known and simply belongs to the other
        # list, and a reader told "unknown league_id ucl" would go looking for a typo.
        assert "unknown" not in msg.lower()

    def test_a_genuinely_unknown_id_still_reads_as_unknown(self):
        assert "unknown" in server._not_a_league("zzz-x").lower()

    def test_the_tool_endpoints_validate_against_the_league_list(self):
        import inspect
        src = inspect.getsource(server)
        assert "if league_id not in MANAGED_LEAGUE_IDS" not in src, \
            "a cup id would be accepted by a tool that only knows how to sync leagues"

    def test_logging_a_cup_pick_can_find_its_competition_name(self):
        """The pick endpoint validates against MANAGED_LEAGUE_IDS — which now accepts a
        cup — and then reads the name out of the metadata. A league-only read there is a
        KeyError: a 500 on the one endpoint that writes the published record."""
        assert server.COMPETITION_META["ucl"]["name"]
        for lid in ("ucl", "eng-pl"):
            assert lid in server.MANAGED_LEAGUE_IDS
            assert lid in server.COMPETITION_META


class TestTheFixturePage:
    """The detail page read `db.teams.find({"league_id": fx["league_id"]})` for its
    yardstick. On a cup that finds NOTHING, `league_avg_corners` comes back 0.0, and
    team_profile returns an empty list whenever the yardstick is falsy — so every trait on
    both sides disappears. No error, no empty state: a fixture page that mysteriously has
    nothing to say about either team."""

    def detail(self, monkeypatch, teams, fixtures, fid):
        monkeypatch.setattr(server, "db", FakeDB(teams, fixtures))
        return run(server.fixture_detail(fid, user={"user_id": "u1"}))

    def test_a_cup_tie_still_has_a_league_average_to_measure_against(self, monkeypatch):
        d = self.detail(monkeypatch, [BUSY, QUIET],
                        [fixture(CUP_TIE, "ucl", BUSY, QUIET)], CUP_TIE)
        assert d["league_avg_corners"] > 0

    def test_and_therefore_still_has_traits_on_both_sides(self, monkeypatch):
        d = self.detail(monkeypatch, [BUSY, QUIET],
                        [fixture(CUP_TIE, "ucl", BUSY, QUIET)], CUP_TIE)
        assert d["home_team"]["profile"], "the home side's traits vanished"
        assert d["away_team"]["profile"], "the away side's traits vanished"

    def test_the_page_names_the_competition_not_a_sides_league(self, monkeypatch):
        """`league_name` is what a posted pick prints."""
        d = self.detail(monkeypatch, [BUSY, QUIET],
                        [fixture(CUP_TIE, "ucl", BUSY, QUIET)], CUP_TIE)
        assert d["league_name"] == "Champions League"
        assert d["competition"]["name"] == "Champions League"

    def test_the_caveat_travels_with_the_payload(self, monkeypatch):
        """Built server-side so the page, the export and any posted pick quote the same
        sentence — two copies of a warning drift."""
        d = self.detail(monkeypatch, [BUSY, QUIET],
                        [fixture(CUP_TIE, "ucl", BUSY, QUIET)], CUP_TIE)
        comp = d["competition"]
        assert comp["is_cup"] is True and comp["cross_league"] is True
        assert comp["home_league_name"] == "Premier League"
        assert comp["away_league_name"] == "Bundesliga"
        assert "Premier League" in comp["transfer_note"]

    def test_a_domestic_fixture_carries_no_caveat(self, monkeypatch):
        d = self.detail(monkeypatch, [BUSY, BUSY2],
                        [fixture(DOMESTIC, "eng-pl", BUSY, BUSY2)], DOMESTIC)
        assert d["competition"]["is_cup"] is False
        assert d["competition"]["cross_league"] is False
        assert d["competition"]["transfer_note"] == ""

    def test_an_all_english_tie_in_europe_is_a_cup_without_the_caveat(self, monkeypatch):
        d = self.detail(monkeypatch, [BUSY, BUSY2],
                        [fixture("ucl-2", "ucl", BUSY, BUSY2)], "ucl-2")
        assert d["competition"]["is_cup"] is True
        assert d["competition"]["cross_league"] is False
        assert d["competition"]["transfer_note"] == ""

    def test_each_side_is_priced_against_its_own_league_here_too(self, monkeypatch):
        """The page and the board must not disagree about the same fixture."""
        d = self.detail(monkeypatch, [BUSY, QUIET],
                        [fixture(CUP_TIE, "ucl", BUSY, QUIET)], CUP_TIE)
        right = server.expected_lambdas(BUSY, QUIET, 16.0, 4.0, 10.0, 4.0)
        assert d["model"]["lambdas"]["home"] == right["home"]
        assert d["model"]["lambdas"]["away"] == right["away"]


class TestTheCardsCorroborationBar:
    """`weak_opponent` asks whether a defence concedes more corners than most, and "most"
    meant the STREAKING TEAM's league. Correct while both sides were in it; in a cup tie
    it reads every low-corner league as full of strong defences and every high-corner one
    as leaky — a bar silently measuring the wrong thing, on the card people pay for."""

    ROW = {"streak": {"length": 6},
           "projection": {"prob": 71.0, "lambda": 6.8, "opp_conceded": 6.0}}

    def test_a_genuinely_leaky_side_from_a_quiet_league_is_not_read_as_solid(self):
        import angle_of_day
        import cups as cuplib
        # eng-pl averages 7.0 corners won per team-game, ger-bl 3.5. A Bundesliga defence
        # conceding 6.0 is nearly double its own league's norm — genuinely leaky, and the
        # exact case the streaking side is looking for.
        against_england_only = angle_of_day.support_for(dict(self.ROW), 7.0)
        assert against_england_only["weak_opponent"] is False, \
            "this is the misreading: 6.0 judged against a 7.7 English bar looks solid"
        blended = angle_of_day.support_for(dict(self.ROW),
                                           cuplib.blend(7.0, 3.5, None))
        assert blended["weak_opponent"] is True

    def test_and_a_domestic_row_is_judged_exactly_as_before(self):
        import angle_of_day
        import cups as cuplib
        one = angle_of_day.support_for(dict(self.ROW), 4.5)
        both = angle_of_day.support_for(dict(self.ROW), cuplib.blend(4.5, 4.5, None))
        assert one == both

    def test_a_missing_opponent_league_falls_back_rather_than_dropping_the_bar(self):
        import angle_of_day
        import cups as cuplib
        s = angle_of_day.support_for(dict(self.ROW), cuplib.blend(3.5, None, None))
        assert s["opp_bar"] is not None
        assert s["weak_opponent"] is True

    def test_the_board_blends_and_records_the_flag(self):
        """Source-level, because reaching `_angle_board` needs the whole streak scan. The
        two things that must not drift: the bar spans both leagues, and the fact that a
        pick was a cup tie is written onto the row where the snapshot will freeze it."""
        import inspect
        src = inspect.getsource(server._angle_rows)
        assert "cups.blend(league_avgs.get(r[\"league_id\"]), opp_avg, None)" in src
        assert "cross_league" in src

    def test_the_snapshot_freezes_whether_a_pick_was_a_cup_tie(self):
        """Derived afterwards from a fixture list that has since been resynced is exactly
        the survivorship problem the snapshot exists to avoid."""
        import inspect
        src = inspect.getsource(server)
        i = src.index('"opponent": nf.get("opponent"), "is_home": nf.get("is_home")')
        assert '"cross_league": bool(nf.get("cross_league"))' in src[i:i + 1200]


class TestTheGuardsThatWereAlreadyThere:
    def test_a_fixture_whose_side_is_missing_is_still_dropped(self, monkeypatch):
        rows = projections(monkeypatch, [BUSY],
                           [fixture(CUP_TIE, "ucl", BUSY, QUIET)], days=7)
        assert rows == {}

    def test_a_fixture_outside_the_window_is_still_dropped(self, monkeypatch):
        rows = projections(monkeypatch, [BUSY, QUIET],
                           [fixture(CUP_TIE, "ucl", BUSY, QUIET, hours=24 * 40)], days=7)
        assert rows == {}

    def test_a_kickoff_in_the_past_is_still_dropped(self, monkeypatch):
        rows = projections(monkeypatch, [BUSY, QUIET],
                           [fixture(CUP_TIE, "ucl", BUSY, QUIET, hours=-2)], days=7)
        assert rows == {}
