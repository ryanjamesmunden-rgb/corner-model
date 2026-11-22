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

    def sort(self, field, direction=1):
        # Mongo sorts a missing field as null — the lowest value — so descending puts
        # documents without it last. The board leans on exactly that: legacy prices
        # carry no `updated_at` and must not outrank one entered this morning.
        present = [d for d in self._docs if d.get(field) is not None]
        missing = [d for d in self._docs if d.get(field) is None]
        present.sort(key=lambda d: d[field], reverse=direction < 0)
        self._docs = present + missing if direction < 0 else missing + present
        return self

    async def to_list(self, n):
        return self._docs[:n]


class FakeCollection:
    def __init__(self, docs, key):
        self._docs, self._key = docs, key

    def find(self, q=None, proj=None):
        return FakeCursor(list(self._match(q)))

    async def delete_many(self, q):
        doomed = list(self._match(q))
        self._docs[:] = [d for d in self._docs if d not in doomed]
        return type("Result", (), {"deleted_count": len(doomed)})()

    def _match(self, q):
        ids = ((q or {}).get(self._key) or {}).get("$in") if q else None
        return self._docs if ids is None else [d for d in self._docs if d[self._key] in ids]


class FakeDB:
    def __init__(self, odds, fixtures, teams, leagues, odds_feed=None):
        self.odds = FakeCollection(odds, "fixture_id")
        # The second price store. The board reads BOTH now and merges them per market key
        # with a hand-typed price always winning — see server._merged_prices. Defaulting
        # it to empty keeps every test below asking its original question: what the board
        # does with the prices somebody entered.
        self.odds_feed = FakeCollection(list(odds_feed or []), "fixture_id")
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


def install(monkeypatch, *, odds, fixtures, teams=None, markets=None, feed=None):
    """Wire a board up over the fake db, with the model stubbed to a fixed ladder."""
    teams = teams if teams is not None else [{"team_id": "t-home"}, {"team_id": "t-away"}]
    monkeypatch.setattr(server, "db",
                        FakeDB(odds, fixtures, teams,
                               [{"league_id": "eng-pl", "name": "Premier League"}],
                               odds_feed=feed))
    ladder = markets if markets is not None else [market(6.0), market(1.0)]
    monkeypatch.setattr(server, "fixture_model_from",
                        lambda h, a, lg, o: {"markets": ladder,
                                             "confidence": {"score": 70, "label": "High"},
                                             "lambdas": {"total": 10.4}})


MEMBER = {"member": True}


def run(coro):
    """Sync runner, like the rest of the suite — the repo has no async pytest plugin.

    Deliberately NOT asyncio.run(): that clears the process's event loop on the way out,
    and the modules that reach for get_event_loop() then fail when they happen to share
    an xdist worker with this file.
    """
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def board(**kw):
    kw.setdefault("within_days", 0)
    kw.setdefault("min_ev", -100.0)
    kw.setdefault("user", MEMBER)
    return run(server.value_board(**kw))


def priced(fid):
    return {"fixture_id": fid, "odds": {"total_over_9.5": 1.8}, "updated_at": iso(-1)}


def seeded(fid):
    """A price from before timestamps existed — i.e. the demo seed data."""
    return {"fixture_id": fid, "odds": {"total_over_9.5": 1.8}}


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


# --- the prices that were never even read --------------------------------------------

def test_purge_removes_prices_whose_fixture_is_gone(monkeypatch):
    """The demo seeder's leak: mock fixtures deleted, their unstamped prices left behind."""
    install(monkeypatch, odds=[priced("live"), seeded("dead-1"), seeded("dead-2")],
            fixtures=[fixture("live")])
    assert run(server.purge_orphan_odds()) == 2
    assert [r["fixture_id"] for r in board()] == ["live"]
    assert run(server.purge_orphan_odds()) == 0        # idempotent


