"""What the bot says when asked for the record, rendered for Telegram.

WHY THE BOT HAD NOTHING TO SAY. It registers two commands, /pick and /help, and /help
ends "Stats commands are still being built". Meanwhile /api/results/boards has been
grading every board the channel publishes — streaks, perfect games, quick scan — off
snapshots frozen before kick-off, and nothing read it. The data was computed and never
spoken.

THE RESIDUAL IS THE ANSWER, NOT THE HIT RATE. This is the whole reason the card is built
here rather than printing whatever is handy. A board landing 73% against its own stated
82% is LOSING; one landing 61% against a stated 59% is winning. The hit rate on its own
describes which games happened to get picked, not whether the board was right about them,
so a card that leads with it flatters a board that overstates and buries a board that
does not. Every row here shows the claim, the outcome and the gap.

AND A RATE REFUSES TO EXIST WITHOUT SETTLED GAMES — the same rule as recordCard, the
backend's _tally and boardBreakdown. Nothing settled and everything missed are different
facts, and 0% for the first is a lie about the second.

Pure string building, no database and no network, so what the bot says is testable
without either.
"""
import math
from typing import List, Optional

#: Telegram collapses long messages behind "show more" at around this length, and a
#: record nobody expands is a record nobody reads.
MAX_ROWS = 6


def _pct(v) -> Optional[float]:
    """A number, or nothing. NAN AND INFINITY ARE NOTHING.

    isinstance(float("nan"), float) is True and every comparison against NaN is False,
    so a bare isinstance check let a NaN through the staleness guard: `hours <= threshold`
    was False, the alarm fired, and it read "The data is nanh old". A number that cannot
    be compared cannot be reported either."""
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        return None
    return float(v) if math.isfinite(v) else None


def _verdict(residual) -> str:
    """Word AND sign, never a colour and never an arrow alone.

    A reader seeing "-9.0" has to know whether lower is good here. It is not: the
    residual is the board's actual rate minus the rate it claimed, so negative means it
    promised more than it delivered."""
    r = _pct(residual)
    if r is None:
        return "no stated price to judge against"
    if r >= 2:
        return f"beating its own claim by {r:+.0f}pts"
    if r <= -2:
        return f"short of its own claim by {r:+.0f}pts"
    return f"landing about as claimed ({r:+.0f}pts)"


def units_text(b: dict) -> Optional[str]:
    """Units, but ONLY when every settled row carried a price.

    _tally answers `units: None` when nothing was priced and reports `unpriced` beside the
    total, because settlement.pick_profit returns None for a win at an unknown price.
    A total computed over an unstated subset of the settled rows is not a smaller number,
    it is a different number — so where any row is unpriced this says how many it covers
    instead of printing a figure that looks like the whole board."""
    u = _pct(b.get("units"))
    if u is None:
        return None
    priced = b.get("priced") or 0
    unpriced = b.get("unpriced") or 0
    if unpriced:
        return f"{u:+.2f}u over the {priced} priced of {priced + unpriced}"
    return f"{u:+.2f}u"


def board_line(b: dict) -> Optional[str]:
    """One board -> one line, or None when there is nothing frozen to describe.

    A board with no claims is not a board with a bad record, so it says that rather than
    showing 0%."""
    if not isinstance(b, dict):
        return None
    label = str(b.get("label") or b.get("key") or "").strip()
    if not label:
        return None
    claims = b.get("claims") or 0
    if not claims:
        return f"• {label}: nothing frozen yet"
    settled = b.get("settled") or 0
    if not settled:
        return f"• {label}: {claims} claims, none settled yet"
    landed = b.get("landed")
    rate = _pct(b.get("hit_rate"))
    head = f"• {label}: "
    if landed is not None and rate is not None:
        head += f"{landed}/{settled} ({rate:.0f}%)"
    elif rate is not None:
        head += f"{rate:.0f}% of {settled}"
    else:
        head += f"{settled} settled"
    mean_p = _pct(b.get("mean_prob"))
    if mean_p is not None:
        head += f" vs {mean_p:.0f}% claimed — {_verdict(b.get('residual'))}"
    u = units_text(b)
    if u:
        head += f"\n   {u}"
    return head


def results_card(payload: dict) -> str:
    """The record, split by which board made the claim."""
    boards = (payload or {}).get("boards") or []
    weeks = (payload or {}).get("weeks")
    lines = [l for l in (board_line(b) for b in boards) if l]
    if not lines:
        return ("📊 No board has frozen a claim yet.\n\n"
                "Nothing has been published and graded, which is different from a bad "
                "record — there is simply nothing to report.")
    head = "📊 The record, by board"
    if weeks:
        head += f" — last {weeks} week{'s' if weeks != 1 else ''}"
    tail = ("\nGraded off snapshots frozen before kick-off. The gap against the claim is "
            "the result; the hit rate alone only says which games got picked.")
    return head + "\n\n" + "\n".join(lines) + "\n" + tail


