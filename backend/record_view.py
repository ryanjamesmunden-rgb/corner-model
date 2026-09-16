"""How the record is grouped and what it counts.

TWO THINGS WENT WRONG WHEN THE SNAPSHOT WENT DAILY.

It reads as days. Each snapshot became one section on the page, labelled by its tag, under
a heading that still said "week". A month of football arrived as thirty blocks. The record
was no less true and much harder to read, and a record nobody reads is not doing its job.

It counts a quota. The snapshot freezes the top 25 of the board every day. On a Saturday
with sixty fixtures, 25 is a selection. On a Tuesday with ten it is the whole board
including the bottom of it — so a quiet midweek contributed as many claims as a full
weekend, and they were the weakest claims on offer. The site published nothing that night
and the record wrote down twenty-five picks.

WHAT COUNTS, AND THE RULE THAT DECIDES IT.

Each row is counted under the rule that was in force WHEN IT WAS FROZEN, never re-judged
by today's. Rows frozen since the corroboration bar carry `qualified`; rows frozen before
it do not, and for those the board WAS the claim — that is what the site was publishing at
the time, and the record's job is to say what was claimed, not what would be claimed now.

Re-judging the old rows against the new bar would be scoring yesterday's calls by a rule
they were never made under, which is the same look-ahead this whole file exists to avoid.
Quietly counting the new unqualified ones would be the opposite error: recording claims the
site declined to make.

Pure functions, no database, so the rule can be tested without one.
"""
from datetime import date, datetime, timezone
from typing import List, Optional

# Monday, because that is when the football week is talked about and when the join window
# opens. ISO weeks agree, which is why isocalendar is used rather than arithmetic.
WEEK_START = "Monday"


def week_of(tag: Optional[str]) -> Optional[str]:
    """The Monday that a snapshot tag falls in, as a date string.

    Keyed by the Monday rather than by "2026-W38" because the page renders it as a date and
    a reader should not have to know what week 38 was.
    """
    if not tag:
        return None
    try:
        d = date.fromisoformat(str(tag)[:10])
    except ValueError:
        return None
    return (d.fromordinal(d.toordinal() - d.weekday())).isoformat()


def counted(entry: dict) -> bool:
    """Was this row something the site actually stood behind?

    THE DEFAULT IS TRUE AND THAT IS THE WHOLE POINT. `qualified` is absent on every row
    frozen before the corroboration bar existed, and for those the board was the claim.
    Treating absence as "not qualified" would erase the record back to nothing overnight
    and read as the site having deleted its own history.
    """
    if "qualified" not in entry:
        return True
    return bool(entry.get("qualified"))


def split(entries: List[dict]) -> tuple:
    """(published, also_on_the_board).

    Both halves are returned because both are shown. Dropping the second would hide that
    the board had more on it than the site chose to publish, and the gap between those two
    numbers is the most interesting thing on a quiet Tuesday.
    """
    published = [e for e in entries if counted(e)]
    held = [e for e in entries if not counted(e)]
    return published, held


def group_by_week(snapshots: List[dict]) -> List[dict]:
    """Snapshot-per-day -> one block per calendar week, newest first.

    The days within a week are kept, so a reader can still see which night a claim was made
    on. What changes is the unit the page is read in.
    """
    weeks = {}
    for s in snapshots:
        key = week_of(s.get("tag"))
        if key is None:
            continue
        weeks.setdefault(key, []).append(s)
    out = []
    for key in sorted(weeks, reverse=True):
        days = sorted(weeks[key], key=lambda s: s.get("tag") or "", reverse=True)
        out.append({"week": key, "days": days})
    return out


def label(week: Optional[str], today: Optional[date] = None) -> str:
    """"This week", "Last week", or the date it began.

    A relative label for the two weeks anyone is actually thinking about, and an absolute
    one beyond that — "3 weeks ago" makes a reader do arithmetic to place a result.
    """
    if not week:
        return ""
    try:
        start = date.fromisoformat(week)
    except ValueError:
        return str(week)
    today = today or datetime.now(timezone.utc).date()
    this_week = today.fromordinal(today.toordinal() - today.weekday())
    gap = (this_week - start).days // 7
    if gap == 0:
        return "This week"
    if gap == 1:
        return "Last week"
    return f"Week of {start.strftime('%-d %B %Y')}"
