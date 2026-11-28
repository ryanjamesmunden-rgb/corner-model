"""The streak board is what takes the site down, and this is the proof for the two fixes.

MEASURED AGAINST PRODUCTION. One `/api/streaks` request with a non-default filter dropped
connections outright and left every endpoint on the site answering 502 for several
minutes, recovering on its own once the request finished. The cache answers only when all
eleven parameters are at their defaults, so every filter the Streaks page offers misses
it — and so does `_combined_rows`, which runs the streak walk THREE times with
`min_hits=4` and is called on every single week-card load.

Two changes, both pinned here:

  1. The query stops pulling `matches`. A team document holds three match arrays built
     from one set of games — forty, the last twenty of those, and a copy of the twenty —
     so two thirds of it is duplicate, and this path reads only two of the three. The
     test below drives the REAL handler with the field present and absent and asserts the
     boards are byte-identical, so "nothing reads it" is checked rather than claimed.

  2. `_combined_rows` memoises. Two page loads a second apart both used to run the whole
     thing.
"""
import asyncio
import copy
import json
import os
import sys
from datetime import datetime, timedelta, timezone

import pytest

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "test_corner_model")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import server  # noqa: E402

NOW = datetime.now(timezone.utc)


def iso(days_ago):
    return (NOW - timedelta(days=days_ago)).isoformat().replace("+00:00", "Z")


def match(i, home, won, conceded):
    """One stored game, with the shot features the lambda reads."""
    return {"date": iso(60 - i * 3), "opponent": f"Opp {i}", "home": home,
            "season": 2026, "corners_for": won, "corners_against": conceded,
            "goals_for": 1, "goals_against": 0,
            "fh_goals_for": 1, "fh_goals_against": 0,
            "shots_for": 12, "shots_against": 9,
            "shots_on_target_for": 5, "shots_on_target_against": 3,
            "blocked_shots_for": 3, "blocked_shots_against": 2,
            "dangerous_attacks_for": 40, "dangerous_attacks_against": 31,
            # The bulky fields a results view wants and a streak board does not.
            "scorers": [{"player": f"Player {i}", "minute": 23}],
            "minutes_trailing": 0, "first_goal_min": 23, "opp_first_goal_min": None,
            "scored_first": True}


def team(tid, won_pattern):
    """A team whose document carries all three match arrays, as the sync writes them."""
    history = [match(i, i % 2 == 0, w, 4) for i, w in enumerate(won_pattern)]
    real = history[-20:]
    return {"team_id": tid, "api_team_id": int(tid.split("-")[-1]), "league_id": "eng-l1",
            "name": f"Team {tid}", "history_matches": history, "history_samples": len(history),
            "real_matches": real, "real_samples": len(real),
            # The duplicate. Identical to `real_matches`, which is what the sync stores
            # for any side with five or more real games.
            "matches": copy.deepcopy(real),
            "new_to_league": False}


TEAMS = [team("eng-l1-1", [7, 6, 8, 5, 9, 7, 6, 8, 7, 6] * 2),
         team("eng-l1-2", [4, 5, 3, 6, 4, 5, 4, 3, 5, 4] * 2)]

FIXTURES = [{"fixture_id": "fx1", "league_id": "eng-l1",
             "date": (NOW + timedelta(days=2)).isoformat().replace("+00:00", "Z"),
             "home_team_id": "eng-l1-1", "away_team_id": "eng-l1-2",
             "home_name": "Team eng-l1-1", "away_name": "Team eng-l1-2",
             "status": "upcoming", "round": "R18"}]

LEAGUES = [{"league_id": "eng-l1", "name": "League One", "avg_shots": 11.0,
            "avg_blocked": 3.0, "season": 2026}]


class FakeCursor:
    def __init__(self, docs):
        self._docs = docs

    def sort(self, field, direction=1):
        present = [d for d in self._docs if d.get(field) is not None]
        missing = [d for d in self._docs if d.get(field) is None]
        present.sort(key=lambda d: d[field], reverse=direction < 0)
        self._docs = present + missing if direction < 0 else missing + present
        return self

    def limit(self, n):
        self._docs = self._docs[:n]
        return self

    async def to_list(self, n):
        return self._docs[:n]


