"""The front door: countries, their competitions, and the games coming up.

Every other board answers "what should I bet", which assumes the reader has already
decided to be shown a selection. This answers the question somebody arriving actually has
— "what is on, and where" — so what is pinned here is the grouping, and the one thing a
filtered browser can get wrong without anybody noticing: a count that does not match what
opening it reveals.
"""
import asyncio
import os
import sys
from datetime import datetime, timedelta, timezone

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "test_corner_model")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import server  # noqa: E402

SOON = (datetime.now(timezone.utc) + timedelta(days=2)).isoformat()
LATER = (datetime.now(timezone.utc) + timedelta(days=20)).isoformat()
PAST = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()


class FakeCollection:
    def __init__(self, rows):
        self.rows = list(rows)

    def find(self, *a, **k):
        return self

    async def to_list(self, _n):
        return list(self.rows)


class FakeDB:
    def __init__(self, teams, fixtures, leagues):
        self.teams = FakeCollection(teams)
        self.fixtures = FakeCollection(fixtures)
        self.leagues = FakeCollection(leagues)


def run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def match(cf, home=True, i=0):
    return {"home": home, "corners_for": cf, "corners_against": 4,
            "goals_for": 1, "goals_against": 1, "opponent": "X",
            "date": f"2026-08-{(i % 27) + 1:02d}"}


NAMES = {}


def team(tid, name, league, corners):
    NAMES[tid] = name
    return {"team_id": tid, "name": name, "league_id": league,
            "real_matches": [match(c, i=i) for i, c in enumerate(corners)]}


def fixture(fid, league, home, away, date=SOON):
    return {"fixture_id": fid, "league_id": league, "date": date,
            "home_team_id": home, "away_team_id": away,
            "home_name": NAMES.get(home, home), "away_name": NAMES.get(away, away),
            "round": "R1"}


LEAGUES = [
    {"league_id": "eng-pl", "name": "Premier League", "country": "England"},
    {"league_id": "eng-ch", "name": "Championship", "country": "England"},
    {"league_id": "nor-d1", "name": "Eliteserien", "country": "Norway"},
]

# A long run at a high line, a flat side, and one whose rate has jumped lately.
STREAKY = team("eng-pl-a", "Arsenal", "eng-pl", [8, 8, 9, 8, 9, 8, 9, 8])
FLAT = team("eng-pl-b", "Brentford", "eng-pl", [5, 5, 5, 5, 5, 5, 5, 5])
RISING = team("eng-ch-c", "Cardiff", "eng-ch", [2, 2, 3, 2, 3, 9, 9, 10])
QUIET = team("eng-ch-d", "Derby", "eng-ch", [4, 4, 4, 4, 4, 4, 4, 4])
# Ordinary: a run exists at a low rung, which is exactly what the filter must NOT keep.
NOR1 = team("nor-d1-e", "Brann", "nor-d1", [5, 4, 6, 5, 4, 6])
NOR2 = team("nor-d1-f", "Viking", "nor-d1", [4, 5, 4, 5, 4, 5])

TEAMS = [STREAKY, FLAT, RISING, QUIET, NOR1, NOR2]
FIXTURES = [
    fixture("f-pl", "eng-pl", "eng-pl-a", "eng-pl-b"),
    fixture("f-ch", "eng-ch", "eng-ch-c", "eng-ch-d"),
    fixture("f-no", "nor-d1", "nor-d1-e", "nor-d1-f"),
]


def browse(monkeypatch, **kw):
    monkeypatch.setattr(server, "db", FakeDB(TEAMS, FIXTURES, LEAGUES))
    return run(server.browse(**kw))


def leagues_of(data, country):
    c = next((c for c in data["countries"] if c["country"] == country), None)
    return {l["league_id"]: l for l in (c or {}).get("leagues", [])}


