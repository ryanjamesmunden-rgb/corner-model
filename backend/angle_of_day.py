"""The angle of the day — what this site will put its name to today, or nothing at all.

WHY THE STREAK BOARD AND NOTHING CLEVERER. Because it is the only technique with a graded
record behind it. Every entry in `streak_snapshots` was produced by one call — five of the
last five cleared the line, team corners, over, line 3 or higher — frozen before kick-off
and settled afterwards against real match data. That record is on the results page and it
can be checked row by row.

Any other rule this file could implement would be published on the strength of nothing.
Backtests here have a bad history: `chase_score`, `lambda_only` and `venue_delta` all
looked like rankings and all came out flat or artifactual when replayed walk-forward, and
`consistency_only` scored +7.9 against a known-spurious +7.5 from estimation error alone
(see DAILY_PICK_RULE in server.py). The board that has actually been graded wins by
default, and that is the whole argument.

THE RECORD IS EVIDENCE, NEVER THE SELECTOR. It is tempting — the results tab is right
there — to ask which lines, leagues or streak lengths have been landing and to lead with
those. Do not. Picking the best-performing slice out of a handful of settled bets is
choosing noise and calling it a finding, which is exactly the mistake the paragraph above
records being made and caught. So the rule is STATED: the board's own order, restricted to
today. The record is shown next to it so a reader can judge the rule, and it never reaches
back to change it.

A DEAD DAY PUBLISHES NOTHING. The bar is absolute. Nothing in here relaxes `min_hits` to
find a fifth angle, tops the list up from a wider horizon, or reaches into tomorrow because
today came back empty. An angle published because the page looked bare is a bet nobody
would have made, offered to someone who will make it — and a board that always has five
rows teaches its readers that the five rows mean nothing.

Pure functions, no database and no network, so the rule can be tested without either.
"""
from typing import List, Optional
from zoneinfo import ZoneInfo

# What the rule IS, named after what it does rather than what anyone hopes it does. Same
# discipline as DAILY_PICK_RULE: a name like "value_finder" would be a claim.
RULE = "corroborated_streaks_by_model_probability"

# How many angles the page publishes. A CEILING, NOT A TARGET, and the difference is the
# whole point of the corroboration bar below: a big Saturday can fill it, a Tuesday should
# not be able to. Eight because eight on a weekend read about right; nothing tops a Tuesday
# up to eight, and nothing here ever will.
COUNT = 8

# THE FIXTURE BARS, AND WHY THERE HAD TO BE ANY.
#
# A streak on its own says a team keeps clearing a line. It says nothing about who they
# play next, which is the half that decides whether the run continues. Ordered only by the
# board's own sort — highest line, then most hits — a quiet midweek simply served whatever
# was left, and eight rows on a Tuesday is the board reporting that it found eight things
# worth backing when what it found was eight rows.
#
# So a streak now has to be long enough to be a streak (see MIN_RUN below) AND
# corroborated by the FIXTURE:
#
#   1. The opponent is actually weak at this. `opp_conceded` against the league's own
#      average, at the mismatch board's own margin — one number, one source, so the two
#      boards cannot drift into separate opinions about what "weak" means.
#   2. The model makes it likely. `projection.prob` is the model's probability for THIS
#      team clearing THIS line against THIS opponent, which is the direct answer to "is it
#      more likely to land" and was already being computed and thrown away.
#
# Only the OPPONENT half of the mismatch test is applied. The mismatch board also requires
# the team to be above average at winning corners; a team that has cleared its line in five
# straight has demonstrated that far better than an average can, and testing it twice would
# just be the streak bar wearing a second hat.
#
# WHAT IS DELIBERATELY NOT IN HERE: how often the opponent scores first. It is the obvious
# chase mechanism and it has been measured five times in this repo, most recently by
# measure_chase_board.py replaying the board walk-forward, and no effect has ever been
# found — `no_opp_fh` scored +0.03 against a RANDOM control that came out flat, which is
# the same number. test_chase_score.py exists to stop it creeping back into an ordering.
# It is carried on every row as CONTEXT and it gates nothing, because a number displayed
# beside a pick reads as a reason for the pick, and this one has been shown not to be.
MISMATCH_EDGE = 1.1     # the mismatch board's own margin over the league average
MIN_PROB = 60.0         # the model's probability for the streak continuing, in percent

# HOW LONG THE RUN ITSELF HAS TO BE, and the bar this file was missing entirely.
#
# The two bars above ask about the FIXTURE — is the opponent leaky, does the model rate it.
# Neither asks the first question anyone would: how long has this actually been going? So a
# team two games into a run could qualify on a soft opponent and a good number, and did.
#
# Five, because below that there is no run worth the word — three in a row is a thing that
# happens to most teams most months, and a streak that short is carrying no information the
# opponent test has not already supplied. Ten is where it stops adding much: a side that
# has cleared its line ten straight is telling you what it is, and the eleventh does not
# change the call.
#
# IT MATTERS MOST WHEN THE OPPONENT HAS NOT BEEN LOOKED AT. The fixture bars need an
# opponent with enough history to have an average at all; where that is missing the run is
# the only evidence there is, and a short one is no evidence.
MIN_RUN = 5
STRONG_RUN = 10         # where length stops adding — stated so nobody reads MIN_RUN as a target

