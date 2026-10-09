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


def match(cf, home=True, i=0, ca=4):
    return {"home": home, "corners_for": cf, "corners_against": ca,
            "goals_for": 1, "goals_against": 1, "opponent": "X",
            "date": f"2026-08-{(i % 27) + 1:02d}"}


NAMES = {}


def team(tid, name, league, corners, conceded=None):
    NAMES[tid] = name
    ca = conceded or [4] * len(corners)
    return {"team_id": tid, "name": name, "league_id": league,
            "real_matches": [match(c, i=i, ca=ca[i]) for i, c in enumerate(corners)]}


def par(team_avg, match_avg=None, conceded_avg=4.0):
    """The league yardstick a run has to beat, one number per streak subject.

    `match_avg` defaults to the team number plus the four corners every synthetic match
    here concedes, which is what the division's match total actually comes to.
    """
    return {"team": team_avg, "conceded": conceded_avg,
            "match": team_avg + conceded_avg if match_avg is None else match_avg}


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

    def test_and_the_row_says_whose_run_it_is_and_which_games(self, monkeypatch):
        # A row on a filtered list has to say why it is there, not merely that it survived.
        #
        # IT DOES NOT PIN WHICH SIDE. Both of these are on a qualifying run — one eight in
        # a row over a high line, the other held a rung below the division eight times —
        # and which outranks the other is the ranking rule's business, tested below. A
        # test that named Arsenal here would fail the day the rule correctly changed its
        # mind, which is the opposite of what it is for.
        d = browse(monkeypatch, show="streaks")
        g = leagues_of(d, "England")["eng-pl"]["games"][0]
        s = g["streak"]
        assert s["team"] in (g["home"], g["away"])
        assert s["run"] >= server.PANEL_MIN_RUN
        assert s["venue"] in ("home", "away", "overall"), "a run with no venue reads as a lie"
        assert s["margin"] > 0

    def test_the_row_says_how_many_runs_are_behind_the_one_it_prints(self, monkeypatch):
        # "+3 more" is the difference between a game with one quirk and a game where
        # everything lines up, and the row has no space to print all four.
        d = browse(monkeypatch, show="streaks")
        for c in d["countries"]:
            for l in c["leagues"]:
                for g in l["games"]:
                    assert g["streak_count"] >= 1
        assert leagues_of(d, "England")["eng-pl"]["games"][0]["streak_count"] >= 2

    def test_a_game_with_no_run_carries_neither(self, monkeypatch):
        g = next(x for c in browse(monkeypatch)["countries"] for l in c["leagues"]
                 for x in l["games"] if x["fixture_id"] == "f-no")
        assert g["streak"] is None and g["streak_count"] == 0

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


def dirs(t):
    """Trend directions keyed by subject, so a test says which END of the team moved."""
    return {x["subject"]: x["direction"] for x in server._trends_of(t)}


class TestTrendItself:
    def test_a_side_that_always_does_the_same_is_not_trending(self):
        assert dirs(FLAT) == {}

    def test_a_jump_is_up_and_a_collapse_is_down(self):
        assert dirs(RISING)["team"] == "up"
        falling = team("x", "x", "l", [10, 9, 10, 9, 2, 2, 3])
        assert dirs(falling)["team"] == "down"

    def test_too_little_history_has_no_direction(self):
        # Three of five games IS the season; the delta would be noise with a direction
        # printed on it.
        assert dirs(team("y", "y", "l", [2, 9, 3])) == {}

    def test_it_is_measured_against_the_TEAM_not_the_league(self):
        # A side that always wins six has not changed, however high six is.
        assert dirs(team("z", "z", "l", [9, 9, 9, 9, 9, 9, 9])) == {}

    def test_a_defence_suddenly_being_got_at_is_a_trend_of_its_own(self):
        # BOTH ENDS OF A TEAM. A side conceding two more corners a game is exactly as
        # interesting as one winning them, and it is the half that finds the fixture —
        # the trend belongs to the defence and the bet to their opponent. Leaving it out
        # halved the list for no reason anybody could have defended.
        leaky = team("lk", "Leaky", "l", [5] * 7,
                     conceded=[3, 4, 3, 4, 8, 9, 8])
        assert dirs(leaky) == {"conceded": "up"}

    def test_a_side_keeping_them_out_lately_trends_down(self):
        tight = team("tg", "Tight", "l", [5] * 7, conceded=[9, 8, 9, 8, 3, 3, 4])
        assert dirs(tight)["conceded"] == "down"

    def test_a_trend_carries_the_two_numbers_it_is_claiming(self):
        # "corners up" with no figures is a direction nobody can check. The row prints
        # recent against season, so the claim is falsifiable on sight.
        t = next(x for x in server._trends_of(RISING) if x["subject"] == "team")
        assert t["recent"] > t["season"] and t["label"]


