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

TWO TECHNIQUES, TWO RECORDS. THE HEADLINE IS ONE OF THEM.

The picks were chosen one way and are now chosen another: a streak had only to be a streak,
and now it has to be corroborated by the fixture it is walking into. A single percentage
spanning both describes neither. It is an average of two rules, and the reader has no way
to know which one they are being sold.

So the record starts again at the change. The headline, the rate, and everything the page
argues from cover the CURRENT rule only, and they begin with almost nothing in them —
which is the honest state of a rule that is two days old and the thing a clean slate
actually means.

NOTHING IS DELETED. The earlier era is kept whole, graded, and shown under its own heading
with its own tally. Two reasons, and the second is the one that matters:

  It is still true. Those calls were made before kick-off and they landed or they did not.
  Hiding them because the method has moved on is how a record becomes a highlight reel.

  It cannot be rebuilt. A snapshot is the only evidence of what was claimed before a game
  was played; recomputing it afterwards counts only the survivors. Deleted, it is gone for
  good, and no future version of this site can ever grade that period again.

WHICH ERA A SNAPSHOT BELONGS TO IS READ FROM THE DATA, NOT FROM A DATE. A snapshot frozen
under the new rule records `qualified` on its rows; one frozen before it does not. Using
the field rather than a hardcoded cutover means nothing depends on guessing which side of a
deploy a given night fell on — the commonest way a boundary like this ends up one day out,
silently, in whichever direction flatters the number.

WHAT COUNTS WITHIN THE CURRENT ERA. Only rows the site actually published. The snapshot
freezes the top 25 of the board every night; on a quiet Tuesday that is the whole board
including the bottom of it, and the site published none of it. Those are shown and not
counted — recording claims it declined to make would be the same dishonesty pointed the
other way.

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


# The two selection rules this site has used. Named rather than "old" and "new", because
# in six months "new" will be neither.
ERA_CORROBORATED = "corroborated"   # a streak AND the fixture backing it up
ERA_STREAK_ONLY = "streak_only"     # a streak was enough on its own


def era_of(snapshot: dict) -> str:
    """Which rule froze this snapshot, read off the snapshot itself.

    NOT A DATE. The obvious implementation is a cutover constant, and it would need to be
    the exact night the deploy landed relative to an 11:00 UTC job — which is how a
    boundary ends up a day out, silently, in whichever direction flatters the number.

    A snapshot frozen under the corroboration bar records `qualified` on its rows. One
    frozen before it does not. The data says which it is, so nothing has to be remembered.
    """
    for e in (snapshot.get("entries") or []):
        if "qualified" in e:
            return ERA_CORROBORATED
    return ERA_STREAK_ONLY


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


def split_eras(snapshots: List[dict]) -> tuple:
    """(current, earlier) — the clean slate, drawn where the rule actually changed.

    A single week can straddle the boundary, so this splits by SNAPSHOT and not by week.
    That week then appears in both lists, which looks odd exactly once and is the truth:
    some of its nights were picked one way and some the other.
    """
    current = [s for s in snapshots if era_of(s) == ERA_CORROBORATED]
    earlier = [s for s in snapshots if era_of(s) == ERA_STREAK_ONLY]
    return current, earlier


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
