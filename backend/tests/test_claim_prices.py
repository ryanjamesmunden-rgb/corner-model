"""A price for every claim: at posting, at the close, and never one that was not takeable.

WHAT THESE GUARD. A price attached to the record turns a hit rate into a P/L, so a wrong
one is a wrong P/L. The failures that would flatter the record — a price fetched after
kick-off, yesterday's price on today's claim, a typed price overwritten by a fetched one —
are each pinned here. So is the one that would mislead without flattering: an under
quietly priced as if it were an over.
"""
import asyncio
import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import claim_prices as cp  # noqa: E402

NOW = datetime(2026, 11, 22, 12, 0, tzinfo=timezone.utc)


def iso(dt):
    return dt.isoformat()


def claim(**kw):
    base = {"subject": "team", "direction": "over", "line": 5, "is_home": False,
            "fixture_id": "f1", "kickoff": iso(NOW + timedelta(hours=3))}
    return {**base, **kw}


def feed(price=2.30, hours_ago=1, key="away_over_4.5"):
    return {"fixture_id": "f1", "odds": {key: price}, "books": {key: "Pinnacle"},
            "fetched_at": iso(NOW - timedelta(hours=hours_ago))}


class TestPostPrice:
    def test_the_fetched_price_is_frozen_with_its_book(self):
        out = cp.post_price(claim(), feed(), NOW)
        assert out == {"post_price": 2.30, "post_book": "Pinnacle",
                       "post_fetched_at": feed()["fetched_at"]}

    def test_five_plus_is_the_four_point_five_line(self):
        # "5+" is struck on Over 4.5; a key one line out prices a different bet
        assert cp.market_for(claim(line=5))[0] == "away_over_4.5"
        assert cp.market_for(claim(line=5, is_home=True))[0] == "home_over_4.5"

    def test_no_price_after_kick_off(self):
        out = cp.post_price(claim(kickoff=iso(NOW - timedelta(minutes=5))), feed(), NOW)
        assert "post_price" not in out and out["post_why"] == "posted after kick-off"

    def test_yesterdays_price_is_not_one_a_reader_could_take(self):
        out = cp.post_price(claim(), feed(hours_ago=13), NOW)
        assert "post_price" not in out and "12 hours" in out["post_why"]

    def test_an_under_is_refused_not_priced_as_an_over(self):
        out = cp.post_price(claim(direction="under"), feed(), NOW)
        assert "post_price" not in out and "under" in out["post_why"]

    def test_a_market_nobody_quoted_says_so(self):
        out = cp.post_price(claim(line=7), feed(), NOW)
        assert "post_price" not in out and "away_over_6.5" in out["post_why"]


class TestClosePrice:
    def test_the_closing_capture_wins(self):
        closing = {"odds": {"away_over_4.5": 2.10}, "books": {"away_over_4.5": "Bet365"},
                   "minutes_before_kickoff": 40}
        out = cp.close_price(claim(), closing, feed(2.30))
        assert out["close_price"] == 2.10 and out["close_source"] == "closing capture"

    def test_the_last_pre_match_fetch_stands_in_when_it_is_late_enough(self):
        ko = NOW + timedelta(hours=2)
        out = cp.close_price(claim(kickoff=iso(ko)), None, feed(2.25, hours_ago=0))
        assert out["close_price"] == 2.25 and out["close_source"] == "last pre-match fetch"

    def test_a_fetch_from_the_morning_is_not_the_close(self):
        ko = NOW + timedelta(hours=8)
        out = cp.close_price(claim(kickoff=iso(ko)), None, feed(hours_ago=0))
        assert "close_price" not in out

    def test_a_fetch_after_kick_off_is_never_the_close(self):
        ko = NOW - timedelta(hours=1)
        out = cp.close_price(claim(kickoff=iso(ko)), None, feed(hours_ago=0))
        assert "close_price" not in out


class TestSummary:
    def rows(self):
        return [
            {"result": "win", "price": 2.0, "stake": 2, "post_price": 2.2, "close_price": 2.0},
            {"result": "loss", "post_price": 1.9, "close_price": 2.0},
            {"result": "win", "close_price": 1.5},
            {"result": "pending", "post_price": 3.0},
        ]

    def test_each_price_is_totalled_over_its_own_rows(self):
        s = cp.priced_summary(self.rows())
        assert s["price"] == {"priced": 1, "unpriced": 2, "units": 2.0, "roi": 100.0}
        assert s["post_price"]["priced"] == 2 and s["post_price"]["units"] == 0.2
        assert s["close_price"]["priced"] == 3 and s["close_price"]["units"] == 0.5

    def test_typed_stake_is_used_only_for_the_typed_price(self):
        # the fetched columns are 1u flat: nobody staked anything at a fetched price
        s = cp.priced_summary([{"result": "loss", "price": 2.0, "stake": 3,
                                "post_price": 2.0}])
        assert s["price"]["units"] == -3.0 and s["post_price"]["units"] == -1.0

    def test_clv_needs_both_prices(self):
        s = cp.priced_summary(self.rows())
        assert s["clv"]["measured"] == 2
        assert s["clv"]["beat_close"] == 1

    def test_nothing_priced_is_none_not_zero(self):
        s = cp.priced_summary([{"result": "win"}])
        assert s["post_price"]["units"] is None and s["post_price"]["unpriced"] == 1