class TestTheStreakBarIsTheLeaguesNotTheTeams:
    """THE SECOND ATTEMPT, and the first one is why this class exists. A team-relative bar
    looked right and let an ordinary side through: a run is reported at the HIGHEST line
    it held, which for a low-variance side is simply its floor — so "4+ in six straight"
    from a team winning four or five every week cleared its own average and read as a
    streak. Unusual has to be measured against the division."""

    ORDINARY = [4, 5, 4, 5, 4, 5]
    BIG = [8, 8, 9, 8, 9, 8, 9, 8]

    def test_an_ordinary_side_on_a_long_low_run_is_not_a_streak(self):
        # Four or five every week. A run exists at 4+; it describes the team, not a change.
        ordinary = team("o", "Ordinary", "l", self.ORDINARY)
        assert server.live_streak(ordinary, "overall", "team", "over",
                                  min_len=server.PANEL_MIN_RUN) is not None
        assert server._browse_streak(ordinary, par(4.75), "overall") is None

    def test_but_a_run_past_what_the_division_does_is(self):
        big = team("b", "Big", "l", self.BIG)
        r = server._browse_streak(big, par(5.2), "overall")
        assert r and r["margin"] > 0 and r["run"] >= server.PANEL_MIN_RUN

    def test_the_same_run_in_a_higher_scoring_league_does_not_clear_on_the_over(self):
        # The bar moves with the division, which is the whole point of it being the
        # league's number.
        over8 = {"subject": "team", "direction": "over", "line": 8}
        assert server._browse_margin(over8, par(5.2)) == 8 - 5.2
        assert server._browse_margin(over8, par(9.5)) is None

    def test_an_under_is_judged_on_the_ceiling_it_held_not_its_line(self):
        # "under 6" wins at five or fewer and voids at six, so the ceiling actually held
        # is FIVE, and five is what has to clear the division. The two readings differ by
        # exactly one corner, so for a whole band of divisions they disagree about
        # whether the row survives at all — this is not a quibble. Comparing the line
        # would throw away every under holding a side a rung below average, which is most
        # of the real ones.
        #
        # STATED AGAINST THE CONSTANT, not against a number copied out of it, so that
        # moving the bar on evidence does not silently turn this into a test of nothing.
        bar = server.BROWSE_MIN_MARGIN
        avg = 6.0
        under6 = {"subject": "team", "direction": "under", "line": 6}
        ceiling_view = avg - 5          # what the rule measures
        line_view = avg - 6             # what comparing the line would measure
        assert ceiling_view >= bar > line_view, "the fixture no longer separates the two"
        assert server._browse_margin(under6, par(avg)) == ceiling_view

    def test_and_a_rung_looser_says_nothing_in_the_same_division(self):
        # "under 7" is a ceiling of six in a division that does six: a true sentence
        # about the sport rather than about the side.
        assert server._browse_margin(
            {"subject": "team", "direction": "under", "line": 7}, par(6.0)) is None

    def test_a_line_merely_past_the_average_is_not_enough(self):
        # The measured change: "strictly past it" kept over half the card. A quarter of a
        # corner past the division average is the same sentence with rounding.
        assert server._browse_margin(
            {"subject": "team", "direction": "over", "line": 6}, par(5.75)) is None
        assert server._browse_margin(
            {"subject": "team", "direction": "over", "line": 6},
            par(6.0 - server.BROWSE_MIN_MARGIN)) == server.BROWSE_MIN_MARGIN

    def test_a_line_exactly_on_the_average_is_not_past_it(self):
        assert server._browse_margin(
            {"subject": "conceded", "direction": "over", "line": 4}, par(5.0)) is None

    def test_a_league_with_no_history_makes_no_claims(self):
        assert server._browse_margin(
            {"subject": "team", "direction": "over", "line": 9}, {}) is None


