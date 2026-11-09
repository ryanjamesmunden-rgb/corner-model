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


#: Unpriced rungs shown per side, beneath the lowest line that IS priced.
#:
#: Two, because the point is "here is the safer line and what it is worth", not a printout
#: of the whole ladder. These are not bets and carry no EV — a book price for them was
#: never fetched, so the only honest thing to show is the model's own number.
MAX_REFERENCE_RUNGS = 2


def reference_rungs(ladder: List[dict], group: str, below: Optional[int]) -> List[dict]:
    """The SAFER rungs on one side that no book price was fetched for.

    WHY THESE ARE WORTH A LINE EACH. EV needs a fetched price, so a rung nothing quoted
    produces no market row, no EV and no mention — the message simply has a hole in it
    where the lowest line should be. That is not a near-miss being filtered out, it is the
    model having an opinion nobody was shown: a 5+ priced at 69.6% is a fair 1.44, and
    against a book offering 1.70 it is the best bet on the card by some distance.

    So the fair price goes in, clearly not as a pick. Whoever reads it can compare it to
    whatever their own book is showing, which is the only way to use a line this feed
    cannot see — the provider carries 33 books and Sky Bet, Paddy Power, Coral and
    BoyleSports are not among them.

    LOWER ONLY. A rung above the priced ones is a longer shot, which is the opposite of
    what is missing, and the ladder is long enough that printing all of it would bury the
    bets it sits under.
    """
    out = []
    for m in (ladder or []):
        if not isinstance(m, dict) or m.get("group") != group:
            continue
        if m.get("book_odds") is not None:
            continue                       # it has a price; it is a bet or it is not value
        line = plus_line(m.get("line"))
        if line is None or (below is not None and line >= below):
            continue
        if _pct(m.get("fair_odds")) is None:
            continue
        out.append({"line": line, "fair_odds": m.get("fair_odds"),
                    "prob": m.get("prob"), "reference": True})
    # Closest to the priced lines first: the nearest safer rung is the one being asked for.
    out.sort(key=lambda r: -r["line"])
    return out[:MAX_REFERENCE_RUNGS]


def value_rows(rows: List[dict], min_ev: Optional[float] = None,
               with_ladder: bool = False) -> List[dict]:
    """Value-board rows -> what value_card prints.

    ONLY `status == "ok"` ROWS. The board deliberately returns everything it looked at,
    labelled — kicked_off, no_fixture, below_floor, outside_window — so a screen can show
    why a fixture is absent instead of silently dropping it. A card is not that screen: a
    row that did not clear the floor is not a pick, and one whose game has kicked off is
    not a bet at all.

    `min_ev` TURNS ON EVERY ANGLE, NOT JUST THE BEST ONE. Each board row carries `best`
    plus up to three `alternatives` — the same fixture's other priced markets, already
    computed and, until this existed, thrown away. One game can be value at 6+ AND at 7+,
    and a card showing only the single highest EV hides the safer line on the same match.
    Left as None only `best` is emitted, which is what the digest's section has always
    shown.

    THE ALTERNATIVES ARE NOT PRE-FILTERED. The board keeps the next three by EV whatever
    they are, so they reach here including negative ones — the floor has to be applied
    here or a +12% bet would arrive with a -4% bet printed underneath it as though both
    were picks.
    """
    floor = _pct(min_ev)
    out = []
    for r in (rows or []):
        if not isinstance(r, dict) or r.get("status") != "ok":
            continue
        home, away = r.get("home_name") or "?", r.get("away_name") or "?"
        # EVERY QUALIFYING RUNG WHEN THE LADDER IS THERE, not the board's top four.
        #
        # `best` + `alternatives` is marks[0:4] by EV, and that cap is upstream of every
        # choice this module makes — so a rung ranked fifth could not be shown however
        # the card was written. Torreense's 5+ at +9.8% ranked sixth on its own fixture
        # and never reached here at all. The ladder carries the lot; the per-game cap
        # below decides what fits, and _pick_per_game decides WHICH, by more than EV.
        lad = [m for m in (r.get("ladder") or []) if isinstance(m, dict)]
        picks = []
        if floor is not None and lad:
            picks = [m for m in lad
                     if _pct(m.get("ev")) is not None and _pct(m.get("ev")) >= floor]
            picks.sort(key=lambda m: -_pct(m["ev"]))
        # FALLS BACK RATHER THAN RETURNING NOTHING. A `status == "ok"` row has a `best`
        # that already cleared the floor, so a ladder yielding no qualifying rung is a
        # broken ladder, not a fixture without value — and preferring it would drop a
        # real bet to silence. Caught by the junk-ladder test: `[None, 3, {}]` survives
        # the isinstance filter as one empty dict, qualifies nothing, and took the bet
        # with it.
        if not picks:
            picks = [r.get("best") or {}]
            if floor is not None:
                picks += [m for m in (r.get("alternatives") or [])
                          if isinstance(m, dict) and _pct(m.get("ev")) is not None
                          and _pct(m.get("ev")) >= floor]
        for m in picks:
            group = m.get("group")
            if group == "home":
                team, subject = home, home
            elif group == "away":
                team, subject = away, away
            else:
                team, subject = f"{home} v {away} total", "Match total"
            out.append({
                "team": team, "line": plus_line(m.get("line")),
                "ev": m.get("ev"), "book_odds": m.get("book_odds"),
                "fair_odds": m.get("fair_odds"),
                # From the odds document, not the market: it says who chose the price,
                # and a price the model effectively wrote itself (the seeders generate
                # fair_odds * uniform(0.90, 1.15)) must stay distinguishable.
                "odds_source": r.get("odds_source"),
                # WHICH GAME, so several angles on one fixture group under it instead of
                # repeating the pair on every line.
                "match": f"{home} v {away}", "subject": subject,
                # The identity a send is remembered by. Per MARKET, not per fixture, so
                # two angles on the same game are tracked — and suppressed — separately.
                "dedup_key": f"{r.get('fixture_id')}:{m.get('key')}",
            })
        if with_ladder and picks:
            # THE SAFER RUNGS NOBODY QUOTED, per side that produced a bet. Keyed off the
            # lowest line actually priced for that side, so these sit underneath it.
            by_group = {}
            for m in picks:
                g = m.get("group")
                ln = plus_line(m.get("line"))
                if ln is None:
                    continue
                by_group[g] = min(ln, by_group.get(g, ln))
            for group, lowest in by_group.items():
                subject = (home if group == "home" else
                           away if group == "away" else "Match total")
                for ref in reference_rungs(r.get("ladder"), group, lowest):
                    out.append({**ref, "match": f"{home} v {away}", "subject": subject,
                                "team": subject, "ev": None})
    return out