class TestTheTree:
    def test_games_are_grouped_under_their_country(self, monkeypatch):
        d = browse(monkeypatch)
        assert {c["country"] for c in d["countries"]} == {"England", "Norway"}

    def test_a_country_holds_its_competitions(self, monkeypatch):
        assert set(leagues_of(browse(monkeypatch), "England")) == {"eng-pl", "eng-ch"}

    def test_the_busiest_country_is_first(self, monkeypatch):
        # The list is browsed top down, so the country with most on is the one to open.
        d = browse(monkeypatch)
        assert d["countries"][0]["country"] == "England"

    def test_a_league_carries_its_games_in_kick_off_order(self, monkeypatch):
        g = leagues_of(browse(monkeypatch), "Norway")["nor-d1"]["games"]
        assert [x["fixture_id"] for x in g] == ["f-no"]
        assert g[0]["home"] and g[0]["away"]

    def test_games_outside_the_window_are_not_there(self, monkeypatch):
        monkeypatch.setattr(server, "db", FakeDB(
            TEAMS, FIXTURES + [fixture("f-far", "nor-d1", "nor-d1-e", "nor-d1-f", LATER),
                               fixture("f-old", "nor-d1", "nor-d1-e", "nor-d1-f", PAST)],
            LEAGUES))
        ids = {g["fixture_id"] for c in run(server.browse(days=7))["countries"]
               for l in c["leagues"] for g in l["games"]}
        assert "f-far" not in ids and "f-old" not in ids

    def test_a_wider_window_reaches_them(self, monkeypatch):
        monkeypatch.setattr(server, "db", FakeDB(
            TEAMS, FIXTURES + [fixture("f-far", "nor-d1", "nor-d1-e", "nor-d1-f", LATER)],
            LEAGUES))
        ids = {g["fixture_id"] for c in run(server.browse(days=28))["countries"]
               for l in c["leagues"] for g in l["games"]}
        assert "f-far" in ids


class TestTheFilter:
    """`show` filters the GAMES, which is the whole point of it being on the home page."""

    def test_all_is_everything(self, monkeypatch):
        assert browse(monkeypatch, show="all")["total"] == 3

    def test_streaks_keeps_only_games_with_a_run_going_in(self, monkeypatch):
        d = browse(monkeypatch, show="streaks")
        ids = {g["fixture_id"] for c in d["countries"] for l in c["leagues"]
               for g in l["games"]}
        assert "f-pl" in ids, "a side 8 in a row has to survive the streak filter"
        assert "f-no" not in ids, "a side with no run must not"

    def test_and_the_row_says_whose_run_it_is(self, monkeypatch):
        # A row on a filtered list has to say why it is there, not merely that it survived.
        d = browse(monkeypatch, show="streaks")
        g = leagues_of(d, "England")["eng-pl"]["games"][0]
        assert g["streak"]["team"] == "Arsenal"
        assert g["streak"]["run"] >= server.PANEL_MIN_RUN

    def test_trends_keeps_only_games_where_a_rate_has_moved(self, monkeypatch):
        d = browse(monkeypatch, show="trends")
        ids = {g["fixture_id"] for c in d["countries"] for l in c["leagues"]
               for g in l["games"]}
        assert "f-ch" in ids, "a side gone from two corners to nine is trending"
        assert "f-no" not in ids, "a side that does the same thing every week is not"

    def test_an_unknown_filter_falls_back_rather_than_emptying_the_page(self, monkeypatch):
        assert browse(monkeypatch, show="nonsense")["total"] == 3


class TestTheCountsMatchWhatOpeningItShows:
    """The one thing a filtered browser can get wrong without anybody noticing. A league
    that reads "12 games" and opens to show two is worse than one that reads two — the
    number is what a reader decides to open on."""

    def test_every_league_count_equals_its_games(self, monkeypatch):
        for show in ("all", "streaks", "trends"):
            d = browse(monkeypatch, show=show)
            for c in d["countries"]:
                for l in c["leagues"]:
                    assert l["count"] == len(l["games"]), f"{l['league_id']} on {show}"

    def test_every_country_count_equals_its_leagues(self, monkeypatch):
        for show in ("all", "streaks", "trends"):
            d = browse(monkeypatch, show=show)
            for c in d["countries"]:
                assert c["count"] == sum(l["count"] for l in c["leagues"])

    def test_and_the_total_equals_the_lot(self, monkeypatch):
        for show in ("all", "streaks", "trends"):
            d = browse(monkeypatch, show=show)
            assert d["total"] == sum(c["count"] for c in d["countries"])


class TestTrendItself:
    def test_a_side_that_always_does_the_same_is_not_trending(self):
        assert server._trend_of(FLAT) is None

    def test_a_jump_is_up_and_a_collapse_is_down(self):
        assert server._trend_of(RISING) == "up"
        falling = team("x", "x", "l", [10, 9, 10, 9, 2, 2, 3])
        assert server._trend_of(falling) == "down"

    def test_too_little_history_has_no_direction(self):
        # Three of five games IS the season; the delta would be noise with a direction
        # printed on it.
        assert server._trend_of(team("y", "y", "l", [2, 9, 3])) is None

    def test_it_is_measured_against_the_TEAM_not_the_league(self):
        # A side that always wins six has not changed, however high six is.
        assert server._trend_of(team("z", "z", "l", [9, 9, 9, 9, 9, 9, 9])) is None


