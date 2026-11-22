"""Will the side we are backing be CHASING, or parking the bus, or buried?

WHY THIS EXISTS. A weekend card (20-22 Nov 2026) landed 45 of 115 team-corner lines and
the losses were not spread evenly. Thirty-six lines on underdogs away at the big sides —
Köln at Bayern, Villarreal at Barcelona, Venezia at Juventus, Angers at Paris FC — landed
4 and lost 29.5 points flat. Those sides averaged under two corners. Outside that group
the card was close to break-even. The pattern in the losers was game state, not form:

  - a side that went ahead sat deep and stopped winning corners (Magdeburg 0-2 up at
    half-time: 1 corner; Sirius 1-0 up on 41% of the ball: 3)
  - a side facing a much stronger opponent never got the ball to chase with, whatever
    the score (Bayern 72% possession, Barcelona 70%)

THE REPO ALREADY KNOWS THE EFFECT IS REAL. state_bias (issue #107, 11,122 team-matches)
found a side trailing at half-time beats the model's price by about four points at 5+,
and a side leading falls about five short — "led at HT, did NOT win" worst of all, seven
points short. Issue #321 repeated it on 17,058. What it has never found is a way to tell
BEFORE kick-off which side will be in which state: the opponent's first-half scoring rate
was falsified five times, and the chase board's ordering replayed flat against random.

SO THIS TAKES A DIFFERENT ROUTE, and it is three questions about a side rather than one
rate about its opponent:

  CHASE    When this side HAS been behind at half-time, did its corners go up or down
           against its own average? Some sides throw bodies forward, some sit deep
           whatever the score. A trait, so it gets a long lookback (STATE_WINDOW).
  PARK     The same question for leading. A side whose corners collapse when ahead is
           the one that nicks a goal and kills the over.
  GAP      How much stronger is the opponent, by goal difference per game? A side that
           is weaker but not hopeless is the one likely to trail by ONE with time left —
           the only state that pays. A huge gap is the Bayern game.

Plus one floor: SHOTS. A side that does not shoot does not win corners, whatever state
it is in (Cerezo: 58% of the ball, 2 shots, 0 corners).

WHAT THIS CANNOT SEE, said plainly because it decides how much the verdict is worth:

  - CORNERS ARE FULL-MATCH ONLY (probe_corner_halves, issue #260). "Corners when trailing
    at half-time" is the side's FULL-MATCH count in games where it was behind at the
    break, not corners won while behind. A chase concentrated after the break reads
    diluted here. It cannot be fixed for history.
  - IT IS UNMEASURED AS A FILTER. measure_chase_filter.py replays exactly these rules
    walk-forward against the live model with a random control. Until that has run and
    shown the verdicts separating, the verdict is a label to read beside the price, not
    a reason to reorder the board — which is why value_board does not sort on it.
  - "GIVING UP" IS NOT MODELLED, deliberately. state_bias's own numbers say a side 2+
    down at half-time still BEATS the model at 5+ (965 team-matches), so the instinct that
    a buried side stops winning corners is not supported in aggregate. The gap test is
    about never getting the ball, not about morale.

Pure functions: no database, no HTTP, no imports from server. The harness and the live
board both call this module, so the rules being measured are the rules being shown.
"""
from typing import Dict, List, Optional

#: The chase and park TRAITS need a long lookback: at a ten-match window only about two
#: of a side's games involve trailing at half-time, too few to say anything. Same number
#: measure_features uses for the same reason.
STATE_WINDOW = 40

#: Strength and shot volume are FORM, so they use the ten-match window the rest of the
#: model and every post on the channel use.
FORM_WINDOW = 10

#: Shrinkage towards "no effect" for the chase and park ratios. A side with two trailing
#: games and a 1.6x ratio is mostly noise; k pseudo-games at 1.0 pull it back. The same
#: k measure_features shrinks the chase trait with.
SHRINK_K = 5

#: Raw games in a state before the trait is NAMED at all. Below this the ratio is still
#: computed and shown, but no chaser/parker flag is raised on it.
MIN_STATE_GAMES = 4

#: Shrunk ratio thresholds. 10% either side of the side's own average: big enough that a
#: 6-corner side is winning most of a corner more or less in that state, small enough to
#: fire on a real fraction of the division rather than on three outliers.
CHASER_RATIO = 1.10
PARKER_RATIO = 0.90