class FakeCollection:
    """Honours an EXCLUSION projection, which is the whole point of this file.

    A double that ignored `{"matches": 0}` would hand the handler the field anyway and
    the test would pass whether or not anything read it — asserting nothing.
    """
    def __init__(self, docs, key="fixture_id"):
        self._docs, self._key = docs, key
        self.projections = []
        # The QUERY as well, because "did this scan the whole collection" is a question
        # about the filter, not the projection: the opponent lookup inside perfect_games
        # asks for a list of ids under the same `{"_id": 0}` projection as a full scan.
        self.calls = []

    def find(self, q=None, proj=None):
        self.projections.append(dict(proj or {}))
        self.calls.append((dict(q or {}), dict(proj or {})))
        docs = [copy.deepcopy(d) for d in self._docs]
        lid = (q or {}).get("league_id") if q else None
        if isinstance(lid, str):
            docs = [d for d in docs if d.get("league_id") == lid]
        ids = ((q or {}).get(self._key) or {}).get("$in") if q else None
        if ids is not None:
            docs = [d for d in docs if d.get(self._key) in ids]
        drop = [k for k, v in (proj or {}).items() if v == 0 and k != "_id"]
        keep = [k for k, v in (proj or {}).items() if v == 1 and k != "_id"]
        for d in docs:
            for k in drop:
                d.pop(k, None)
            if keep:
                for k in list(d):
                    if k not in keep:
                        d.pop(k, None)
        return FakeCursor(docs)


class FakeDB:
    def __init__(self, teams):
        self.teams = FakeCollection(teams, "team_id")
        self.fixtures = FakeCollection(FIXTURES)
        self.fixtures_played = FakeCollection([])
        self.leagues = FakeCollection(LEAGUES, "league_id")
        self.odds = FakeCollection([])
        self.odds_feed = FakeCollection([])
        self.screens = FakeCollection([], "_id")


def run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def board(monkeypatch, teams, **kw):
    """The REAL handler, on a filter that misses the screen cache."""
    monkeypatch.setattr(server, "db", FakeDB(teams))
    monkeypatch.setattr(server, "_cache_ok", lambda: False)
    params = {"league_id": "eng-l1", "side": "home", "window": 5, "min_hits": 4,
              "min_line": 3, "direction": "over", "subject": "team",
              "user": {"user_id": "u1", "member": True}}
    params.update(kw)
    return run(server.streaks(**params))


# --- the projection ------------------------------------------------------------------

def test_the_board_is_identical_with_and_without_the_duplicate_array(monkeypatch):
    """THE WHOLE POINT. Drive the real handler against documents that carry `matches` and
    against documents that do not, and compare the output. If anything on this path ever
    starts reading it, this fails rather than the board quietly going wrong."""
    with_it = board(monkeypatch, copy.deepcopy(TEAMS))
    without = board(monkeypatch, [{k: v for k, v in t.items() if k != "matches"}
                                  for t in copy.deepcopy(TEAMS)])
    assert json.dumps(with_it, sort_keys=True) == json.dumps(without, sort_keys=True)
    assert with_it, "the fixture produced no rows, so this compared two empty lists"


def test_the_query_actually_asks_mongo_to_leave_it_out(monkeypatch):
    """The test above would also pass if the handler fetched the field and ignored it —
    which costs exactly the bytes this is meant to save."""
    fake = FakeDB(copy.deepcopy(TEAMS))
    monkeypatch.setattr(server, "db", fake)
    monkeypatch.setattr(server, "_cache_ok", lambda: False)
    run(server.streaks(league_id="eng-l1", side="home", window=5, min_hits=4,
                       user={"user_id": "u1", "member": True}))
    assert any(p.get("matches") == 0 for p in fake.teams.projections), \
        "the streak query no longer excludes the duplicate match array"


def test_a_side_with_no_real_games_still_does_not_need_it(monkeypatch):
    """`matches` exists so a sparse team has something to model from, and _src falls back
    to it. This path never calls _src — so a team with nothing in `real_matches` must
    simply produce no row, not reach for the synthetic copy."""
    thin = copy.deepcopy(TEAMS[0])
    thin["real_matches"], thin["real_samples"] = [], 0
    rows = board(monkeypatch, [thin, copy.deepcopy(TEAMS[1])])
    assert all(r["team_id"] != thin["team_id"] or r.get("projection") is None
               for r in rows)


# --- the memo ------------------------------------------------------------------------

