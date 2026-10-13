"""When the model says 65%, does it happen 65% of the time?

THE QUESTION, AND WHY IT IS THE RIGHT ONE. Every other record on this site answers "did
this bet win". That is a fact about a handful of selections. This answers "is the number
printed on the screen honest", which is a fact about the model itself and the thing a
sceptical reader actually wants before trusting anything else here. One game cannot say;
hundreds can. Take every time the model said about 65%, count how often it happened, and
the gap between those two numbers is the whole answer.

    residual = actual hit rate - the model's own stated probability

Zero means calibrated. Negative means the model promises more than it delivers, and every
EV figure computed from it is inflated by roughly that much.

SPLIT BY LINE AS WELL AS BY BAND, because a model can be honest at 4+ and overconfident at
7+ and a pooled table would show neither.

AND THE SHAPE OF THE ERROR NAMES ITS CAUSE — but not in the way it is usually stated. The
received version, including in this repo's own measure_calibration.py, is "if the gap
widens as the line goes up, it is the tail, so dispersion". That is backwards, and the
simulation in test_calibration_record.py is the evidence. Overdispersion inflates variance
in BOTH directions: more mass piles up near zero as well as out in the tail. Pricing with
r=11 against reality at r=1.5, at lambda 5.5:

    3+   model 86.1%   true 66.9%   -19.2
    5+   model 59.6%   true 47.1%   -12.5
    7+   model 32.6%   true 32.2%    -0.4
    8+   model 22.3%   true 26.4%    +4.1

So too little assumed spread makes the model OVERSTATE the likely claims and UNDERSTATE
the unlikely ones, and the gap shrinks and then changes sign as the line rises. Banded by
probability — which is how this table is built — that is a TILT: negative residuals at the
top, positive at the bottom, crossing over somewhere around a third. A LEVEL error looks
entirely different: every band off in the same direction by about the same amount. The two
call for different work, and reading the tilt as a level error is how a model gets a
constant subtracted from it when the distribution was the problem.

A correct mean does not buy correct tail probabilities. Corners are streaky — some games
have two and some have twelve — and a model that assumes games are more alike than they are
will overrate 5+ with the average spot on. NB_R, fixed at 11 for every team in every
league, is the suspect whenever the tilt shows up.

WHAT MAKES THIS AN HONEST RECORD RATHER THAN A FLATTERING ONE — four things, and the
fourth is the one most often skipped:

  1. THE PROBABILITY IS THE ONE THAT WAS FROZEN BEFORE KICK-OFF. snapshot_projections
     writes every upcoming fixture nightly, with no quality bar and both ends of the
     board. Recomputing a probability afterwards would use a sample that now contains the
     result, and the model would be graded against a version of itself that knew more.

  2. EVERY FIXTURE, NOT THE GOOD ONES. The snapshot has no filter, so this has no
     selection to explain away. That matters more than it sounds: a table built from the
     model's most confident picks measures the winner's curse as much as the model.

  3. VOIDS AND UNGRADED FIXTURES ARE DROPPED, NEVER SCORED AS LOSSES. A fixture whose
     result never synced has no answer, and counting it as a miss manufactures exactly
     the overconfidence this is meant to detect.

  4. THE DENOMINATOR IS REPORTED TWICE, and this is the caveat a calibration table most
     easily hides. One fixture produces many claims — six team lines on each side plus the
     match totals — and they are NOT independent: a game with twelve corners lands home
     3+, 4+ and 5+ together. "212 selections" reads as 212 trials and is nothing of the
     sort. So every row carries `claims` AND `fixtures`, and the second is the one closer
     to the real sample size.

NOTHING HERE RANKS ANYTHING OR CLAIMS AN EDGE. It cannot justify a bet. The only actions it
can justify are recalibrating the model or saying plainly on the site that a stated
percentage runs high.
"""
import math
from collections import defaultdict
from typing import Callable, Dict, List, Optional

# Bands over the model's STATED probability, in percent.
#
# THE EDGES AT 60, 65 AND 70 ARE THE ONES ASKED FOR, and they are also where the useful
# corner lines land — a 5+ on a side averaging six sits right there. The bands above 75
# exist so the table covers the whole range rather than only the part somebody has a
# theory about: a model honest at 65 and wild at 85 is still one that cannot be trusted.
#
# AND THE LOWER EDGES ARE NOT PADDING. The first draft had a single "under 55%" bucket; on
# a simulated season it held 5,564 of 10,800 claims, averaged a promise of 32.6% and showed
# a residual of -0.3 — a flat, reassuring, meaningless number. It was meaningless because
# the sign of the error CHANGES inside that range: an overdispersed model overstates
# claims around 50% and understates ones around 15%, and pooled in one bucket those cancel
# exactly. The bucket that looked cleanest was the one hiding the most, and it also hid the
# tilt that names the cause. Resolving the bottom of the range is what makes the table
# diagnostic rather than decorative.
BAND_EDGES = (25.0, 35.0, 45.0, 55.0, 60.0, 65.0, 70.0, 75.0, 80.0)