#: Goal difference per game, opponent minus us, over FORM_WINDOW games. 1.0 is a full
#: goal a game better — the shape of Bayern v Köln, Barcelona v Villarreal, Genk v La
#: Louvière on the weekend that prompted this. Below CLOSE_LOW the side is the stronger
#: one and less likely to be chasing at all.
MISMATCH_GD = 1.0
CLOSE_LOW = -0.4

#: A side averaging under this share of its league's shots is not going to win corners in
#: any game state. Shots of 0 are treated as missing: sync_real writes `shots or 0`, so a
#: provider gap and a genuine zero look identical and the former is far more common.
BLUNT_SHOTS = 0.85

#: Opponent's no-margin win probability at or above this is roughly "odds-on at 1.50 or
#: shorter" once the book's margin is taken off. Shown as a fact beside the verdict when a
#: Match Winner price was fetched; NOT part of the verdict, because no stored history of
#: match prices exists to measure it against.
MARKET_SHORT = 0.63

VERDICT_ORDER = {"chase_spot": 0, "neutral": 1, "caution": 2, "avoid": 3}


def _ht_state(m: dict) -> Optional[int]:
    f, a = m.get("fh_goals_for"), m.get("fh_goals_against")
    if f is None or a is None:
        return None
    return (f > a) - (f < a)


def _shrunk(raw: Optional[float], n: int, k: int = SHRINK_K) -> Optional[float]:
    if raw is None:
        return None
    return (raw * n + 1.0 * k) / (n + k)


def state_trait(matches: List[dict], window: int = STATE_WINDOW) -> dict:
    """How this side's corners move when it trails, and when it leads, at half-time.

    Ratios are against the side's OWN average over the same pool, so a side that wins
    nine a game and one that wins three are judged on the same scale."""
    pool = [m for m in (matches or []) if m.get("corners_for") is not None][-window:]
    if not pool:
        return {"games": 0, "base": None,
                "trail": {"games": 0, "avg": None, "raw": None, "ratio": None},
                "lead": {"games": 0, "avg": None, "raw": None, "ratio": None}}
    base = sum(m["corners_for"] for m in pool) / len(pool)

    def bucket(state):
        rows = [m["corners_for"] for m in pool if _ht_state(m) == state]
        n = len(rows)
        avg = sum(rows) / n if n else None
        raw = (avg / base) if (n and base) else None
        return {"games": n, "avg": round(avg, 2) if avg is not None else None,
                "raw": round(raw, 3) if raw is not None else None,
                "ratio": round(_shrunk(raw, n), 3) if raw is not None else None}

    return {"games": len(pool), "base": round(base, 2),
            "trail": bucket(-1), "lead": bucket(1)}


def goal_diff_per_game(matches: List[dict], window: int = FORM_WINDOW) -> Optional[float]:
    pool = [m for m in (matches or [])
            if m.get("goals_for") is not None and m.get("goals_against") is not None][-window:]
    if not pool:
        return None
    return sum(m["goals_for"] - m["goals_against"] for m in pool) / len(pool)


def shots_per_game(matches: List[dict], window: int = FORM_WINDOW) -> Optional[float]:
    pool = [m["shots_for"] for m in (matches or []) if m.get("shots_for")][-window:]
    return sum(pool) / len(pool) if pool else None


def match_winner(entry: dict) -> Optional[dict]:
    """The market's view of who wins, from the Match Winner prices on an /odds entry.

    FREE: /odds is already called per fixture for the corner markets and the response
    carries every market, Match Winner included. This is read out of the same payload.

    CONSENSUS, NOT BEST PRICE. For a backer the best price is the right number; for "how
    likely is this" it is the wrong one, because the best price on each outcome comes from
    a different book and together they can sum under 100%. So each book's three prices are
    turned into probabilities with that book's margin removed, then averaged."""
    per_book = []
    for bm in (entry or {}).get("bookmakers") or []:
        for bet in bm.get("bets") or []:
            if str(bet.get("name") or "").strip() != "Match Winner":
                continue
            prices = {}
            for v in bet.get("values") or []:
                key = {"Home": "home", "Draw": "draw", "Away": "away"}.get(
                    str(v.get("value") or "").strip())
                try:
                    odd = float(v.get("odd"))
                except (TypeError, ValueError):
                    continue
                if key and odd > 1.0:
                    prices[key] = odd
            if len(prices) == 3:
                inv = {k: 1.0 / p for k, p in prices.items()}
                s = sum(inv.values())
                per_book.append({k: x / s for k, x in inv.items()})
    if not per_book:
        return None
    n = len(per_book)
    out = {k: round(sum(b[k] for b in per_book) / n, 4) for k in ("home", "draw", "away")}
    out["books"] = n
    return out