# The audience is in the UK, and "today" is a local idea. A kick-off at 00:30 BST is
# tomorrow's game to a reader even though UTC has already turned over.
TZ = "Europe/London"

# Below this many settled picks no percentage is stated, only the raw count. Mirrors
# MIN_SAMPLE in frontend/src/lib/record.js deliberately: two places decide whether a rate
# may be shown and they must not disagree, because the disagreement would be between what
# the site claims in one panel and what it claims in another.
#
# It is not a significance test. It is a floor beneath which a percentage actively
# misleads — "88%" off eight games reads as a track record and is barely more than the
# difference between seven and eight.
MIN_SAMPLE = 20


def london_day(iso: Optional[str], tz: str = TZ) -> Optional[str]:
    """The calendar day a kick-off falls on, in the zone the audience reads it in."""
    if not iso:
        return None
    try:
        from datetime import datetime, timezone
        dt = datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(ZoneInfo(tz)).date().isoformat()
    except Exception:
        return None


def kickoff_of(row: dict) -> Optional[str]:
    """Where the kick-off lives, on a board row or on a frozen snapshot entry.

    They differ — a board row nests it under `next_fixture`, an entry carries it flat —
    and one function that reads both is the reason the same selection can be applied to
    today's board and to a snapshot taken months ago.
    """
    if row.get("kickoff"):
        return row["kickoff"]
    return (row.get("next_fixture") or {}).get("date")


def todays(rows: List[dict], day: str, tz: str = TZ) -> List[dict]:
    """The rows kicking off on `day`. Board order preserved, because that order IS the rule.

    Re-sorting here would quietly become a second ranking, competing with the board's, and
    whichever won would be undocumented.
    """
    return [r for r in rows if london_day(kickoff_of(r), tz) == day]


def upcoming(rows: List[dict], now_iso: str) -> List[dict]:
    """Drop anything that has already kicked off.

    THE BOARD IS CACHED AND THE DAY IS NOT. A scan built at 06:00 still lists the lunchtime
    games at 20:00, and "today's angle" on a match that finished three hours ago is not a
    stale number — it is a bet the reader cannot place, on a result they may already know.

    A row with no readable kick-off is dropped rather than kept: it cannot be shown to be
    live, and a shortlist is the wrong place to give something the benefit of the doubt.
    """
    from datetime import datetime, timezone

    def when(iso):
        try:
            dt = datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
            return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt
        except Exception:
            return None

    now = when(now_iso)
    if now is None:
        return list(rows)
    out = []
    for r in rows:
        dt = when(kickoff_of(r))
        if dt is not None and dt >= now:
            out.append(r)
    return out


def support_for(row: dict, league_avg: Optional[float],
                edge: float = MISMATCH_EDGE) -> dict:
    """What this fixture contributes to the streak, as numbers a reader can check.

    Built where the data is (see _angle_rows) and carried on the row, so that the decision
    below is a comparison rather than a second calculation — and so a frozen snapshot
    records WHY a row qualified, which is the only way the tightened rule can ever be
    graded on its own record.
    """
    proj = row.get("projection") or {}
    opp_conceded = proj.get("opp_conceded")
    bar = round(league_avg * edge, 2) if league_avg else None
    return {
        # THE RUN ALIVE RIGHT NOW, not the window's hit count. A 4-of-5 whose most recent
        # game was the miss is a broken streak wearing a good record, and the hit count
        # cannot tell the two apart.
        "run": (row.get("streak") or {}).get("length") or 0,
        "prob": proj.get("prob"),
        "lambda": proj.get("lambda"),
        "opp_conceded": opp_conceded,
        "league_avg": round(league_avg, 2) if league_avg else None,
        "opp_bar": bar,
        "weak_opponent": bool(bar is not None and opp_conceded is not None
                              and opp_conceded >= bar),
        # CONTEXT, NEVER A GATE. See the note beside MIN_PROB — five measurements, no
        # effect, and a test elsewhere stops it re-entering an ordering.
        "opp_fh_rate": row.get("opp_fh_rate"),
    }


def qualifies(row: dict, min_prob: float = MIN_PROB, min_run: int = MIN_RUN) -> bool:
    """Three bars now, and a row missing the numbers to prove any of them does not pass.

    THE RUN IS FIRST BECAUSE IT WAS MISSING. The other two ask about the fixture — is the
    opponent leaky, does the model rate it — and neither asks how long the thing has been
    going. A team two games into a run could clear both and be published as a streak.

    A row whose projection could not be built — no opponent history, a fixture the model
    cannot price — still fails rather than passing on its streak alone. Length is necessary
    and was never sufficient.
    """
    s = row.get("support") or {}
    prob = s.get("prob")
    if (s.get("run") or 0) < min_run:
        return False
    return bool(s.get("weak_opponent") and prob is not None and prob >= min_prob)


