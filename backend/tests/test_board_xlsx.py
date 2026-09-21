"""The fill-in sheet has to point its formulas at the columns it labelled.

A SPREADSHEET FAILS QUIETLY IN A WAY CODE DOES NOT. Insert a column, and every EV formula
below still evaluates — against the wrong cell. There is no exception, no red cell, nothing
in a recalculation to catch it. The sheet just multiplies the odds by the wrong number and
prints a verdict with full confidence, and the only way to notice is to work an EV out by
hand and compare.

So these tests read the workbook back and check the arithmetic against the HEADERS rather
than against the column letters the builder happens to use: find the column called "Book",
find the one carrying the probability, and assert the EV formula multiplies those two. That
way moving a column is free and mislabelling one is caught.

The three sheets do not share a layout — Streaks has two extra columns and no fair price —
which is exactly the condition under which one of them drifts.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "tools"))

openpyxl = pytest.importorskip("openpyxl")
board_xlsx = pytest.importorskip("board_xlsx")


def fixture_row(**kw):
    row = {"name": "Middlesbrough", "league_name": "Championship", "line": 6,
           "next_fixture": {"opponent": "Stoke City", "is_home": True,
                            "date": "2026-09-16T18:45:00Z"}}
    row.update(kw)
    return row


PAYLOAD = {
    "within_days": 3, "data_age_hours": 4,
    "streaks": [fixture_row(hits=5, settled=5, window=5, voids=0, hit_rate=100.0,
                            avg=7.4, streak={"length": 5})],
    "mismatches": [fixture_row(team_for=6.8, opp_conceded=7.1, prob=61.2, fair_odds=1.63)],
    "chase": [fixture_row(**{"lambda": 5.9, "consistency": 4, "consistency_of": 5,
                             "opp_fh_rate": 62.0, "prob": 70.1, "fair_odds": 1.43,
                             "book_odds": 1.83})],
}


@pytest.fixture(scope="module")
def wb(tmp_path_factory):
    out = tmp_path_factory.mktemp("board") / "board.xlsx"
    board_xlsx.build(PAYLOAD, out)
    return openpyxl.load_workbook(out)


def columns(ws):
    """Header text -> column letter, read off row 1."""
    return {ws.cell(row=1, column=c).value: ws.cell(row=1, column=c).column_letter
            for c in range(1, ws.max_column + 1)}


# The probability each sheet's EV is computed against, named by its header. Streaks has no
# model probability at all — its "Hit %" is a strike rate over five games — and that
# difference is the single most dangerous thing in this workbook, so it is stated here.
PROB_HEADER = {"Streaks": "Hit %", "Mismatches": "Prob", "Chase": "Prob"}


class TestTheEvFormulaMultipliesTheRightTwoCells:
    @pytest.mark.parametrize("sheet", ["Streaks", "Mismatches", "Chase"])
    def test_ev_is_book_times_prob_minus_one(self, wb, sheet):
        ws = wb[sheet]
        col = columns(ws)
        book, prob, ev = col["Book"], col[PROB_HEADER[sheet]], col["EV"]
        formula = ws[f"{ev}2"].value
        assert f"{book}2" in formula, \
            f"{sheet}: EV does not reference the Book column ({book}) — {formula}"
        assert f"{prob}2" in formula, \
            f"{sheet}: EV multiplies the wrong column; " \
            f"{PROB_HEADER[sheet]} is in {prob} — {formula}"
        assert f"{book}2*{prob}2-1" in formula.replace(" ", ""), \
            f"{sheet}: EV is not odds*prob-1 — {formula}"

    @pytest.mark.parametrize("sheet", ["Streaks", "Mismatches", "Chase"])
    def test_a_blank_price_leaves_ev_blank(self, wb, sheet):
        # Without the guard an empty Book cell reads as 0, and 0*p-1 is -100% — printed in
        # red beside every unpriced row, which looks like a strong call AGAINST the bet
        # rather than an absence of information.
        ws = wb[sheet]
        formula = ws[f"{columns(ws)['EV']}2"].value
        book = columns(ws)["Book"]
        assert f'{book}2=""' in formula.replace(" ", ""), \
            f"{sheet}: no empty-price guard — an unpriced row will read -100% — {formula}"

    @pytest.mark.parametrize("sheet", ["Streaks", "Mismatches", "Chase"])
    def test_the_verdict_reads_the_ev_cell_and_nothing_else(self, wb, sheet):
        # A verdict typed as a value can end up saying BET beside a negative number, and
        # nothing in the file would contradict it.
        ws = wb[sheet]
        col = columns(ws)
        verdict = ws[f"{col['Verdict']}2"].value
        assert verdict.startswith("=IF("), f"{sheet}: Verdict is not a formula"
        assert f"{col['EV']}2" in verdict, \
            f"{sheet}: Verdict does not read the EV column ({col['EV']}) — {verdict}"
        assert str(board_xlsx.BET_AT) in verdict, \
            f"{sheet}: Verdict does not use the BET_AT threshold — {verdict}"


def evaluate(ws, formula, row, typed=None):
    """Work out what Excel would print, for the two formula shapes this builder writes.

    STANDING IN FOR A RECALCULATION. LibreOffice cannot be run here, so "the formula
    references the right cells" is as far as the tests above get — and a formula can
    reference exactly the right cells and still be wrong about what to do with them. This
    substitutes the sheet's own values and does the arithmetic, so a wrong sign, a missing
    -1, or a threshold facing the wrong way is caught by a number rather than by eye.

    Narrow on purpose: it understands IFERROR, IF, comparison and blankness, and nothing
    else. A formula it cannot read raises rather than quietly passing.
    """
    def cell(ref):
        if ref in typed:
            return typed[ref]
        v = ws[ref].value
        return "" if v is None else v

    typed = typed or {}
    f = _tighten(formula.lstrip("="))
    if f.startswith("IFERROR("):
        f = f[len("IFERROR("):f.rindex(',"")')]
    return _eval(f, cell, row)


def _tighten(formula):
    """Drop whitespace OUTSIDE quoted strings. Inside one it is part of the answer.

    Stripping it everywhere turned "awaiting price" into "awaitingprice" and failed two
    tests that were describing correct behaviour — the evaluator's bug, not the sheet's.
    """
    out, quoted = "", False
    for ch in formula:
        if ch == '"':
            quoted = not quoted
        if quoted or not ch.isspace():
            out += ch
    return out


def _eval(expr, cell, row):
    import re
    if expr.startswith("IF("):
        cond, then, other = _split_args(expr[3:-1])
        return _eval(then, cell, row) if _truth(cond, cell, row) else _eval(other, cell, row)
    if expr.startswith('"') and expr.endswith('"'):
        return expr[1:-1]
    # A bare arithmetic expression over cell references: B2*I2-1
    def sub(m):
        v = cell(m.group(0))
        return repr(float(v)) if v != "" else "0"
    return eval(re.sub(r"[A-Z]+\d+", sub, expr))  # noqa: S307 — our own strings only


def _truth(cond, cell, row):
    import re
    m = re.match(r'^([A-Z]+\d+)(=|>=|<=|>|<)(.+)$', cond)
    assert m, f"cannot read condition: {cond}"
    ref, op, rhs = m.groups()
    left = cell(ref)
    right = rhs[1:-1] if rhs.startswith('"') else float(rhs)
    if isinstance(right, str) or left == "":
        return (left == right) if op == "=" else False
    left = float(left)
    return {"=": left == right, ">=": left >= right, "<=": left <= right,
            ">": left > right, "<": left < right}[op]


def _split_args(body):
    """Split IF(a,b,c) on its top-level commas, ignoring those inside nested calls."""
    out, depth, cur, quoted = [], 0, "", False
    for ch in body:
        if ch == '"':
            quoted = not quoted
        if not quoted:
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
            elif ch == "," and depth == 0:
                out.append(cur)
                cur = ""
                continue
        cur += ch
    out.append(cur)
    assert len(out) == 3, f"expected three IF arguments, got {len(out)}: {body}"
    return out


class TestTheArithmeticIsRight:
    """What the sheet would actually print, not just which cells it points at."""

    def ev_and_verdict(self, wb, sheet, price):
        ws = wb[sheet]
        col = columns(ws)
        typed = {f"{col['Book']}2": price}
        ev = evaluate(ws, ws[f"{col['EV']}2"].value, 2, typed)
        verdict = evaluate(ws, ws[f"{col['Verdict']}2"].value, 2,
                           {**typed, f"{col['EV']}2": ev})
        return ev, verdict

    def test_a_real_price_produces_the_edge_the_model_published(self, wb):
        # Hull City 5+, model probability 70.1%, offered at 1.83.
        # 1.83 * 0.701 - 1 = +28.3%, which is what the board itself reports for this row.
        ev, verdict = self.ev_and_verdict(wb, "Chase", 1.83)
        assert round(ev * 100, 1) == 28.3
        assert verdict == "BET"

    def test_an_unpriced_row_says_so_instead_of_reading_minus_one_hundred(self, wb):
        ev, verdict = self.ev_and_verdict(wb, "Chase", "")
        assert ev == ""
        assert verdict == "awaiting price"

    def test_the_fair_price_itself_is_a_zero_edge(self, wb):
        # Taking exactly the model's price is break-even, and must not read as a bet.
        ev, verdict = self.ev_and_verdict(wb, "Chase", 1 / 0.701)
        assert abs(ev) < 1e-9
        assert verdict == "thin"

    def test_a_short_price_is_no_bet(self, wb):
        # 1.20 against a 70.1% chance is -15.9%. A verdict that said anything else here
        # would be the sheet actively recommending a loser.
        ev, verdict = self.ev_and_verdict(wb, "Chase", 1.20)
        assert round(ev * 100, 1) == -15.9
        assert verdict == "no bet"

    def test_the_bet_threshold_is_a_boundary_not_an_approximation(self, wb):
        ws = wb["Chase"]
        prob = ws[f"{columns(ws)['Prob']}2"].value
        at = (1 + board_xlsx.BET_AT) / prob          # exactly BET_AT edge
        assert self.ev_and_verdict(wb, "Chase", at)[1] == "BET"
        assert self.ev_and_verdict(wb, "Chase", at * 0.999)[1] == "thin"

    @pytest.mark.parametrize("sheet", ["Streaks", "Mismatches"])
    def test_the_other_sheets_do_the_same_arithmetic(self, wb, sheet):
        ws = wb[sheet]
        prob = ws[f"{columns(ws)[PROB_HEADER[sheet]]}2"].value
        ev, verdict = self.ev_and_verdict(wb, sheet, 2.0)
        assert round(ev, 6) == round(2.0 * prob - 1, 6)
        assert verdict == ("BET" if ev >= board_xlsx.BET_AT else
                           "thin" if ev >= 0 else "no bet")


class TestTheColumnsSayWhatTheyHold:
    def test_streaks_carries_no_fair_price(self, wb):
        # A run of five clears is not a probability the model priced. Turning "5 of 5" into
        # a fair price would invent a number the board never produced, and it would be the
        # most confident number on the sheet.
        ws = wb["Streaks"]
        assert ws[f"{columns(ws)['Fair']}2"].value == "n/a"

    def test_streaks_warns_that_its_ev_is_indicative(self, wb):
        ws = wb["Streaks"]
        text = " ".join(str(ws.cell(row=r, column=1).value or "")
                        for r in range(2, ws.max_row + 1))
        assert "not a model probability" in text.lower() or "indicative" in text.lower(), \
            "the Streaks sheet computes EV off a five-game strike rate and must say so"

    @pytest.mark.parametrize("sheet", ["Streaks", "Mismatches", "Chase"])
    def test_the_book_column_is_the_one_marked_for_typing(self, wb, sheet):
        # Yellow is the convention for "you fill this in" and it is the only instruction the
        # sheet gives. A Book column that is not yellow is a sheet nobody knows how to use.
        ws = wb[sheet]
        cell = ws[f"{columns(ws)['Book']}2"]
        assert cell.fill.fgColor.rgb in ("FFFFFF00", "00FFFF00"), \
            f"{sheet}: the Book column is not marked as an input"

    def test_a_price_already_entered_is_written_in(self, wb):
        # /prices holds real book odds for a handful of fixtures. Leaving those blank would
        # ask for a number the site already has.
        ws = wb["Chase"]
        assert ws[f"{columns(ws)['Book']}2"].value == 1.83


class TestTheFixtureReadsTheRightWayRound:
    def test_home_fixtures_put_the_team_first(self, wb):
        ws = wb["Streaks"]
        col = columns(ws)
        assert ws[f"{col['Fixture']}2"].value == "Middlesbrough v Stoke City"
        assert ws[f"{col['Venue']}2"].value == "Home"

    def test_away_fixtures_put_the_opponent_first(self):
        # Swapping these silently moves the angle onto the other team — the sheet still
        # reads plausibly, and the bet is on the wrong side of the game.
        row = fixture_row(name="NEC Nijmegen")
        row["next_fixture"] = {"opponent": "Ajax", "is_home": False,
                               "date": "2026-09-17T17:00:00Z"}
        assert board_xlsx.fixture(row) == ("Ajax v NEC Nijmegen", "Away")

    def test_kick_offs_are_london_not_utc(self):
        # 17:00 UTC in September is 18:00 in London. An hour out is the difference between
        # a price you can still take and a game that has started.
        row = fixture_row()
        row["next_fixture"]["date"] = "2026-09-17T17:00:00Z"
        assert board_xlsx.kickoff(row) == "Thu 17 Sep 18:00"


class TestEmptyBoards:
    def test_a_board_with_no_rows_still_writes_a_sheet(self, tmp_path):
        # The workflow refuses to upload an empty workbook, but the builder must not be the
        # thing that decides that by crashing.
        out = tmp_path / "empty.xlsx"
        counts = board_xlsx.build({"streaks": [], "mismatches": [], "chase": []}, out)
        assert counts == {"streaks": 0, "mismatches": 0, "chase": 0}
        book = openpyxl.load_workbook(out)
        assert book.sheetnames == ["Read me", "Streaks", "Mismatches", "Chase"]

    def test_a_missing_board_key_is_not_an_error(self, tmp_path):
        # /api/share/rows returns {} when the backend is asleep, and the builder is asked
        # for the file before anything has checked.
        out = tmp_path / "none.xlsx"
        assert board_xlsx.build({}, out)["chase"] == 0