class TestTheStreakBarIsTheLeaguesNotTheTeams:
    """THE SECOND ATTEMPT, and the first one is why this class exists. A team-relative bar
    looked right and let an ordinary side through: a run is reported at the HIGHEST line
    it held, which for a low-variance side is simply its floor — so "4+ in six straight"
    from a team winning four or five every week cleared its own average and read as a
    streak. Unusual has to be measured against the division."""

    def test_an_ordinary_side_on_a_long_low_run_is_not_a_streak(self):
        # Four or five every week. A run exists at 4+; it describes the team, not a change.
        ordinary = team("o", "Ordinary", "l", [4, 5, 4, 5, 4, 5])
        assert server.live_streak(ordinary, "overall", "team", "over",
                                  min_len=server.PANEL_MIN_RUN) is not None
        assert server._browse_streak(ordinary, 4.75) is None

    def test_but_a_run_above_what_the_division_does_is(self):
        big = team("b", "Big", "l", [8, 8, 9, 8, 9, 8, 9, 8])
        assert server._browse_streak(big, 5.2)["line"] >= 8

    def test_the_same_team_in_a_higher_scoring_league_is_not(self):
        # The bar moves with the division, which is the whole point of it being the
        # league's number.
        big = team("b", "Big", "l", [8, 8, 9, 8, 9, 8, 9, 8])
        assert server._browse_streak(big, 9.5) is None


class TestTheDayFilter:
    """A window answers "what is on this week"; a day answers "what is on Saturday", and
    the second is the question somebody has when they are actually going to bet."""

    def day_of(self, monkeypatch, fid):
        d = browse(monkeypatch)
        for c in d["countries"]:
            for l in c["leagues"]:
                for g in l["games"]:
                    if g["fixture_id"] == fid:
                        return g["day"]
        return None

    def test_every_game_carries_the_day_it_is_played_in_london(self, monkeypatch):
        d = browse(monkeypatch)
        for c in d["countries"]:
            for l in c["leagues"]:
                for g in l["games"]:
                    assert len(g["day"]) == 10 and g["day"].count("-") == 2

    def test_the_calendar_lists_the_window_with_counts(self, monkeypatch):
        d = browse(monkeypatch)
        assert d["calendar"], "the chips have nothing to render"
        assert sum(x["count"] for x in d["calendar"]) == d["total"]
        assert [x["day"] for x in d["calendar"]] == sorted(x["day"] for x in d["calendar"])

    def test_picking_a_day_narrows_to_it(self, monkeypatch):
        target = self.day_of(monkeypatch, "f-pl")
        d = browse(monkeypatch, day=target)
        seen = {g["day"] for c in d["countries"] for l in c["leagues"] for g in l["games"]}
        assert seen == {target}

    def test_the_calendar_still_shows_the_other_days(self, monkeypatch):
        # Built BEFORE the day filter, so the chips keep saying what else is on rather
        # than collapsing to the one that is selected.
        target = self.day_of(monkeypatch, "f-pl")
        full = browse(monkeypatch)["calendar"]
        assert browse(monkeypatch, day=target)["calendar"] == full

    def test_counts_still_match_what_opening_it_shows(self, monkeypatch):
        target = self.day_of(monkeypatch, "f-pl")
        d = browse(monkeypatch, day=target)
        for c in d["countries"]:
            assert c["count"] == sum(l["count"] for l in c["leagues"])
            for l in c["leagues"]:
                assert l["count"] == len(l["games"])
        assert d["total"] == sum(c["count"] for c in d["countries"])

    def test_a_country_with_nothing_that_day_is_dropped(self, monkeypatch):
        # An empty LEAGUE inside an open country is information. An empty COUNTRY is a row
        # that can only be opened to be disappointed, and on one day most are empty.
        target = self.day_of(monkeypatch, "f-pl")
        d = browse(monkeypatch, day=target)
        assert all(c["count"] > 0 for c in d["countries"])

    def test_a_day_with_nothing_on_it_is_empty_rather_than_everything(self, monkeypatch):
        d = browse(monkeypatch, day="1999-01-01")
        assert d["total"] == 0 and d["countries"] == []

    def test_no_day_is_the_whole_window(self, monkeypatch):
        assert browse(monkeypatch, day="")["total"] == browse(monkeypatch)["total"]