def test_the_combined_board_is_computed_once_for_a_burst_of_requests(monkeypatch):
    """Three week-card loads ran the streak walk nine times — three boards, three venues
    each — on the event loop of a single worker. That is the outage."""
    calls = []

    async def fake_uncached(within_days, min_samples, min_opp_games, min_boards, user):
        calls.append(within_days)
        return [{"team_id": "t1", "within": within_days}]

    monkeypatch.setattr(server, "_combined_rows_uncached", fake_uncached)
    server._combined_cache.clear()
    server._combined_locks.clear()
    out = [run(server._combined_rows(within_days=3, min_boards=1)) for _ in range(3)]
    assert len(calls) == 1
    assert all(o == out[0] for o in out)


def test_different_parameters_are_different_answers(monkeypatch):
    """A day in the future and a day next week are not the same board, and a cache that
    confused them would be worse than no cache."""
    calls = []

    async def fake_uncached(within_days, min_samples, min_opp_games, min_boards, user):
        calls.append((within_days, min_boards))
        return [{"within": within_days, "boards": min_boards}]

    monkeypatch.setattr(server, "_combined_rows_uncached", fake_uncached)
    server._combined_cache.clear()
    server._combined_locks.clear()
    a = run(server._combined_rows(within_days=3, min_boards=1))
    b = run(server._combined_rows(within_days=8, min_boards=1))
    c = run(server._combined_rows(within_days=3, min_boards=2))
    assert len(calls) == 3
    assert a != b and a != c


def test_it_goes_stale_rather_than_standing_for_ever(monkeypatch):
    """A hand-typed price has to reach the board while somebody is still looking for it."""
    calls = []

    async def fake_uncached(within_days, min_samples, min_opp_games, min_boards, user):
        calls.append(within_days)
        return [{"n": len(calls)}]

    monkeypatch.setattr(server, "_combined_rows_uncached", fake_uncached)
    server._combined_cache.clear()
    server._combined_locks.clear()
    run(server._combined_rows(within_days=3))
    # Age the entry past the window rather than sleeping through it.
    key = (3, server.combined.DEFAULT_MIN_SAMPLES, server.combined.DEFAULT_MIN_OPP_GAMES, 2)
    built, rows = server._combined_cache[key]
    server._combined_cache[key] = (built - server.COMBINED_TTL_SECONDS - 1, rows)
    run(server._combined_rows(within_days=3))
    assert len(calls) == 2


def test_the_window_is_minutes_not_hours():
    """Long enough to collapse a browsing session, short enough that a price typed in
    now is on the board before the person who typed it has given up."""
    assert 60 <= server.COMBINED_TTL_SECONDS <= 900


def test_who_asked_is_not_part_of_the_key(monkeypatch):
    """Every board this gathers is fetched with no `response`, and _preview returns rows
    untouched when there is none — so the answer cannot depend on the caller, and keying
    on them would multiply the one computation that must not run twice."""
    calls = []

    async def fake_uncached(within_days, min_samples, min_opp_games, min_boards, user):
        calls.append(user)
        return []

    monkeypatch.setattr(server, "_combined_rows_uncached", fake_uncached)
    server._combined_cache.clear()
    server._combined_locks.clear()
    run(server._combined_rows(within_days=3, user={"member": True}))
    run(server._combined_rows(within_days=3, user={"member": False}))
    assert len(calls) == 1


@pytest.fixture(autouse=True)
def _clean_cache():
    yield
    server._combined_cache.clear()
    server._combined_locks.clear()


# --- a stale screen must never be rebuilt on the request path ------------------------
#
# The combined screen's build IS _combined_rows. Once it fails the screen stays stale, so
# the next visitor runs the same doomed rebuild — the outage feeds itself. Measured
# against production: 300 seconds, dropped connection, every endpoint down with it.

class FakeScreens:
    def __init__(self, docs):
        self._docs = {d["_id"]: d for d in docs}

    async def find_one(self, q):
        return self._docs.get(q["_id"])


def _screen_db(monkeypatch, docs):
    class DB:
        screens = FakeScreens(docs)
    monkeypatch.setattr(server, "db", DB())


def test_a_stale_screen_is_served_at_once_rather_than_rebuilt(monkeypatch):
    built = []

    async def never(name):
        built.append(name)
        raise AssertionError("the request path rebuilt a stale screen")

    _screen_db(monkeypatch, [{"_id": "combined", "payload": [{"team": "old"}]}])
    monkeypatch.setattr(server, "_screen_is_stale", lambda doc: _true())
    monkeypatch.setattr(server, "_build_screen", never)
    monkeypatch.setattr(server, "_refresh_screen_later", lambda name: built.append(name))
    assert run(server._screen("combined")) == [{"team": "old"}]
    assert built == ["combined"], "no background refresh was scheduled"