def order(row: dict) -> float:
    """Among qualifying angles: the model's own confidence, nothing cleverer.

    Same choice as daily_pick_order and for the same reason — it is readable, and it makes
    the record measure something meaningful (how the model's most confident calls land)
    rather than a ranking nobody has been able to demonstrate.

    WHAT THIS DELIBERATELY DOES NOT DO: chase long odds. Most probable means lowest lines,
    so this leads with 5+ ahead of 8+ even when the 8+ run is longer. That is the honest
    consequence of sorting by "most likely to land" and not a bug to sort around.
    """
    return (row.get("support") or {}).get("prob") or 0.0


def shortlist(rows: List[dict], day: str, count: int = COUNT, tz: str = TZ,
              min_prob: float = MIN_PROB) -> List[dict]:
    """What the page publishes for `day` — at most `count`, and usually fewer.

    A THIN DAY YIELDS FEWER RATHER THAN TOPPING UP, and now it actually will. The bar is a
    property of the angle and its fixture, not a quota: nothing here relaxes `min_prob`,
    drops the opponent test, or reaches past `day` because the list came back short. If two
    fixtures corroborate, two is the honest answer and the page says two.
    """
    picked = [r for r in todays(rows, day, tz) if qualifies(r, min_prob)]
    picked.sort(key=order, reverse=True)
    return picked[:max(0, count)]


def published(entries: List[dict], count: int = COUNT) -> List[dict]:
    """The rows a past snapshot would have shown, in the order the board ranked them.

    A snapshot freezes up to 25 rows; the page shows five. Grading all 25 and printing the
    result beside a list of five would be quoting one thing's record next to another
    thing — so the record reads back the same slice that gets published.

    THIS IS NOT LOOK-AHEAD. The order was fixed before kick-off, when the snapshot was
    written, and nothing here consults a result to decide which rows to count.
    """
    return list(entries or [])[:max(0, count)]


def snapshot_order(entry: dict) -> float:
    """`order`, for a frozen entry rather than a live board row.

    The two shapes differ — an entry stores `prob` flat, a board row nests it under
    `support` — and the record has to reconstruct the panel's ORDER, not just its
    membership, or "the top angle that day" grades a row that was never top.
    """
    return entry.get("prob") or (entry.get("support") or {}).get("prob") or 0.0


def gate(tally: Optional[dict], min_sample: int = MIN_SAMPLE) -> dict:
    """What a tally is allowed to be stated as.

    `show_rate` is the only thing standing between a real record and an advert. Kept out of
    the template so the threshold is one testable decision rather than a JSX conditional
    that someone loosens on a quiet afternoon.
    """
    tally = tally or {}
    settled = tally.get("settled") or 0
    return {
        "landed": tally.get("landed") or 0,
        "missed": tally.get("missed") or 0,
        "settled": settled,
        "voided": tally.get("voided") or tally.get("void") or 0,
        "pending": tally.get("pending") or 0,
        # None rather than 0 on an empty set, for the same reason _tally does it: nothing
        # settled and everything missed are different facts.
        "hit_rate": tally.get("hit_rate"),
        "show_rate": settled >= min_sample,
        "min_sample": min_sample,
    }


# Why a day has nothing on it. The distinction is worth carrying: "no football today" and
# "football today, none of it good enough" say different things about the site, and only
# the second demonstrates that the bar does anything.
DEAD_STALE = "stale"
DEAD_NO_FIXTURES = "no_fixtures"
DEAD_NO_QUALIFIER = "no_qualifier"

DEAD_REASONS = {
    DEAD_STALE:
        "The match data is too old to publish an angle off. Nothing is being offered "
        "today rather than a call made on stale form.",
    DEAD_NO_FIXTURES:
        "Nothing from the leagues this model covers kicks off today.",
    DEAD_NO_QUALIFIER:
        "There is football on, and none of it clears the bar. The board only publishes a "
        "team that has cleared its line in all five of its last five — today nobody has.",
}


def state(angles: List[dict], fixtures_today: int, stale: bool = False) -> dict:
    """Live, or dead and why.

    `fixtures_today` is what separates a quiet calendar from a strict bar, and it is the
    reason this takes a count rather than inferring emptiness from the angle list.
    """
    if stale:
        reason = DEAD_STALE
    elif not angles and not fixtures_today:
        reason = DEAD_NO_FIXTURES
    elif not angles:
        reason = DEAD_NO_QUALIFIER
    else:
        return {"dead": False, "reason": None, "note": None}
    return {"dead": True, "reason": reason, "note": DEAD_REASONS[reason]}
