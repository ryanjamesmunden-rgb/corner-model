"""The league's corner table, split by venue and rankable by any column.

WHAT THIS PINS. One solid average table answers one question, and a side winning eight
corners at home and four away averages six — a number describing neither half. So the
split has to be a real split (the home row must be the home games and nothing else), and
the shot columns have to carry their own coverage, because the provider's shot data is
thinner than its corner data and a four-game average sorted into a league table looks
exactly like a twelve-game one.
"""
import asyncio
import os
import sys

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "test_corner_model")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import server  # noqa: E402


class FakeCollection:
    def __init__(self, rows):
        self.rows = list(rows)

    def find(self, q=None, *a, **k):
        q = q or {}
        rows = [r for r in self.rows
                if all(r.get(key) == val for key, val in q.items())]
        return FakeCursor(rows)

    async def find_one(self, q=None, *a, **k):
        q = q or {}
        return next((r for r in self.rows
                     if all(r.get(key) == val for key, val in q.items())), None)


class FakeCursor:
    def __init__(self, rows):
        self.rows = rows

    async def to_list(self, _n):
        return list(self.rows)


class FakeDB:
    def __init__(self, teams, leagues):
        self.teams = FakeCollection(teams)
        self.leagues = FakeCollection(leagues)


def run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def match(home, cf, ca, shots=None, sot=None):
    m = {"home": home, "corners_for": cf, "corners_against": ca,
         "goals_for": 1, "goals_against": 1, "opponent": "X", "date": "2026-08-01"}
    if shots is not None:
        m["shots_for"], m["shots_against"] = shots, 10
    if sot is not None:
        m["shots_on_target_for"], m["shots_on_target_against"] = sot, 4
    return m


# Eight at home, two away. The overall average is five, which describes neither.
LOPSIDED = {
    "team_id": "a", "name": "Lopsided", "league_id": "l",
    "real_matches": [match(True, 8, 3, 18, 7), match(True, 8, 3, 18, 7),
                     match(False, 2, 9, 6, 1), match(False, 2, 9, 6, 1)],
}
# Shots recorded in one game of four: the coverage trap this table has to show.
THIN_SHOTS = {
    "team_id": "b", "name": "Thin", "league_id": "l",
    "real_matches": [match(True, 5, 5, 30, 14), match(True, 5, 5),
                     match(False, 5, 5), match(False, 5, 5)],
}
# No shot data at all. Must read as "not recorded", never as zero shots taken.
NO_SHOTS = {
    "team_id": "c", "name": "Dark", "league_id": "l",
    "real_matches": [match(True, 6, 4), match(False, 6, 4)],
}
TEAMS = [LOPSIDED, THIN_SHOTS, NO_SHOTS]
LEAGUES = [{"league_id": "l", "name": "Test League", "country": "Nowhere"}]


def table(monkeypatch):
    monkeypatch.setattr(server, "db", FakeDB(TEAMS, LEAGUES))
    return run(server.corner_table("l"))


def row(data, name):
    return next(t for t in data["teams"] if t["name"] == name)


class TestTheSplitIsARealSplit:
    def test_all_three_venues_come_back(self, monkeypatch):
        s = row(table(monkeypatch), "Lopsided")["splits"]
        assert set(s) == {"overall", "home", "away"}

    def test_the_home_row_is_the_home_games_and_nothing_else(self, monkeypatch):
        s = row(table(monkeypatch), "Lopsided")["splits"]
        assert s["home"]["games"] == 2 and s["home"]["corners_won"] == 8
        assert s["away"]["games"] == 2 and s["away"]["corners_won"] == 2

    def test_and_the_overall_row_describes_neither_half(self, monkeypatch):
        # The whole reason the split exists: 5 is not what this side does anywhere.
        s = row(table(monkeypatch), "Lopsided")["splits"]
        assert s["overall"]["corners_won"] == 5
        assert s["overall"]["games"] == 4

    def test_corners_conceded_splits_too(self, monkeypatch):
        s = row(table(monkeypatch), "Lopsided")["splits"]
        assert s["home"]["corners_conceded"] == 3 and s["away"]["corners_conceded"] == 9

    def test_a_venue_with_no_games_is_empty_rather_than_zero(self, monkeypatch):
        only_home = {"team_id": "d", "name": "Homers", "league_id": "l",
                     "real_matches": [match(True, 7, 4)]}
        monkeypatch.setattr(server, "db", FakeDB([only_home], LEAGUES))
        s = run(server.corner_table("l"))["teams"][0]["splits"]
        assert s["away"]["games"] == 0
        assert s["away"]["corners_won"] is None, "zero corners away is a claim, not a gap"


class TestTheShotColumnsCarryTheirCoverage:
    """The provider's shot data is thinner than its corner data and thinner again on
    shots on target. An average over four games sorted into a league table looks exactly
    like one over twelve, so the denominator has to travel with the number."""

    def test_coverage_is_counted_separately_from_games(self, monkeypatch):
        t = row(table(monkeypatch), "Thin")["splits"]["overall"]
        assert t["games"] == 4
        assert t["covered"]["shots"] == 1, "one of four games carried shots"

    def test_and_the_average_is_over_the_covered_games_not_all_of_them(self, monkeypatch):
        # 30 shots in the one covered game. Dividing by four would read 7.5 and be a
        # coverage gap dressed up as a quiet side.
        t = row(table(monkeypatch), "Thin")["splits"]["overall"]
        assert t["shots"] == 30

    def test_nothing_recorded_reads_as_nothing_recorded(self, monkeypatch):
        t = row(table(monkeypatch), "Dark")["splits"]["overall"]
        assert t["shots"] is None and t["shots_on_target"] is None
        assert t["covered"]["shots"] == 0
        # And the corners are still there — a shot gap is not a data gap.
        assert t["corners_won"] == 6

    def test_shots_on_target_is_there_to_rank_on(self, monkeypatch):
        t = row(table(monkeypatch), "Lopsided")["splits"]
        assert t["home"]["shots_on_target"] == 7 and t["away"]["shots_on_target"] == 1

    def test_both_ends_of_the_shot_columns_are_carried(self, monkeypatch):
        # Against as well as for, so the table can show a match-up rather than one side.
        t = row(table(monkeypatch), "Lopsided")["splits"]["home"]
        assert t["shots_against"] == 10 and t["shots_on_target_against"] == 4


class TestTheOldShapeStillWorks:
    """The flat fields are what this endpoint has always returned and the page that
    reads them should not have to change to keep working."""

    def test_the_flat_fields_are_the_overall_split(self, monkeypatch):
        t = row(table(monkeypatch), "Lopsided")
        assert t["corners_won"] == t["splits"]["overall"]["corners_won"]
        assert t["corners_conceded"] == t["splits"]["overall"]["corners_conceded"]
        assert t["games"] == t["splits"]["overall"]["games"]

    def test_the_default_order_is_still_corners_won(self, monkeypatch):
        names = [t["name"] for t in table(monkeypatch)["teams"]]
        assert names[0] == "Dark", "6 a game, ahead of Lopsided's 5 and Thin's 5"

    def test_a_team_with_no_shot_data_reports_zero_in_the_flat_field(self, monkeypatch):
        # Flat fields are zero-filled as they always were; `splits` is where None lives.
        assert row(table(monkeypatch), "Dark")["shots"] == 0.0

    def test_the_league_name_rides_along(self, monkeypatch):
        d = table(monkeypatch)
        assert d["league_name"] == "Test League" and d["country"] == "Nowhere"
