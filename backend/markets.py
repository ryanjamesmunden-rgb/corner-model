"""The corner markets this model can price beyond "one team, over a line".

WHY THIS EXISTS. Until now the board priced three things: the match total over a line, the
home side over a line, the away side over a line. Overs only, one side at a time. A
handwritten card from the person running this site had "UNDER 4 @ 2.00" and "4 corners each
team" on it — two bets the site could not express at all, let alone find a price for.

WHAT IS ADDED HERE, and what each one costs in assumptions:

  UNDERS — free. Under 9.5 is "nine or fewer", which is exactly 1 - P(X >= 10) from the
  same distribution the over already uses. No new assumption, no new data, and it doubles
  what the board can say about a fixture. The .5 lines matter: an integer line is an Asian
  line where the exact number pushes, and this prices no pushes (see odds_feed's note).

  BOTH TEAMS OVER — not free, and the whole reason this is a module rather than four more
  lines in build_markets. "Both teams to win 4+ corners" is a JOINT event, and the obvious
  price — P(home >= 4) x P(away >= 4) — assumes the two sides' corner counts are
  independent. They are not, and the direction is not obvious either: a frantic end-to-end
  game lifts both (positive), while one side camped in the other's half lifts one and
  crushes the other (negative). Guessing wrong here does not make the price slightly off;
  on a joint event it moves the edge by tens of percent, and it moves it in the direction
  that makes a bad bet look good.

  So the dependence is MEASURED, from the matches already stored. Every match row carries
  `corners_for` AND `corners_against`, which is both sides of one game — so the joint is
  observable directly rather than inferred. See `dependence`.

NOTHING HERE INVENTS A PRICE. Every function takes the model's own lambdas and the same
pmf/tail functions the single-side markets use, passed in, so there is one model and not
two. If the single-side price changes, these change with it.
"""
from typing import Callable, Dict, Iterable, List, Optional, Tuple

#: Lines for "both teams over N". Deliberately lower than the single-team ladder: both
#: sides have to clear it, so 5+ each is already a much rarer event than one side's 5+.
BOTH_LINES = [1.5, 2.5, 3.5, 4.5, 5.5]

#: Below this many paired matches the measured dependence is noise, and the factor is
#: shrunk hard towards 1 (independence) rather than trusted.
DEPENDENCE_SHRINK = 25

#: However strong the measurement looks, one fixture's history cannot justify moving a
#: joint probability by more than this. A factor outside the band is a sign of a thin or
#: freak sample, not of an edge nobody else has noticed.
DEPENDENCE_MIN = 0.70
DEPENDENCE_MAX = 1.30

#: Fewer paired matches than this and no factor is produced at all — the price falls back
#: to independence and says so, rather than being nudged by four games.
MIN_PAIRS = 8


def pair_counts(*teams: dict, limit: int = 0) -> List[Tuple[int, int]]:
    """(team's corners, opponent's corners) for every stored match of these teams.

    ONE MATCH IS ONE OBSERVATION OF BOTH SIDES. `corners_against` is the opponent's count
    in that same game, so a team's own history is already a sample of the joint
    distribution — no join, no second query, and it covers the exact leagues these two
    sides play in rather than a global average.

    Pooled across both teams of the fixture, because the question is about how corner
    counts in a game of this kind co-move, and two sides' histories answer it with twice
    the sample. Ordered newest first where the stored rows are.
    """
    out: List[Tuple[int, int]] = []
    for team in teams:
        rows = (team or {}).get("real_matches") or []
        if limit:
            rows = rows[-limit:]
        for m in rows:
            cf, ca = m.get("corners_for"), m.get("corners_against")
            if isinstance(cf, (int, float)) and isinstance(ca, (int, float)):
                out.append((int(cf), int(ca)))
    return out


