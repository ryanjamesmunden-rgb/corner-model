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

    def find(self, q=None, proj=None):
        self.projections.append(dict(proj or {}))
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