#: Angles in one value message, and how many of them one fixture may take.
#:
#: MAX_ROWS is six because Telegram collapses a long message behind "show more". These are
#: higher because a grouped card spends a line on each fixture heading and because several
#: angles on one game is the point — but the per-game cap exists so a single fixture with
#: a fully priced ladder cannot fill the message and push every other game out of it.
MAX_VALUE_ANGLES = 10
MAX_ANGLES_PER_GAME = 4


def _pick_per_game(angles: List[dict], cap: int) -> List[dict]:
    """Which of one game's angles to carry: the safest of each side, then the best edges.

    `angles` arrives sorted by EV descending. Returned in LADDER order — by subject, then
    by line — because a reader comparing rungs on the same side is reading a ladder, and
    EV order scatters it.
    """
    if cap <= 0:
        return []
    lowest, rest = {}, []
    for a in angles:
        subject = str(a.get("subject") or a.get("team") or "?")
        line = _pct(a.get("line"))
        best_so_far = lowest.get(subject)
        if line is not None and (best_so_far is None
                                 or line < (_pct(best_so_far.get("line")) or line)):
            if best_so_far is not None:
                rest.append(best_so_far)
            lowest[subject] = a
        else:
            rest.append(a)
    # The safe rungs first, worst-priced side last if they do not all fit — then fill on
    # EV, which `rest` is already ordered by.
    keep = sorted(lowest.values(), key=lambda a: -(_pct(a.get("ev")) or 0))[:cap]
    for a in rest:
        if len(keep) >= cap:
            break
        keep.append(a)
    return sorted(keep, key=lambda a: (str(a.get("subject") or ""),
                                       _pct(a.get("line")) or 0))


def value_plan(rows: List[dict]):
    """Which angles a value message will actually carry, grouped by game.

    SPLIT OUT OF value_card BECAUSE THE CAPS DECIDE WHAT GETS REMEMBERED. The sender
    records every angle it sent so it does not repeat itself, and the card drops whatever
    does not fit. If those two disagree, an angle gets recorded as told-about without ever
    appearing in a message — and because a recorded angle is suppressed until its EV
    improves, it would be silently and permanently lost. That is strictly worse than a
    duplicate, so there is one function deciding it and both callers use it.

    Returns (plan, dropped): plan is [(match, [angle, ...]), ...] in EV order, dropped is
    how many cleared the floor and did not fit.
    """
    rows = [r for r in (rows or []) if isinstance(r, dict) and _pct(r.get("ev")) is not None]
    rows.sort(key=lambda r: -_pct(r["ev"]))
    order, by_match = [], {}
    for r in rows:
        key = str(r.get("match") or r.get("team") or r.get("name") or "?")
        if key not in by_match:
            by_match[key] = []
            order.append(key)
        by_match[key].append(r)

    plan, shown, dropped = [], 0, 0
    for key in order:
        angles = by_match[key]
        # PER-GAME CAP as well as a total one. One fixture whose whole ladder is priced
        # over would otherwise fill the message on its own and push every other game out.
        #
        # BUT NOT THE TOP FOUR BY EV, WHICH IS WHAT THIS USED TO BE. Measured on
        # Torreense v União de Leiria: the home ladder ran +9.8% at 5+, +12.4% at 6+,
        # +22.6% at 7+, +29.6% at 8+. EV rose monotonically with the line, so ranking on
        # it alone kept the three longest shots and the match total, and discarded the
        # safest bet on the board. That is not a one-off — a book's margin on a long
        # corner count is where this model most often disagrees with it, so "best EV"
        # systematically means "longest odds" and the safe line never survives the cap.
        #
        # So each SUBJECT's lowest qualifying rung is kept first, and the rest of the
        # slots go to the biggest edges. The safe line and the big edge are different
        # bets and both are worth seeing; picking between them on EV answers a question
        # nobody asked.
        keep = _pick_per_game(angles, MAX_ANGLES_PER_GAME)
        dropped += len(angles) - len(keep)
        room = MAX_VALUE_ANGLES - shown
        if room <= 0:
            dropped += len(keep)
            continue
        if len(keep) > room:
            dropped += len(keep) - room
            keep = keep[:room]
        plan.append((key, keep))
        shown += len(keep)
    return plan, dropped