def dependence(pairs: Iterable[Tuple[int, int]], k: int,
               shrink: int = DEPENDENCE_SHRINK,
               min_pairs: int = MIN_PAIRS) -> Optional[dict]:
    """How much more (or less) often BOTH sides clear k than independence would say.

    Returns `{"factor", "pairs", "raw", "both", "expected"}`, or None when there is not
    enough history to measure. `factor` multiplies the independent product:

        P(both >= k)  ~=  factor * P(home >= k) * P(away >= k)

    MEASURED AT THIS k, not once for the fixture. Dependence is not one number: two sides
    both reaching 2 corners is near-certain in any game, while both reaching 6 needs a
    particular kind of match. A single correlation coefficient would average those into
    something true of neither.

    SHRUNK TOWARDS 1 BY SAMPLE SIZE, then clamped. Twenty games can show a factor of 1.6
    by luck, and a joint price is exactly where that lie is most expensive. The raw
    measurement is returned beside the shrunk one so a reader can see the difference.
    """
    rows = [(a, b) for a, b in pairs if a is not None and b is not None]
    n = len(rows)
    if n < max(1, min_pairs):
        return None
    a_hits = sum(1 for a, _ in rows if a >= k)
    b_hits = sum(1 for _, b in rows if b >= k)
    both = sum(1 for a, b in rows if a >= k and b >= k)
    # An independent expectation of zero cannot be divided into: neither side ever cleared
    # k in this sample, which says the line is out of reach, not that the two are linked.
    expected = (a_hits / n) * (b_hits / n) * n
    if expected <= 0:
        return None
    raw = both / expected
    factor = 1.0 + (raw - 1.0) * (n / (n + shrink))
    factor = max(DEPENDENCE_MIN, min(DEPENDENCE_MAX, factor))
    return {"factor": round(factor, 3), "pairs": n, "raw": round(raw, 3),
            "both": both, "expected": round(expected, 2)}


def both_over_prob(k: int, lam_home: float, lam_away: float,
                   ge: Callable[[int, float], float],
                   factor: float = 1.0) -> float:
    """P(both sides win k or more corners), from the two single-side tails.

    `ge` is the model's own P(X >= k) — negative binomial for a team line — passed in so
    this cannot drift away from the price the same line gets on its own.
    """
    p = ge(k, lam_home) * ge(k, lam_away) * (factor if factor else 1.0)
    return max(0.0, min(1.0, p))


def under_prob(line: float, lam: float, ge: Callable[[int, float], float]) -> float:
    """P(corners <= floor(line)), the exact complement of the over at the same .5 line.

    Only ever called with a .5 line. On an integer line the exact number is a push and
    this would be wrong — see the note in odds_feed about why integer lines are refused.
    """
    return max(0.0, min(1.0, 1.0 - ge(int(line) + 1, lam)))


def build_extra_markets(lambdas: Dict[str, float], odds: Dict[str, float],
                        team_ge: Callable[[int, float], float],
                        total_ge: Callable[[int, float], float],
                        fair_odds: Callable[[float], Optional[float]],
                        ev_percent: Callable[[float, float], float],
                        tier_for_ev: Callable[[float], str],
                        team_lines: Iterable[float], total_lines: Iterable[float],
                        pairs: Optional[Iterable[Tuple[int, int]]] = None,
                        both_lines: Iterable[float] = BOTH_LINES) -> List[dict]:
    """The unders and the both-teams lines, shaped exactly like build_markets' rows.

    Shaped identically on purpose: every screen, the spreadsheet, the bot card and the
    value board's credibility check all read `{key, group, label, line, prob, fair_odds,
    book_odds, ev, tier}`, and a market that arrives in a different shape is a market each
    of them has to learn about separately.
    """
    rows: List[dict] = []
    pair_rows = list(pairs or [])

    def add(key, group, group_label, line, label, p, extra=None):
        book = odds.get(key)
        ev = ev_percent(book, p) if book else None
        row = {"key": key, "group": group, "group_label": group_label, "line": line,
               "label": label, "prob": round(p * 100, 1), "fair_odds": fair_odds(p),
               "book_odds": book, "ev": ev,
               "tier": tier_for_ev(ev) if ev is not None else None}
        if extra:
            row.update(extra)
        rows.append(row)

    # --- unders, on every group that already has overs -------------------------------
    for group, group_label, lam, lines, ge in (
            ("total", "Total", lambdas.get("total"), total_lines, total_ge),
            ("home", "Home Team", lambdas.get("home"), team_lines, team_ge),
            ("away", "Away Team", lambdas.get("away"), team_lines, team_ge)):
        if not lam:
            continue
        for line in lines:
            add(f"{group}_under_{line}", f"{group}_under", group_label, line,
                f"Under {line}", under_prob(line, lam, ge))

    # --- both teams over -------------------------------------------------------------
    lh, la = lambdas.get("home"), lambdas.get("away")
    if lh and la:
        for line in both_lines:
            k = int(line) + 1
            dep = dependence(pair_rows, k)
            p = both_over_prob(k, lh, la, team_ge, (dep or {}).get("factor", 1.0))
            add(f"both_over_{line}", "both", "Both Teams", line, f"Over {line}", p,
                # SAID ON THE ROW, because a joint price built on a measured factor and
                # one built on an assumption of independence are different claims, and
                # the row is read by a bot that cannot ask.
                {"dependence": dep,
                 "independent_prob": round(
                     both_over_prob(k, lh, la, team_ge, 1.0) * 100, 1)})
    return rows
