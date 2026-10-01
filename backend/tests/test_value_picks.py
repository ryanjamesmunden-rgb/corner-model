"""The day's priced bets: what may be frozen, and what the card is allowed to claim.

THIS RE-ARMS A LEDGER THAT WAS DELIBERATELY SWITCHED OFF. The Daily 2 block in server.py
ends with the condition for ever turning one back on: "do not re-arm it without giving
each pick a price first — an unpriced ledger is worse than no ledger, because it looks
like evidence." So the first thing these pin is that a pick CANNOT be frozen without a
price, and that the price has to be one a person typed rather than one the seed scripts
generated as `fair_odds * rng.uniform(0.90, 1.15)` — an EV computed against that is the
model finding value in its own jitter, which on a published card is indistinguishable
from a real edge.

The second thing they pin is that every frozen pick can actually SETTLE. A bet published
on a card and then stuck pending forever is worse than one that loses: the record quietly
stops being a record. So the market mapping is tested against settlement.resolve_market
itself rather than against a copy of what it is believed to accept.
"""
import asyncio
import os
import sys
from datetime import datetime, timedelta, timezone

import pytest

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "test_corner_model")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import server  # noqa: E402
import settlement  # noqa: E402
from fastapi import HTTPException  # noqa: E402


def run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


NOW = datetime.now(timezone.utc)


def iso(hours):
    return (NOW + timedelta(hours=hours)).isoformat().replace("+00:00", "Z")


# --- a database small enough to read ------------------------------------------------

class FakeCursor:
    def __init__(self, docs):
        self._docs = docs

    def sort(self, *a, **k):
        return self

    async def to_list(self, n):
        return self._docs[:n]


class FakePicks:
    def __init__(self):
        self.docs = []

    def find(self, q=None, proj=None):
        return FakeCursor([d for d in self.docs if self._match(d, q)])

    async def find_one(self, q=None, proj=None):
        return next((d for d in self.docs if self._match(d, q)), None)

    async def insert_one(self, doc):
        self.docs.append(doc)

    @staticmethod
    def _match(doc, q):
        for k, v in (q or {}).items():
            got = doc.get(k)
            if isinstance(v, dict):
                # Only the operators share_bets actually uses — a range over the day key.
                if "$gte" in v and (got is None or got < v["$gte"]):
                    return False
                if "$lte" in v and (got is None or got > v["$lte"]):
                    return False
                if "$ne" in v and got == v["$ne"]:
                    return False
            elif got != v:
                return False
        return True


class FakeOdds:
    def __init__(self, n=1):
        self.n = n

    async def count_documents(self, q):
        return self.n


class FakeDB:
    def __init__(self, odds=1):
        self.picks = FakePicks()
        self.odds = FakeOdds(odds)


def row(fid="f1", ev=8.0, source="manual", hours=4, key="total_over_9.5",
        book=1.95, home="Home", away="Away"):
    """One value-board row, in the shape value_board actually returns."""
    return {
        "fixture_id": fid, "status": "ok", "odds_source": source,
        "home_name": home, "away_name": away, "date": iso(hours),
        "league_id": "eng-pl", "league_name": "Premier League",
        "best": {"key": key, "group": key.split("_")[0], "label": "Total Over 9.5",
                 "line": 9.5, "book_odds": book, "fair_odds": 1.63,
                 "prob": 61.5, "ev": ev, "tier": "small"},
    }


@pytest.fixture
def db(monkeypatch):
    fake = FakeDB()
    monkeypatch.setattr(server, "db", fake)
    return fake


def install(monkeypatch, rows):
    async def board(**kw):
        return rows

    monkeypatch.setattr(server, "value_board", board)


def today_of(hours):
    return server.value_pick_day(NOW + timedelta(hours=hours))


# --- the market mapping, checked against the settler itself --------------------------

