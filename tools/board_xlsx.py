"""Turn a board run into the fill-in EV sheet.

WHY A SPREADSHEET AT ALL. The model produces a fair price; a bookmaker's price is the one
thing it cannot know, and without it there is no EV and no bet. That gap was being closed
by hand in a spreadsheet built from scratch each week. This writes the same sheet straight
off the board, so the only manual step left is the one that actually needs a human: typing
what the market is offering.

THE EV COLUMN IS A FORMULA, NEVER A NUMBER. Type a price and the edge appears. A sheet
that arrives with EV already computed for the three rows that happen to be priced, and
blank cells for the rest, is a dead document — this one does the arithmetic as it is
filled in.

Reads the JSON that /api/share/rows returns; writes one .xlsx. No network, no state.
"""
import json
import sys
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.worksheet.datavalidation import DataValidation

FONT = "Arial"
LON = ZoneInfo("Europe/London")

HEAD_FILL = PatternFill("solid", fgColor="1F3864")
HEAD_FONT = Font(name=FONT, bold=True, color="FFFFFF", size=10)
INPUT_FILL = PatternFill("solid", fgColor="FFFF00")     # the one column you type in
BLUE = Font(name=FONT, color="0000FF", size=10)         # a hardcoded input
BLACK = Font(name=FONT, size=10)
BOLD = Font(name=FONT, bold=True, size=10)
GREY = Font(name=FONT, size=10, italic=True, color="808080")
WARN = Font(name=FONT, size=9, italic=True, color="C00000")
THIN = Side(style="thin", color="BFBFBF")
BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)

# The bar the model's own tiering uses, so the sheet and the site agree about what counts
# as an edge rather than each having an opinion.
BET_AT = 0.05


