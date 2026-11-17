"""What the calendar is willing to call one of YOUR games.

THE BUG THIS IS ABOUT. The site has two stars and does not say so anywhere. StarButton
saves a FIXTURE into db.favourites; TeamStar follows a TEAM into favourite_teams. The
calendar read only the second, so somebody who had saved thirty games and followed no
teams got an empty grid — and a note telling them, truthfully and uselessly, that they
followed nobody. They had said exactly which games they cared about and the page ignored
every one of them.

So the tests that matter here are about the JOIN, not the drawing: which fixtures end up
on a square, under which list, and — the one that silently corrupts every total under the
grid — that a game cannot land on it twice.

server imports cryptography, which is absent in this container, so the endpoint is
exercised through a slice of its source: the technique test_stat_picks and
test_fetch_ahead use.
"""
import asyncio
import os
import sys
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

TODAY = date(2026, 11, 17)


def _sliced():
    with open(os.path.join(HERE, "server.py")) as fh:
        src = fh.read()
    # From _month_bounds, not from local_day: the endpoint calls it, and a slice that
    # starts below it compiles cleanly and then fails at run time with a NameError.
    start = src.index("def _month_bounds(")
    end = src.index('@api_router.get("/my-teams")')
    body = src[start:end]
    # The decorator and the Depends() signature need FastAPI; the function body does not.
    body = body.replace('@api_router.get("/calendar")\n', "")
    body = body.replace("async def calendar(month: Optional[str] = None, source: str = \"all\",\n"
                        "                   league_id: Optional[str] = None,\n"
                        "                   user: dict = Depends(require_user)):",
                        "async def calendar(db, user, month=None, source='all', league_id=None):")

    class HTTPException(Exception):
        def __init__(self, status_code=400, detail=""):
            self.status_code, self.detail = status_code, detail

    from typing import Dict, Optional
    ns = {
        "Optional": Optional, "Dict": Dict, "timedelta": timedelta, "date": date,
        "datetime": datetime, "timezone": timezone, "ZoneInfo": ZoneInfo,
        "HTTPException": HTTPException,
        "CALENDAR_TZ": ZoneInfo("Europe/London"),
        "CALENDAR_HORIZON_MIN": 3, "CALENDAR_MONTHS_BACK": 2, "CALENDAR_MONTHS_AHEAD": 3,
        "CALENDAR_PLAYING_MAX": 300,
    }
    exec(compile(body, "sliced", "exec"), ns)
    return ns["calendar"]


calendar = _sliced()


def fx(fid, day, home, away, league="bra-sb"):
    return {"fixture_id": fid, "league_id": league,
            "date": datetime(2026, 11, day, 20, 0, tzinfo=timezone.utc).isoformat(),
            "home_team_id": home, "away_team_id": away,
            "home_name": home.split("-")[-1], "away_name": away.split("-")[-1],
            "round": "Round 38"}


class Coll:
    def __init__(self, rows):
        self.rows = rows

    @staticmethod
    def _matches(row, key, cond):
        # $in as well as equality: the teams lookup asks with {"team_id": {"$in": [...]}},
        # and a fake that only understood equality returned nothing — which looked exactly
        # like the endpoint failing to name a followed side.
        if isinstance(cond, dict) and "$in" in cond:
            return row.get(key) in cond["$in"]
        return row.get(key) == cond

    def find(self, q=None, _proj=None):
        rows = [r for r in self.rows
                if all(self._matches(r, k, v) for k, v in (q or {}).items())]
        class C:
            async def to_list(self, _n):
                return list(rows)
        return C()


class DB:
    def __init__(self, fixtures=(), fav_teams=(), trk_teams=(), saved=()):
        self.fixtures = Coll(list(fixtures))
        self.favourite_teams = Coll([{"user_id": "u1", "team_id": t} for t in fav_teams])
        self.tracked_teams = Coll([{"user_id": "u1", "team_id": t} for t in trk_teams])
        self.favourites = Coll([{"user_id": "u1", "fixture_id": f} for f in saved])
        self.teams = Coll([{"team_id": "bra-sb-vila", "name": "Vila Nova",
                            "league_id": "bra-sb"},
                           {"team_id": "bra-sb-forta", "name": "Fortaleza",
                            "league_id": "bra-sb"}])
        self.leagues = Coll([{"league_id": "bra-sb", "name": "Série B"}])


def call(db, **kw):
    kw.setdefault("month", "2026-11")
    return asyncio.run(calendar(db, {"user_id": "u1"}, **kw))


def mine_of(res):
    return [m for d in res["days"] for m in d["mine"]]


# --- the join ------------------------------------------------------------------------

def test_a_saved_game_is_one_of_yours_even_with_neither_side_followed():
    # THE REPORTED BUG, in one case. Nothing followed, one game saved: the calendar used
    # to show an empty month.
    db = DB(fixtures=[fx("bra-sb-1", 21, "bra-sb-vila", "bra-sb-forta")],
            saved=["bra-sb-1"])
    got = mine_of(call(db))
    assert [m["list"] for m in got] == ["saved"]
    assert got[0]["home_name"] == "vila" and got[0]["away_name"] == "forta"