def _fixture_line(r: dict) -> str:
    team = str(r.get("team") or r.get("name") or "?")
    opp = str(r.get("opponent") or "")
    line = r.get("line")
    where = "v" if r.get("is_home") or r.get("venue") == "home" else "@"
    bit = f"• {team} {line}+" if line is not None else f"• {team}"
    if opp:
        bit += f" ({where} {opp})"
    p = _pct(r.get("prob"))
    if p is not None:
        bit += f" — {p * 100 if p <= 1 else p:.0f}%"
    fo = r.get("fair_odds")
    if isinstance(fo, (int, float)):
        bit += f", fair {fo:.2f}"
    return bit


def board_card(title: str, rows: List[dict], blurb: str = "",
               empty: str = "Nothing qualifies today.") -> str:
    """A board of today's rows. Trimmed, and SAYS it was trimmed.

    A list cut to six without saying so reads as the whole board, which makes a busy day
    look like a quiet one."""
    rows = [r for r in (rows or []) if isinstance(r, dict)]
    if not rows:
        return f"{title}\n\n{empty}"
    shown = rows[:MAX_ROWS]
    out = [title]
    if blurb:
        out.append(blurb)
    out.append("")
    out += [_fixture_line(r) for r in shown]
    if len(rows) > len(shown):
        out.append(f"\n…and {len(rows) - len(shown)} more on the site.")
    return "\n".join(out)


def plus_line(line) -> Optional[int]:
    """A market key's N -> the "N+" the channel's posts actually say.

    THE OFF-BY-ONE THAT LOOKS LIKE VALUE. build_markets carries `line: 4.5` and prices
    nb_ge(int(4.5) + 1) = P(X >= 5), labelling the row "Over 4.5". Every post in the
    channel is written "5+ corners". Printing "4.5+" or "4+" would put a different bet's
    name beside this bet's probability and price, which reads as an edge that is not
    there — the same trap odds_feed.parse_line exists to avoid from the other direction."""
    n = _pct(line)
    return int(n) + 1 if n is not None else None


#: Which name to print for each market group. The total is about the fixture, not a side,
#: so it is named as the fixture rather than given one team's name.
GROUP_NAME = {"home": "home", "away": "away", "total": "total"}


def worth_sending(ev, previous_ev=None, gain: float = 0.0) -> bool:
    """Should this bet go in a message, given what was already said about it?

    THE PROBLEM THIS SOLVES. The value send runs off the back of the odds fetch, so every
    bet is re-examined each time a price lands — several times on a matchday. Sending the
    same row every time is how social_draft.yml produced "the bot sends me so many
    messages that are not value"; saying nothing on a re-look is the opposite error,
    because a price drifting from +5% to +15% is new information and that second message
    is the one worth acting on.

    So a bet is sent when it has never been sent, or when its EV has IMPROVED by at least
    `gain`. A bet whose edge has shrunk is not re-sent: the first message already made the
    claim and a worse price does not need announcing.

    NaN AND INFINITY ARE NOT NUMBERS HERE, for the reason _pct exists — a non-finite EV
    passing a `>=` test is how "nanh old" reached a message once already. An unreadable
    `previous_ev` is treated as never sent, which risks one duplicate rather than
    permanently silencing a live bet.
    """
    now = _pct(ev)
    if now is None:
        return False
    before = _pct(previous_ev)
    if before is None:
        return True
    step = _pct(gain) or 0.0
    return (now - before) >= step


def value_rows(rows: List[dict]) -> List[dict]:
    """Value-board rows -> what value_card prints.

    ONLY `status == "ok"` ROWS. The board deliberately returns everything it looked at,
    labelled — kicked_off, no_fixture, below_floor, outside_window — so a screen can show
    why a fixture is absent instead of silently dropping it. A card is not that screen: a
    row that did not clear the floor is not a pick, and one whose game has kicked off is
    not a bet at all.
    """
    out = []
    for r in (rows or []):
        if not isinstance(r, dict) or r.get("status") != "ok":
            continue
        best = r.get("best") or {}
        group = best.get("group")
        home, away = r.get("home_name") or "?", r.get("away_name") or "?"
        if group == "home":
            team = home
        elif group == "away":
            team = away
        else:
            team = f"{home} v {away} total"
        out.append({"team": team, "line": plus_line(best.get("line")),
                    "ev": best.get("ev"), "book_odds": best.get("book_odds"),
                    "fair_odds": best.get("fair_odds"),
                    # From the odds document, not the market: it says who chose the price,
                    # and a price the model effectively wrote itself (the seeders generate
                    # fair_odds * uniform(0.90, 1.15)) must stay distinguishable.
                    "odds_source": r.get("odds_source")})
    return out


