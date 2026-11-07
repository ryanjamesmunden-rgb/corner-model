"""The two spreadsheets the site hands over.

WHAT THESE GUARD. A downloaded CSV outlives every screen it came from. It gets opened next
week, sorted, pasted into a P&L and acted on long after anybody could check it against the
site — so a column that is mislabelled, silently absent, or carrying a number the reader
is not entitled to is worse here than anywhere else in the app.

Three failures specifically:

  - A LADDER COLUMN NAMED FOR THE WRONG BET. build_markets stores `line: 4.5` and prices
    P(X >= 5). The channel says "5+". A column headed 4.5 beside the probability of five
    or more invites somebody to price a different bet than the one the number describes.
  - A HEADER TAKEN FROM THE FIRST ROW. Every other CSV in server.py does that, and it is
    right only while all rows share a shape. These rows do not: a match-total row carries
    the total ladder and a team row carries the team ladder, so `extrasaction="ignore"`
    would drop whole columns and the file would still look complete.
  - PRICES REACHING A NON-MEMBER. /value-board is behind require_member because a ranked
    list of live prices the model disagrees with is the finished product. The same content
    in a CSV is the same product.
"""
import os
import sys

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "test_corner_model")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import asyncio  # noqa: E402
import csv  # noqa: E402
import io  # noqa: E402

import pytest  # noqa: E402

import server  # noqa: E402


