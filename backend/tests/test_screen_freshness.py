"""A screen must go stale the moment a price lands after it was built.

THE BUG THIS PINS. `_data_version` truncates the newest odds write to the hour, so a
rebuild and a later write inside the same hour produce the identical version string and
the screen stays marked fresh while holding pre-fetch prices. Seen directly on
production: a fetch at 23:24 stored 3,922 lines, and all three streak screens — built
23:22 to 23:24 — reported `fresh: true` and went on serving a weekend with no prices on
it. Nothing would rebuild them until the next hour's write, which on a quiet night may
never come.

Truncation was chosen to avoid rebuilding on every write, and that property is worth
keeping. It is kept here for a better reason: `built_at` is compared against the newest
write exactly, so a rebuild happens when a write genuinely postdates the build and not
otherwise.
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


def iso(seconds):
    return (NOW + timedelta(seconds=seconds)).isoformat()


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
    def __init__(self, docs):
        self._docs = docs

    def find(self, q=None, proj=None):
        return FakeCursor(list(self._docs))


class FakeDB:
    def __init__(self, leagues, feed):
        self.leagues = FakeCollection(leagues)
        self.odds_feed = FakeCollection(feed)


def run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


SYNCED = iso(-7200)                                   # the league sync, two hours back
LEAGUES = [{"league_id": "eng-pl", "synced_at": SYNCED}]


def screen(built_at, version):
    return {"_id": "streaks", "schema": server.SCREEN_SCHEMA,
            "built_at": built_at, "data_version": version}


def wire(monkeypatch, feed):
    monkeypatch.setattr(server, "db", FakeDB(LEAGUES, feed))
    return run(server._data_version())


def test_a_price_written_after_the_build_makes_the_screen_stale(monkeypatch):
    """THE REPORTED CASE, in the same hour so the version string cannot catch it."""
    # Built at 23:22, priced at 23:24 — two minutes apart, one hour bucket.
    feed_before = [{"fetched_at": iso(-240)}]
    version = wire(monkeypatch, feed_before)
    doc = screen(iso(-120), version)                  # built after that price
    assert run(server._screen_is_stale(doc)) is False

    # Now a fetch lands, later than the build and inside the same hour.
    monkeypatch.setattr(server, "db", FakeDB(LEAGUES, [{"fetched_at": iso(-60)}]))
    assert run(server._screen_is_stale(doc)) is True


def test_the_hour_bucket_alone_would_have_missed_it(monkeypatch):
    """Proof the test above is testing the new check and not the version string.

    If both timestamps fall in one hour the version is unchanged, so the only thing that
    can report staleness is the exact comparison.
    """
    built = iso(-120)
    v_before = wire(monkeypatch, [{"fetched_at": iso(-240)}])
    v_after = wire(monkeypatch, [{"fetched_at": iso(-60)}])
    assert v_before == v_after, "the two writes must share an hour bucket for this to bite"
    assert run(server._screen_is_stale(screen(built, v_after))) is True


def test_a_build_newer_than_every_price_is_fresh(monkeypatch):
    version = wire(monkeypatch, [{"fetched_at": iso(-600)}])
    assert run(server._screen_is_stale(screen(iso(-60), version))) is False


def test_no_prices_at_all_does_not_make_everything_stale(monkeypatch):
    version = wire(monkeypatch, [])
    assert run(server._screen_is_stale(screen(iso(-60), version))) is False


def test_an_unreadable_price_clock_is_not_treated_as_newer(monkeypatch):
    """A price store full of junk must not force a permanent rebuild loop."""
    version = wire(monkeypatch, [{"fetched_at": "not a date"}])
    assert run(server._screen_is_stale(screen(iso(-60), version))) is False


def test_a_screen_with_no_build_time_is_stale(monkeypatch):
    version = wire(monkeypatch, [{"fetched_at": iso(-600)}])
    assert run(server._screen_is_stale(screen(None, version))) is True


def test_an_old_schema_is_stale_whatever_the_clocks_say(monkeypatch):
    version = wire(monkeypatch, [{"fetched_at": iso(-600)}])
    doc = screen(iso(-60), version)
    doc["schema"] = server.SCREEN_SCHEMA - 1
    assert run(server._screen_is_stale(doc)) is True


def test_a_screen_older_than_the_window_is_stale_even_with_no_new_prices(monkeypatch):
    version = wire(monkeypatch, [{"fetched_at": iso(-600)}])
    ancient = iso(-(server.SCREEN_STALE_HOURS + 2) * 3600)
    assert run(server._screen_is_stale(screen(ancient, version))) is True
