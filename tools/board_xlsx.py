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


def wire(ws, first, last, book, prob, ev, verdict):
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
        ws[f"{ev}{r}"] = f'=IFERROR(IF({b}="","",{b}*{p}-1),"")'
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
        "Three sheets, one per section. They answer different questions and are kept apart:",
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
    ws = wb.create_sheet("Streaks")
    header(ws, ["Kick-off", "League", "Team", "Venue", "Fixture", "Line", "Run (L5)",
                "In a row", "Hit %", "Avg won", "Fair", "Book", "EV", "Verdict"])
    for r, row in enumerate(rows, start=2):
        fx, venue = fixture(row)
        run = f"{row.get('hits', 0)}/{row.get('settled', row.get('window', 0))}"
        if row.get("voids"):
            run += f"+{row['voids']}v"
        for c, v in enumerate([kickoff(row), row.get("league_name", ""), row.get("name"),
                               venue, fx, row.get("line"), run,
                               (row.get("streak") or {}).get("length")], start=1):
            cell = ws.cell(row=r, column=c, value=v)
            cell.font = BOLD if c == 3 else BLACK
            cell.border = BORDER
        hit = row.get("hit_rate")
        ws.cell(row=r, column=9, value=None if hit is None else hit / 100).number_format = "0.0%"
        ws.cell(row=r, column=9).font = BLACK
        ws.cell(row=r, column=10, value=row.get("avg")).number_format = "0.00"
        ws.cell(row=r, column=10).font = BLACK
        # NO FAIR PRICE HERE, and that is honest rather than an omission. A streak is a run
        # of outcomes, not a probability the model priced — turning "5 of 5" into a price
        # would invent a number the board never produced.
        ws.cell(row=r, column=11, value="n/a").font = GREY
        ws.cell(row=r, column=11).alignment = Alignment(horizontal="center")
    last = len(rows) + 1
    wire(ws, 2, last, "L", "I", "M", "N")
    ws.cell(row=last + 2, column=1,
            value="Hit % is the last-5 strike rate, NOT a model probability — a 5/5 run "
                  "reads 100% and is five games, so EV here is indicative only. Treat "
                  "this sheet as a shortlist to price up, not as an edge.").font = WARN
    widths(ws, {"A": 17, "B": 18, "C": 21, "D": 7, "E": 38, "F": 6, "G": 9, "H": 9,
                "I": 8, "J": 9, "K": 7, "L": 8, "M": 9, "N": 13})


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


def build(data, out_path, generated=None):
    generated = generated or datetime.now(timezone.utc)
    wb = Workbook()
    readme(wb, data, generated)
    streaks_sheet(wb, data.get("streaks") or [])
    mismatches_sheet(wb, data.get("mismatches") or [])
    chase_sheet(wb, data.get("chase") or [])
    wb.save(out_path)
    return {"streaks": len(data.get("streaks") or []),
            "mismatches": len(data.get("mismatches") or []),
            "chase": len(data.get("chase") or [])}


if __name__ == "__main__":
    src = sys.argv[1] if len(sys.argv) > 1 else "rows.json"
    out = sys.argv[2] if len(sys.argv) > 2 else "board.xlsx"
    with open(src) as f:
        counts = build(json.load(f), out)
    print(f"wrote {out}: " + ", ".join(f"{v} {k}" for k, v in counts.items()))