class TestTheFilterLooksAtMoreThanATeamsOwnCorners:
    """THE THIRD ATTEMPT, and the reason is a user saying "the streaks and trends only come
    up with a few options, there should be loads". They were right. It walked ONE slice —
    a team's own corners, over, overall — which is a sixth of what the fixture panel shows,
    so the one filter whose job is to find streaks hid most of the site's streaks."""

    def test_an_under_counts(self):
        # A side held to five every week in a division averaging 6.7 is a finding, and the
        # old filter could not see it at all.
        held = team("h", "Held", "l", [5] * 8)
        r = server._browse_streak(held, par(6.7), "overall")
        assert r and r["direction"] == "under" and r["subject"] == "team"

    def test_SO_DOES_A_DEFENCE_BEING_GOT_AT(self):
        # The run belongs to the defence and the bet to their opponent. This is the half
        # that finds a fixture nobody's attacking numbers would have flagged.
        leaky = team("l2", "Leaky", "l", [4] * 8, conceded=[8] * 8)
        # A division that concedes five and whose matches run to a number this side's
        # never reach, so the conceded run is the only thing left to find — the point
        # being that the filter finds it, not that it outranks anything.
        r = server._browse_streak(leaky, par(4.0, match_avg=99.0, conceded_avg=5.0),
                                  "overall")
        assert r and r["subject"] == "conceded" and r["direction"] == "over"

    def test_and_a_match_total(self):
        wild = team("w", "Wild", "l", [7] * 8, conceded=[7] * 8)
        subs = {server._browse_streak(wild, par(5.0, conceded_avg=5.0), "overall")["subject"]}
        assert subs & {"match", "team", "conceded"}

    def test_a_venue_run_is_looked_at_as_well_as_the_overall_one(self):
        # For most of a season only one of them is long enough to mean anything and which
        # one changes — fixture_streaks has the argument in full. A side eight in a row at
        # home whose overall run is three had nothing on the old filter.
        # Nine at home, two away, alternating: six straight at home, nothing overall.
        split = {"team_id": "hv", "name": "Homers", "league_id": "l",
                 "real_matches": [match(9 if i % 2 == 0 else 2, home=(i % 2 == 0), i=i)
                                  for i in range(12)]}
        assert server._browse_streak(split, par(5.0), "overall") is None
        r = server._browse_streak(split, par(5.0), "home")
        assert r and r["venue"] == "home" and r["run"] >= server.PANEL_MIN_RUN

    def test_the_best_run_wins_on_length_then_on_how_unusual_it_is(self):
        # Of two runs the reader is offered the more unusual one, because the row has space
        # for exactly one and it should be the one worth opening the game for.
        big = team("b2", "Big", "l", [9, 9, 9, 9, 9, 9, 9, 9])
        r = server._browse_streak(big, par(5.0), "overall")
        others = [server.live_streak(big, "overall", s, d, min_len=server.PANEL_MIN_RUN)
                  for s in server.BROWSE_SUBJECTS for d in ("over", "under")]
        others = [o for o in others if o and server._browse_margin(o, par(5.0)) is not None]
        assert r["run"] == max(o["run"] for o in others)


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


def test_a_game_carries_both_team_ids(monkeypatch):
    """So a row can offer "follow this club" beside "save this game". They are different
    bookmarks — a fixture star is spent once the game kicks off, following a team is not —
    and the page cannot offer the second without an id."""
    d = browse(monkeypatch)
    for c in d["countries"]:
        for l in c["leagues"]:
            for g in l["games"]:
                assert g["home_team_id"] and g["away_team_id"]
                assert g["home_team_id"] != g["away_team_id"]


