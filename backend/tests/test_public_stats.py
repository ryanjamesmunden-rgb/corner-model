"""The stats are public — all of them. Two SCREENS are not.

THE LINE HAS MOVED TWICE AND THIS FILE IS THE RECORD OF BOTH. It was first how many ROWS a
reader got: three signed out, six signed in, the rest stripped. Then it became which
COLUMNS: every row public, the probability, fair price, edge and tier held back. It is now
neither — the boards and the fixture page are public in full, numbers included.

WHAT IS SOLD IS /value-board AND THE BETS BOARD. The value board is the ranked list of live
prices the model disagrees with; the Bets board is the weekend's slips. Everything else is
the evidence for those two, and evidence nobody can check sells nothing.

A FAIR PRICE IS AN EV, AND THAT WAS SAID BEFORE THE CHANGE WAS MADE. A reader holding a
bookmaker's price does one division and has the edge. So publishing the fair price while
withholding `ev` would have been a lock with the key beside it, and the decision taken was
the coherent one: the edge is public, the finished list of where it currently sits is not.

WHAT THESE GUARD NOW:

  - Every row reaches a signed-out reader, with every number on it. A regression to a trim
    or a strip is a silent loss of the thing that does the selling.
  - The fixture page is public too, curve included — it was gated by the same switch.
  - The two paid screens stay hard walls. Not previewed, not blurred: 401/402 at the door,
    because a blurred value board is an empty screen rather than a taste.
  - The MECHANISM survives unused. _preview and _blur_model still work, so the decision is
    one line to reverse, and the tests that pin their behaviour are kept for that reason.
  - What describes WHAT HAPPENED stays public — the streaks, the records, the form.
"""
import os
import sys

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "test_corner_model")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import server  # noqa: E402

SIGNED_OUT = {"user_id": server.PUBLIC_USER_ID}
SIGNED_IN = {"user_id": "u1"}
MEMBER = {"user_id": "u2", "member": True}


class Res:
    """Just enough of a Response to collect the headers _preview writes."""

    def __init__(self):
        self.headers = {}


def rows(n):
    return [{"name": f"T{i}", "line": 4, "prob": 70.0 + i, "fair_odds": 1.4,
             "ev": 3.2, "tier": "strong", "streak": {"length": 9},
             "projection": {"prob": 70.0, "fair_odds": 1.4, "games": 20},
             "angles": [{"kind": "mismatch", "prob": 66.0, "label": "5+ corners"}]}
            for i in range(n)]


class TestEveryRowIsPublic:
    def test_a_signed_out_reader_gets_the_whole_board(self):
        out = server._preview(rows(40), SIGNED_OUT, Res())
        assert len(out) == 40, "the board was trimmed — the rows are what does the selling"

    def test_and_so_does_a_signed_in_one(self):
        # There is nothing left for an account alone to unlock on a board, so the two are
        # deliberately the same. An account still buys saved fixtures, slips and the group.
        assert len(server._preview(rows(40), SIGNED_IN, Res())) == 40

    def test_nobody_is_previewed_any_more(self):
        # The strip under the board reads these headers. X-Preview false is what tells it
        # there is nothing withheld to advertise, so it draws no wall.
        res = Res()
        server._preview(rows(40), SIGNED_OUT, res)
        assert res.headers["X-Total-Rows"] == "40"
        assert res.headers["X-Preview"] == "false"
        assert "X-Readable-Rows" not in res.headers

    def test_a_member_is_not_previewed_at_all(self):
        res = Res()
        out = server._preview(rows(40), MEMBER, res)
        assert res.headers["X-Preview"] == "false"
        assert all("blurred" not in r for r in out)