class TestEveryFrozenBetCanSettle:
    def test_a_team_over_is_stored_as_the_X_plus_line_settlement_expects(self):
        m = server.value_pick_market("home_over_5.5", "Arsenal", "Leeds")
        assert m["market"] == "team_corners" and m["team"] == "Arsenal"
        # resolve_market grades team_corners as an over at line - 0.5, so a 5.5 market
        # has to be written down as 6 or every one of these settles a line too low.
        assert m["line"] == 6
        assert settlement.resolve_market(m, 6, 3) == (6.0, 5.5, "over")

    def test_and_it_grades_the_way_the_price_was_taken(self):
        m = server.value_pick_market("away_over_4.5", "Arsenal", "Leeds")
        assert m["team"] == "Leeds" and m["venue"] == "away"
        # 5 away corners clears 4.5; 4 does not.
        assert settlement.grade_pick(m, 5, 0)[0] == settlement.WON
        assert settlement.grade_pick(m, 4, 0)[0] == settlement.LOST

    def test_a_match_total_keeps_its_line_and_can_push(self):
        m = server.value_pick_market("total_over_9", "Home", "Away")
        assert m["market"] == "asian_total" and m["line"] == 9
        # Graded on the two sides summed, and a whole line lands exactly: a void, not a
        # loss. Storing this as a team line would have graded one side's corners.
        assert settlement.grade_pick(m, 5, 4)[0] == settlement.VOID
        assert settlement.grade_pick(m, 6, 4)[0] == settlement.WON

    def test_a_market_settlement_cannot_grade_is_refused_rather_than_guessed(self):
        # resolve_market's team_corners branch forces direction "over", so a team under
        # would settle as its own opposite. Freezing one would publish a bet that can
        # never be graded correctly.
        assert server.value_pick_market("home_under_4", "Home", "Away") is None
        assert server.value_pick_market("nonsense", "Home", "Away") is None
        assert server.value_pick_market("", "Home", "Away") is None


# --- what may be frozen --------------------------------------------------------------

class TestOnlyARealPricedEdgeIsFrozen:
    def test_a_priced_positive_ev_bet_is_frozen_with_its_price(self, db, monkeypatch):
        install(monkeypatch, [row(ev=8.0, book=1.95)])
        out = run(server._snapshot_value_picks(today_of(4), min_ev=0.0))
        assert out["inserted"] == 1
        p = db.picks.docs[0]
        assert p["odds"] == 1.95 and p["ev"] == 8.0
        assert p["signal"] == "value" and p["selected_by"] == server.VALUE_PICK_RULE
        assert p["status"] == settlement.PENDING

    def test_a_seeded_price_is_refused_however_good_its_edge_looks(self, db, monkeypatch):
        """THE ONE THAT WOULD PUBLISH A FICTION. A demo price is derived from the model's
        own fair odds, so the EV against it is noise that looks exactly like an edge."""
        install(monkeypatch, [row(ev=40.0, source="demo"), row(fid="f2", ev=35.0, source=None)])
        assert run(server._snapshot_value_picks(today_of(4)))["inserted"] == 0

    def test_a_bet_below_the_floor_is_not_frozen(self, db, monkeypatch):
        install(monkeypatch, [row(ev=1.0)])
        assert run(server._snapshot_value_picks(today_of(4), min_ev=5.0))["inserted"] == 0

    def test_a_game_that_has_kicked_off_is_not_frozen(self, db, monkeypatch):
        """A price on a game in progress is not a bet, and freezing one after the fact is
        how a ledger starts selecting its own winners."""
        install(monkeypatch, [row(hours=-2)])
        assert run(server._snapshot_value_picks(today_of(-2)))["inserted"] == 0

    def test_another_day_belongs_to_another_card(self, db, monkeypatch):
        install(monkeypatch, [row(hours=4)])
        assert run(server._snapshot_value_picks(today_of(4 + 48)))["inserted"] == 0

    def test_a_row_the_board_could_not_turn_into_a_bet_is_skipped(self, db, monkeypatch):
        install(monkeypatch, [{**row(), "status": "kicked_off"},
                              {**row(fid="f2"), "best": None}])
        assert run(server._snapshot_value_picks(today_of(4)))["inserted"] == 0

    def test_the_biggest_edge_goes_first_and_the_card_is_capped(self, db, monkeypatch):
        install(monkeypatch, [row(fid=f"f{i}", ev=float(i)) for i in range(10)])
        out = run(server._snapshot_value_picks(today_of(4), count=3))
        assert out["inserted"] == 3
        assert [p["ev"] for p in db.picks.docs] == [9.0, 8.0, 7.0]