def value_card(rows: List[dict]) -> str:
    """Priced rows with positive EV.

    EV NEEDS A PRICE AND SAYS SO WHEN IT HAS NONE. An empty value board usually means no
    prices are stored, not that no edge exists, and those are opposite problems — one is
    the market being efficient, the other is nobody having typed anything in."""
    rows = [r for r in (rows or []) if isinstance(r, dict)
            and isinstance(r.get("ev"), (int, float))]
    if not rows:
        return ("💰 No positive-EV rows.\n\n"
                "Either nothing clears the bar, or no prices are stored to measure "
                "against — the board can only find value against a price somebody "
                "entered.")
    rows.sort(key=lambda r: -r["ev"])
    out = ["💰 Positive EV", ""]
    for r in rows[:MAX_ROWS]:
        team = str(r.get("team") or r.get("name") or "?")
        line = r.get("line")
        head = f"• {team} {line}+" if line is not None else f"• {team}"
        book = r.get("book_odds")
        fair = r.get("fair_odds")
        if isinstance(book, (int, float)):
            head += f" @ {book:.2f}"
        if isinstance(fair, (int, float)):
            head += f" (fair {fair:.2f})"
        head += f" — EV {r['ev']:+.1f}%"
        src = r.get("odds_source")
        if src and src != "manual":
            head += f" [{src} price]"
        out.append(head)
    if len(rows) > MAX_ROWS:
        out.append(f"\n…and {len(rows) - MAX_ROWS} more on the site.")
    return "\n".join(out)


def perfect_card(rows: List[dict]) -> str:
    """Perfect games, with all three legs shown.

    THE THREE LEGS ARE THE CLAIM. This board's whole argument is that a run, a mismatch
    and a leaky opponent agree — so a line printing only the probability would be the same
    row the streak board already sends, dressed up with a different heading. The run, the
    opponent's own concession count and the fair price each appear, because a reader
    deciding whether to back it is deciding whether those three still hold."""
    rows = [r for r in (rows or []) if isinstance(r, dict)]
    if not rows:
        return ("🎯 Perfect games\n\n"
                "Nothing clears all three legs today. The board asks for a live run, a "
                "mismatch and an opponent that actually concedes — most days something is "
                "missing, and a board that always has rows on it teaches you to ignore it.")
    out = ["🎯 Perfect games", ""]
    for r in rows[:MAX_ROWS]:
        nf = r.get("next_fixture") or {}
        st = r.get("streak") or {}
        mm = r.get("mismatch") or {}
        leak = r.get("opp_leak") or {}
        name = str(r.get("name") or "?")
        opp = str(nf.get("opponent") or leak.get("opponent") or "")
        where = "v" if nf.get("is_home") else "@"
        line = st.get("line", mm.get("line"))
        head = f"• {name} {line}+" if line is not None else f"• {name}"
        if opp:
            head += f" {where} {opp}"
        out.append(head)
        bits = []
        hits, of = st.get("hits"), st.get("settled")
        if hits is not None and of:
            bits.append(f"won it in {hits}/{of}")
        at_line, games = leak.get("at_line"), leak.get("games")
        if at_line is not None and games:
            bits.append(f"{opp or 'opponent'} shipped it in {at_line}/{games}")
        p = _pct(mm.get("prob"))
        if p is not None:
            bits.append(f"{p * 100 if p <= 1 else p:.0f}%")
        fo = _pct(mm.get("fair_odds"))
        if fo is not None:
            bits.append(f"fair {fo:.2f}")
        if bits:
            out.append("   " + " · ".join(bits))
    if len(rows) > MAX_ROWS:
        out.append(f"\n…and {len(rows) - MAX_ROWS} more on the site.")
    return "\n".join(out)


def week_card(payload: dict) -> str:
    """The week's fixtures, by day, with the reason each one is on.

    A DAY THAT QUALIFIED NOTHING IS PRINTED, NOT DROPPED. _fixture_board deliberately
    returns those days with an empty list, because an absent Thursday reads as missing
    data while an empty one reads as a quiet Thursday — and the bar is applied before the
    per-day ceiling precisely so a thin day stays thin."""
    days = [d for d in ((payload or {}).get("days") or []) if isinstance(d, dict)]
    total = (payload or {}).get("fixtures") or 0
    if not days:
        return ("📅 The week\n\nNothing on the board for the next seven days — either the "
                "calendar is empty or the data behind it has not synced.")
    out = [f"📅 The week — {total} fixture{'s' if total != 1 else ''} clear the bar", ""]
    for d in days:
        fx = [f for f in (d.get("fixtures") or []) if isinstance(f, dict)]
        day = str(d.get("day") or "?")
        if not fx:
            out.append(f"{day} — nothing qualified")
            continue
        out.append(f"{day}")
        for f in fx[:4]:
            home, away = f.get("home") or "?", f.get("away") or "?"
            line = f"  • {home} v {away}"
            a = f.get("best_angle") or {}
            if a.get("team") and a.get("label"):
                line += f" — {a['team']} {a['label']}"
            out.append(line)
        if len(fx) > 4:
            out.append(f"  …{len(fx) - 4} more")
    out.append("\nOn the board means it cleared the bar, not that it is priced. "
               "/value ranks what is priced.")
    return "\n".join(out)