def value_sent(rows: List[dict]) -> List[dict]:
    """The angles a value message really carries — what the sender must record, and only
    that. See value_plan for why the two cannot be allowed to drift apart."""
    plan, _ = value_plan(rows)
    return [r for _match, angles in plan for r in angles]


def _value_line(r: dict, subject: bool = False) -> str:
    """One priced angle. `subject` names the side instead of repeating the fixture, which
    is what a row under a fixture heading needs."""
    who = r.get("subject") if subject else None
    who = str(who or r.get("team") or r.get("name") or "?")
    line = r.get("line")
    head = f"• {who} {line}+" if line is not None else f"• {who}"
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
    return head


def value_card(rows: List[dict]) -> str:
    """Priced rows with positive EV.

    EV NEEDS A PRICE AND SAYS SO WHEN IT HAS NONE. An empty value board usually means no
    prices are stored, not that no edge exists, and those are opposite problems — one is
    the market being efficient, the other is nobody having typed anything in."""
    # THE REFERENCE RUNGS ARE PULLED OUT BEFORE THE EV FILTER, because they deliberately
    # have no EV — there is no fetched price to compute one from. Filtering first dropped
    # them silently, which is the same disappearing act this whole change exists to undo.
    refs = {}
    for r in (rows or []):
        if isinstance(r, dict) and r.get("reference"):
            refs.setdefault(str(r.get("match") or ""), []).append(r)
    rows = [r for r in (rows or []) if isinstance(r, dict)
            and not r.get("reference")
            and isinstance(r.get("ev"), (int, float))]
    if not rows:
        return ("💰 No positive-EV rows.\n\n"
                "Either nothing clears the bar, or no prices are stored to measure "
                "against — the board can only find value against a price somebody "
                "entered.")
    rows.sort(key=lambda r: -r["ev"])

    # GROUPED BY GAME WHEN THERE IS A GAME TO GROUP BY. Several angles on one fixture
    # printed flat repeat the team on every line and read as separate games; under one
    # heading they read as what they are, a ladder on the same match with the safer line
    # visible beside the biggest edge. Rows with no `match` (the digest's long-standing
    # shape) fall through to the flat list, so nothing that worked before changes.
    grouped = [r for r in rows if r.get("match")]
    if not grouped:
        return "\n".join(["💰 Positive EV", ""] + [_value_line(r) for r in rows[:MAX_ROWS]]
                         + ([f"\n…and {len(rows) - MAX_ROWS} more on the site."]
                            if len(rows) > MAX_ROWS else []))

    # `refs` was collected above, and is deliberately NOT part of the plan: the plan is
    # what gets RECORDED as sent, and a reference rung is not a bet — recording one would
    # suppress the real bet on that market if a price ever arrived for it.
    plan, dropped = value_plan(rows)
    out = ["💰 Positive EV", ""]
    for match, angles in plan:
        out.append(match)
        for r in angles:
            out.append(_value_line(r, subject=True))
        for r in refs.get(match, []):
            # NO BULLET AND NO EV, so it cannot be read as a pick. It is the model's price
            # for a rung this feed could not fetch, to check against your own book.
            fair = _pct(r.get("fair_odds"))
            pct = _pct(r.get("prob"))
            tail = f"  ↳ {r.get('subject')} {r.get('line')}+ — fair {fair:.2f}"
            if pct is not None:
                tail += f" ({pct:.0f}%)"
            out.append(tail + ", no price fetched")
        out.append("")
    while out and out[-1] == "":
        out.pop()
    if dropped:
        out.append(f"\n…and {dropped} more angle(s) on the site.")
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