class TestTheMinimumRunIsAskable:
    """Five is a run; nine is a story. On a busy weekend the difference between them is
    the difference between a list to read and a list to scan."""

    # ITS OWN DATASET, because the shared one is deliberately rich — Derby is on an
    # eight-game UNDER run, so "raise the bar and only the long one survives" cannot be
    # stated against it without first saying which of four runs is meant. Here a league
    # holds exactly one long run and one short one.
    LONG = team("x-a", "Marathon", "x", [9, 9, 9, 9, 9, 9, 9, 9])
    SHORT = team("x-b", "Sprinter", "x", [2, 2, 2, 3, 9, 9, 9, 9, 9])
    # THE OPPONENTS HAVE TO BE GENUINELY UNREMARKABLE, and "5 every week" is not: in a
    # division averaging 6.7 that is a side held a rung below par every game, which is a
    # qualifying UNDER run eight long — so the first attempt at this dataset had the
    # opponent, not the team, keeping the fixture on the list. Alternating either side of
    # the average leaves no run in either direction.
    PLAIN = team("x-c", "Plain", "x", [4, 8, 4, 8, 4, 8, 4, 8])
    PLAIN2 = team("x-d", "Plainer", "x", [4, 8, 4, 8, 4, 8, 4, 8])
    OWN_LEAGUES = [{"league_id": "x", "name": "Test League", "country": "Testland"}]

    def own(self, monkeypatch, **kw):
        fixtures = [fixture("f-long", "x", "x-a", "x-c"),
                    fixture("f-short", "x", "x-b", "x-d")]
        monkeypatch.setattr(server, "db", FakeDB(
            [self.LONG, self.SHORT, self.PLAIN, self.PLAIN2], fixtures, self.OWN_LEAGUES))
        d = run(server.browse(show="streaks", **kw))
        return {g["fixture_id"] for c in d["countries"] for l in c["leagues"]
                for g in l["games"]}

    def streak_ids(self, monkeypatch, **kw):
        d = browse(monkeypatch, show="streaks", **kw)
        return {g["fixture_id"] for c in d["countries"] for l in c["leagues"]
                for g in l["games"]}

    def test_raising_it_removes_the_shorter_runs(self, monkeypatch):
        # Marathon are eight in a row at a high line; Sprinter's run is five. At five both
        # games are on the list, at eight only the long one can be.
        assert self.own(monkeypatch, min_run=5) == {"f-long", "f-short"}
        assert self.own(monkeypatch, min_run=8) == {"f-long"}

    def test_and_the_list_only_ever_shrinks_as_the_bar_rises(self, monkeypatch):
        sizes = [len(self.own(monkeypatch, min_run=n)) for n in (5, 6, 7, 8, 9, 10)]
        assert sizes == sorted(sizes, reverse=True), sizes

    def test_asking_for_more_than_anybody_has_empties_it_honestly(self, monkeypatch):
        d = browse(monkeypatch, show="streaks", min_run=10)
        assert d["total"] == 0 and d["countries"] == []

    def test_it_never_goes_below_the_panels_bar(self, monkeypatch):
        # Below five a "run" is three games, which is what a side does by accident. The
        # whole reason this board is stricter than the fixture panel is that the panel
        # describes a game you chose and this one chooses the game for you.
        assert (self.streak_ids(monkeypatch, min_run=1)
                == self.streak_ids(monkeypatch, min_run=server.PANEL_MIN_RUN))

    def test_nor_above_the_ceiling(self, monkeypatch):
        # Past the ceiling an empty page looks exactly like a broken one.
        assert (self.streak_ids(monkeypatch, min_run=99)
                == self.streak_ids(monkeypatch, min_run=server.BROWSE_MAX_MIN_RUN))

    def test_the_run_it_reports_clears_the_bar_it_was_asked_for(self, monkeypatch):
        d = browse(monkeypatch, show="streaks", min_run=7)
        for c in d["countries"]:
            for l in c["leagues"]:
                for g in l["games"]:
                    assert g["streak"]["run"] >= 7

    def test_counts_still_match_what_opening_it_shows(self, monkeypatch):
        d = browse(monkeypatch, show="streaks", min_run=8)
        for c in d["countries"]:
            assert c["count"] == sum(l["count"] for l in c["leagues"])
            for l in c["leagues"]:
                assert l["count"] == len(l["games"])
        assert d["total"] == sum(c["count"] for c in d["countries"])

    def test_it_does_nothing_to_the_unfiltered_list(self, monkeypatch):
        # `all` is not about runs, so raising the bar must not remove games from it.
        assert browse(monkeypatch, show="all", min_run=10)["total"] == 3