# Below this a band is PRINTED AND MARKED, never hidden. Dropping a thin band would make
# the table a selection of the bands that happened to fill up, which is the same fault as
# a record that drops its losing months.
MIN_BAND = 25

# The lines a corner market is actually priced around. Team lines are whole numbers
# because that is how they are sold — "5+ corners" is Over 4.5 and cannot push.
TEAM_LINES = (3, 4, 5, 6, 7, 8)
MATCH_LINES = (8, 9, 10, 11, 12, 13)


def wilson(hits: int, n: int, z: float = 1.96):
    """95% interval on a hit rate, in percent.

    WILSON, NOT THE TEXTBOOK INTERVAL, for the reason measure_calibration gives: at the
    sample sizes and rates here the normal approximation runs past 100%, and an interval
    that cannot be exceeded can never say the promise sits outside it — which is the one
    thing the interval is here to do.
    """
    if n <= 0:
        return (0.0, 100.0)
    p = hits / n
    denom = 1 + z * z / n
    centre = p + z * z / (2 * n)
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return (max(0.0, (centre - half) / denom) * 100.0,
            min(1.0, (centre + half) / denom) * 100.0)


def band_of(prob: Optional[float]) -> Optional[str]:
    """Which band a stated probability falls in, as a label. None for no probability.

    NOT A DEFAULT. A claim with no stored probability has no band, and inventing one would
    put a row with no promise into a table that is entirely about promises.
    """
    if prob is None:
        return None
    try:
        p = float(prob)
    except (TypeError, ValueError):
        return None
    if not (0.0 <= p <= 100.0):
        return None
    lo = None
    for edge in BAND_EDGES:
        if p < edge:
            return f"under {edge:g}%" if lo is None else f"{lo:g}-{edge:g}%"
        lo = edge
    return f"{BAND_EDGES[-1]:g}%+"


def band_keys() -> List[str]:
    """Every band, low to high, so a table can print an empty one rather than skip it."""
    out, lo = [], None
    for edge in BAND_EDGES:
        out.append(f"under {edge:g}%" if lo is None else f"{lo:g}-{edge:g}%")
        lo = edge
    out.append(f"{BAND_EDGES[-1]:g}%+")
    return out


def claims_for(entry: dict,
               team_prob: Callable[[int, float], float],
               match_prob: Callable[[int, float], float],
               team_lines=TEAM_LINES,
               match_lines=MATCH_LINES) -> List[dict]:
    """Every corner line this frozen fixture carries a probability for.

    THE PROBABILITY COMES FROM THE SNAPSHOT WHERE THE SNAPSHOT HAS ONE, and is derived
    from the frozen lambda only where it does not. Both are legitimate and they are not
    the same thing, so the row says which:

      stored   the number the site actually published that night. The record.
      derived  today's distribution applied to a lambda frozen before kick-off. Still
               free of look-ahead bias — the lambda knew nothing about the result — but
               it is the model as it is NOW, not as it was. If NB_R is ever retuned,
               every derived row silently changes and no stored row does.

    Snapshots written before this file existed carry lambdas and no probabilities, so
    deriving is what makes a table possible today instead of in three months. The
    distinction is reported rather than smoothed over, because a reader who is told
    "derived" can discount it and a reader who is not, cannot.

    `side` NAMES WHOSE CORNERS, always. A home 5+ and an away 5+ are different bets on the
    same fixture, and a table that pooled them under "5+" would be averaging two claims it
    could no longer separate.
    """
    out = []
    stored = entry.get("probs") or {}
    for side, lam_key in (("home", "lambda_home"), ("away", "lambda_away")):
        lam = entry.get(lam_key)
        if lam is None:
            continue
        for line in team_lines:
            key = f"{side}_{line}"
            p = stored.get(key)
            source = "stored"
            if p is None:
                p = team_prob(line, float(lam)) * 100.0
                source = "derived"
            out.append({"market": "team", "side": side, "line": line,
                        "prob": round(float(p), 2), "source": source,
                        "fixture_id": entry.get("fixture_id"),
                        "kickoff": entry.get("kickoff"),
                        "league_id": entry.get("league_id")})
    lam_total = entry.get("lambda_total")
    if lam_total is not None:
        for line in match_lines:
            key = f"total_{line}"
            p = stored.get(key)
            source = "stored"
            if p is None:
                p = match_prob(line, float(lam_total)) * 100.0
                source = "derived"
            out.append({"market": "match", "side": "total", "line": line,
                        "prob": round(float(p), 2), "source": source,
                        "fixture_id": entry.get("fixture_id"),
                        "kickoff": entry.get("kickoff"),
                        "league_id": entry.get("league_id")})
    return out