# --- wired into the site -------------------------------------------------------------

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "test_corner_model")
import server  # noqa: E402
from tests.test_value_board import FakeCollection  # noqa: E402


class _DB:
    def __init__(self, feed_docs=(), closing=()):
        self.odds_feed = FakeCollection(list(feed_docs), "fixture_id")
        self.odds_closing = FakeCollection(list(closing), "fixture_id")


def run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def test_a_frozen_claim_gets_the_live_fetched_price(monkeypatch):
    now = datetime.now(timezone.utc)
    f = {"fixture_id": "f1", "odds": {"away_over_4.5": 2.4}, "books": {"away_over_4.5": "1xBet"},
         "fetched_at": (now - timedelta(minutes=30)).isoformat()}
    monkeypatch.setattr(server, "db", _DB(feed_docs=[f]))
    entries = [claim(kickoff=(now + timedelta(hours=5)).isoformat()),
               claim(fixture_id="nope", kickoff=(now + timedelta(hours=5)).isoformat())]
    run(server._stamp_post_prices(entries))
    assert entries[0]["post_price"] == 2.4 and entries[0]["post_book"] == "1xBet"
    assert "post_price" not in entries[1] and entries[1]["post_why"]
    # and the typed-price field is left alone
    assert "price" not in entries[0]


def test_graded_rows_pick_up_the_closing_price(monkeypatch):
    closing = {"fixture_id": "f1", "odds": {"away_over_4.5": 2.05},
               "books": {"away_over_4.5": "Bet365"}, "minutes_before_kickoff": 30}
    monkeypatch.setattr(server, "db", _DB(closing=[closing]))
    rows = run(server._with_close_prices([{**claim(), "result": "win"}]))
    assert rows[0]["close_price"] == 2.05


class _BoardsDB:
    def __init__(self, **colls):
        names = ("streak_snapshots", "mismatch_snapshots", "perfect_snapshots",
                 "value_snapshots", "posted_angles", "teams", "odds_feed", "odds_closing")
        for n in names:
            key = "team_id" if n == "teams" else "fixture_id"
            setattr(self, n, FakeCollection(list(colls.get(n, [])), key))

    def __getitem__(self, name):
        return getattr(self, name)


def _entry(fid, team, opp, line=5, **kw):
    return {"team_id": team, "name": team, "league_id": "eng-pl", "fixture_id": fid,
            "kickoff": "2026-11-21T15:00:00+00:00", "opponent": opp, "is_home": True,
            "line": line, "direction": "over", "subject": "team", "prob": 0.6, **kw}


def _played(opp, corners):
    return {"opponent": opp, "date": "2026-11-21", "home": True,
            "corners_for": corners, "corners_against": 4}


def test_the_card_is_its_own_section_and_every_section_is_priced(monkeypatch):
    streak = {"tag": "2026-11-20", "entries": [
        _entry("f1", "A", "X", qualified=True, post_price=2.0),       # on the card, lands
        _entry("f2", "B", "Y", qualified=False, post_price=2.5)]}     # board only, misses
    value = {"tag": "2026-11-20", "entries": [_entry("f3", "C", "Z", price=2.2)]}
    teams = [{"team_id": "A", "real_matches": [_played("X", 7)]},
             {"team_id": "B", "real_matches": [_played("Y", 2)]},
             {"team_id": "C", "real_matches": [_played("Z", 6)]}]
    closing = [{"fixture_id": "f1", "odds": {"home_over_4.5": 1.8}, "books": {}}]
    monkeypatch.setattr(server, "db", _BoardsDB(streak_snapshots=[streak],
                                                value_snapshots=[value], teams=teams,
                                                odds_closing=closing))
    boards = {b["key"]: b for b in run(server.board_records())}
    card = boards["card"]
    assert card["settled"] == 1 and card["landed"] == 1
    assert card["prices"]["post_price"]["units"] == 1.0
    assert card["prices"]["close_price"]["units"] == 0.8
    assert boards["streaks"]["settled"] == 2
    assert boards["streaks"]["prices"]["post_price"]["units"] == 0.0      # +1.0 -1.0
    # the value board's frozen price is a FETCHED price, so it is reported as post_price
    v = boards["value"]["prices"]
    assert v["post_price"]["units"] == 1.2 and v["price"]["priced"] == 0