def test_a_fresh_screen_is_not_refreshed_at_all(monkeypatch):
    scheduled = []
    _screen_db(monkeypatch, [{"_id": "combined", "payload": [{"team": "new"}]}])
    monkeypatch.setattr(server, "_screen_is_stale", lambda doc: _false())
    monkeypatch.setattr(server, "_refresh_screen_later", lambda n: scheduled.append(n))
    assert run(server._screen("combined")) == [{"team": "new"}]
    assert scheduled == []


def test_only_a_screen_that_has_never_been_built_blocks(monkeypatch):
    # There is nothing else to send, so this one has to wait.
    async def build(name):
        return {"payload": [{"team": "first"}]}

    _screen_db(monkeypatch, [])
    monkeypatch.setattr(server, "_build_screen", build)
    server._screen_locks.clear()
    assert run(server._screen("combined")) == [{"team": "first"}]


def test_a_burst_of_visitors_starts_one_refresh_not_fifty(monkeypatch):
    server._refreshing.clear()
    starts = []

    async def build(name):
        starts.append(name)
        return {"payload": []}

    monkeypatch.setattr(server, "_build_screen", build)

    async def main():
        for _ in range(50):
            server._refresh_screen_later("combined")
        # Let the one scheduled task run.
        await asyncio.sleep(0)
        await asyncio.sleep(0)

    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(main())
    finally:
        loop.close()
    assert len(starts) <= 1
    server._refreshing.clear()


def test_a_failing_background_rebuild_leaves_the_stale_copy_alone(monkeypatch):
    # Nobody is waiting on it: the request was already answered from the stale copy, and
    # a build that dies must not take anything down with it.
    server._refreshing.clear()

    async def boom(name):
        raise RuntimeError("out of memory")

    monkeypatch.setattr(server, "_build_screen", boom)

    async def main():
        server._refresh_screen_later("combined")
        await asyncio.sleep(0)
        await asyncio.sleep(0)

    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(main())      # must not raise
    finally:
        loop.close()
    assert "combined" not in server._refreshing, "a failed build left the flag stuck"


def test_every_day_of_the_card_shares_one_board():
    """Thursday's card and Friday's card were two different `within_days`, so two
    different runs of the computation that takes the site down. The rows are filtered to
    the day asked for regardless, so one wide board serves every day."""
    import inspect
    src = inspect.getsource(server.week_card_board)
    assert "within_days=WEEK_CARD_MAX_AHEAD + 1" in src
    assert "within_days=max(1, ahead + 1)" not in src


async def _true():
    return True


async def _false():
    return False


# --- every board graded in the same currency ------------------------------------------
#
# Streaks, Quick Scan and Perfect Games froze `prob` and `fair_odds` — the model's own
# opinion — so their record could say the LINE LANDED and never that the BET WON. Two
# boards with the same hit rate and different prices are one row in that record and
# opposite outcomes in a bank, and the price a book offered on a Tuesday cannot be
# recovered once the market has moved. Value Finder and Combined already froze it, which
# is the only reason they report units.

def test_the_frozen_price_is_named_what_the_grader_reads():
    """`_tally` turns a settled row into units off `r.get("price")`. Under any other name
    the number is stored and silently ignored, which is where this started."""
    got = server._frozen_price({"projection": {"market_key": "home_over_4.5",
                                               "book_odds": 1.85, "book_name": "Bet365",
                                               "ev": 12.4}})
    assert got["price"] == 1.85
    assert got["market_key"] == "home_over_4.5"
    assert got["book_name"] == "Bet365" and got["ev_at_freeze"] == 12.4


def test_it_reads_whichever_shape_the_board_hands_over():
    # Streaks and Perfect Games carry `projection`; the value-shaped rows carry `best`.
    assert server._frozen_price({"best": {"book_odds": 2.1}})["price"] == 2.1


def test_an_unquoted_claim_freezes_a_null_and_never_the_fair_price():
    # "No book had priced this when we called it" is a fact about the claim and belongs
    # in the record. Substituting the model's number would turn an unbackable row into a
    # settled winner.
    got = server._frozen_price({"projection": {"fair_odds": 1.6, "book_odds": None}})
    assert got["price"] is None
    assert "fair_odds" not in got