def run(coro):
    """Sync runner that leaves the process-wide loop alone — see test_value_board."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def parse(resp):
    """A CSV response -> (header, rows as dicts)."""
    body = resp.body.decode() if hasattr(resp, "body") else str(resp)
    rdr = csv.DictReader(io.StringIO(body))
    return rdr.fieldnames or [], list(rdr)


MEMBER = {"member": True, "user_id": "u1"}
VISITOR = {"user_id": "u2"}


# --- the header is the union, not the first row -------------------------------------

class TestEveryColumnSurvives:
    def test_a_later_rows_extra_column_is_not_dropped(self):
        # The exact shape of the projections export: the total row carries total-ladder
        # columns the team rows never have.
        head, rows = parse(server._csv_response(
            [{"team": "A", "p5plus": 70.0}, {"team": "T", "p10plus": 55.0}], "x.csv"))
        assert "p5plus" in head and "p10plus" in head
        assert rows[0]["p10plus"] == "" and rows[1]["p5plus"] == ""

    def test_column_order_follows_first_appearance(self):
        head, _ = parse(server._csv_response(
            [{"b": 1, "a": 2}, {"c": 3}], "x.csv"))
        assert head == ["b", "a", "c"]

    def test_no_rows_is_a_sentence_not_an_empty_file(self):
        body = server._csv_response([], "x.csv").body.decode()
        assert body.strip() == "no rows"

    def test_the_filename_is_offered_as_a_download(self):
        resp = server._csv_response([{"a": 1}], "corner-model-projections.csv")
        assert "attachment" in resp.headers["Content-Disposition"]
        assert "corner-model-projections.csv" in resp.headers["Content-Disposition"]


# --- the projected corners list ------------------------------------------------------

def install_projections(monkeypatch, *, odds=None, source="manual"):
    """One fixture, two teams, a stubbed model with a three-group ladder."""
    fx = {"fixture_id": "fx1", "date": "2026-11-08T15:00:00Z", "league_id": "eng-ch",
          "league_name": "Championship", "home": "Derby", "away": "Bolton",
          "lambda_home": 5.6, "lambda_away": 4.8, "lambda_total": 10.4,
          "league_avg_total": 10.1, "corner_edge": 1.03,
          "home_games": 14, "away_games": 13, "is_cup": False, "cross_league": False}

    async def fake_projections(days=7, league_id=None):
        return {"fx1": dict(fx)}

    async def fake_base():
        return {"by_id": {"t-derby": {"team_id": "t-derby", "league_id": "eng-ch"},
                          "t-bolton": {"team_id": "t-bolton", "league_id": "eng-ch"}},
                "leagues": {"eng-ch": {"league_id": "eng-ch", "name": "Championship"}}}

    async def fake_priced(ids):
        return {"fx1": {"odds": odds or {}, "source": source}} if odds else {}

    class FakeFixtures:
        def find(self, q=None, proj=None):
            class C:
                async def to_list(self, n):
                    return [{"fixture_id": "fx1", "home_team_id": "t-derby",
                             "away_team_id": "t-bolton"}]
            return C()

    monkeypatch.setattr(server, "_fixture_projections", fake_projections)
    monkeypatch.setattr(server, "_browse_base", fake_base)
    monkeypatch.setattr(server, "_odds_for_many", fake_priced)
    monkeypatch.setattr(server, "db", type("D", (), {"fixtures": FakeFixtures()})())
    monkeypatch.setattr(server, "fixture_model_from",
                        lambda h, a, lg, o, **k: {
                            "lambdas": {"home": 5.6, "away": 4.8, "total": 10.4},
                            "confidence": {"score": 72, "label": "High"},
                            "markets": [
                                {"group": "home", "line": 4.5, "prob": 70.1,
                                 "fair_odds": 1.43, "book_odds": o.get("home_over_4.5"),
                                 "ev": 8.2 if o.get("home_over_4.5") else None},
                                {"group": "away", "line": 6.5, "prob": 66.0,
                                 "fair_odds": 1.52, "book_odds": None, "ev": None},
                                {"group": "total", "line": 9.5, "prob": 58.3,
                                 "fair_odds": 1.72, "book_odds": None, "ev": None},
                            ]})


class TestTheProjectedCornersList:
    def test_it_is_one_row_per_subject(self, monkeypatch):
        # A fixture is not one bet: the home side's corners, the away side's and the match
        # total are three claims with three ladders, and flattening them into one row is
        # what forces a reader to remember which columns belong to whom.
        install_projections(monkeypatch)
        _head, rows = parse(run(server.export_projections_csv(user=MEMBER)))
        assert [r["subject"] for r in rows] == ["home", "away", "total"]
        assert rows[0]["team"] == "Derby" and rows[0]["opponent"] == "Bolton"
        assert rows[1]["team"] == "Bolton" and rows[1]["opponent"] == "Derby"
        assert rows[2]["team"] == "Derby v Bolton"

    def test_the_ladder_column_is_named_for_the_bet_not_the_stored_line(self, monkeypatch):
        # 4.5 stored, P(X>=5) priced, "5+" posted. The column says 5plus.
        install_projections(monkeypatch)
        head, rows = parse(run(server.export_projections_csv(user=MEMBER)))
        # 4.5 stored -> 5+ offered, so the column is p5plus.
        assert "p5plus" in head and "fair5plus" in head
        assert rows[0]["p5plus"] == "70.1" and rows[0]["fair5plus"] == "1.43"
        # Each group keeps its own numbering: 6.5 -> 7+, 9.5 -> 10+.
        assert rows[1]["p7plus"] == "66.0"
        assert rows[2]["p10plus"] == "58.3"
        # AND NOTHING IS NAMED FOR THE RAW STORED LINE. A column headed p4.5plus beside
        # the probability of five-or-more is the exact confusion this naming prevents,
        # and no bet in this model is struck on a half.
        assert not [c for c in head if "." in c], head
        assert "p4plus" not in head, "the 4.5 line must not be named for four"

    def test_every_row_carries_the_fixture_and_the_sample_behind_it(self, monkeypatch):
        install_projections(monkeypatch)
        _head, rows = parse(run(server.export_projections_csv(user=MEMBER)))
        r = rows[0]
        assert r["kickoff"].startswith("2026-11-08")
        assert r["league"] == "Championship" and r["fixture_id"] == "fx1"
        assert r["home_games"] == "14" and r["away_games"] == "13"
        assert r["confidence"] == "72" and r["confidence_label"] == "High"
        assert r["lambda_total"] == "10.4"

    def test_a_member_gets_the_price_and_the_ev(self, monkeypatch):
        install_projections(monkeypatch, odds={"home_over_4.5": 1.91})
        head, rows = parse(run(server.export_projections_csv(user=MEMBER)))
        assert "book5plus" in head and "ev5plus" in head
        assert rows[0]["book5plus"] == "1.91" and rows[0]["ev5plus"] == "8.2"
        assert rows[0]["price_source"] == "manual"

    def test_a_visitor_gets_the_model_and_no_prices_at_all(self, monkeypatch):
        # /value-board is members-only because a ranked list of live prices the model
        # disagrees with IS the product. The same content in a CSV is the same product.
        install_projections(monkeypatch, odds={"home_over_4.5": 1.91})
        head, rows = parse(run(server.export_projections_csv(user=VISITOR)))
        assert "p5plus" in head and "fair5plus" in head, "the model's own numbers stay"
        for col in head:
            assert not col.startswith("book"), col
            assert not col.startswith("ev"), col
        assert "price_source" not in head
        # And no price leaks into a value somewhere else on the row.
        assert "1.91" not in ",".join(rows[0].values())

    def test_a_fixture_whose_teams_are_missing_is_skipped_not_half_rendered(self, monkeypatch):
        install_projections(monkeypatch)

        class Empty:
            def find(self, q=None, proj=None):
                class C:
                    async def to_list(self, n):
                        return []
                return C()
        monkeypatch.setattr(server, "db", type("D", (), {"fixtures": Empty()})())
        body = run(server.export_projections_csv(user=MEMBER)).body.decode()
        assert body.strip() == "no rows"

    def test_an_empty_board_says_so_rather_than_erroring(self, monkeypatch):
        async def nothing(days=7, league_id=None):
            return {}
        monkeypatch.setattr(server, "_fixture_projections", nothing)
        body = run(server.export_projections_csv(user=MEMBER)).body.decode()
        assert body.strip() == "no rows"

    def test_the_window_is_clamped(self, monkeypatch):
        seen = {}

        async def record(days=7, league_id=None):
            seen["days"] = days
            return {}
        monkeypatch.setattr(server, "_fixture_projections", record)
        run(server.export_projections_csv(days=9999, user=MEMBER))
        assert seen["days"] == 21
        run(server.export_projections_csv(days=-5, user=MEMBER))
        assert seen["days"] == 1


# --- what is worth tracking for long-term profit -------------------------------------
#
# These two columns are the ones that are about BEHAVIOUR rather than about the model, and
# both come straight out of the October P&L: a month that finished +48.7 units with 76% of
# it on one afternoon, and a ladder habit that returned -4.4% over 112 units while single
# bets returned +13.0% over 512.5.

def claim(day="2026-11-01", fid="fx1", units=None, kickoff=None):
    return {"day": day, "fixture_id": fid, "units": units,
            "kickoff": kickoff or f"{day}T15:00:00Z"}


class TestTheDisciplineColumns:
    def test_a_ladder_on_one_fixture_is_counted_on_every_row_of_it(self):
        # 59% of these won or lost as a block, so a ladder is one opinion with several
        # stakes. The column is what makes that visible in a pivot.
        rows = server._add_discipline_columns(
            [claim(fid="fx1"), claim(fid="fx1"), claim(fid="fx1"), claim(fid="fx2")])
        assert [r["claims_on_fixture"] for r in rows] == [3, 3, 3, 1]

    def test_a_row_with_no_fixture_resolved_counts_as_one_not_zero(self):
        # Zero would read as "no claims on this fixture", which is false of a row that is
        # itself a claim on it.
        rows = server._add_discipline_columns([claim(fid=""), claim(fid=None)])
        assert [r["claims_on_fixture"] for r in rows] == [1, 1]

    def test_the_day_total_is_the_realised_pl_for_that_day(self):
        rows = server._add_discipline_columns(
            [claim(day="2026-11-01", units=4.5), claim(day="2026-11-01", units=-1.0),
             claim(day="2026-11-02", units=2.0)])
        assert rows[0]["day_units"] == 3.5 and rows[1]["day_units"] == 3.5
        assert rows[2]["day_units"] == 2.0

    def test_one_afternoon_carrying_a_month_reads_as_one_afternoon(self):
        # The October shape: a big day beside a lot of small ones.
        rows = server._add_discipline_columns(
            [claim(day="2026-10-24", units=37.0)]
            + [claim(day=f"2026-10-{d:02d}", units=0.4) for d in range(1, 24)])
        big = next(r for r in rows if r["day"] == "2026-10-24")
        assert big["day_units"] == 37.0
        assert all(r["day_units"] == 0.4 for r in rows if r["day"] != "2026-10-24")

    def test_claims_and_units_have_different_denominators_on_purpose(self):
        # Most rows are frozen claims with no stake behind them. day_claims counts them
        # all; day_units sums only the priced ones. Conflating the two would divide a
        # day's P/L by a count that includes rows nothing was staked on.
        rows = server._add_discipline_columns(
            [claim(units=3.0), claim(units=None), claim(units=None)])
        assert rows[0]["day_claims"] == 3
        assert rows[0]["day_units"] == 3.0

    def test_a_day_with_nothing_priced_has_no_units_rather_than_zero(self):
        # Zero would read as "broke even that day", which is a claim about a result.
        rows = server._add_discipline_columns([claim(units=None), claim(units=None)])
        assert rows[0]["day_units"] is None
        assert rows[0]["day_claims"] == 2

    def test_an_empty_list_is_not_an_error(self):
        assert server._add_discipline_columns([]) == []


class TestTheTrackingExportIsGatedLikeTheRecord:
    def test_a_signed_out_visitor_is_refused(self):
        # Same gate as /results: the record lists the picks, and the picks are the product.
        import fastapi
        with pytest.raises(fastapi.HTTPException) as e:
            run(server.export_tracking_csv(user={"user_id": server.PUBLIC_USER_ID}))
        assert e.value.status_code == 401

    def test_the_window_is_clamped(self):
        # Read the WHOLE function, not a fixed slice: the docstring alone is longer than
        # the 2000 characters this first looked at, so it tested the prose and passed over
        # the code.
        src = open(os.path.join(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__))), "server.py")).read()
        body = src.split("async def export_tracking_csv", 1)[1].split("@api_router")[0]
        assert "max(1, min(weeks, 400))" in body
