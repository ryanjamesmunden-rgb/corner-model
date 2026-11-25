"""Pricing the week ahead once per fixture — and why the filter is the whole feature.

WHAT WAS WRONG. The hourly pass reaches one day out, so a weekend fixture was invisible
until Friday — and every price anybody ever saw had already been cut. Reaching six days
out on the hourly pass's own rule would re-pay for every fixture once an hour for a price
that had not moved since the morning.

So this pass asks a different question: which of these has nobody captured AT ALL. That
answer shrinks to nothing as a week fills in, which is what makes a six-day reach
affordable — expensive on the first run of a week, nearly free on every run after it.

THE TESTS THAT MATTER HERE ARE THE ONES ABOUT NOT SPENDING. A bug that prices a fixture
twice does not fail; it bills.
"""
import asyncio
import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _sliced():
    """fetch_odds imports httpx, which is absent in this container, so the selector is
    exercised through a slice of the source — the technique test_price_provenance and
    test_stat_picks use.

    THE SLICE STARTS AT THE BACK-OFF, not at the selector, because unpriced_ahead calls
    recheck_after_hours. Started lower it compiled fine and raised NameError only on the
    first test that happened to have a stored timestamp — a fake that is silently missing
    half of what it is faking.
    """
    with open(os.path.join(HERE, "fetch_odds.py")) as fh:
        src = fh.read()
    start = src.index("RECHECK_GIVE_UP = ")
    end = src.index("async def fetch_ahead(")
    ns = {"timedelta": timedelta, "datetime": datetime, "timezone": timezone,
          "_now": lambda: datetime(2026, 11, 17, 12, 0, tzinfo=timezone.utc),
          "_iso": _iso}
    exec(compile(src[start:end], "sliced", "exec"), ns)
    return ns


def _iso(value):
    """The module's own parser, copied rather than sliced: it lives above the slice."""
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt


_NS = _sliced()
unpriced_ahead = _NS["unpriced_ahead"]
recheck_after_hours = _NS["recheck_after_hours"]
RECHECK_GIVE_UP = _NS["RECHECK_GIVE_UP"]
NOW = datetime(2026, 11, 17, 12, 0, tzinfo=timezone.utc)


def fx(fid, days_out, league="ger-bl", api=True):
    d = {"fixture_id": fid, "league_id": league,
         "date": (NOW + timedelta(days=days_out)).isoformat(),
         "home_name": f"{fid} home", "away_name": f"{fid} away"}
    if api:
        # The provider id is a number and need not match the slug, which is why the
        # fixtures here are named rather than numbered: a test that only ever used
        # numeric suffixes would not notice a selector that derived one from the slug.
        d["api_fixture_id"] = 1500000 + (abs(hash(fid)) % 90000)
    return d


class FakeCursor:
    def __init__(self, rows):
        self._rows = rows

    def sort(self, *_a, **_k):
        self._rows = sorted(self._rows, key=lambda r: r.get("date") or "")
        return self

    async def to_list(self, n):
        return self._rows[:n]

    def __aiter__(self):
        async def gen():
            for r in self._rows:
                yield r
        return gen()


class FakeColl:
    def __init__(self, rows):
        self.rows = rows
        self.queries = []

    def find(self, q=None, _proj=None):
        self.queries.append(q or {})
        rows = self.rows
        q = q or {}
        if "date" in q:
            lo, hi = q["date"]["$gte"], q["date"]["$lte"]
            rows = [r for r in rows if lo <= r["date"] <= hi]
        if "league_id" in q:
            rows = [r for r in rows if r["league_id"] in q["league_id"]["$in"]]
        if "fixture_id" in q:
            rows = [r for r in rows if r["fixture_id"] in q["fixture_id"]["$in"]]
        return FakeCursor(list(rows))


class FakeDB:
    def __init__(self, fixtures, feed):
        self.fixtures = FakeColl(fixtures)
        self.odds_feed = FakeColl(feed)


def run(db, days=6, from_days=1, leagues=None, limit=120, prefer=None):
    return asyncio.run(unpriced_ahead(db, days, from_days, leagues, limit, prefer))


# --- not spending twice -------------------------------------------------------------

def test_a_fixture_that_already_has_a_price_is_not_fetched_again():
    # THE WHOLE ECONOMICS. Without this the pass re-pays for every fixture every day for
    # a price that has not moved, and a six-day reach is unaffordable.
    db = FakeDB([fx("ger-bl-1", 3), fx("ger-bl-2", 4)],
                [{"fixture_id": "ger-bl-1", "odds": {"home_over_4.5": 2.1}}])
    todo, already, _, _ = run(db)
    assert [f["fixture_id"] for f, _ in todo] == ["ger-bl-2"]
    assert already == 1