def test_purge_keeps_a_price_you_entered_recently(monkeypatch):
    """A played game leaves the fixture list, which orphans its price through nobody's
    fault. Deleting that on the spot would erase the record of what you backed."""
    install(monkeypatch, odds=[priced("played-yesterday")], fixtures=[fixture("other")])
    assert run(server.purge_orphan_odds()) == 0
    row = board()[0]
    assert row["status"] == "no_fixture"
    assert "record of what you priced" in row["note"]        # not "re-enter it"


def test_purge_lets_go_of_a_price_once_it_is_ancient(monkeypatch):
    old = dict(priced("long-gone"), updated_at=iso(-24 * (server.ORPHAN_KEEP_DAYS + 1)))
    install(monkeypatch, odds=[old], fixtures=[fixture("other")])
    assert run(server.purge_orphan_odds()) == 1


def test_purge_does_nothing_when_there_are_no_fixtures(monkeypatch):
    """A half-loaded database must not read as "no fixtures exist, so delete the lot"."""
    install(monkeypatch, odds=[seeded("a"), seeded("b")], fixtures=[])
    assert run(server.purge_orphan_odds()) == 0
    assert len(board()) == 2


def test_the_board_reads_the_newest_prices_not_the_oldest(monkeypatch):
    """What actually emptied the board: dead seed data filled the read cap, so every
    price entered on the live site sat past it and was never looked at."""
    monkeypatch.setattr(server, "ODDS_SCAN", 2)
    old = [{"fixture_id": f"seed{i}", "odds": {"total_over_9.5": 1.8}} for i in range(5)]
    mine = dict(priced("mine"), updated_at=iso(-1))
    install(monkeypatch, odds=old + [mine], fixtures=[fixture("mine")])
    assert [r["fixture_id"] for r in board()][0] == "mine"


def test_a_flood_of_dead_prices_cannot_bury_the_live_rows(monkeypatch):
    monkeypatch.setattr(server, "ORPHAN_ROWS", 2)
    install(monkeypatch, odds=[priced("live")] + [seeded(f"dead{i}") for i in range(5)],
            fixtures=[fixture("live")])
    rows = board()
    assert [r["status"] for r in rows] == ["ok", "no_fixture", "no_fixture"]
    assert rows[-1]["more_orphans"] == 3


# --- two price stores, one board ----------------------------------------------------
#
# Prices now arrive two ways: typed in on a fixture page (db.odds, source "manual") and
# fetched from the bookmaker feed (db.odds_feed, source "api"). They are kept in separate
# collections because db.odds is ONE document per fixture with a single `source` flag that
# set_odds merges dicts into — so a fetched price written there would either overwrite a
# price somebody chose or be overwritten by one, and that one flag could never say which
# key came from where.
#
# So the merge happens on the read, per market key, and these are its rules.

def fetched(fid, odds=None, hours_ago=1):
    return {"fixture_id": fid, "source": "api",
            "odds": odds if odds is not None else {"total_over_9.5": 2.10},
            "books": {"total_over_9.5": "Pinnacle"},
            "fetched_at": iso(-hours_ago)}


def test_a_fetched_price_alone_still_makes_a_row(monkeypatch):
    """The point of the whole pipeline: a board that works without anybody typing."""
    install(monkeypatch, odds=[], fixtures=[fixture("fx1")], feed=[fetched("fx1")])
    rows = board()
    assert [r["fixture_id"] for r in rows] == ["fx1"]
    assert rows[0]["status"] == "ok"
    assert rows[0]["odds_source"] == "api"
    assert rows[0]["best"]["price_source"] == "api"


def test_a_hand_typed_price_beats_a_fetched_one_on_the_same_market(monkeypatch):
    """A person typing a price has looked at the market and chosen that number. A fetched
    price is whatever was quoted when the job last ran."""
    install(monkeypatch, odds=[priced("fx1")], fixtures=[fixture("fx1")],
            feed=[fetched("fx1")])
    rows = board()
    assert rows[0]["best"]["price_source"] == "manual"
    # And the fixture-level flag still answers its own, older question: did a human type
    # anything here at all.
    assert rows[0]["odds_source"] != "api"


