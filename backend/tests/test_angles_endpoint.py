"""The endpoint wiring, over a database small enough to read.

test_angle_of_day covers the rule. This covers the thing the rule is plugged into, because
every one of these failures is silent: a stale day that publishes anyway, a record that
counts a fixture once per day it sat in the window, a record that grades twenty-five rows
and prints the result beside a list of five. None of them raises, and each produces a page
that looks completely normal and is making a claim it has not earned.
"""
import asyncio
import os
import sys
from datetime import datetime, timedelta, timezone

import pytest

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "test_corner_model")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import angle_of_day as aod  # noqa: E402
import server  # noqa: E402

NOW = datetime.now(timezone.utc)
USER = {"user_id": "u1", "email": "a@b.c"}


def iso(hours):
    return (NOW + timedelta(hours=hours)).isoformat().replace("+00:00", "Z")


TODAY = aod.london_day(iso(0))


class FakeCursor:
    def __init__(self, docs):
        self._docs = list(docs)

    def sort(self, field, direction=1):
        self._docs.sort(key=lambda d: d.get(field) or "", reverse=direction < 0)
        return self

    def limit(self, n):
        self._docs = self._docs[:n]
        return self

    async def to_list(self, n):
        return self._docs[:n]


class FakeCollection:
    def __init__(self, docs):
        self._docs = list(docs)

    def find(self, q=None, proj=None):
        return FakeCursor(self._docs)


class FakeDB:
    def __init__(self, *, leagues, fixtures, snapshots):
        self.leagues = FakeCollection(leagues)
        self.fixtures = FakeCollection(fixtures)
        self.streak_snapshots = FakeCollection(snapshots)


def board_row(name, hours=6, line=6, fixture_id=None):
    """A streaks-board row, as the board hands one over."""
    return {"team_id": f"t-{name}", "name": name, "league_id": "eng-ch", "line": line,
            "line_label": f"{line}+", "direction": "over", "subject": "team",
            "hits": 5, "settled": 5, "window": 5, "voids": 0,
            "streak": {"length": 5},
            "next_fixture": {"fixture_id": fixture_id or f"fx-{name}", "date": iso(hours),
                             "opponent": "Stoke", "is_home": True}}


def snap_entry(name, fixture_id=None, line=6):
    return {"team_id": f"t-{name}", "name": name, "league_id": "eng-ch", "line": line,
            "direction": "over", "subject": "team", "hits": 5, "window": 5,
            "fixture_id": fixture_id or f"fx-{name}", "kickoff": iso(-48),
            "opponent": "Stoke", "is_home": True}


def install(monkeypatch, *, rows=(), snapshots=(), fixtures=None, age_hours=2.0,
            results=None):
    """Wire the endpoint over a fake db, with the board and settlement stubbed.

    Settlement is stubbed because it has its own tests and needs real match history to say
    anything. What is under test here is which rows reach it.
    """
    synced = (NOW - timedelta(hours=age_hours)).isoformat()
    fixtures = fixtures if fixtures is not None else [{"date": iso(6)}]
    monkeypatch.setattr(server, "db", FakeDB(
        leagues=[{"league_id": "eng-ch", "synced_at": synced}],
        fixtures=fixtures, snapshots=list(snapshots)))

    async def fake_screen(name):
        assert name == "angle_board"
        return list(rows)

    monkeypatch.setattr(server, "_screen", fake_screen)

    async def fake_teams_for(entries):
        return {}

    monkeypatch.setattr(server, "_teams_for", fake_teams_for)
    # Every graded row lands unless the test says otherwise — the counts are what matter.
    monkeypatch.setattr(server, "_grade_entries", lambda entries, teams: [
        {**e, "result": (results or {}).get(e["name"], server.WIN), "value": 9}
        for e in entries])


def run(coro):
    """Sync runner, like the rest of the suite — the repo has no async pytest plugin.

    Deliberately NOT asyncio.run(): that clears the process's event loop on the way out,
    and modules reaching for get_event_loop() then fail when they share an xdist worker.
    """
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def call(**kw):
    return run(server.angles_today(user=USER, **kw))


class TestALiveDay:
    def test_the_top_angle_is_the_boards_first_row(self, monkeypatch):
        install(monkeypatch, rows=[board_row("A"), board_row("B"), board_row("C")])
        out = call()
        assert out["dead"] is False
        assert out["top"]["name"] == "A"
        assert [a["name"] for a in out["angles"]] == ["A", "B", "C"]

    def test_the_count_caps_the_list_and_the_overflow_is_reported(self, monkeypatch):
        install(monkeypatch, rows=[board_row(str(i)) for i in range(9)])
        out = call(count=5)
        assert len(out["angles"]) == 5
        # So the panel can say "5 of 9 qualifying" rather than implying five was all there was.
        assert out["qualified"] == 9

    def test_a_game_that_has_already_kicked_off_is_not_offered(self, monkeypatch):
        install(monkeypatch, rows=[board_row("done", hours=-3), board_row("later", hours=5)])
        out = call()
        assert [a["name"] for a in out["angles"]] == ["later"]

    def test_tomorrows_game_is_not_todays_angle(self, monkeypatch):
        # The board is two days wide on purpose; the panel is one London day.
        install(monkeypatch, rows=[board_row("today", hours=6), board_row("later", hours=40)])
        out = call()
        assert [a["name"] for a in out["angles"]] == ["today"]
        assert out["day"] == TODAY