def test_an_empty_price_document_still_counts_as_unpriced():
    # fetch_one writes nothing when no bookmaker quotes the fixture, but a quote carrying
    # no usable corner line DOES write a doc with an empty `odds` map. Treating that as
    # done would mean never looking again at exactly the fixtures whose market has not
    # opened — which is the thing this pass exists to catch.
    db = FakeDB([fx("ger-bl-1", 3)], [{"fixture_id": "ger-bl-1", "odds": {}}])
    todo, already, _, _ = run(db)
    assert [f["fixture_id"] for f, _ in todo] == ["ger-bl-1"]
    assert already == 0


def test_the_whole_week_priced_costs_nothing():
    rows = [fx(f"ger-bl-{i}", 2 + i % 4) for i in range(1, 9)]
    feed = [{"fixture_id": r["fixture_id"], "odds": {"home_over_4.5": 2.0}} for r in rows]
    todo, already, _, _ = run(FakeDB(rows, feed))
    assert todo == []
    assert already == 8


# --- the window ----------------------------------------------------------------------

def test_it_starts_beyond_the_hourly_pass_so_the_two_never_overlap():
    # The hourly pass reaches one day out. Anything inside that is its job, and paying for
    # it here would be paying twice on the same day.
    db = FakeDB([fx("ger-bl-near", 0), fx("ger-bl-edge", 2), fx("ger-bl-far", 5)], [])
    got = [f["fixture_id"] for f, _ in run(db, from_days=1, days=6)[0]]
    assert "ger-bl-near" not in got
    assert got == ["ger-bl-edge", "ger-bl-far"]


def test_it_does_not_reach_past_the_window():
    db = FakeDB([fx("ger-bl-in", 5), fx("ger-bl-out", 9)], [])
    assert [f["fixture_id"] for f, _ in run(db, days=6)[0]] == ["ger-bl-in"]


def test_soonest_first_so_a_cap_keeps_what_kicks_off_next():
    rows = [fx("ger-bl-late", 6), fx("ger-bl-soon", 2), fx("ger-bl-mid", 4)]
    todo, _, _, _ = run(FakeDB(rows, []), limit=2)
    assert [f["fixture_id"] for f, _ in todo] == ["ger-bl-soon", "ger-bl-mid"]


def test_the_limit_is_a_ceiling_on_calls():
    rows = [fx(f"ger-bl-{i}", 2) for i in range(1, 30)]
    todo, _, _, _ = run(FakeDB(rows, []), limit=5)
    assert len(todo) == 5


def test_a_league_filter_narrows_it():
    db = FakeDB([fx("ger-bl-1", 3, "ger-bl"), fx("esp-ll-1", 3, "esp-ll")], [])
    got = [f["fixture_id"] for f, _ in run(db, leagues=["esp-ll"])[0]]
    assert got == ["esp-ll-1"]


# --- what cannot be asked for ---------------------------------------------------------

def test_a_fixture_with_no_numeric_provider_id_is_skipped_not_guessed():
    # The provider is asked by ITS id. A fixture whose id cannot be resolved to one would
    # be a call made against nothing, charged all the same.
    bad = {"fixture_id": "friendly-xyz", "league_id": "ger-bl",
           "date": (NOW + timedelta(days=3)).isoformat()}
    db = FakeDB([bad, fx("ger-bl-9", 3)], [])
    assert [f["fixture_id"] for f, _ in run(db)[0]] == ["ger-bl-9"]


def test_nothing_in_the_window_is_an_empty_list_not_an_error():
    assert run(FakeDB([], [])) == ([], 0)


def test_the_feed_is_only_asked_about_fixtures_in_the_window():
    # A query with no fixture filter would walk the whole collection to answer a question
    # about eight rows.
    db = FakeDB([fx("ger-bl-1", 3)], [])
    run(db)
    assert db.odds_feed.queries, "the feed was never consulted"
    assert "fixture_id" in db.odds_feed.queries[0]


# --- aiming the budget ----------------------------------------------------------------
#
# A run on 23 Nov 2026 spent all 120 calls, priced 48, reported `capped: true` — and left
# every one of that weekend's twenty streak picks without a price, because the ceiling was
# spent in date order on games nobody had an angle on.

def test_a_fixture_the_board_recommends_is_reached_before_a_sooner_one():
    rows = [fx("ger-bl-soon", 2), fx("ger-bl-later", 5)]
    todo, _, preferred, _ = run(FakeDB(rows, []), limit=1, prefer={"ger-bl-later"})
    assert [f["fixture_id"] for f, _ in todo] == ["ger-bl-later"]
    assert preferred == 1


def test_the_preferred_ones_keep_their_own_date_order():
    rows = [fx("ger-bl-a", 5), fx("ger-bl-b", 3), fx("ger-bl-c", 2)]
    todo, _, _, _ = run(FakeDB(rows, []), prefer={"ger-bl-a", "ger-bl-b"})
    assert [f["fixture_id"] for f, _ in todo] == ["ger-bl-b", "ger-bl-a", "ger-bl-c"]