def test_nothing_at_all_still_gives_the_four_keys():
    # Spread into an entry with **, so a missing shape must not drop the columns and
    # leave half the snapshot with a different schema from the other half.
    got = server._frozen_price({})
    assert set(got) == {"market_key", "price", "book_name", "ev_at_freeze"}
    assert all(v is None for v in got.values())
    assert server._frozen_price(None)["price"] is None


def test_a_priced_row_now_settles_into_units():
    """End to end through the real tally: a frozen price is what turns a win into a bank
    movement. Without it the row counts as settled-but-unpriced and the units stay nil."""
    entry = {"team_id": "t1", "line": 5, "direction": "over", "subject": "team",
             **server._frozen_price({"projection": {"book_odds": 1.85}})}
    won = server._tally([{**entry, "result": "win"}])
    assert won["units"] > 0 and won["priced"] == 1 and won["unpriced"] == 0
    bare = server._tally([{"result": "win", "line": 5}])
    assert bare["unpriced"] == 1


def test_all_three_boards_freeze_it():
    """The point of the change, asserted on the source: a board that stops calling this
    goes back to a record that cannot be read in units, and nothing else would notice."""
    import re
    src = open(server.__file__.replace(".pyc", ".py")).read()
    for coll in ("streak_snapshots", "mismatch_snapshots", "perfect_snapshots"):
        i = src.index(f"db.{coll}.insert_one")
        assert "_frozen_price(r)" in src[max(0, i - 3000):i], \
            f"{coll} no longer freezes the bookmaker's price"


# --- the page that says whether a board is worth following -----------------------------
#
# /api/results/boards answered 502. It fetched every team document — all three match
# arrays — once PER BOARD, on a page whose whole job is to compare the boards and which
# therefore always asks for all of them.

def test_the_team_fetch_asks_for_the_games_and_nothing_else(monkeypatch):
    seen = {}

    class Teams:
        def find(self, q, proj):
            seen["proj"] = proj
            seen["ids"] = sorted(q["team_id"]["$in"])
            class C:
                async def to_list(self, n):
                    return [{"team_id": "t1", "real_matches": []}]
            return C()

    class DB:
        teams = Teams()
    monkeypatch.setattr(server, "db", DB())
    run(server._teams_for([{"team_id": "t1"}, {"team_id": "t1"}]))
    assert seen["proj"].get("real_matches") == 1
    # The two the settlement never reads. Two thirds of the document.
    assert "history_matches" not in seen["proj"]
    assert "matches" not in seen["proj"]
    assert seen["ids"] == ["t1"], "the same side was asked for twice"


def test_an_entry_with_no_team_does_not_break_the_fetch(monkeypatch):
    # Snapshots predate several fields; one malformed row must not take the page down.
    class DB:
        class teams:
            @staticmethod
            def find(q, proj):
                raise AssertionError("asked the database for nothing")
    monkeypatch.setattr(server, "db", DB())
    assert run(server._teams_for([{"line": 5}, {}])) == {}


def test_the_teams_are_fetched_once_for_every_board():
    """Read off the source: the fetch must sit OUTSIDE the per-board loop. Inside it, the
    same sides are loaded once per board and the page times out again."""
    import inspect
    src = inspect.getsource(server.results_by_board)
    body = src[src.index("per_board = []"):]
    loop = body.index("for key, label, blurb, entries in per_board")
    assert "_teams_for" in body[:loop], "the team fetch fell back inside the loop"
    assert body.count("_teams_for") == 1


def test_value_finder_is_on_the_page_now():
    """Frozen nightly since it was built and shown nowhere — the one board that can
    always report a bank was missing from the page that compares banks."""
    keys = [b[0] for b in server.RESULT_BOARDS]
    assert keys == ["streaks", "perfect", "mismatch", "combined", "value"]
    blurb = dict((b[0], b[3]) for b in server.RESULT_BOARDS)["value"]
    # Its denominator is not comparable either, and for its own reason.
    assert "price" in blurb


def test_every_listed_board_has_a_collection_the_server_writes():
    """A board on this page whose snapshots nobody writes shows an empty record as though
    it were a bad one."""
    import inspect
    src = inspect.getsource(server)
    for key, label, coll, _ in server.RESULT_BOARDS:
        assert f"db.{coll}.insert_one" in src or f"db.{coll}.insert_many" in src, \
            f"{label} is listed but nothing writes {coll}"