def side_verdict(team_matches: List[dict], opp_matches: List[dict],
                 league_shots: Optional[float] = None,
                 opp_win_prob: Optional[float] = None) -> dict:
    """Everything above for ONE side of one fixture, plus a verdict and the reasons.

    `team_matches` / `opp_matches` are real_matches-shaped rows, oldest first, carrying
    corners_for, goals_for/against, fh_goals_for/against and shots_for. The harness builds
    rows of the same shape from fixture_stats so it scores exactly this function.

    VERDICTS, in the order they are decided:
      avoid       the opponent is MISMATCH_GD a game better, or this side is blunt —
                  either way the corners are not coming, whatever the model says
      chase_spot  weaker-or-level but not swamped, AND a side whose corners have gone up
                  when it trailed — the one state that pays, from a side that responds
      caution     a parker: corners have dropped when it led, so an early goal for it
                  kills the bet
      neutral     none of the above, or too little history to say
    """
    trait = state_trait(team_matches)
    gd_us = goal_diff_per_game(team_matches)
    gd_them = goal_diff_per_game(opp_matches)
    gap = (gd_them - gd_us) if (gd_us is not None and gd_them is not None) else None
    shots = shots_per_game(team_matches)
    shot_ratio = (shots / league_shots) if (shots and league_shots) else None

    trail, lead = trait["trail"], trait["lead"]
    chaser = (trail["games"] >= MIN_STATE_GAMES and trail["ratio"] is not None
              and trail["ratio"] >= CHASER_RATIO)
    fader = (trail["games"] >= MIN_STATE_GAMES and trail["ratio"] is not None
             and trail["ratio"] <= PARKER_RATIO)
    parker = (lead["games"] >= MIN_STATE_GAMES and lead["ratio"] is not None
              and lead["ratio"] <= PARKER_RATIO)
    mismatch = gap is not None and gap >= MISMATCH_GD
    close = gap is not None and CLOSE_LOW <= gap < MISMATCH_GD
    blunt = shot_ratio is not None and shot_ratio < BLUNT_SHOTS
    market_short = opp_win_prob is not None and opp_win_prob >= MARKET_SHORT

    flags, reasons = [], []
    if mismatch:
        flags.append("mismatch")
        reasons.append(f"Opponent is {gap:.1f} goals a game better over the last "
                       f"{FORM_WINDOW} — likely to have the ball, not give it up.")
    if blunt:
        flags.append("blunt")
        reasons.append(f"Only {shots:.1f} shots a game ({shot_ratio * 100:.0f}% of the "
                       f"league average) — corners come from shots.")
    if chaser:
        flags.append("chaser")
        reasons.append(f"Wins {trail['avg']:.1f} corners when behind at half-time against "
                       f"{trait['base']:.1f} overall ({trail['games']} games).")
    if fader:
        flags.append("fades_behind")
        reasons.append(f"Corners DROP when behind at half-time: {trail['avg']:.1f} against "
                       f"{trait['base']:.1f} overall ({trail['games']} games).")
    if parker:
        flags.append("parker")
        reasons.append(f"Sits on a lead: {lead['avg']:.1f} corners when ahead at half-time "
                       f"against {trait['base']:.1f} overall ({lead['games']} games).")
    if close:
        flags.append("close")
    if market_short:
        flags.append("market_short")
        reasons.append(f"Market makes the opponent {opp_win_prob * 100:.0f}% to win — "
                       f"odds-on, around 1.50 or shorter.")

    if mismatch or blunt:
        verdict = "avoid"
    elif chaser and close:
        verdict = "chase_spot"
        reasons.insert(0, f"Underdog or level but not swamped (gap {gap:+.1f} goals a "
                          f"game) — the game most likely to have this side ONE behind.")
    elif parker or fader:
        verdict = "caution"
    else:
        verdict = "neutral"

    return {
        "verdict": verdict, "flags": flags, "reasons": reasons,
        "gap": round(gap, 2) if gap is not None else None,
        "shots": round(shots, 1) if shots is not None else None,
        "shot_ratio": round(shot_ratio, 2) if shot_ratio is not None else None,
        "opp_win_prob": opp_win_prob,
        "trait": trait,
        # Said on every row, because the board shows this beside a price and a reader
        # will otherwise take it as a measured edge.
        "measured": False,
    }