def test_nothing_is_dropped_by_preferring_it_is_only_reordered():
    rows = [fx(f"ger-bl-{i}", 2 + i) for i in range(5)]
    plain = {f["fixture_id"] for f, _ in run(FakeDB(rows, []))[0]}
    aimed = {f["fixture_id"] for f, _ in run(FakeDB(rows, []), prefer={"ger-bl-3"})[0]}
    assert plain == aimed


def test_no_preference_leaves_the_order_exactly_as_it_was():
    rows = [fx("ger-bl-late", 6), fx("ger-bl-soon", 2), fx("ger-bl-mid", 4)]
    for p in (None, set()):
        todo, _, preferred, _ = run(FakeDB(rows, []), prefer=p)
        assert [f["fixture_id"] for f, _ in todo] == ["ger-bl-soon", "ger-bl-mid", "ger-bl-late"]
        assert preferred == 0


def test_a_preferred_fixture_that_already_has_a_price_is_still_skipped():
    # Aiming decides the ORDER, never whether a fixture is paid for twice.
    rows = [fx("ger-bl-1", 3)]
    db = FakeDB(rows, [{"fixture_id": "ger-bl-1", "odds": {"total_over_9.5": 1.9}}])
    todo, already, preferred, _ = run(db, prefer={"ger-bl-1"})
    assert todo == [] and already == 1 and preferred == 0


# --- scanning often without paying for it every time ----------------------------------
#
# An unopened corner market used to leave no trace, so every run re-asked every one of
# them at a call apiece: 72 of 120 calls on 23 Nov 2026 went on markets that were not
# open. Running four times a day would have spent that four times over. The stamp is what
# makes "scan as soon as it opens" affordable.

def ago(hours):
    return (NOW - timedelta(hours=hours)).isoformat()


def checked(fid, hours_ago, checks=1):
    return {"fixture_id": fid, "odds": {}, "checked_at": ago(hours_ago), "checks": checks}


def test_a_market_asked_about_an_hour_ago_is_not_asked_again():
    db = FakeDB([fx("ger-bl-1", 3)], [checked("ger-bl-1", 1)])
    todo, _, _, recent = run(db)
    assert todo == [] and recent == 1


def test_once_it_is_due_it_is_asked_again():
    # Three days out the gap is twelve hours; thirteen hours ago is due.
    db = FakeDB([fx("ger-bl-1", 3)], [checked("ger-bl-1", 13)])
    todo, _, _, recent = run(db)
    assert [f["fixture_id"] for f, _ in todo] == ["ger-bl-1"] and recent == 0


def test_a_fixture_nobody_has_ever_asked_about_goes_straight_in():
    db = FakeDB([fx("ger-bl-1", 3)], [])
    todo, _, _, recent = run(db)
    assert len(todo) == 1 and recent == 0


def test_the_gap_tightens_as_kick_off_approaches():
    # Books open corner markets late, so a game tomorrow is worth asking about often and
    # one next week is not.
    assert recheck_after_hours(12) < recheck_after_hours(36)
    assert recheck_after_hours(36) < recheck_after_hours(72)
    assert recheck_after_hours(72) <= recheck_after_hours(200)


def test_a_fixture_asked_repeatedly_with_nothing_to_show_backs_off():
    # Some competitions are never quoted at all. Without this they burn a call every run
    # for a week.
    assert recheck_after_hours(72, checks=RECHECK_GIVE_UP) == 24
    db = FakeDB([fx("ger-bl-1", 3)], [checked("ger-bl-1", 13, checks=RECHECK_GIVE_UP)])
    assert run(db)[0] == []


def test_backing_off_stops_once_the_game_is_close():
    # Whatever it has answered before, a game tomorrow gets asked again: that is when the
    # market actually opens.
    assert recheck_after_hours(12, checks=99) == 2
    db = FakeDB([fx("ger-bl-1", 0.5)], [checked("ger-bl-1", 3, checks=99)])
    assert [f["fixture_id"] for f, _ in run(db, from_days=0)[0]] == ["ger-bl-1"]


def test_a_priced_fixture_is_skipped_by_price_not_by_the_stamp():
    # The two reasons must stay distinguishable: one says "done", the other "not yet".
    db = FakeDB([fx("ger-bl-1", 3)],
                [{"fixture_id": "ger-bl-1", "odds": {"total_over_9.5": 1.9},
                  "checked_at": ago(99), "checks": 9}])
    todo, already, _, recent = run(db)
    assert todo == [] and already == 1 and recent == 0


def test_unreadable_stamps_do_not_strand_a_fixture_forever():
    # Stored junk must mean "ask", never "never ask again".
    for bad in (None, "", "not a date", 12345):
        db = FakeDB([fx("ger-bl-1", 3)],
                    [{"fixture_id": "ger-bl-1", "odds": {}, "checked_at": bad}])
        assert len(run(db)[0]) == 1, bad