def test_a_followed_team_still_lands_under_its_own_list():
    db = DB(fixtures=[fx("bra-sb-1", 21, "bra-sb-vila", "bra-sb-forta")],
            fav_teams=["bra-sb-vila"])
    got = mine_of(call(db))
    assert [(m["list"], m["team"], m["side"]) for m in got] == [("favourites", "Vila Nova", "home")]


def test_a_saved_game_whose_team_you_also_follow_is_counted_once():
    # THE ONE THAT CORRUPTS THE TOTALS. Both stars pointing at the same game must not
    # make the line under the grid read two.
    db = DB(fixtures=[fx("bra-sb-1", 21, "bra-sb-vila", "bra-sb-forta")],
            fav_teams=["bra-sb-vila"], saved=["bra-sb-1"])
    got = mine_of(call(db))
    assert len(got) == 1, got
    assert got[0]["list"] == "favourites"


def test_two_followed_teams_playing_each_other_still_say_so_twice():
    # The existing rule, which the saved-game branch must not have broken: that square
    # reads from both points of view.
    db = DB(fixtures=[fx("bra-sb-1", 21, "bra-sb-vila", "bra-sb-forta")],
            fav_teams=["bra-sb-vila", "bra-sb-forta"], saved=["bra-sb-1"])
    got = mine_of(call(db))
    assert sorted(m["side"] for m in got) == ["away", "home"]


def test_the_counts_match_what_the_squares_hold():
    db = DB(fixtures=[fx("bra-sb-1", 21, "bra-sb-vila", "bra-sb-forta"),
                      fx("bra-sb-2", 22, "bra-sb-forta", "bra-sb-vila")],
            fav_teams=["bra-sb-vila"], saved=["bra-sb-2"])
    res = call(db)
    assert res["counts"]["mine"] == len(mine_of(res)) == 2
    assert res["counts"]["saved"] == 1


# --- the source filter -----------------------------------------------------------------

def test_saved_alone_drops_the_followed_teams():
    db = DB(fixtures=[fx("bra-sb-1", 21, "bra-sb-vila", "bra-sb-forta"),
                      fx("bra-sb-2", 22, "bra-sb-forta", "bra-sb-vila")],
            fav_teams=["bra-sb-vila"], saved=["bra-sb-2"])
    got = mine_of(call(db, source="saved"))
    assert [(m["list"], m["fixture_id"]) for m in got] == [("saved", "bra-sb-2")]


def test_a_team_list_drops_the_saved_games():
    # Asking for favourites means the team list, not "everything I ever starred".
    db = DB(fixtures=[fx("bra-sb-1", 21, "bra-sb-vila", "bra-sb-forta"),
                      fx("bra-sb-2", 22, "bra-sb-forta", "bra-sb-vila")],
            fav_teams=["bra-sb-vila"], saved=["bra-sb-2"])
    got = mine_of(call(db, source="favourites"))
    assert all(m["list"] == "favourites" for m in got)
    assert {m["fixture_id"] for m in got} == {"bra-sb-1", "bra-sb-2"}


def test_an_unknown_source_falls_back_to_all_rather_than_erroring():
    db = DB(fixtures=[fx("bra-sb-1", 21, "bra-sb-vila", "bra-sb-forta")],
            saved=["bra-sb-1"])
    assert call(db, source="nonsense")["source"] == "all"


# --- the teams the page can offer -------------------------------------------------------

def test_it_offers_the_sides_playing_that_you_do_not_already_follow():
    # The dead end this removes: an empty calendar whose only advice was to go and find a
    # star somewhere else on the site.
    db = DB(fixtures=[fx("bra-sb-1", 21, "bra-sb-vila", "bra-sb-forta")])
    names = {t["team_id"] for t in call(db)["playing"]}
    assert names == {"bra-sb-vila", "bra-sb-forta"}


def test_a_side_you_already_follow_is_not_offered_again():
    db = DB(fixtures=[fx("bra-sb-1", 21, "bra-sb-vila", "bra-sb-forta")],
            fav_teams=["bra-sb-vila"])
    assert [t["team_id"] for t in call(db)["playing"]] == ["bra-sb-forta"]


def test_the_busiest_sides_come_first():
    db = DB(fixtures=[fx("bra-sb-1", 21, "bra-sb-vila", "bra-sb-forta"),
                      fx("bra-sb-2", 24, "bra-sb-vila", "bra-sb-other")])
    out = call(db)["playing"]
    assert out[0]["team_id"] == "bra-sb-vila" and out[0]["games"] == 2


def test_a_fixture_outside_the_month_offers_nobody():
    db = DB(fixtures=[{**fx("bra-sb-1", 21, "bra-sb-vila", "bra-sb-forta"),
                       "date": datetime(2026, 12, 21, 20, 0, tzinfo=timezone.utc).isoformat()}])
    res = call(db)
    assert res["playing"] == []
    assert res["counts"]["fixtures"] == 0