def test_a_better_fetched_price_is_reported_beside_it_never_swapped_in(monkeypatch):
    """So the row can say "2.10 is available elsewhere" without overriding a choice
    somebody made. Switching silently would mean the board quoting a price the owner
    never agreed to take."""
    install(monkeypatch, odds=[priced("fx1")], fixtures=[fixture("fx1")],
            feed=[fetched("fx1", {"total_over_9.5": 2.10})])
    best = board()[0]["best"]
    assert best["price_source"] == "manual"
    assert best["feed_price"] == 2.10


def test_a_worse_fetched_price_is_not_mentioned_at_all(monkeypatch):
    install(monkeypatch, odds=[priced("fx1")], fixtures=[fixture("fx1")],
            feed=[fetched("fx1", {"total_over_9.5": 1.50})])
    assert "feed_price" not in board()[0]["best"]


def test_a_stale_fetched_price_is_dropped_rather_than_ranked_on(monkeypatch):
    """An edge measured against a price that was available yesterday is not an edge. A
    hand-typed price is left alone at any age — somebody chose to put it there."""
    install(monkeypatch, odds=[], fixtures=[fixture("fx1")],
            feed=[fetched("fx1", hours_ago=server.FEED_PRICE_STALE_HOURS + 2)])
    assert board() == []


def test_a_fetched_price_with_no_readable_clock_is_not_trusted(monkeypatch):
    """It cannot be aged, so it cannot be shown to be current."""
    doc = fetched("fx1")
    doc.pop("fetched_at")
    install(monkeypatch, odds=[], fixtures=[fixture("fx1")], feed=[doc])
    assert board() == []


def test_the_two_stores_combine_rather_than_replace(monkeypatch):
    """A fixture can carry one typed line and a fetched ladder around it, and both reach
    the model. Merging on the FIXTURE rather than on the market key would throw one of
    them away — which is the mistake that made two collections necessary in the first
    place."""
    install(monkeypatch,
            odds=[{"fixture_id": "fx1", "odds": {"total_over_9.5": 1.8},
                   "updated_at": iso(-1), "source": "manual"}],
            fixtures=[fixture("fx1")],
            feed=[fetched("fx1", {"total_over_10.5": 2.40, "home_over_4.5": 1.75})])

    seen = {}
    monkeypatch.setattr(server, "fixture_model_from",
                        lambda h, a, lg, o: seen.update(o) or {
                            "markets": [market(6.0)],
                            "confidence": {"score": 70, "label": "High"},
                            "lambdas": {"total": 10.4}})
    rows = board()
    assert len(rows) == 1
    # All three prices are handed to the model, each from whichever store had it.
    assert seen == {"total_over_9.5": 1.8, "total_over_10.5": 2.40,
                    "home_over_4.5": 1.75}


# --- how big is too big ------------------------------------------------------------
#
# A board ranked by EV is ranked by how far the model disagrees with the market, so its
# top rows were a mix of real edges and the model's worst misreads — under a footnote
# that said so and changed nothing. These cover the two halves of the fix: the verdict,
# and the sort that acts on it.

