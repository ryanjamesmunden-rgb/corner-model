"""The value board must never lose a price without saying so.

This is the regression test for a week of "nothing is coming up". The board used to walk
FIXTURES and end every failure path in a bare `continue`: no fixture matched the stored
id, the game had kicked off, no stored key matched a market, nothing cleared the floor.
Five ways for a price to vanish, all of them rendering the same empty screen, and no way
to tell them apart from outside. Days went into guessing which one was firing.

So the invariant tested here is stronger than "returns the right rows": EVERY stored
price produces a row, and a row that cannot become a bet carries a status saying why.
"""
import asyncio
import os
import sys
from datetime import datetime, timedelta, timezone

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "test_corner_model")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import server  # noqa: E402


# --- a database small enough to read ------------------------------------------------

class FakeCursor:
    def __init__(self, docs):
        self._docs = docs

    async def to_list(self, n):
        return self._docs[:n]


class FakeCollection:
    def __init__(self, docs, key):
        self._docs, self._key = docs, key

    def find(self, q=None, proj=None):
        docs = self._docs
        ids = ((q or {}).get(self._key) or {}).get("$in") if q else None
        if ids is not None:
            docs = [d for d in docs if d[self._key] in ids]
        return FakeCursor(list(docs))


class FakeDB:
    def __init__(self, odds, fixtures, teams, leagues):
        self.odds = FakeCollection(odds, "fixture_id")
        self.fixtures = FakeCollection(fixtures, "fixture_id")
        self.teams = FakeCollection(teams, "team_id")
        self.leagues = FakeCollection(leagues, "league_id")


NOW = datetime.now(timezone.utc)


def iso(hours):
    return (NOW + timedelta(hours=hours)).isoformat().replace("+00:00", "Z")


def fixture(fid, hours=48, home="t-home", away="t-away"):
    return {"fixture_id": fid, "league_id": "eng-pl", "date": iso(hours),
            "home_team_id": home, "away_team_id": away,
            "home_name": "Home", "away_name": "Away", "round": "R5"}


def market(ev):
    return {"key": "total_over_9.5", "group": "total", "group_label": "Total",
            "label": "Over 9.5", "line": 9.5, "book_odds": 1.8, "fair_odds": 1.63,
            "prob": 61.5, "ev": ev, "tier": "small"}


def install(monkeypatch, *, odds, fixtures, teams=None, markets=None):
    """Wire a board up over the fake db, with the model stubbed to a fixed ladder."""
    teams = teams if teams is not None else [{"team_id": "t-home"}, {"team_id": "t-away"}]
    monkeypatch.setattr(server, "db", FakeDB(odds, fixtures, teams, [{"league_id": "eng-pl", "name": "Premier League"}]))
    ladder = markets if markets is not None else [market(6.0), market(1.0)]
    monkeypatch.setattr(server, "fixture_model_from",
                        lambda h, a, lg, o: {"markets": ladder,
                                             "confidence": {"score": 70, "label": "High"},
                                             "lambdas": {"total": 10.4}})


MEMBER = {"member": True}


def board(**kw):
    """Run the endpoint. Sync, like the rest of the suite — the repo has no async
    pytest plugin and this needs none."""
    kw.setdefault("within_days", 0)
    kw.setdefault("min_ev", -100.0)
    kw.setdefault("user", MEMBER)
    return asyncio.run(server.value_board(**kw))


def priced(fid):
    return {"fixture_id": fid, "odds": {"total_over_9.5": 1.8}, "updated_at": iso(-1)}


# --- the invariant ------------------------------------------------------------------

def test_every_stored_price_produces_a_row(monkeypatch):
    """Six prices in, six rows out — whatever is wrong with them."""
    install(monkeypatch,
            odds=[priced(f"f{i}") for i in range(6)],
            fixtures=[fixture("f0"),                          # fine
                      fixture("f1", hours=-3),                # kicked off
                      fixture("f2", away="missing"),          # team not in db
                      fixture("f3", hours=24 * 30)])          # far future
    # f4 and f5 have no fixture at all.
    rows = board()
    assert len(rows) == 6
    assert {r["fixture_id"] for r in rows} == {f"f{i}" for i in range(6)}
    assert all(r["status"] for r in rows)


def test_each_failure_names_itself(monkeypatch):
    install(monkeypatch,
            odds=[priced("gone"), priced("late"), priced("teamless"), priced("live")],
            fixtures=[fixture("late", hours=-3), fixture("teamless", away="missing"),
                      fixture("live")])
    by_id = {r["fixture_id"]: r for r in board()}
    assert by_id["gone"]["status"] == "no_fixture"
    assert by_id["late"]["status"] == "kicked_off"
    assert by_id["teamless"]["status"] == "no_teams"
    assert by_id["live"]["status"] == "ok"
    # And each of those says something a reader can act on.
    for fid in ("gone", "late", "teamless"):
        assert len(by_id[fid]["note"]) > 20


def test_stored_keys_matching_no_market_are_not_silence(monkeypatch):
    """The failure that is invisible from the fixture page: prices stored, none priced up."""
    install(monkeypatch, odds=[priced("f0")], fixtures=[fixture("f0")],
            markets=[dict(market(0), ev=None, book_odds=None)])
    rows = board()
    assert [r["status"] for r in rows] == ["no_market"]
    assert rows[0]["best"] is None
    assert rows[0]["market_count"] == 1


def test_the_edge_filter_greys_out_rather_than_deletes(monkeypatch):
    """A floor nothing clears used to empty the board. Now it re-labels it."""
    install(monkeypatch, odds=[priced("f0")], fixtures=[fixture("f0")],
            markets=[market(-6.6)])
    rows = board(min_ev=0.0)
    assert [r["status"] for r in rows] == ["below_floor"]
    assert rows[0]["best"]["ev"] == -6.6           # still shown, still ranked
    assert (board(min_ev=-100.0))[0]["status"] == "ok"


def test_the_window_filter_greys_out_rather_than_deletes(monkeypatch):
    install(monkeypatch, odds=[priced("f0")], fixtures=[fixture("f0", hours=24 * 10)])
    assert (board(within_days=3))[0]["status"] == "outside_window"
    assert (board(within_days=0))[0]["status"] == "ok"


def test_backable_rows_come_first_and_rank_by_edge(monkeypatch):
    install(monkeypatch, odds=[priced("f0"), priced("dead")], fixtures=[fixture("f0")])
    rows = board()
    assert rows[0]["status"] == "ok" and rows[1]["status"] == "no_fixture"
    assert rows[0]["best"]["ev"] == 6.0                      # the ladder's top line
    assert [a["ev"] for a in rows[0]["alternatives"]] == [1.0]
    assert rows[0]["other_count"] == 1


def test_empty_only_when_nothing_is_stored(monkeypatch):
    install(monkeypatch, odds=[], fixtures=[fixture("f0")])
    assert board() == []


def test_a_price_with_no_odds_on_it_is_not_a_price(monkeypatch):
    install(monkeypatch, odds=[{"fixture_id": "f0", "odds": {}}], fixtures=[fixture("f0")])
    assert board() == []