def test_the_value_board_decides_the_window_before_it_builds_a_model():
    """A board asked for ONE day used to build a full model for every priced fixture in
    the whole horizon and then throw most away — on the event loop of a single worker,
    on the endpoint the week card calls on every load.

    Read off the source, because the cost is in the ORDER and a reordering is exactly the
    kind of thing a later edit undoes without any test noticing."""
    import inspect
    src = inspect.getsource(server.value_board)
    body = src[src.index('for fid, doc in priced.items():'):]
    window = body.index('"status": "outside_window"')
    model = body.index("fixture_model_from(")
    assert window < model, \
        "the window check fell back below the model build; a one-day board pays for a week"


# --- a price fetched at lunchtime has to reach the board before the evening ------------
#
# `_data_version` was the league sync timestamp alone, and a screen is stale only when
# that string changes. So a board built at 08:15 stayed "fresh" for thirteen hours
# however many prices arrived in between — and prices arrive hourly. A full scan could
# price forty fixtures at lunchtime and the Streaks page would still show them unpriced
# at seven, which reads as "the site never fetched the odds".

class _OneDoc:
    def __init__(self, doc): self._doc = doc
    def sort(self, *a, **k): return self
    def limit(self, n): return self
    async def to_list(self, n): return [self._doc] if self._doc else []


def _version_db(monkeypatch, synced, fetched, odds_raises=False):
    class DB:
        class leagues:
            @staticmethod
            def find(q, proj): return _OneDoc({"synced_at": synced} if synced else None)

        class odds_feed:
            @staticmethod
            def find(q, proj):
                if odds_raises:
                    raise RuntimeError("no such collection")
                return _OneDoc({"fetched_at": fetched} if fetched else None)
    monkeypatch.setattr(server, "db", DB())


def test_a_price_fetched_this_hour_changes_the_version(monkeypatch):
    _version_db(monkeypatch, "2026-11-26T07:00:00Z", "2026-11-26T08:15:00Z")
    before = run(server._data_version())
    _version_db(monkeypatch, "2026-11-26T07:00:00Z", "2026-11-26T14:47:00Z")
    assert run(server._data_version()) != before, "the board would still show 08:15 prices"


def test_two_fetches_in_the_same_hour_do_not_rebuild_twice(monkeypatch):
    """Truncated to the hour on purpose: the alternative is a rebuild on every write, and
    the odds passes run hourly, so an hour is the real resolution of what is tracked."""
    _version_db(monkeypatch, "2026-11-26T07:00:00Z", "2026-11-26T14:02:00Z")
    a = run(server._data_version())
    _version_db(monkeypatch, "2026-11-26T07:00:00Z", "2026-11-26T14:58:00Z")
    assert run(server._data_version()) == a


def test_a_league_sync_still_changes_it(monkeypatch):
    _version_db(monkeypatch, "2026-11-26T07:00:00Z", "2026-11-26T14:00:00Z")
    a = run(server._data_version())
    _version_db(monkeypatch, "2026-11-26T19:00:00Z", "2026-11-26T14:00:00Z")
    assert run(server._data_version()) != a


def test_an_unreachable_odds_store_falls_back_rather_than_raising(monkeypatch):
    """This decides whether a cached page may be served and must never be the reason one
    cannot be."""
    _version_db(monkeypatch, "2026-11-26T07:00:00Z", None, odds_raises=True)
    v = run(server._data_version())
    assert v and "2026-11-26T07:00:00Z" in v


def test_nothing_at_all_is_none_rather_than_a_version_of_two_empties(monkeypatch):
    # None means "cannot tell", which _screen_is_stale already treats as not-a-reason.
    _version_db(monkeypatch, None, None)
    assert run(server._data_version()) is None


# --- one scan per projection for a composite board -----------------------------------
#
# `_combined_rows` gathers five boards and each scanned the team collection for itself:
# _all_mismatches once, streaks once per venue, and perfect_games — which calls streaks
# and _all_mismatches again internally. Eight scans of the whole collection for one page
# load, on one worker, with the week card calling it on every visit.
#
# The screens were the visible end of it: eleven of thirteen stale and four not rebuilt in
# two days, because a rebuild heavy enough to exhaust the worker never finishes, so the
# screen never goes fresh and the next visitor queues the same doomed rebuild.

def _combined(monkeypatch, teams, scoped=True):
    """The real composite build, with the scan counter on the fake."""
    monkeypatch.setattr(server, "db", FakeDB(teams))
    monkeypatch.setattr(server, "_cache_ok", lambda: False)
    if not scoped:
        # The same gather with the memo never opened — i.e. the behaviour before the fix.
        import contextlib
        monkeypatch.setattr(server, "_teams_scope", contextlib.nullcontext)
    rows = run(server._combined_rows_uncached(7, 0, 0, 1, {"user_id": "u1",
                                                           "member": True}))
    return rows, server.db.teams.calls