class TestEvCredibility:
    def test_an_ordinary_edge_is_credible_and_unlabelled(self):
        for ev in (0.0, 5.0, 12.5, 30.0):
            v = server.ev_credibility(ev)
            assert v["band"] == "credible", ev
            # No note: labelling the normal case labels every row, which says nothing.
            assert v["note"] == ""

    def test_no_ev_gets_no_opinion(self):
        # A row with no priced market must come back exactly as it was rather than
        # being called fine.
        assert server.ev_credibility(None) is None

    def test_past_the_hard_cap_it_is_not_an_edge_at_all(self):
        v = server.ev_credibility(240.0, {"books": 6, "over_second": 0.5})
        assert v["band"] == "implausible"
        assert "wrong line" in v["note"]

    def test_one_book_clear_of_the_market_points_at_the_line(self):
        # 2.90 where the next five books are near 2.00: far more often a wrong
        # half-point than a gift, and the thing to check is the stored line.
        v = server.ev_credibility(45.0, {"books": 6, "over_second": 31.0})
        assert v["band"] == "outlier"
        assert "clear of the next best" in v["note"]
        assert "check the line" in v["note"]

    def test_a_market_agreeing_with_itself_points_at_the_model(self):
        # Every book within a whisker of the price, so the PRICE is real and the
        # disagreement is the model's. Opposite job from the row above, same number
        # on screen — which is why one threshold cannot do this.
        v = server.ev_credibility(45.0, {"books": 6, "over_second": 1.4})
        assert v["band"] == "stretch"
        assert "the model is the one out on its own" in v["note"]
        assert "projection" in v["note"]

    def test_without_a_quorum_it_says_there_is_nothing_to_check_against(self):
        for spread in (None, {"books": 1, "over_second": None},
                       {"books": 2, "over_second": 40.0}):
            v = server.ev_credibility(45.0, spread)
            assert v["band"] == "stretch", spread
            assert "nothing to check it against" in v["note"]

    def test_the_boundary_belongs_to_credible(self):
        assert server.ev_credibility(server.EV_CREDIBLE_MAX)["band"] == "credible"
        assert server.ev_credibility(server.EV_CREDIBLE_MAX + 0.1)["band"] == "stretch"
        assert server.ev_credibility(server.EV_HARD_CAP)["band"] != "implausible"
        assert server.ev_credibility(server.EV_HARD_CAP + 0.1)["band"] == "implausible"


def test_a_believable_edge_outranks_a_bigger_broken_one(monkeypatch):
    """THE FIX, in one assertion. The board sorted purely by EV, so the misprices led
    the page and the rows worth backing sat under them."""
    install(monkeypatch,
            odds=[priced("real"), priced("broken")],
            fixtures=[fixture("real"), fixture("broken")])

    # Two fixtures, same shape, different edges: +8% and +250%.
    def model(h, a, lg, o):
        ev = 250.0 if model.calls == 0 else 8.0
        model.calls += 1
        return {"markets": [market(ev)], "confidence": {"score": 70, "label": "High"},
                "lambdas": {"total": 10.4}}
    model.calls = 0
    monkeypatch.setattr(server, "fixture_model_from", model)

    rows = board()
    assert [r["best"]["ev"] for r in rows] == [8.0, 250.0], \
        "the +250% row must not head the board"
    assert rows[0]["best"]["credibility"] == "credible"
    assert rows[1]["best"]["credibility"] == "implausible"
    # Still on the board — flagged and demoted, never dropped.
    assert rows[1]["status"] == "ok"
    assert rows[1]["best"]["credibility_note"]


def test_within_a_band_the_bigger_edge_still_wins(monkeypatch):
    """Credibility is the first key, not the only one."""
    install(monkeypatch, odds=[priced("a"), priced("b")],
            fixtures=[fixture("a"), fixture("b")])

    def model(h, a, lg, o):
        ev = 4.0 if model.calls == 0 else 19.0
        model.calls += 1
        return {"markets": [market(ev)], "confidence": {"score": 70, "label": "High"},
                "lambdas": {"total": 10.4}}
    model.calls = 0
    monkeypatch.setattr(server, "fixture_model_from", model)
    assert [r["best"]["ev"] for r in board()] == [19.0, 4.0]


def test_a_fixture_leads_with_its_soundest_rung_not_its_biggest(monkeypatch):
    """THE SAME BUG ONE LEVEL DOWN, and the one the board fix alone would have made
    worse. A ladder ranked by raw EV makes a game's headline line its most broken rung,
    so a fixture with a sound +7% and a mispriced +180% led with the +180% — and once
    flagged rows sort to the bottom, that whole fixture including the good line would
    have gone with it."""
    install(monkeypatch, odds=[priced("fx1")], fixtures=[fixture("fx1")],
            markets=[market(7.0), market(180.0), market(2.0)])
    row = board()[0]
    assert row["best"]["ev"] == 7.0
    assert row["best"]["credibility"] == "credible"
    # Still reachable, still flagged: the drawer is bet off exactly as the headline is.
    bands = [m["credibility"] for m in row["alternatives"]]
    assert "implausible" in bands, bands
    assert row["other_count"] == 2