class TestADeadDayPublishesNothing:
    def test_stale_data_suppresses_angles_that_would_otherwise_qualify(self, monkeypatch):
        # The failure this prevents: a sync breaks overnight, the board still has rows in
        # it, and the page makes a call on two-day-old form without saying so.
        install(monkeypatch, rows=[board_row("A")],
                age_hours=server.SNAPSHOT_MAX_AGE_HOURS + 1)
        out = call()
        assert out["dead"] is True and out["reason"] == aod.DEAD_STALE
        assert out["angles"] == [] and out["top"] is None

    def test_football_on_and_nothing_qualifying_says_so(self, monkeypatch):
        install(monkeypatch, rows=[], fixtures=[{"date": iso(4)} for _ in range(30)])
        out = call()
        assert out["reason"] == aod.DEAD_NO_QUALIFIER
        assert out["fixtures_today"] == 30

    def test_an_empty_calendar_is_a_different_answer(self, monkeypatch):
        install(monkeypatch, rows=[], fixtures=[{"date": iso(72)}])
        out = call()
        assert out["reason"] == aod.DEAD_NO_FIXTURES
        assert out["fixtures_today"] == 0

    def test_the_record_is_still_published_on_a_dead_day(self, monkeypatch):
        # The record of a rule is not suspended because the rule declined to fire.
        install(monkeypatch, rows=[], snapshots=[{"tag": "2026-09-10",
                                                  "entries": [snap_entry("X")]}])
        out = call()
        assert out["dead"] is True
        assert out["record"]["shortlist"]["settled"] == 1


class TestTheRecordMatchesWhatIsPublished:
    def test_only_the_top_rows_of_each_snapshot_are_graded(self, monkeypatch):
        # A snapshot holds 25 and the panel shows 5. Grading all 25 would print one thing's
        # record beside another thing's list.
        entries = [snap_entry(f"e{i}") for i in range(25)]
        install(monkeypatch, snapshots=[{"tag": "2026-09-10", "entries": entries}])
        out = call(count=5)
        assert out["record"]["shortlist"]["settled"] == 5

    def test_the_lead_angle_carries_its_own_number(self, monkeypatch):
        entries = [snap_entry(f"e{i}") for i in range(5)]
        install(monkeypatch, snapshots=[{"tag": "2026-09-10", "entries": entries}])
        out = call(count=5)
        assert out["record"]["top"]["settled"] == 1
        assert out["record"]["shortlist"]["settled"] == 5

    def test_a_fixture_frozen_on_two_days_is_counted_once(self, monkeypatch):
        # The snapshot runs daily over an overlapping window, so the same game is frozen on
        # consecutive days. Counted per snapshot it lands twice, quietly weighting whichever
        # fixtures sat longest in the window.
        entry = snap_entry("Repeat", fixture_id="fx-repeat")
        install(monkeypatch, snapshots=[
            {"tag": "2026-09-11", "entries": [dict(entry)]},
            {"tag": "2026-09-10", "entries": [dict(entry)]},
        ])
        out = call()
        assert out["record"]["shortlist"]["settled"] == 1

    def test_misses_are_counted(self, monkeypatch):
        install(monkeypatch, snapshots=[{"tag": "2026-09-10", "entries": [
            snap_entry("win1"), snap_entry("win2"), snap_entry("lost")]}],
            results={"lost": server.LOSS})
        rec = (call())["record"]["shortlist"]
        assert (rec["landed"], rec["missed"], rec["settled"]) == (2, 1, 3)

    def test_a_small_sample_is_not_allowed_a_percentage(self, monkeypatch):
        install(monkeypatch, snapshots=[{"tag": "2026-09-10",
                                         "entries": [snap_entry(f"e{i}") for i in range(3)]}])
        rec = (call())["record"]["shortlist"]
        assert rec["settled"] == 3 and rec["show_rate"] is False

    def test_a_sample_past_the_floor_is(self, monkeypatch):
        snaps = [{"tag": f"2026-09-{d:02d}", "entries": [snap_entry(f"d{d}d{i}") for i in range(5)]}
                 for d in range(10, 15)]
        install(monkeypatch, snapshots=snaps)
        rec = (call(count=5))["record"]["shortlist"]
        assert rec["settled"] == 25 and rec["show_rate"] is True


class TestTheDoor:
    def test_a_guest_is_refused(self, monkeypatch):
        install(monkeypatch, rows=[board_row("A")])
        with pytest.raises(server.HTTPException) as e:
            run(server.angles_today(user={"user_id": server.PUBLIC_USER_ID}))
        assert e.value.status_code == 401

    def test_the_count_cannot_be_used_to_pull_the_whole_board(self, monkeypatch):
        install(monkeypatch, rows=[board_row(str(i)) for i in range(40)])
        out = call(count=999)
        assert len(out["angles"]) <= 10