class TestFreezingIsIdempotent:
    def test_running_it_twice_does_not_double_the_card(self, db, monkeypatch):
        install(monkeypatch, [row()])
        run(server._snapshot_value_picks(today_of(4)))
        assert run(server._snapshot_value_picks(today_of(4)))["inserted"] == 0
        assert len(db.picks.docs) == 1

    def test_and_a_price_that_has_moved_since_does_not_rewrite_the_record(self, db, monkeypatch):
        """The record is of the bet that was published, not of where the market ended up."""
        install(monkeypatch, [row(book=1.95, ev=8.0)])
        run(server._snapshot_value_picks(today_of(4)))
        install(monkeypatch, [row(book=1.60, ev=-2.0)])
        run(server._snapshot_value_picks(today_of(4)))
        assert db.picks.docs[0]["odds"] == 1.95

    def test_two_lines_on_one_fixture_are_two_bets_only_if_the_key_differs(self, db, monkeypatch):
        install(monkeypatch, [row(key="total_over_9.5"), row(key="home_over_5.5")])
        # Same fixture id, different market: value_board hands back one best per fixture,
        # so this only happens across runs — and when it does, they are different bets.
        assert run(server._snapshot_value_picks(today_of(4)))["inserted"] == 2


# --- the endpoint --------------------------------------------------------------------

def share(db, monkeypatch, **kw):
    monkeypatch.setattr(server, "TOOLS_TOKEN", "t0ken")
    monkeypatch.setattr(server, "_run_settlement", lambda: _noop())
    kw.setdefault("token", "t0ken")
    kw.setdefault("day", today_of(4))
    return run(server.share_bets(**kw))


async def _noop():
    return {"status": "ok"}


