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

ONE RECORD, ALL OF IT, AND THE SPLIT THAT MATTERS IS PER ROW.

This briefly divided into eras — the tightened rule in the headline, everything before it
in an archive — and that was the wrong fix to the right complaint. The complaint was a
quiet Tuesday freezing twenty-five forced streaks and every one of them counting. It was
never that the weeks before had been picked differently: those calls were made before
kick-off and they landed or they did not, and moving them out of the number is hiding them
however carefully the heading is worded.

So the record is whole, and the distinction is made where it belongs — on each row. A row
the site PUBLISHED counts. A row the board carried and the site declined to publish does
not. That separates the forced night from the rest without discarding a month of honest
record to do it, and it needs no cutover date to get wrong.

Rows frozen before the bar existed carry no verdict, and for those the board WAS the claim.
Absence therefore means counted — treating it as unpublished would erase the record
overnight, which is exactly the hiding this file now exists not to do.

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
    """Within the current era: was this row something the site actually published?

    Only meaningful for a corroborated-era snapshot, where `qualified` exists. Applied to
    an older row it answers True, which is correct for that era in its own terms — the
    board WAS the claim then — and is why the archive tallies read the way they always did.
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