def grade_claim(claim: dict, actual: dict) -> Optional[int]:
    """Did it happen? 1 / 0 / None.

    None IS A REAL ANSWER and must stay distinct from 0. A fixture whose result never
    synced, or a side whose corner count is missing, has no outcome — scoring it as a miss
    would drag every actual rate down and invent the overconfidence this file exists to
    measure. The caller drops them and says how many it dropped.

    `>=` BECAUSE THESE LINES ARE SOLD AS "5+", which is Over 4.5 and cannot push. There is
    no void case to handle here, and inventing one would be wrong in the other direction.
    """
    if not actual:
        return None
    key = {"home": "home_corners", "away": "away_corners",
           "total": "total_corners"}.get(claim.get("side"))
    value = (actual or {}).get(key)
    if value is None or isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    line = claim.get("line")
    if line is None:
        return None
    return 1 if value >= line else 0


def _row(claims: List[dict]) -> dict:
    """One line of a table: the promise, what happened, and both denominators."""
    n = len(claims)
    hits = sum(1 for c in claims if c.get("hit") == 1)
    promised = sum(c["prob"] for c in claims) / n if n else None
    actual = 100.0 * hits / n if n else None
    lo, hi = wilson(hits, n)
    fixtures = len({c.get("fixture_id") for c in claims if c.get("fixture_id")})
    return {
        "claims": n,
        # SEE THE HEADER. Claims within a fixture are correlated, so this is the number
        # closer to the real sample size and it is never left out.
        "fixtures": fixtures,
        "hits": hits,
        "promised": round(promised, 1) if promised is not None else None,
        "actual": round(actual, 1) if actual is not None else None,
        "residual": round(actual - promised, 1)
                    if (actual is not None and promised is not None) else None,
        "lo": round(lo, 1), "hi": round(hi, 1),
        # The interval is what decides whether a residual means anything, so the verdict
        # is computed here rather than left to a caller who might forget to.
        "thin": n < MIN_BAND,
        "calibrated": (promised is not None and lo <= promised <= hi),
        "derived": sum(1 for c in claims if c.get("source") == "derived"),
    }


def by_band(rows: List[dict]) -> List[dict]:
    """The headline table: one line per probability band, low to high.

    EVERY BAND IS PRINTED, including the empty ones, so the table is the whole range
    rather than the part that happened to fill up.
    """
    groups = defaultdict(list)
    for r in rows:
        b = band_of(r.get("prob"))
        if b:
            groups[b].append(r)
    return [{"band": k, **_row(groups.get(k, []))} for k in band_keys()]


def by_line(rows: List[dict], market: str = "team") -> List[dict]:
    """One line per corner line, within one market.

    SPLIT BY MARKET FIRST, because a team's 8+ and a match total of 8+ are different
    claims about different quantities — the match number is roughly twice the team one —
    and a table keyed on the bare line would add them together.
    """
    groups = defaultdict(list)
    for r in rows:
        if r.get("market") == market:
            groups[r["line"]].append(r)
    return [{"line": k, **_row(groups[k])} for k in sorted(groups)]


def by_band_and_line(rows: List[dict], market: str = "team") -> List[dict]:
    """The grid that separates a level error from a tail error.

    THIS IS THE TABLE THAT DIAGNOSES. A gap of the same size at every line is a level
    error and one parameter fixes it. A gap that widens with the line is the distribution's
    tail being wrong, which is dispersion, and no amount of shifting the mean will help.
    The pooled table cannot tell those apart, and they call for different work.
    """
    out = []
    for band in band_keys():
        cells = []
        for line in sorted({r["line"] for r in rows if r.get("market") == market}):
            sel = [r for r in rows
                   if r.get("market") == market and r["line"] == line
                   and band_of(r.get("prob")) == band]
            if sel:
                cells.append({"line": line, **_row(sel)})
        if cells:
            out.append({"band": band, "lines": cells})
    return out