class TestTheFilterLooksAtEveryLineNotJustTheHeadlineOne:
    """THE FOURTH THING WRONG WITH THIS FILTER, and the one that cost it most rows.

    live_streak ranks candidates by run LENGTH first, which is right for a panel
    describing a game you have already chosen — the longest story is the headline. Here
    it was fatal: the long story is usually at a trivial line, _browse_margin correctly
    rejects a trivial line, and the short run at the big line was never looked at.
    """

    # Last nine: a lean spell, then five straight at nine corners.
    TURNED = team("tn-a", "Turned", "tn", [2, 2, 2, 3, 9, 9, 9, 9, 9])
    OTHERS = [team(f"tn-{c}", f"Mid{c}", "tn", [4, 8, 4, 8, 4, 8, 4, 8])
              for c in "bcd"]
    LEAGUES = [{"league_id": "tn", "name": "Turn League", "country": "Turnland"}]

    def par(self):
        pool = {s: [] for s in server.BROWSE_SUBJECTS}
        for t in [self.TURNED] + self.OTHERS:
            for m in server._src(t):
                for s in pool:
                    pool[s].append(server.streak_value(m, s))
        return {k: sum(v) / len(v) for k, v in pool.items()}

    def test_the_headline_run_is_the_long_trivial_one(self):
        # What live_streak hands back, and why it is useless to this filter: 3+ in a
        # division that averages nearly seven is a description of the sport.
        head = server.live_streak(self.TURNED, "overall", "team", "over", min_len=5)
        assert head["line"] == 3 and head["run"] == 6
        assert server._browse_margin(head, self.par()) is None

    def test_but_the_short_remarkable_one_is_in_the_candidates(self):
        cands = server.live_streak_candidates(self.TURNED, "overall", "team", "over",
                                              min_len=5)
        nine = next(c for c in cands if c["line"] == 9)
        assert nine["run"] == 5
        assert server._browse_margin(nine, self.par()) > 0

    def test_and_the_filter_finds_it(self):
        r = server._browse_streak(self.TURNED, self.par(), "overall")
        assert r and r["line"] == 9 and r["run"] == 5, \
            "the side's only interesting run must not be hidden by its dullest one"

    def test_live_streak_still_returns_the_headline_for_everybody_else(self):
        # The panel's behaviour is unchanged; only this filter reads the candidates.
        head = server.live_streak(self.TURNED, "overall", "team", "over", min_len=5)
        assert head == max(
            server.live_streak_candidates(self.TURNED, "overall", "team", "over",
                                          min_len=5),
            key=server.streak_rank)

    def test_candidates_are_empty_rather_than_None_when_there_is_no_history(self):
        # It is iterated directly by _browse_streak, so None here is a TypeError in
        # production for every team with fewer games than the bar — which it was.
        assert server.live_streak_candidates(
            team("e", "Empty", "l", [5]), "overall", "team", "over", min_len=5) == []


class TestAGameCarriesItsOwnEvidence:
    """A row that says "+3 more" has told the reader something exists and given them no
    way to look at it short of loading the whole fixture page — which is the trip the
    preview is meant to save. The runs were already computed and thrown away."""

    def rows(self, monkeypatch, **kw):
        d = browse(monkeypatch, **kw)
        return [g for c in d["countries"] for l in c["leagues"] for g in l["games"]]

    def test_every_game_carries_a_streak_list(self, monkeypatch):
        for g in self.rows(monkeypatch):
            assert isinstance(g["streaks"], list)

    def test_the_list_holds_the_runs_the_count_promised(self, monkeypatch):
        # "+2 more" with one run behind it is worse than no number at all.
        for g in self.rows(monkeypatch):
            assert len(g["streaks"]) == min(g["streak_count"], server.BROWSE_PREVIEW_RUNS)

    def test_the_headline_run_is_the_first_of_them(self, monkeypatch):
        # The panel must not open to find a different best row than the one on the row.
        for g in self.rows(monkeypatch, show="streaks"):
            assert g["streaks"][0]["run"] == g["streak"]["run"]
            assert g["streaks"][0]["team"] == g["streak"]["team"]
            assert g["streaks"][0]["line"] == g["streak"]["line"]

    def test_they_are_ordered_best_first(self, monkeypatch):
        for g in self.rows(monkeypatch, show="streaks"):
            keys = [(r["run"], r.get("margin") or 0) for r in g["streaks"]]
            assert keys == sorted(keys, reverse=True)

    def test_each_one_says_whose_it_is_and_which_games(self, monkeypatch):
        # A run with no venue reads as home form when it is overall form — the mistake
        # that reached published posts before the panel started labelling.
        for g in self.rows(monkeypatch, show="streaks"):
            for r in g["streaks"]:
                assert r["team"] in (g["home"], g["away"])
                assert r["venue"] in ("home", "away", "overall")
                assert r["line_label"] and r["subject"] and r["direction"]

    def test_a_game_with_no_run_carries_an_empty_list_not_a_missing_key(self, monkeypatch):
        g = next(x for x in self.rows(monkeypatch) if x["fixture_id"] == "f-no")
        assert g["streaks"] == [] and g["streak"] is None

    def test_the_list_is_capped(self, monkeypatch):
        for g in self.rows(monkeypatch):
            assert len(g["streaks"]) <= server.BROWSE_PREVIEW_RUNS