def test_a_high_floor_surfaces_the_broken_rung_so_it_can_be_fixed(monkeypatch):
    """Asking for 100%+ is asking to see the misprices, not to be protected from them.
    The floor filters RUNGS, so the rung that cleared it is the one shown."""
    install(monkeypatch, odds=[priced("fx1")], fixtures=[fixture("fx1")],
            markets=[market(7.0), market(180.0), market(2.0)])
    row = board(min_ev=100.0)[0]
    assert row["status"] == "ok"
    assert row["best"]["ev"] == 180.0
    assert row["best"]["credibility"] == "implausible"
    assert row["best"]["credibility_note"]


def test_a_row_clearing_nothing_keeps_its_best_line(monkeypatch):
    """below_floor is a label on a row, never a row with no price on it."""
    install(monkeypatch, odds=[priced("fx1")], fixtures=[fixture("fx1")],
            markets=[market(7.0), market(2.0)])
    row = board(min_ev=50.0)[0]
    assert row["status"] == "below_floor"
    assert row["best"]["ev"] == 7.0


# --- one day, for one post ----------------------------------------------------------
#
# The windows are cumulative — "next 3 days" is today AND tomorrow AND the day after —
# which is right for browsing and wrong for the card that goes to the channel. A day is
# a day.

def at_day(fid, iso, **kw):
    """A fixture at an exact instant rather than N hours from now."""
    return {"fixture_id": fid, "league_id": "eng-pl", "date": iso,
            "home_team_id": "t-home", "away_team_id": "t-away",
            "home_name": "Home", "away_name": "Away", "round": "R5", **kw}


def test_a_day_takes_that_day_and_leaves_the_rest(monkeypatch):
    soon = (NOW + timedelta(days=2)).astimezone(server.VALUE_PICK_TZ).date()
    after = soon + timedelta(days=1)
    install(monkeypatch,
            odds=[priced("on"), priced("off")],
            fixtures=[at_day("on", f"{soon.isoformat()}T15:00:00Z"),
                      at_day("off", f"{after.isoformat()}T15:00:00Z")])
    rows = {r["fixture_id"]: r["status"] for r in board(day=soon.isoformat())}
    assert rows["on"] == "ok"
    assert rows["off"] == "outside_window"


def test_the_day_wins_over_the_horizon(monkeypatch):
    """`day` IS the window; passing both must not narrow it twice or widen it."""
    far = (NOW + timedelta(days=9)).astimezone(server.VALUE_PICK_TZ).date()
    install(monkeypatch, odds=[priced("far")],
            fixtures=[at_day("far", f"{far.isoformat()}T15:00:00Z")])
    # within_days=3 would normally file this as outside_window.
    assert board(day=far.isoformat(), within_days=3)[0]["status"] == "ok"


def test_a_late_kick_off_is_filed_under_its_london_day(monkeypatch):
    """A 23:30Z game in summer is 00:30 the next morning in London. Filing it under the
    UTC date puts Saturday's game in Sunday's post."""
    # A date in a FUTURE summer: British Summer Time is the only time the two dates
    # differ, and a past kick-off would come back "kicked_off" before the day filter was
    # ever consulted.
    summer = NOW.year + 1
    install(monkeypatch, odds=[priced("late")],
            fixtures=[at_day("late", f"{summer}-06-21T23:30:00Z")])
    assert board(day=f"{summer}-06-22")[0]["status"] == "ok"
    assert board(day=f"{summer}-06-21")[0]["status"] == "outside_window"