def summarise(rows: List[dict], ungraded: int = 0) -> dict:
    """The whole record in one object, with what it cannot support said out loud."""
    graded = [r for r in rows if r.get("hit") in (0, 1)]
    overall = _row(graded)
    bands = by_band(graded)
    readable = [b for b in bands if not b["thin"] and b["claims"]]
    worst = min((b for b in readable), key=lambda b: b["residual"], default=None)
    return {
        "overall": overall,
        "bands": bands,
        "team_lines": by_line(graded, "team"),
        "match_lines": by_line(graded, "match"),
        "grid": by_band_and_line(graded, "team"),
        "ungraded": ungraded,
        "derived_claims": overall["derived"],
        "min_band": MIN_BAND,
        # WHICH KIND of miscalibration, where the table can see one. None is a real answer
        # and the common one — naming a cause off a sample that cannot support it is how
        # the next piece of work goes in the wrong direction.
        "shape": shape_of(readable),
        "shape_note": SHAPE_NOTE.get(shape_of(readable) or ""),
        # THE VERDICT IS A SENTENCE, NOT A SCORE, and it refuses to give one where the
        # sample cannot carry it. "Not enough yet" is the correct answer far more often
        # than a table like this usually admits.
        "verdict": _verdict(readable, worst),
    }


def shape_of(bands: List[dict]) -> Optional[str]:
    """Which KIND of miscalibration the table is showing, where it shows one.

    See the header. A level error misses every band in the same direction; overdispersion
    TILTS — overstating the likely claims and understating the unlikely ones. The two need
    different work, so guessing between them is worse than declining to say.

    DECLINES WHEREVER IT CANNOT SEE BOTH ENDS. A tilt is a statement about the top of the
    range relative to the bottom, so with only one end populated there is nothing to
    compare and the honest answer is None. Ten points is the threshold for "clearly"; it
    is a judgement, and a smaller gap is reported as no shape rather than as a faint one.
    """
    usable = [b for b in bands if not b["thin"] and b["claims"] and b["residual"] is not None]
    if len(usable) < 4:
        return None
    usable.sort(key=lambda b: b["promised"] or 0)

    # MEASURED END TO END, NOT AS TWO HALVES AVERAGED. Averaging everything below a
    # threshold was the first attempt and it failed on a season where the tilt was
    # unmistakable: the band straddling the crossover sits near zero BY CONSTRUCTION, so
    # including it in the low half pulled a +7.1 bottom down to +4.0 and the shape read as
    # None exactly when the table was at its clearest. The two lowest and two highest
    # populated bands are far from the crossover on either side, which is where a tilt
    # actually shows, and taking two of each rather than one keeps a single noisy band
    # from deciding it.
    lo = sum(b["residual"] for b in usable[:2]) / 2
    hi = sum(b["residual"] for b in usable[-2:]) / 2
    tilt = lo - hi
    level = (lo + hi) / 2

    if tilt > 10.0:
        return "overdispersion"
    if tilt < -10.0:
        return "underdispersion"
    if abs(tilt) < 5.0 and abs(level) > 5.0:
        return "level"
    return None


SHAPE_NOTE = {
    "overdispersion": (
        "The high percentages run low and the low ones run high — the signature of real "
        "corner counts being streakier than the model assumes. That is a dispersion "
        "problem (NB_R is fixed at 11 for every team), not something a constant offset "
        "fixes."),
    "underdispersion": (
        "The opposite tilt: the model is treating corners as streakier than they are."),
    "level": (
        "Every band is off in the same direction by about the same amount, which is a "
        "level error rather than a shape one."),
}


def _verdict(readable: List[dict], worst: Optional[dict]) -> str:
    if not readable:
        return ("Not enough settled fixtures yet to say. Every band is below "
                f"{MIN_BAND} graded claims.")
    off = [b for b in readable if not b["calibrated"]]
    if not off:
        return ("Every band with enough behind it lands inside its 95% interval — the "
                "stated percentages are holding up so far.")
    low = [b for b in off if (b["residual"] or 0) < 0]
    if low and len(low) == len(off):
        # THE AVERAGE MISS, WITH THE WORST NAMED SEPARATELY. The first version quoted the
        # worst band alone as "optimistic by about N points", which on a table whose misses
        # ran 6 to 14 told a reader the typical case was the extreme one. Overstating the
        # fault is still misreporting it, and a page arguing for its own honesty is the
        # last place to do it.
        avg = sum(abs(b["residual"]) for b in low) / len(low)
        tail = (f" by about {avg:.0f} points on average"
                + (f", {abs(worst['residual']):.0f} at worst" if worst else "") + ".")
        return ("The stated percentages are running HIGH: "
                + ", ".join(f"{b['band']} came in at {b['actual']}%" for b in low[:3])
                + ". Treat any EV figure computed from them as optimistic" + tail)
    return ("Mixed: at least one band sits outside its interval in each direction, which "
            "is a shape error rather than a level one. See the per-line grid.")