def _wide(calls):
    """Scans with no id filter — the ones that read every team document."""
    return [proj for q, proj in calls if "team_id" not in q]


def test_the_composite_board_scans_the_teams_once_per_projection(monkeypatch):
    _rows, calls = _combined(monkeypatch, copy.deepcopy(TEAMS))
    # Whole-collection scans only: the opponent lookup inside perfect_games is keyed on a
    # list of ids and is not what made this expensive.
    wide = _wide(calls)
    shapes = {repr(sorted(p.items())) for p in wide}
    assert len(wide) == len(shapes), (
        f"the same scan ran more than once: {len(wide)} scans, {len(shapes)} distinct "
        f"projections")
    # Three distinct projections remain, and that is the floor without changing what the
    # callers ask for: `{"_id": 0}` for _all_mismatches (which needs `matches` for _src's
    # fallback), the same minus `matches` for the streak walk, and a two-field scan for
    # `real_samples`. Eight scans became three, and the two heavy ones run once each.
    assert len(wide) <= 3, f"expected at most three whole-collection scans, got {len(wide)}"


def test_without_the_scope_it_really_did_scan_many_times(monkeypatch):
    """The counter above is only meaningful if it would catch the old behaviour."""
    _rows, calls = _combined(monkeypatch, copy.deepcopy(TEAMS), scoped=False)
    wide = _wide(calls)
    assert len(wide) >= 5, (
        f"only {len(wide)} wide scans without the memo — if the gather no longer repeats "
        f"them, the test above is measuring nothing")


def test_the_memo_does_not_change_the_board(monkeypatch):
    """Sharing one scan between callers must produce the identical board.

    The documents are handed to several callers rather than copied, so this is the test
    that would fail if any of them mutated a team document in place.
    """
    scoped, _ = _combined(monkeypatch, copy.deepcopy(TEAMS))
    plain, _ = _combined(monkeypatch, copy.deepcopy(TEAMS), scoped=False)
    assert json.dumps(scoped, sort_keys=True) == json.dumps(plain, sort_keys=True)


def test_outside_a_scope_a_scan_is_not_memoised(monkeypatch):
    """The memo must be invisible to ordinary endpoints: no cross-request caching."""
    monkeypatch.setattr(server, "db", FakeDB(copy.deepcopy(TEAMS)))
    monkeypatch.setattr(server, "_cache_ok", lambda: False)
    proj = {"_id": 0, "matches": 0}
    run(server._teams_scan({}, proj, 5000))
    run(server._teams_scan({}, proj, 5000))
    assert len(server.db.teams.projections) == 2, \
        "two scans outside a scope must hit the database twice"


# --- the endpoint that stopped the daily post ----------------------------------------
#
# /api/share/rows gathers every board in one request — a streak pass per grid entry, the
# fixture board, the mismatches, the chase board, the combined board and the value board
# — and each scanned the team collection for itself. The draft job gave up at 120 seconds
# on 25 and 26 November and the post did not go, two days running. Last success was the
# 24th, which is the date on the last post anyone received.

def test_share_rows_scans_the_teams_once_per_projection(monkeypatch):
    monkeypatch.setattr(server, "db", FakeDB(copy.deepcopy(TEAMS)))
    monkeypatch.setattr(server, "_cache_ok", lambda: False)
    monkeypatch.setattr(server, "_check_tools_token", lambda t: None)
    run(server.share_rows(days=3, limit=5, token="t", streak_grid=False))
    wide = _wide(server.db.teams.calls)
    shapes = {repr(sorted(p.items())) for p in wide}
    assert len(wide) == len(shapes), (
        f"a scan ran more than once across the endpoint: {len(wide)} scans, "
        f"{len(shapes)} distinct projections")


def test_without_the_scope_share_rows_really_did_repeat_them(monkeypatch):
    """So the count above is measuring the fix and not a coincidence of this fixture."""
    import contextlib
    monkeypatch.setattr(server, "db", FakeDB(copy.deepcopy(TEAMS)))
    monkeypatch.setattr(server, "_cache_ok", lambda: False)
    monkeypatch.setattr(server, "_check_tools_token", lambda t: None)
    monkeypatch.setattr(server, "_teams_scope", contextlib.nullcontext)
    run(server.share_rows(days=3, limit=5, token="t", streak_grid=False))
    wide = _wide(server.db.teams.calls)
    assert len(wide) > len({repr(sorted(p.items())) for p in wide}), \
        "unscoped, this endpoint must repeat at least one scan"