class TestTheCardsPayload:
    def test_it_needs_the_tools_token(self, db, monkeypatch):
        install(monkeypatch, [row()])
        monkeypatch.setattr(server, "TOOLS_TOKEN", "t0ken")
        with pytest.raises(HTTPException) as e:
            run(server.share_bets(token="wrong"))
        assert e.value.status_code == 403

    def test_it_freezes_and_returns_in_one_call(self, db, monkeypatch):
        install(monkeypatch, [row()])
        out = share(db, monkeypatch)
        assert out["frozen"] == 1 and len(out["cards"][0]["rows"]) == 1
        # Nothing can reach the card without reaching the ledger first.
        assert len(db.picks.docs) == 1

    def test_a_preview_reads_without_creating_a_record(self, db, monkeypatch):
        install(monkeypatch, [row()])
        out = share(db, monkeypatch, freeze=False)
        assert out["cards"] == [] and db.picks.docs == []

    def test_an_empty_day_says_which_kind_of_empty_it_is(self, db, monkeypatch):
        install(monkeypatch, [])
        assert "no priced bet cleared" in share(db, monkeypatch)["note"]
        db.odds.n = 0
        assert "no prices stored at all" in share(db, monkeypatch)["note"]

    def test_and_names_the_hurdle_each_price_fell_at(self, db, monkeypatch):
        """THE ONE THE FIRST REAL RUN NEEDED. "Nothing cleared the floor" was true and
        useless: a price typed for tomorrow, a seeded price and a game already kicked off
        are three different things to go and do something about."""
        install(monkeypatch, [
            row(fid="f1", source="demo"),                       # price not typed in
            row(fid="f2", hours=-1),                            # kicked off
            row(fid="f3", hours=72),                            # another day
            row(fid="f4", ev=-3.0),                             # below the floor
            row(fid="f5", key="home_under_4"),                  # cannot be settled
            {**row(fid="f6"), "status": "no_fixture", "best": None},
        ])
        out = share(db, monkeypatch, min_ev=0.0)
        assert out["cards"] == []
        assert out["drops"] == {"price not typed in": 1, "kicked off": 1, "another day": 1,
                                "below the floor": 1, "market cannot be settled": 1,
                                "no_fixture": 1}
        for phrase in ("price not typed in", "kicked off", "another day",
                       "below the floor", "market cannot be settled"):
            assert phrase in out["note"]

    def test_a_preview_still_gets_the_diagnosis_without_writing_anything(self, db, monkeypatch):
        """The preview is the run somebody dispatches BY HAND to find out why nothing is
        going out, so it is the one that most needs this — and it must still create no
        record while answering."""
        install(monkeypatch, [row(source="demo")])
        out = share(db, monkeypatch, freeze=False)
        assert out["drops"] == {"price not typed in": 1}
        assert "price not typed in" in out["note"]
        assert db.picks.docs == []

    def test_a_quiet_today_falls_forward_to_the_days_that_do_have_bets(self, db, monkeypatch):
        """Rather than silence. Each day gets its OWN card: they settle on different
        evenings, and one card mixing two days could not carry a day's result."""
        install(monkeypatch, [row(fid="f1", hours=30), row(fid="f2", hours=54)])
        out = share(db, monkeypatch, days=4)
        assert [c["day"] for c in out["cards"]] == [today_of(30), today_of(54)]
        assert out["frozen"] == 2

    def test_but_a_day_with_bets_on_it_is_never_buried_under_tomorrows(self, db, monkeypatch):
        """Today's card is the one worth posting — its prices can still be taken."""
        install(monkeypatch, [row(fid="f1", hours=4), row(fid="f2", hours=30)])
        out = share(db, monkeypatch, days=4)
        assert [c["day"] for c in out["cards"]] == [today_of(4)]

    def test_and_tomorrow_is_frozen_when_it_is_shown(self, db, monkeypatch):
        # A bet shown for tomorrow is a published bet, recorded at the price that was
        # there when it was shown. The alternative is a card nobody is accountable for.
        install(monkeypatch, [row(fid="f1", hours=30, book=1.91)])
        share(db, monkeypatch, days=3)
        assert db.picks.docs[0]["date"] == today_of(30)
        assert db.picks.docs[0]["odds"] == 1.91

    def test_an_evening_run_redraws_today_even_though_it_has_kicked_off(self, db, monkeypatch):
        """THE ONE THAT WOULD HIDE THE DAY'S RESULTS. By evening today's games no longer
        qualify — they have kicked off — so a look-ahead that only asked the shortlist
        would skip today and post tomorrow's card instead of the results."""
        install(monkeypatch, [row(fid="f1", hours=4)])
        share(db, monkeypatch)                       # morning: today is frozen
        db.picks.docs[0]["status"] = settlement.WON
        install(monkeypatch, [row(fid="f2", hours=30)])   # evening: only tomorrow qualifies
        out = share(db, monkeypatch, days=3)
        assert [c["day"] for c in out["cards"]] == [today_of(4)]
        assert out["cards"][0]["summary"]["won"] == 1

    def test_a_settled_card_carries_the_units_it_actually_won(self, db, monkeypatch):
        install(monkeypatch, [row(book=1.95)])
        share(db, monkeypatch)
        db.picks.docs[0]["status"] = settlement.WON
        out = share(db, monkeypatch)
        card = out["cards"][0]
        assert card["rows"][0]["profit"] == 0.95
        assert card["summary"]["won"] == 1 and card["summary"]["profit"] == 0.95

    def test_and_a_void_returns_the_stake_rather_than_counting_as_a_win(self, db, monkeypatch):
        install(monkeypatch, [row(key="total_over_9")])
        share(db, monkeypatch)
        db.picks.docs[0]["status"] = settlement.VOID
        card = share(db, monkeypatch)["cards"][0]
        assert card["summary"]["void"] == 1
        assert card["summary"]["won"] == 0 and card["summary"]["profit"] == 0.0