#: What a graded row's `result` can be. WIN/LOSS are the backend's own constants; a row
#: that is neither is pending or void and must not be counted either way.
RESULT_MARK = {"win": "✅", "loss": "❌", "void": "➖"}


def settled_card(day: str, boards: List[dict]) -> str:
    """What landed on one day, per board.

    THE DAY IS NAMED IN THE HEADING, because "yesterday" in a message somebody opens on
    Monday morning is not the same day it was written about. Every row carries its result;
    a row still pending is left out of the count rather than shown as a miss."""
    boards = [b for b in (boards or []) if isinstance(b, dict)]
    shown = [b for b in boards if b.get("rows")]
    if not shown:
        return (f"📅 {day}\n\nNothing settled. Either nothing was claimed for that day or "
                f"the results have not synced yet — and those are different, so this will "
                f"not guess which.")
    out = [f"📅 Settled — {day}", ""]
    for b in shown:
        rows = [r for r in b["rows"] if isinstance(r, dict)]
        t = b.get("tally") or {}
        head = f"{b.get('label') or b.get('key') or '?'}"
        landed, settled = t.get("landed"), t.get("settled")
        if settled:
            head += f" — {landed}/{settled}"
            u = units_text(t)
            if u:
                head += f", {u}"
        out.append(head)
        for r in rows[:MAX_ROWS]:
            mark = RESULT_MARK.get(str(r.get("result") or "").lower(), "⏳")
            name = str(r.get("name") or "?")
            line = r.get("line")
            bit = f"  {mark} {name} {line}+" if line is not None else f"  {mark} {name}"
            val = r.get("value")
            if isinstance(val, (int, float)):
                bit += f" — got {val:g}"
            out.append(bit)
        if len(rows) > MAX_ROWS:
            out.append(f"  …{len(rows) - MAX_ROWS} more")
        out.append("")
    return "\n".join(out).rstrip()


#: Telegram's hard cap. telegram_bot.send does `text[:MAX_MESSAGE]`, which cuts mid-word
#: and mid-section with nothing to show it happened — so the digest budgets against this
#: itself rather than letting a section be silently halved.
TELEGRAM_LIMIT = 4096


def digest_card(date_label: str, sections: List[str], stale: Optional[str] = None,
                limit: int = TELEGRAM_LIMIT) -> str:
    """The morning message: the day's boards in one post.

    IT DROPS WHOLE SECTIONS RATHER THAN LETTING ONE BE CUT IN HALF. Telegram refuses a
    message over 4096 characters and `send` trims to fit, which on a busy Saturday would
    end the post mid-fixture — and a truncated board reads as a short board. Here the last
    section that will not fit is left out and SAID to be left out, so the message is
    shorter but never wrong about how much there was.

    The staleness warning goes FIRST and is never dropped. It is the one line that changes
    how everything below it should be read.
    """
    head = f"☀️ {date_label}"
    out = [head]
    if stale:
        out.append(stale)
    kept, dropped = [], 0
    used = sum(len(s) + 2 for s in out)
    for s in [s for s in (sections or []) if s and s.strip()]:
        if used + len(s) + 2 > limit - 80:      # 80 for the "left out" note itself
            dropped += 1
            continue
        kept.append(s)
        used += len(s) + 2
    if not kept:
        return "\n\n".join(out + ["Nothing on the boards this morning."])
    if dropped:
        kept.append(f"({dropped} more section{'s' if dropped != 1 else ''} wouldn't fit "
                    f"in one message — they're on the site.)")
    return "\n\n".join(out + kept)


def stale_warning(hours, threshold) -> Optional[str]:
    """Said when the data behind every board is too old to trust.

    THE REASON THIS EXISTS. A sync failed on all 36 competitions and sat broken for six
    hours; the failure was recorded honestly in /api/sync/runs and announced to nobody,
    and it was found because the site looked off. The bot is where somebody already
    looks."""
    h = _pct(hours)
    t = _pct(threshold)
    if h is None or t is None or h <= t:
        return None
    return (f"⚠️ The data is {h:.0f}h old (stale after {t:.0f}h). Today's boards are "
            f"built on it, so treat them as yesterday's until the next sync lands.")