def kickoff(row):
    nf = row.get("next_fixture") or {}
    try:
        dt = datetime.fromisoformat((nf.get("date") or "").replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(LON).strftime("%a %d %b %H:%M")
    except Exception:
        return (nf.get("date") or "")[:10]


def fixture(row):
    nf = row.get("next_fixture") or {}
    name = row.get("name") or row.get("team") or "?"
    opp = nf.get("opponent", "?")
    home = name if nf.get("is_home") else opp
    away = opp if nf.get("is_home") else name
    return f"{home} v {away}", ("Home" if nf.get("is_home") else "Away")


def header(ws, headers):
    for c, h in enumerate(headers, start=1):
        cell = ws.cell(row=1, column=c, value=h)
        cell.fill, cell.font = HEAD_FILL, HEAD_FONT
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        cell.border = BORDER
    ws.freeze_panes = "A2"


def widths(ws, spec):
    for col, w in spec.items():
        ws.column_dimensions[col].width = w


def type_label(row):
    """"Team over", "Match under" — the column last week's hand-built workbook filtered on.

    Without it the three kinds sit in one sheet looking like one kind. "under 9 match
    corners" and "9+ team corners" are not variants of each other; they are opposite bets
    on different quantities, and the same two characters mean different things in each.
    """
    subj = "Match" if row.get("subject") == "match" else "Team"
    return f"{subj} {'under' if row.get('direction') == 'under' else 'over'}"


def bet_label(row):
    """"6+ team corners" / "under 9 match corners" — the claim, spelled out."""
    what = "match" if row.get("subject") == "match" else "team"
    lab = row.get("line_label") or (f"{row.get('line')}+")
    return f"{lab} {what} corners"


def wire(ws, first, last, book, prob, ev, verdict, void=None):
    """The fill-in half: a yellow price column, an EV formula, a verdict that follows it.

    IFERROR AND AN EMPTY-STRING GUARD, because a blank price would otherwise read as a
    -100% edge on every unpriced row — a number that looks like a strong call against the
    bet rather than an absence of information.

    The verdict is a formula for the same reason the EV is: a typed one can end up saying
    BET beside a negative number, and nothing would catch it.
    """
    for r in range(first, last + 1):
        b, p = f"{book}{r}", f"{prob}{r}"
        ws[b].fill, ws[b].font, ws[b].number_format = INPUT_FILL, BLUE, "0.00"
        ws[b].border = BORDER
        # AN UNDER ON A WHOLE LINE PUSHES when the count lands exactly on it, and the
        # stake comes back. Without that term every under reads a few points worse than
        # it is — the same correction the backend's own `ev` makes.
        push = f"+{void}{r}" if void else ""
        ws[f"{ev}{r}"] = f'=IFERROR(IF({b}="","",{b}*{p}{push}-1),"")'
        ws[f"{ev}{r}"].number_format = "0.0%;[Red]-0.0%;-"
        ws[f"{ev}{r}"].font = BLACK
        ws[f"{verdict}{r}"] = (
            f'=IF({ev}{r}="","awaiting price",'
            f'IF({ev}{r}>={BET_AT},"BET",IF({ev}{r}>=0,"thin","no bet")))')
        ws[f"{verdict}{r}"].font = BLACK
        ws[f"{verdict}{r}"].alignment = Alignment(horizontal="center")
    if last >= first:
        dv = DataValidation(type="decimal", operator="greaterThan", formula1="1",
                            allow_blank=True, showErrorMessage=True,
                            errorTitle="Decimal odds",
                            error="Enter decimal odds above 1.00 (e.g. 1.83), "
                                  "not fractional.")
        ws.add_data_validation(dv)
        dv.add(f"{book}{first}:{book}{last}")


def readme(wb, data, generated):
    ws = wb.active
    ws.title = "Read me"
    ws["A1"] = f"Corner board — {generated:%A %d %B %Y}"
    ws["A1"].font = Font(name=FONT, bold=True, size=14)
    age = data.get("data_age_hours")
    lines = [
        "",
        "Combined is every team-over line with whatever each board says about it, so a",
        "line carried by more than one is visible without reading three sheets side by",
        "side. The 'On' count is NOT three models agreeing — see the note on that sheet.",
        "",
        "The three source sheets answer different questions and are kept apart:",
        "   Streaks      this team keeps clearing this line — a run, nothing about the opponent",
        "   Mismatches   this attack against THIS defence — about the fixture, not the form",
        "   Chase        this team goes behind early and chases — about game state",
        "",
        "HOW TO USE IT",
        "   Type the bookmaker's decimal odds into the yellow 'Book' column.",
        "   EV and Verdict calculate themselves. Nothing else needs touching.",
        f"   Verdict: BET at {BET_AT:.0%}+ edge, 'thin' between 0 and {BET_AT:.0%}, 'no bet' below 0.",
        "",
        "WHAT THE COLUMNS MEAN",
        "   Line       the model's line, e.g. 6 means 6+ team corners",
        "   Fair       the model's price. Beat it and there is an edge; that is all EV measures.",
        "   Prob       the model's probability for that line",
        "   Lambda     expected corner count for that team in that game",
        "   L5         how many of the last 5 games cleared the line",
        "   Opp 1H     how often the opponent scores first, which is what starts a chase",
        "",
        "WHAT THIS IS NOT",
        "   Not a bet list. A fair price with no book price beside it is a lead to check.",
        "   The lines are the model's, not a bookmaker's — check the market offers that",
        "   line at that price before backing it.",
        "   Kick-offs are London time.",
        "",
        f"Source: corner-model board, {generated:%Y-%m-%d %H:%M} UTC, next "
        f"{data.get('within_days', '?')} days. Data was "
        f"{age if age is not None else 'of unknown age'} hours old when this was built.",
        "Book prices that are already filled in came from prices entered on /prices;",
        "every other Book cell is blank because no price has been recorded.",
    ]
    for i, line in enumerate(lines, start=2):
        ws.cell(row=i, column=1, value=line).font = (
            BOLD if line.strip() and not line.startswith("   ") else BLACK)
    widths(ws, {"A": 100})


def streaks_sheet(wb, rows):
    """All three kinds of streak, priced off the model rather than off the strike rate.

    THE BUG THIS REPLACES, and it was pointing the verdict column the wrong way on almost
    every row. The EV formula was wired to the "Hit %" column — the last-five strike rate
    — so a 5-from-5 run read 100% and EV came out as `Book - 1`. Any price above 1.00
    therefore computed as a large edge and the Verdict said BET. The sheet carried a red
    warning calling it "indicative only", which is not the same as not doing it.

    The model's own probability for that exact line on that exact fixture was sitting in
    the same row the whole time, on `projection` — the readable export has always printed
    it as "model 1.23 (81.4%)". The earlier note here said a fair price would be inventing
    a number the board never produced; that was wrong. `_streak_projection` produces it,
    and EV now reads it.

    Hit % stays as a column. It is a useful thing to see — how often this exact claim
    landed in the last five — it just must not be the number an edge is computed from.
    """
    ws = wb.create_sheet("Streaks")
    header(ws, ["Kick-off", "League", "Team", "Venue", "Fixture", "Type", "Bet",
                "Run (L5)", "In a row", "Hit %", "Avg", "Lambda", "Prob", "Void",
                "Fair", "Book", "EV", "Verdict"])
    for r, row in enumerate(rows, start=2):
        fx, venue = fixture(row)
        proj = row.get("projection") or {}
        run = f"{row.get('hits', 0)}/{row.get('settled', row.get('window', 0))}"
        if row.get("voids"):
            run += f"+{row['voids']}v"
        for c, v in enumerate([kickoff(row), row.get("league_name", ""), row.get("name"),
                               venue, fx, type_label(row), bet_label(row), run,
                               (row.get("streak") or {}).get("length")], start=1):
            cell = ws.cell(row=r, column=c, value=v)
            cell.font = BOLD if c == 3 else BLACK
            cell.border = BORDER
        hit = row.get("hit_rate")
        ws.cell(row=r, column=10, value=None if hit is None else hit / 100).number_format = "0.0%"
        ws.cell(row=r, column=10).font = GREY       # grey: information, not an input to EV
        ws.cell(row=r, column=11, value=row.get("avg")).number_format = "0.00"
        ws.cell(row=r, column=11).font = BLACK
        # The model's numbers, blue because they come from the export rather than a formula.
        for c, v, fmt in ((12, proj.get("lambda"), "0.00"),
                          (15, proj.get("fair_odds"), "0.00")):
            ws.cell(row=r, column=c, value=v).number_format = fmt
            ws.cell(row=r, column=c).font = BLUE
        for c, v in ((13, proj.get("prob")), (14, proj.get("void_prob"))):
            ws.cell(row=r, column=c,
                    value=None if v is None else v / 100).number_format = "0.0%"
            ws.cell(row=r, column=c).font = BLUE
        # A price already entered on /prices arrives filled in, like the chase sheet.
        if proj.get("book_odds") is not None:
            ws.cell(row=r, column=16, value=proj["book_odds"])
    last = len(rows) + 1
    # EV off column M (the model's Prob), crediting the push in N (Void) back.
    wire(ws, 2, last, "P", "M", "Q", "R", void="N")
    ws.cell(row=last + 2, column=1,
            value="EV is computed from the model's own probability (Prob), not from the "
                  "last-five strike rate (Hit %). A 5/5 run reads 100% in Hit % and that "
                  "is five games, not a probability — it is shown for context only. "
                  "Filter the Type column: a team over and a match under are opposite "
                  "bets on different quantities.").font = WARN
    widths(ws, {"A": 17, "B": 18, "C": 21, "D": 7, "E": 38, "F": 12, "G": 22, "H": 9,
                "I": 9, "J": 8, "K": 8, "L": 8, "M": 8, "N": 7, "O": 7, "P": 8,
                "Q": 9, "R": 13})


def mismatches_sheet(wb, rows):
    ws = wb.create_sheet("Mismatches")
    header(ws, ["Kick-off", "League", "Team", "Venue", "Fixture", "Line", "Wins /g",
                "Opp concedes /g", "Prob", "Fair", "Book", "EV", "Verdict"])
    for r, row in enumerate(rows, start=2):
        fx, venue = fixture(row)
        for c, v in enumerate([kickoff(row), row.get("league_name", ""),
                               row.get("name") or row.get("team"), venue, fx,
                               row.get("line")], start=1):
            cell = ws.cell(row=r, column=c, value=v)
            cell.font = BOLD if c == 3 else BLACK
            cell.border = BORDER
        for c, v in ((7, row.get("team_for")), (8, row.get("opp_conceded")),
                     (10, row.get("fair_odds"))):
            ws.cell(row=r, column=c, value=v).number_format = "0.00"
            ws.cell(row=r, column=c).font = BLACK
        prob = row.get("prob")
        ws.cell(row=r, column=9, value=None if prob is None else prob / 100).number_format = "0.0%"
        ws.cell(row=r, column=9).font = BLACK
    wire(ws, 2, len(rows) + 1, "K", "I", "L", "M")
    widths(ws, {"A": 17, "B": 18, "C": 21, "D": 7, "E": 38, "F": 6, "G": 9, "H": 15,
                "I": 8, "J": 7, "K": 8, "L": 9, "M": 13})


def chase_sheet(wb, rows):
    ws = wb.create_sheet("Chase")
    header(ws, ["Kick-off", "League", "Team", "Venue", "Fixture", "Line", "Lambda", "L5",
                "Opp 1H", "Prob", "Fair", "Book", "EV", "Verdict"])
    for r, row in enumerate(rows, start=2):
        fx, venue = fixture(row)
        for c, v in enumerate([kickoff(row), row.get("league_name", ""), row.get("name"),
                               venue, fx, row.get("line")], start=1):
            cell = ws.cell(row=r, column=c, value=v)
            cell.font = BOLD if c == 3 else BLACK
            cell.border = BORDER
        ws.cell(row=r, column=7, value=row.get("lambda")).number_format = "0.00"
        ws.cell(row=r, column=7).font = BLACK
        ws.cell(row=r, column=8,
                value=f"{row.get('consistency','?')}/{row.get('consistency_of','?')}")
        ws.cell(row=r, column=8).font = BLACK
        ws.cell(row=r, column=8).alignment = Alignment(horizontal="center")
        fh = row.get("opp_fh_rate")
        ws.cell(row=r, column=9, value=None if fh is None else fh / 100).number_format = "0%"
        ws.cell(row=r, column=9).font = BLACK
        prob = row.get("prob")
        ws.cell(row=r, column=10, value=None if prob is None else prob / 100).number_format = "0.0%"
        ws.cell(row=r, column=10).font = BLACK
        ws.cell(row=r, column=11, value=row.get("fair_odds")).number_format = "0.00"
        ws.cell(row=r, column=11).font = BLACK
        # A price already entered on /prices is written in, so the sheet arrives with the
        # few rows that CAN be judged already judged.
        if row.get("book_odds") is not None:
            ws.cell(row=r, column=12, value=row["book_odds"])
    wire(ws, 2, len(rows) + 1, "L", "J", "M", "N")
    widths(ws, {"A": 17, "B": 18, "C": 21, "D": 7, "E": 38, "F": 6, "G": 9, "H": 7,
                "I": 8, "J": 8, "K": 7, "L": 8, "M": 9, "N": 13})


def combine_key(row):
    """What makes two rows from different boards the SAME bet.

    The fixture, the side and the line. Not the team name alone: a team appears on three
    boards for three different lines, and joining on the name would stack a 4+ claim onto
    a 6+ one and present the pair as agreement.
    """
    nf = row.get("next_fixture") or {}
    fid = nf.get("fixture_id") or fixture(row)[0]
    return (fid, row.get("name") or row.get("team") or "?", row.get("line"))


def combined_sheet(wb, data):
    """Every team-over line, with whatever each board has to say about it in one row.

    WHY THIS SHEET EXISTS. The other three answer different questions and are kept apart
    on purpose — but a line that shows up on more than one of them is the thing somebody
    opens a spreadsheet to find, and finding it meant reading three sheets side by side
    and joining them by eye.

    TEAM OVERS ONLY, AND THAT IS NOT A TRIM. The chase and mismatch boards produce nothing
    else, so a match-under streak has no counterpart to be joined to; putting it here
    would be a row with two empty thirds pretending to be a comparison. The Streaks sheet
    still carries every kind.

    THE BOARDS COLUMN IS NOT A CONFIRMATION COUNT, and this is the one thing that could
    make the sheet worse than the three it summarises. shareText's own note on the angle
    menu says it plainly: a streak and a mismatch are both driven partly by how many
    corners the team wins, so a strong corner side appears on both WHOEVER it plays.
    Reading "3" as three independent models agreeing is reading one fact three times.

    What is genuinely additional is the OPPONENT half — how much this particular defence
    concedes, measured on its own games — and the chase catalyst, which is about game
    state rather than about either side's corner count. Those two columns are where the
    extra information actually is, and the sheet says so next to them.
    """
    rows = {}

    def slot(row):
        k = combine_key(row)
        if k not in rows:
            fx, venue = fixture(row)
            rows[k] = {"kickoff": kickoff(row), "league": row.get("league_name", ""),
                       "fixture": fx, "team": row.get("name") or row.get("team"),
                       "venue": venue, "line": row.get("line"),
                       "boards": [], "streak": None, "run": None, "in_row": None,
                       "opp_conceded": None, "opp_fh": None, "chase_l5": None,
                       "lam": None, "prob": None, "fair": None, "book": None,
                       "model_src": None}
        return rows[k]

    for row in data.get("streaks") or []:
        # Only the cut the other two boards also produce; see the docstring.
        if row.get("subject") == "match" or row.get("direction") == "under":
            continue
        r = slot(row)
        r["boards"].append("streak")
        settled = row.get("settled") or row.get("window") or 0
        r["run"] = f"{row.get('hits', 0)}/{settled}" if settled else None
        r["in_row"] = (row.get("streak") or {}).get("length")
        proj = row.get("projection") or {}
        if proj.get("prob") is not None and r["prob"] is None:
            r.update(prob=proj.get("prob"), fair=proj.get("fair_odds"),
                     lam=proj.get("lambda"), model_src="streak")
            if proj.get("book_odds") is not None:
                r["book"] = proj["book_odds"]

    for row in data.get("mismatches") or []:
        r = slot(row)
        r["boards"].append("mismatch")
        r["opp_conceded"] = row.get("opp_conceded")
        if row.get("prob") is not None and r["prob"] is None:
            r.update(prob=row.get("prob"), fair=row.get("fair_odds"),
                     model_src="mismatch")

    for row in data.get("chase") or []:
        r = slot(row)
        r["boards"].append("chase")
        r["opp_fh"] = row.get("opp_fh_rate")
        if row.get("consistency_of"):
            r["chase_l5"] = f"{row.get('consistency')}/{row.get('consistency_of')}"
        # THE CHASE BOARD'S MODEL WINS WHERE THERE IS ONE. It is the only source carrying
        # lambda, probability, fair price AND any price already entered, so taking it last
        # and letting it overwrite keeps the most complete row rather than the first one.
        if row.get("prob") is not None:
            r.update(prob=row.get("prob"), fair=row.get("fair_odds"),
                     lam=row.get("lambda"), model_src="chase")
        if row.get("book_odds") is not None:
            r["book"] = row["book_odds"]

    out = sorted(rows.values(),
                 key=lambda r: (-len(r["boards"]), -(r["prob"] or 0), r["kickoff"]))

    ws = wb.create_sheet("Combined", 1)
    header(ws, ["Kick-off", "League", "Fixture", "Team", "Venue", "Line", "Boards",
                "On", "Run", "In a row", "Opp concedes /g", "Opp 1H", "Chase L5",
                "Lambda", "Prob", "Fair", "Book", "EV", "Verdict", "Model from"])
    for r, row in enumerate(out, start=2):
        for c, v in enumerate([row["kickoff"], row["league"], row["fixture"], row["team"],
                               row["venue"], row["line"], len(row["boards"]),
                               ", ".join(row["boards"]), row["run"], row["in_row"]],
                              start=1):
            cell = ws.cell(row=r, column=c, value=v)
            cell.font = BOLD if c == 4 else BLACK
            cell.border = BORDER
        ws.cell(row=r, column=11, value=row["opp_conceded"]).number_format = "0.00"
        ws.cell(row=r, column=11).font = BLACK
        fh = row["opp_fh"]
        ws.cell(row=r, column=12,
                value=None if fh is None else fh / 100).number_format = "0%"
        ws.cell(row=r, column=12).font = BLACK
        ws.cell(row=r, column=13, value=row["chase_l5"]).font = BLACK
        ws.cell(row=r, column=13).alignment = Alignment(horizontal="center")
        ws.cell(row=r, column=14, value=row["lam"]).number_format = "0.00"
        ws.cell(row=r, column=14).font = BLUE
        prob = row["prob"]
        ws.cell(row=r, column=15,
                value=None if prob is None else prob / 100).number_format = "0.0%"
        ws.cell(row=r, column=15).font = BLUE
        ws.cell(row=r, column=16, value=row["fair"]).number_format = "0.00"
        ws.cell(row=r, column=16).font = BLUE
        if row["book"] is not None:
            ws.cell(row=r, column=17, value=row["book"])
        ws.cell(row=r, column=20, value=row["model_src"]).font = GREY

    last = len(out) + 1
    wire(ws, 2, last, "Q", "O", "R", "S")
    ws.cell(row=last + 2, column=1,
            value="'On' counts how many boards carry this line. It is NOT three models "
                  "agreeing: a streak and a mismatch are both driven partly by how many "
                  "corners the team wins, so a strong corner side appears on both "
                  "whoever it plays. The genuinely additional columns are 'Opp concedes' "
                  "— measured on the OPPONENT's games — and 'Opp 1H', which is about game "
                  "state rather than either side's corner count. A row on one board with "
                  "a leaky opponent can be a better bet than a row on three without "
                  "one.").font = WARN
    ws.cell(row=last + 3, column=1,
            value="Team OVER lines only, because the chase and mismatch boards produce "
                  "nothing else. Every other kind of streak is on the Streaks "
                  "sheet.").font = WARN
    widths(ws, {"A": 17, "B": 18, "C": 36, "D": 20, "E": 7, "F": 6, "G": 6, "H": 24,
                "I": 8, "J": 9, "K": 15, "L": 8, "M": 9, "N": 8, "O": 8, "P": 7,
                "Q": 8, "R": 9, "S": 13, "T": 11})
    return len(out)


def build(data, out_path, generated=None):
    generated = generated or datetime.now(timezone.utc)
    wb = Workbook()
    readme(wb, data, generated)
    combined = combined_sheet(wb, data)
    streaks_sheet(wb, data.get("streaks") or [])
    mismatches_sheet(wb, data.get("mismatches") or [])
    chase_sheet(wb, data.get("chase") or [])
    wb.save(out_path)
    return {"combined": combined,
            "streaks": len(data.get("streaks") or []),
            "mismatches": len(data.get("mismatches") or []),
            "chase": len(data.get("chase") or [])}


if __name__ == "__main__":
    src = sys.argv[1] if len(sys.argv) > 1 else "rows.json"
    out = sys.argv[2] if len(sys.argv) > 2 else "board.xlsx"
    with open(src) as f:
        counts = build(json.load(f), out)
    print(f"wrote {out}: " + ", ".join(f"{v} {k}" for k, v in counts.items()))