class TestEveryModelNumberNowReachesEverybody:
    def test_a_signed_out_reader_gets_the_model_numbers(self):
        # The reversal. Each of these was stripped until the boards were opened up, and a
        # regression here would look identical from the UI to a quiet day.
        out = server._preview(rows(3), SIGNED_OUT, Res())
        for r in out:
            for field in ("prob", "fair_odds", "ev", "tier"):
                assert field in r, f"{field} was stripped — the boards are meant to be open"
            assert "blurred" not in r

    def test_the_nested_places_too(self):
        # A probability under `projection` was blurred by the same pass that blurred the
        # top level, so it is the same switch and needs the same guard.
        out = server._preview(rows(3), SIGNED_OUT, Res())
        for r in out:
            assert r["projection"]["prob"] == 70.0
            assert r["projection"]["fair_odds"] == 1.4
            assert all("prob" in a for a in r["angles"])

    def test_the_blur_itself_still_works(self):
        # KEPT DELIBERATELY. _blur is no longer reached, because _row_limit returns None
        # for everyone — but it is one line from being reached again, and a mechanism that
        # rotted while unused would fail on the day it was needed.
        blurred = server._blur(rows(1)[0])
        for field in server.BLURRED_FIELDS:
            assert field not in blurred
        assert blurred["blurred"] is True

    def test_what_happened_is_left_alone(self):
        # The point of the change: the record is public. If this starts failing, the board
        # has become a wall again by another route.
        out = server._preview(rows(3), SIGNED_OUT, Res())
        for r in out:
            assert r["name"]
            assert r["line"] == 4
            assert r["streak"]["length"] == 9
            assert r["projection"]["games"] == 20

    def test_a_member_keeps_every_number(self):
        out = server._preview(rows(3), MEMBER, Res())
        for r in out:
            assert r["prob"] is not None
            assert r["ev"] == 3.2
            assert r["tier"] == "strong"


def model():
    return {"markets": [{"key": "home_over_4.5", "label": "Over 4.5", "line": 4.5,
                         "group": "home", "prob": 71.5, "fair_odds": 1.4, "ev": 2.1,
                         "tier": "strong", "book_odds": 1.5}],
            "lambdas": {"home": 5.4, "away": 4.1, "total": 9.5},
            "distribution": {"total": [{"k": 9, "p": 0.1}]},
            "recent": [{"won": 6}]}


class TestTheFixturePageWithholdsTheSameThings:
    def test_no_market_number_survives(self):
        out = server._blur_model(model())
        m = out["markets"][0]
        for field in ("prob", "fair_odds", "ev", "tier", "book_odds"):
            assert field not in m, f"{field} survived on a market"

    def test_the_market_still_exists_and_is_labelled(self):
        # A shorter table would read as a thinner model rather than a withheld one, and the
        # reader would not know there was anything to buy.
        m = server._blur_model(model())["markets"][0]
        assert m["label"] == "Over 4.5"
        assert m["line"] == 4.5
        assert m["group"] == "home"

    def test_the_curve_goes_with_the_numbers(self):
        # A pmf is the percentages drawn. Leaving it while stripping the column would be a
        # lock with the key beside it.
        out = server._blur_model(model())
        assert "distribution" not in out
        assert "lambdas" not in out

    def test_it_says_it_is_blurred_so_the_page_can_draw_a_lock(self):
        # Without this the page cannot tell "withheld" from "no price typed yet", and a
        # locked board looks like an empty one.
        assert server._blur_model(model())["blurred"] is True

    def test_everything_describing_what_happened_stays(self):
        assert server._blur_model(model())["recent"] == [{"won": 6}]

    def test_junk_is_returned_unchanged_rather_than_crashing(self):
        assert server._blur_model(None) is None
        assert server._blur_model("nope") == "nope"


class TestTheGateIsOnTheServer:
    def test_the_fixture_page_is_open(self):
        # NOT A GREP OVER THE SOURCE, and the earlier version of this test is why. It
        # asserted `'user.get("member")' in src`, which kept passing after the gate was
        # removed because the COMMENT explaining the removal contains that same string. A
        # test that a comment can satisfy is not a test.
        import inspect
        src = inspect.getsource(server.fixture_detail)
        body = "\n".join(l for l in src.splitlines() if not l.strip().startswith("#"))
        assert "full = True" in body, \
            "the fixture model is gated again — say so deliberately and move this test"

    def test_the_bets_board_stays_a_hard_wall_too(self):
        # The weekend's slips, which is the other half of what is actually sold. Public
        # boards are the evidence; this is the thing being tested on them.
        import inspect
        params = inspect.signature(server.bets_this_week).parameters
        assert any(getattr(p.default, "dependency", None) is server.require_member
                   for p in params.values()), \
            "the Bets board is no longer members-only"

    def test_the_value_board_stays_a_hard_wall(self):
        # It is not a board of records with numbers on top; it IS the numbers, ranked. A
        # blurred version of it would be an empty screen, so it stays require_member.
        import inspect
        src = inspect.getsource(server.value_board)
        assert "require_member" in inspect.signature(server.value_board).parameters \
            or "require_member" in src