# --- a windowed request can be served from the cached board --------------------------
#
# /api/share/rows asks for exactly the canonical board except `within_days=1`, and that
# one argument missed the cache, so every call rebuilt the whole walk live. That request
# timed out at 120 seconds on 25, 26, 27 and 28 November and the daily post did not go.
#
# The claim the fix rests on is that `within_days` is not part of the computation — it is
# a filter on each row's next fixture, applied after the walk. That is checked here
# against the REAL handler on both sides rather than asserted: the live windowed board
# must equal the full board put through the same filter.

def _fixtures_at(*day_offsets):
    out = []
    for i, d in enumerate(day_offsets):
        when = (NOW + timedelta(days=d)).isoformat().replace("+00:00", "Z")
        out.append({"fixture_id": f"fx{i}", "league_id": "eng-l1", "date": when,
                    "home_team_id": "eng-l1-1", "away_team_id": "eng-l1-2",
                    "home_name": "Team eng-l1-1", "away_name": "Team eng-l1-2",
                    "status": "upcoming", "round": f"R{i}"})
    return out


def _board(monkeypatch, fixtures, **kw):
    """The real handler against a chosen fixture list, off the screen cache."""
    db = FakeDB(copy.deepcopy(TEAMS))
    db.fixtures = FakeCollection(fixtures)
    monkeypatch.setattr(server, "db", db)
    monkeypatch.setattr(server, "_cache_ok", lambda: False)
    params = {"league_id": "all", "side": "overall", "window": 5, "min_hits": 5,
              "threshold": None, "min_line": 3, "direction": "over", "subject": "team",
              "max_line": None, "min_streak": server.MIN_STREAK_LEN,
              "user": {"user_id": "u1", "member": True}}
    params.update(kw)
    return run(server.streaks(**params))


def test_filtering_the_full_board_matches_asking_for_the_window(monkeypatch):
    """Both directions, because an equality that only ever keeps or only ever drops is
    half a test. _next_fixtures gives each team its EARLIEST upcoming game, so the way
    to make a row fall outside the window is to move that game, not to add a later one.
    """
    # Inside the window: the filter must keep the rows and change nothing about them.
    near = _fixtures_at(0.5)
    windowed = _board(monkeypatch, near, within_days=1)
    whole = _board(monkeypatch, near, within_days=None)
    assert windowed, "the fixture produced no rows, so this compared two empty lists"
    assert json.dumps(windowed, sort_keys=True) == \
        json.dumps(server._rows_within_days(whole, 1), sort_keys=True)

    # Outside it: the live walk returns nothing, so the filter must remove everything.
    far = _fixtures_at(7)
    windowed_far = _board(monkeypatch, far, within_days=1)
    whole_far = _board(monkeypatch, far, within_days=None)
    assert whole_far, "the far fixture produced no rows at all, so nothing was dropped"
    assert windowed_far == []
    assert server._rows_within_days(whole_far, 1) == []


def test_a_row_with_no_next_fixture_is_dropped_by_the_window(monkeypatch):
    """The live path drops it under the same condition, so the cached answer must too —
    otherwise the cache returns a superset and reads as correct until somebody counts."""
    whole = _board(monkeypatch, _fixtures_at(0.5), within_days=None)
    unplayed = dict(whole[0])
    unplayed.pop("next_fixture", None)
    assert server._rows_within_days(whole + [unplayed], 1) == \
        server._rows_within_days(whole, 1)


def test_a_kicked_off_game_is_outside_the_window(monkeypatch):
    whole = _board(monkeypatch, _fixtures_at(0.5), within_days=None)
    past = copy.deepcopy(whole[0])
    past["next_fixture"]["date"] = (NOW - timedelta(hours=3)).isoformat()
    assert server._rows_within_days([past], 1) == []


def test_an_unreadable_date_is_dropped_rather_than_raising(monkeypatch):
    whole = _board(monkeypatch, _fixtures_at(0.5), within_days=None)
    bad = copy.deepcopy(whole[0])
    bad["next_fixture"]["date"] = "not a date"
    assert server._rows_within_days([bad], 1) == []