def test_without_a_day_nothing_changes(monkeypatch):
    """The horizon still works for the people and jobs that use it."""
    install(monkeypatch, odds=[priced("soon"), priced("far")],
            fixtures=[fixture("soon", hours=24), fixture("far", hours=24 * 30)])
    rows = {r["fixture_id"]: r["status"] for r in board(within_days=3)}
    assert rows["soon"] == "ok"
    assert rows["far"] == "outside_window"


# --- the game-state label -----------------------------------------------------------
#
# Every team line carries game_state.side_verdict for the side it is on; a total line has
# no side and carries none. And the label never reorders the board: it is unmeasured
# until measure_chase_filter has replayed it.

def team_market(ev, group="away"):
    return {"key": f"{group}_over_4.5", "group": group, "group_label": group.title(),
            "label": "Over 4.5", "line": 4.5, "book_odds": 2.2, "fair_odds": 1.9,
            "prob": 52.0, "ev": ev, "tier": "small"}


def history(gf, ga, n=10):
    return [{"home": i % 2 == 0, "corners_for": 5, "corners_against": 5,
             "goals_for": gf, "goals_against": ga, "fh_goals_for": 0,
             "fh_goals_against": 0, "shots_for": 12} for i in range(n)]


def test_a_team_line_carries_the_verdict_for_its_own_side(monkeypatch):
    # The away side is two goals a game worse than the home side: the Bayern v Köln shape.
    teams = [{"team_id": "t-home", "real_matches": history(3, 1)},
             {"team_id": "t-away", "real_matches": history(0, 2)}]
    install(monkeypatch, odds=[priced("f0")], fixtures=[fixture("f0")], teams=teams,
            markets=[team_market(20.0, "away")])
    gs_ = board()[0]["game_state"]
    assert gs_["verdict"] == "avoid" and "mismatch" in gs_["flags"]
    assert gs_["measured"] is False


def test_the_opponents_market_price_is_read_from_the_right_side(monkeypatch):
    teams = [{"team_id": "t-home", "real_matches": history(1, 1)},
             {"team_id": "t-away", "real_matches": history(1, 1)}]
    feed = [{**fetched("f0"), "match_odds": {"home": 0.70, "draw": 0.2, "away": 0.10}}]
    install(monkeypatch, odds=[], fixtures=[fixture("f0")], teams=teams, feed=feed,
            markets=[team_market(8.0, "away")])
    # an AWAY line: the opponent is the home side, 70% to win
    assert board()[0]["game_state"]["opp_win_prob"] == 0.70


def test_a_total_line_has_no_side_and_no_verdict(monkeypatch):
    install(monkeypatch, odds=[priced("f0")], fixtures=[fixture("f0")])
    assert board()[0]["game_state"] is None


def test_the_label_does_not_reorder_the_board(monkeypatch):
    # "avoid" carries the bigger edge, "chase" the smaller. If the label sorted the board
    # the chase spot would lead; it must not, until the harness says it works.
    teams = [{"team_id": "a-home", "real_matches": history(3, 1)},
             {"team_id": "a-away", "real_matches": history(0, 2)},     # swamped: avoid
             {"team_id": "c-home", "real_matches": history(1, 1)},
             {"team_id": "c-away", "real_matches": history(1, 1)}]
    install(monkeypatch, odds=[priced("avoid"), priced("chase")],
            fixtures=[fixture("avoid", home="a-home", away="a-away"),
                      fixture("chase", home="c-home", away="c-away")], teams=teams)
    ev = {"a-home": 20.0, "c-home": 6.0}
    monkeypatch.setattr(server, "fixture_model_from",
                        lambda h, a, lg, o: {"markets": [team_market(ev[h["team_id"]])],
                                             "confidence": {"score": 70, "label": "High"},
                                             "lambdas": {"total": 10.4}})
    rows = board()
    assert [r["fixture_id"] for r in rows] == ["avoid", "chase"]
    assert rows[0]["game_state"]["verdict"] == "avoid"
    assert rows[1]["game_state"]["verdict"] != "avoid"
