"""Context lines for a pick — the short, checkable sentences that sit under it.

WHAT THIS IS FOR. A pick on its own is a price and a line. The reader wants to know why,
and "the model says so" is not an answer anybody acts on. These are the surrounding
facts, each one computed from the team's own stored matches so it can be checked against
a scoreline rather than taken on trust.

THE RULES EVERY LINE HERE OBEYS, because a context line is read as evidence even when it
is only colour, and a wrong one is worse than a missing one:

  1. EVIDENCE AND COLOUR ARE LABELLED APART. A corner run bears on a corner pick. An
     unbeaten run does not. Both are worth printing and only one is an argument, so each
     line carries `tier`, and `evidence` always outranks `colour`.

  2. EVERY LINE CARRIES ITS DENOMINATOR. "Often" is not a stat. A claim says how many
     games it was computed over, and `n` travels with it so the caller can refuse a thin
     one.

  3. NOTHING SHORTER THAN MIN_WINDOW GETS PRINTED. "No clean sheet in 3" is three games.
     At a 50% base rate that happens by chance one time in eight, which is not a
     tendency, and a reader cannot tell the difference from the sentence.

  4. A PROVIDER STAT THAT IS MISSING IS NOT ZERO. sync_real stores an uncovered stat as
     None on purpose. Averaging those as zero would quietly invent a team with no shots,
     so every feature line counts its covered games and refuses below MIN_COVERED.

  5. REAL MATCHES ONLY, IN DATE ORDER. `team["matches"]` carries synthetic padding for
     thin sides; a context line off a generated game is a sentence about a match nobody
     played. And the stored order is not guaranteed, so "the last five" means the five
     latest BY DATE, not the last five in the list.

  6. NO LINE MAY IMPLY A HALF-LEVEL CORNER FIGURE. There is none and there cannot be —
     see the corner-half note in server.py (probe_corner_halves.py, issue #260). So the
     half-time state lines here report how OFTEN a side has been behind, and its
     FULL-MATCH corner average in those games, and never "corners won while chasing".
     The chase effect is real and we cannot measure it; saying we can would be the one
     dishonest sentence on the page.

MINUTES ARE THE MISSING GROUP. "Has spent 180 minutes behind in the last three" is the
best corner-context stat in football and it is not here, because `minutes_trailing` is
only populated by backfill_goal_events.py, which has never been run. goal_profile() in
server.py already consumes it and returns games=0 until it has. That backfill is the one
thing standing between this module and the chasing group.
"""
from typing import List, Optional

# ---- the floors. Each one is a refusal to print something that reads like a finding ----
MIN_WINDOW = 5      # games a run or a rate must span before it is a sentence
MIN_COVERED = 5     # covered games a provider-stat average needs (see rule 4)
MIN_BUCKET = 4      # games in a half-time state bucket before its average means anything
THIN_SEASON = 15    # below this the text says "in N games", never "this season"
RECENT = 5          # the standard short window, so every "recent" line means the same thing
RATE_WINDOW = 10    # the window a "9 of 10" style rate is taken over
RATE_FLOOR = 0.8    # a rate below this is not worth a sentence
MAX_COMPOUND = 2    # facts joined into one line. Three in a sentence stops being read.

EVIDENCE, COLOUR = "evidence", "colour"

# Lines that are the same fact in different words. The ranker emits at most one of each
# set, so turning them all on does not produce two sentences saying one thing.
ALIASES = (("corner_run", "corner_run_plain"),)


def _ordered(team: dict) -> List[dict]:
    """Real matches, oldest first. Rule 5 lives here and nowhere else."""
    rms = (team or {}).get("real_matches") or []
    return sorted([m for m in rms if m.get("corners_for") is not None],
                  key=lambda m: m.get("date") or "")


def _venue_pool(matches: List[dict], venue: Optional[str]) -> List[dict]:
    if venue == "home":
        return [m for m in matches if m.get("home")]
    if venue == "away":
        return [m for m in matches if not m.get("home")]
    return list(matches)


def _run(pool: List[dict], pred) -> int:
    """Consecutive games satisfying `pred`, counting back from the most recent."""
    n = 0
    for m in reversed(pool):
        if not pred(m):
            break
        n += 1
    return n


def _hits(pool: List[dict], pred) -> int:
    return sum(1 for m in pool if pred(m))


def _covered(pool: List[dict], key: str) -> List[float]:
    return [m[key] for m in pool if m.get(key) is not None]


def _avg(vals) -> Optional[float]:
    return (sum(vals) / len(vals)) if vals else None


def _season_phrase(n: int) -> str:
    """How to describe a sample out loud. A short record says its own length."""
    return f"in {n} games" if n < THIN_SEASON else "this season"


def _claim(key, group, tier, text, n, strength, subject="team", predicate=None,
           **extra) -> dict:
    """One verified line.

    `predicate` is the sentence WITHOUT its subject — "have won 5+ corners in 9 of 10".
    It is what makes two facts about the same side joinable into one line, which is how
    a reader actually wants them: "Boro have won 5+ in 9 of 10 and conceded in each of
    the last five", not two sentences starting with the same name. A claim with no
    predicate is one that does not read well joined to anything, and `compound()` leaves
    it alone."""
    out = {"key": key, "group": group, "tier": tier, "text": text,
           "n": n, "strength": round(float(strength), 3), "ambiguous": False,
           "subject": subject, "predicate": predicate}
    out.update(extra)
    return out


def _sentence(name: str, predicate: str) -> str:
    """A predicate said as a sentence. Ends it, so no caller has to remember to."""
    return f"{name} {predicate}."


# HOW LINES ARE RANKED, and why it is stated here rather than tuned per claim.
#
# The first version gave every generator its own ad-hoc "edge" number, and the scales
# did not match: a 12-game corner run scored 0.34 while "conceded 2+ in 12" scored 0.84,
# so the single most relevant line for a corner pick ranked ninth. Comparing claims
# needs one unit, and the unit cannot be invented per claim.
#
# So strength has exactly two parts. `effect` is ALWAYS normalised to 0..1 by one of the
# three helpers below, which is what makes two claims comparable at all. GROUP_WEIGHT is
# the editorial judgement — a corner run bears on a corner bet more than a goals line
# does — written down as a number instead of hidden inside a divisor.
GROUP_WEIGHT = {"corners": 1.0, "opponent": 0.85, "pressure": 0.8,
                "state": 0.5, "colour": 0.25}
FULL_RUN = 15          # a run this long is as persuasive as a run gets
FULL_RATIO = 0.5       # being 50% above the yardstick is as big an edge as we score


def _run_effect(run: int) -> float:
    return min(run / FULL_RUN, 1.0)


def _rate_effect(hits: int, of: int, base: float) -> float:
    """How far a hit rate clears the rate you would expect anyway."""
    if not of:
        return 0.0
    return max(0.0, min((hits / of - base) / (1.0 - base), 1.0))


def _ratio_effect(value: Optional[float], ref: Optional[float]) -> float:
    """How far an average clears its yardstick. No yardstick means no claimed effect."""
    if not value or not ref:
        return 0.0
    return max(0.0, min((value / ref - 1.0) / FULL_RATIO, 1.0))


def _strength(group: str, tier: str, effect: float, n: int) -> float:
    """Rank weight: relevance to the bet, times effect size, discounted by thin support.

    Support enters as a capped fraction rather than a multiplier so that twenty games of
    a mild edge does not bury five games of a large one — both are worth saying, and the
    bigger effect is the more interesting sentence."""
    support = 0.6 + 0.4 * (min(n, 20) / 20.0)
    weight = GROUP_WEIGHT.get(group, 0.5) * (1.0 if tier == EVIDENCE else 0.5)
    return weight * max(0.0, min(effect, 1.0)) * support


# =============================== A. corner-direct ===============================
# Straight from the corner counts. The only group whose subject IS the thing being bet,
# which is why its floors are the loosest and its strength the highest.

def _best_line(pool: List[dict]) -> Optional[tuple]:
    """The highest line this side has cleared in every one of its recent games."""
    recent = pool[-RECENT:]
    if len(recent) < MIN_WINDOW:
        return None
    floor = min(m["corners_for"] for m in recent)
    if floor < 1:
        return None
    return floor, _run(pool, lambda m: m["corners_for"] >= floor)


def a_corner_run(team, pool, name, **_):
    best = _best_line(pool)
    if not best:
        return None
    line, run = best
    if run < MIN_WINDOW:
        return None
    return _claim("corner_run", "corners", EVIDENCE,
                  _sentence(name, f"have won {line}+ corners in {run} straight games"),
                  run, _strength("corners", EVIDENCE,
                                 0.65 * _run_effect(run) + 0.35 * min(line / 10.0, 1.0),
                                 run),
                  predicate=f"have won {line}+ corners in {run} straight games",
                  line=line, run=run)


def a_corner_run_plain(team, pool, name, **_):
    """Same fact as a_corner_run, said without the plus sign. ALIASES keeps them apart."""
    best = _best_line(pool)
    if not best:
        return None
    line, run = best
    if run < MIN_WINDOW:
        return None
    return _claim("corner_run_plain", "corners", EVIDENCE,
                  _sentence(name, f"have not been held under {line} corners in {run} games"),
                  run, _strength("corners", EVIDENCE,
                                 0.65 * _run_effect(run) + 0.35 * min(line / 10.0, 1.0),
                                 run),
                  predicate=f"have not been held under {line} corners in {run} games",
                  line=line, run=run)


def a_corner_rate(team, pool, name, **_):
    """"Won 5+ corners in 9 of 10" — a RATE, which is a different claim from a run.

    A run of 9 cannot survive one bad night; 9 of 10 already has. A side can be 9 of 10
    with a run of two, when the miss was the second-most-recent game, and those are not
    the same bet. _hits_and_run in server.py splits them for the sheet export for the
    same reason, and the two must never be collapsed into one sentence here either."""
    window = pool[-RATE_WINDOW:]
    if len(window) < 8:
        return None
    best = None
    for line in range(1, 16):
        hits = _hits(window, lambda m, L=line: m["corners_for"] >= L)
        if hits / len(window) >= RATE_FLOOR:
            best = (line, hits)
    if not best:
        return None
    line, hits = best
    # A perfect rate IS a run, and a_corner_run says it better. Leave it to that one.
    if hits == len(window):
        return None
    pred = f"have won {line}+ corners in {hits} of their last {len(window)}"
    return _claim("corner_rate", "corners", EVIDENCE, _sentence(name, pred),
                  len(window),
                  _strength("corners", EVIDENCE,
                            0.6 * _rate_effect(hits, len(window), 0.5)
                            + 0.4 * min(line / 10.0, 1.0), len(window)),
                  predicate=pred, line=line, hits=hits, of=len(window))


def a_corner_avg(team, pool, name, league_avg=None, **_):
    recent = pool[-RECENT:]
    if len(recent) < MIN_WINDOW:
        return None
    avg = _avg([m["corners_for"] for m in recent])
    ref = league_avg or avg
    return _claim("corner_avg", "corners", EVIDENCE,
                  _sentence(name, f"are averaging {avg:.1f} corners a game across their "
                            f"last {len(recent)}"), len(recent),
                  _strength("corners", EVIDENCE, _ratio_effect(avg, ref), len(recent)),
                  predicate=f"are averaging {avg:.1f} corners a game across their last "
                            f"{len(recent)}",
                  value=round(avg, 2))


def a_corner_string(team, pool, name, **_):
    recent = pool[-RECENT:]
    if len(recent) < MIN_WINDOW:
        return None
    vals = [m["corners_for"] for m in reversed(recent)]   # newest first, how form reads
    return _claim("corner_string", "corners", EVIDENCE,
                  f"{name}'s last {len(vals)}: " + ", ".join(str(v) for v in vals) + ".",
                  len(vals),
                  _strength("corners", EVIDENCE, min(min(vals) / 8.0, 1.0), len(vals)),
                  values=vals, low=min(vals), high=max(vals))


def a_out_cornered(team, pool, name, venue=None, **_):
    vp = _venue_pool(pool, venue)
    if len(vp) < MIN_WINDOW:
        return None
    won = _hits(vp, lambda m: m["corners_for"] > m["corners_against"])
    if won / len(vp) < 0.6:
        return None
    where = "at home" if venue == "home" else "away" if venue == "away" else ""
    return _claim("out_cornered", "corners", EVIDENCE,
                  f"{name} have out-cornered the opposition in {won} of {len(vp)} "
                  f"{where}.".replace("  ", " "),
                  len(vp), _strength("corners", EVIDENCE, _rate_effect(won, len(vp), 0.5), len(vp)),
                  predicate=f"have out-cornered the opposition in {won} of {len(vp)} "
                            f"{where}".strip(),
                  won=won, of=len(vp))


def a_double_figures(team, pool, name, **_):
    recent = pool[-RECENT:]
    if len(recent) < MIN_WINDOW:
        return None
    big = _hits(recent, lambda m: m["corners_for"] >= 10)
    if big < 2:
        return None
    return _claim("double_figures", "corners", EVIDENCE,
                  f"{name} have hit double figures for corners {big} times in their "
                  f"last {len(recent)}.", len(recent),
                  _strength("corners", EVIDENCE, _rate_effect(big, len(recent), 0.2),
                            len(recent)),
                  predicate=f"have hit double figures for corners {big} times in their "
                            f"last {len(recent)}",
                  count=big)


# =============================== B. pressure proxies =============================
# Why the corners happen. Blocked shots lead this group on merit: a blocked shot is
# frequently a corner one touch later, and it is already the term driving the live
# lambda (V3_BLOCKED_WEIGHT in server.py).

def _feature_line(pool, key, covered_min=MIN_COVERED):
    vals = _covered(pool, key)
    if len(vals) < covered_min:
        return None
    return _avg(vals), len(vals)


def b_blocked(team, pool, name, refs=None, **_):
    got = _feature_line(pool, "blocked_shots_for")
    if not got:
        return None
    avg, n = got
    ref = (refs or {}).get("avg_blocked")
    if ref:
        return _claim("blocked", "pressure", EVIDENCE,
                      f"{name} are forcing {avg:.1f} blocked shots a game against a "
                      f"league average of {ref:.1f} — blocks that often come back as "
                      f"corners.", n,
                      _strength("pressure", EVIDENCE, _ratio_effect(avg, ref), n),
                      value=round(avg, 2), ref=round(ref, 2))
    return _claim("blocked", "pressure", EVIDENCE,
                  f"{name} are forcing {avg:.1f} blocked shots a game over {n} games.",
                  n, _strength("pressure", EVIDENCE, 0.30, n), value=round(avg, 2))


def b_shots(team, pool, name, refs=None, **_):
    recent = pool[-RECENT:]
    got = _feature_line(recent, "shots_for", covered_min=min(MIN_COVERED, len(recent)))
    if not got or len(recent) < MIN_WINDOW:
        return None
    avg, n = got
    ref = (refs or {}).get("avg_shots")
    tail = f" against a league average of {ref:.0f}" if ref else ""
    return _claim("shots", "pressure", EVIDENCE,
                  f"{name} are taking {avg:.0f} shots a game over their last {n}{tail}.",
                  n, _strength("pressure", EVIDENCE,
                            _ratio_effect(avg, ref) if ref else 0.25, n),
                  value=round(avg, 2))


def b_opp_blocks(team, pool, name, opp=None, opp_pool=None, opp_name=None,
                 opp_venue=None, **_):
    if not opp_pool:
        return None
    vp = _venue_pool(opp_pool, opp_venue)
    vals = _covered(vp, "blocked_shots_for")
    if len(vals) < MIN_COVERED:
        return None
    run = _run([m for m in vp if m.get("blocked_shots_for") is not None],
               lambda m: m["blocked_shots_for"] >= 5)
    if run < MIN_WINDOW:
        return None
    where = "at home" if opp_venue == "home" else "away" if opp_venue == "away" else ""
    return _claim("opp_blocks", "pressure", EVIDENCE,
                  f"{opp_name} have blocked 5+ shots in each of their last {run} games "
                  f"{where} — a side that defends its box this deep concedes "
                  f"corners.".replace("  ", " "),
                  run, _strength("pressure", EVIDENCE, _run_effect(run), run), run=run)


def b_dangerous(team, pool, name, refs=None, **_):
    got = _feature_line(pool, "dangerous_attacks_for")
    if not got:
        return None
    avg, n = got
    ref = (refs or {}).get("avg_dangerous")
    if not ref:
        # No yardstick stored for this feature, so the bare rate is all that can honestly
        # be said, and it ranks below anything that can be compared to something.
        return _claim("dangerous", "pressure", EVIDENCE,
                      f"{name} are generating {avg:.0f} dangerous attacks a game over "
                      f"{n} games.", n, _strength("pressure", EVIDENCE, 0.20, n),
                      value=round(avg, 2))
    return _claim("dangerous", "pressure", EVIDENCE,
                  f"{name} are generating {avg:.0f} dangerous attacks a game, "
                  f"{abs(avg / ref - 1) * 100:.0f}% "
                  f"{'above' if avg > ref else 'below'} the league average.",
                  n, _strength("pressure", EVIDENCE, _ratio_effect(avg, ref), n),
                  value=round(avg, 2))


def b_fouls(team, pool, name, opp_pool=None, refs=None, **_):
    got = _feature_line(pool, "fouls_for")
    if not got:
        return None
    avg, n = got
    ref = (refs or {}).get("avg_fouls")
    tail = f", against a league average of {ref:.0f}" if ref else ""
    return _claim("fouls", "pressure", COLOUR,
                  f"{name} commit {avg:.0f} fouls a game{tail} — a stop-start match.",
                  n, _strength("pressure", COLOUR,
                            _ratio_effect(avg, ref) if ref else 0.15, n),
                  value=round(avg, 2))


# =============================== C. game state ===================================
# From the half-time score, which is stored (fh_goals_for / fh_goals_against) and is the
# only game-state signal available without the goal-minute backfill.
#
# READ RULE 6 BEFORE EDITING ANYTHING HERE. These lines report how often a side has been
# in a state, and its FULL-MATCH corner average in those games. They must never be
# phrased as corners won while in that state.

def _ht(m) -> Optional[int]:
    f, a = m.get("fh_goals_for"), m.get("fh_goals_against")
    if f is None or a is None:
        return None
    return (f > a) - (f < a)


def _ft(m) -> Optional[int]:
    f, a = m.get("goals_for"), m.get("goals_against")
    if f is None or a is None:
        return None
    return (f > a) - (f < a)


def c_trailed_ht(team, pool, name, **_):
    known = [m for m in pool if _ht(m) is not None]
    if len(known) < MIN_WINDOW:
        return None
    recent = known[-RECENT:] if len(known) >= RECENT else known
    behind = [m for m in recent if _ht(m) == -1]
    if len(behind) < 2:
        return None
    allbehind = [m for m in known if _ht(m) == -1]
    text = (f"{name} have trailed at half-time in {len(behind)} of their last "
            f"{len(recent)}.")
    if len(allbehind) >= MIN_BUCKET:
        avg = _avg([m["corners_for"] for m in allbehind])
        text += (f" Across all {len(allbehind)} games they went behind, they finished "
                 f"with {avg:.1f} corners.")
    return _claim("trailed_ht", "state", EVIDENCE, text, len(recent),
                  _strength("state", EVIDENCE,
                            _rate_effect(len(behind), len(recent), 0.33), len(recent)),
                  behind=len(behind), of=len(recent))


def c_second_half_goals(team, pool, name, **_):
    known = [m for m in pool
             if m.get("goals_for") is not None and m.get("fh_goals_for") is not None]
    if len(known) < MIN_WINDOW:
        return None
    run = _run(known, lambda m: (m["goals_for"] - m["fh_goals_for"]) > 0)
    if run < MIN_WINDOW:
        return None
    return _claim("second_half_goals", "state", EVIDENCE,
                  _sentence(name, f"have scored in the second half in {run} straight games"),
                  run, _strength("state", EVIDENCE, _run_effect(run), run),
                  predicate=f"have scored in the second half in {run} straight games",
                  run=run)


def c_opp_led_ht(team, pool, name, opp_pool=None, opp_name=None, **_):
    known = [m for m in (opp_pool or []) if _ht(m) is not None]
    if len(known) < MIN_WINDOW:
        return None
    led = _hits(known, lambda m: _ht(m) == 1)
    if led / len(known) > 0.35:
        return None
    return _claim("opp_led_ht", "state", EVIDENCE,
                  f"{opp_name} have led at half-time just {led} times in {len(known)} "
                  f"games — they spend most matches level or chasing.",
                  len(known),
                  _strength("state", EVIDENCE,
                            _rate_effect(len(known) - led, len(known), 0.65), len(known)),
                  led=led, of=len(known))


def c_comeback(team, pool, name, **_):
    known = [m for m in pool if _ht(m) is not None and _ft(m) is not None]
    if len(known) < MIN_WINDOW:
        return None
    backs = _hits(known, lambda m: _ht(m) == -1 and _ft(m) >= 0)
    if backs < 2:
        return None
    return _claim("comeback", "state", COLOUR,
                  f"{name} have recovered from a half-time deficit {backs} times "
                  f"{_season_phrase(len(known))}.", len(known),
                  _strength("state", COLOUR, _rate_effect(backs, len(known), 0.1),
                            len(known)), count=backs)


def c_btts(team, pool, name, **_):
    known = [m for m in pool
             if m.get("goals_for") is not None and m.get("goals_against") is not None]
    if len(known) < MIN_WINDOW:
        return None
    recent = known[-7:] if len(known) >= 7 else known
    both = _hits(recent, lambda m: m["goals_for"] > 0 and m["goals_against"] > 0)
    if both / len(recent) < 0.7:
        return None
    return _claim("btts", "state", EVIDENCE,
                  f"Both sides have scored in {both} of {name}'s last {len(recent)} — "
                  f"open games, corners at both ends.", len(recent),
                  _strength("state", EVIDENCE, _rate_effect(both, len(recent), 0.5),
                            len(recent)), both=both, of=len(recent))


def c_opp_conceded_two(team, pool, name, opp_pool=None, opp_name=None, **_):
    known = [m for m in (opp_pool or []) if m.get("goals_against") is not None]
    if len(known) < MIN_WINDOW:
        return None
    run = _run(known, lambda m: m["goals_against"] >= 2)
    if run < MIN_WINDOW:
        return None
    return _claim("opp_conceded_two", "state", EVIDENCE,
                  f"{opp_name} have conceded 2+ goals in {run} straight — they get "
                  f"opened up.", run, _strength("state", EVIDENCE, _run_effect(run), run), run=run)


# =============================== D. opponent side ================================
# Frequently the real reason a pick exists. A side projected high because its opponent
# leaks corners is not a story about the side's form, and leading with its form would be
# asserting something the data may well contradict.

def d_opp_concedes(team, pool, name, opp_pool=None, opp_name=None, opp_venue=None,
                   league_avg=None, **_):
    vp = _venue_pool(opp_pool or [], opp_venue)
    if len(vp) < MIN_WINDOW:
        return None
    avg = _avg([m["corners_against"] for m in vp])
    where = ("per home game" if opp_venue == "home"
             else "per away game" if opp_venue == "away" else "per game")
    ref = league_avg or avg
    return _claim("opp_concedes", "opponent", EVIDENCE,
                  f"{opp_name} have conceded {avg:.1f} corners {where} "
                  f"({len(vp)} games).", len(vp),
                  _strength("opponent", EVIDENCE, _ratio_effect(avg, ref), len(vp)),
                  subject="opponent",
                  predicate=f"have conceded {avg:.1f} corners {where} over {len(vp)} games",
                  value=round(avg, 2))


def d_opp_concedes_run(team, pool, name, opp_pool=None, opp_name=None, opp_venue=None,
                       **_):
    vp = _venue_pool(opp_pool or [], opp_venue)
    if len(vp) < MIN_WINDOW:
        return None
    line = 6
    hits = _hits(vp, lambda m: m["corners_against"] >= line)
    if hits / len(vp) < 0.7:
        return None
    where = "at home" if opp_venue == "home" else "away" if opp_venue == "away" else ""
    return _claim("opp_concedes_run", "opponent", EVIDENCE,
                  f"{opp_name} have conceded {line}+ corners in {hits} of {len(vp)} "
                  f"{where}.".replace("  ", " "), len(vp),
                  _strength("opponent", EVIDENCE, _rate_effect(hits, len(vp), 0.5), len(vp)),
                  subject="opponent",
                  predicate=f"have conceded {line}+ corners in {hits} of {len(vp)} "
                            f"{where}".strip(),
                  hits=hits, of=len(vp))


def d_opp_shots_faced(team, pool, name, opp_pool=None, opp_name=None, opp_venue=None,
                      refs=None, **_):
    vp = _venue_pool(opp_pool or [], opp_venue)
    got = _feature_line(vp, "shots_against")
    if not got:
        return None
    avg, n = got
    ref = (refs or {}).get("avg_shots")
    where = "on the road" if opp_venue == "away" else "at home" if opp_venue == "home" else ""
    tail = f", against a league average of {ref:.0f}" if ref else ""
    return _claim("opp_shots_faced", "opponent", EVIDENCE,
                  f"{opp_name} face {avg:.0f} shots a game {where}{tail}.".replace("  ", " "),
                  n, _strength("opponent", EVIDENCE,
                            _ratio_effect(avg, ref) if ref else 0.20, n),
                  subject="opponent",
                  predicate=f"face {avg:.0f} shots a game {where}".strip(),
                  value=round(avg, 2))


def d_opp_quiet_attack(team, pool, name, opp_pool=None, opp_name=None, opp_venue=None,
                       league_avg=None, **_):
    vp = _venue_pool(opp_pool or [], opp_venue)
    if len(vp) < MIN_WINDOW or not league_avg:
        return None
    avg = _avg([m["corners_for"] for m in vp])
    if avg >= league_avg * 0.8:
        return None
    where = "away" if opp_venue == "away" else "at home" if opp_venue == "home" else ""
    return _claim("opp_quiet_attack", "opponent", EVIDENCE,
                  f"{opp_name} take only {avg:.1f} corners a game {where} against a "
                  f"{league_avg:.1f} league average — the corners in this one should be "
                  f"one-sided.".replace("  ", " "), len(vp),
                  _strength("opponent", EVIDENCE, _ratio_effect(league_avg, avg), len(vp)),
                  subject="opponent",
                  predicate=f"take only {avg:.1f} corners a game {where}".strip(),
                  value=round(avg, 2))


# =============================== E. colour =======================================
# Readable, and not an argument about corners. Labelled COLOUR so it can never outrank
# a line that is.

def e_unbeaten(team, pool, name, **_):
    known = [m for m in pool if _ft(m) is not None]
    run = _run(known, lambda m: _ft(m) >= 0)
    if run < MIN_WINDOW:
        return None
    return _claim("unbeaten", "colour", COLOUR,
                  _sentence(name, f"are unbeaten in {run}"), run,
                  _strength("colour", COLOUR, _run_effect(run), run),
                  predicate=f"are unbeaten in {run}", run=run)


def e_no_clean_sheet(team, pool, name, **_):
    known = [m for m in pool if m.get("goals_against") is not None]
    run = _run(known, lambda m: m["goals_against"] > 0)
    if run < MIN_WINDOW:
        return None
    c = _claim("no_clean_sheet", "colour", COLOUR,
               _sentence(name, f"have conceded in each of their last {run}"), run,
               _strength("colour", COLOUR, _run_effect(run), run),
               predicate=f"have conceded in each of their last {run}", run=run)
    # Points both ways: a side conceding every week may be getting overrun, which feeds
    # the opponent's corners, or playing stretched open games, which feeds both. The
    # direction is not recoverable from the sentence, so it is marked rather than ranked.
    c["ambiguous"] = True
    return c


def e_venue_wins(team, pool, name, venue=None, **_):
    vp = [m for m in _venue_pool(pool, venue) if _ft(m) is not None]
    recent = vp[-RECENT:]
    if len(recent) < MIN_WINDOW:
        return None
    wins = _hits(recent, lambda m: _ft(m) == 1)
    if wins < 3:
        return None
    where = "at home" if venue == "home" else "away" if venue == "away" else ""
    return _claim("venue_wins", "colour", COLOUR,
                  f"{name} have won {wins} of their last {len(recent)} "
                  f"{where}.".replace("  ", " "), len(recent),
                  _strength("colour", COLOUR, _rate_effect(wins, len(recent), 0.4), len(recent)),
                  predicate=f"have won {wins} of their last {len(recent)} {where}".strip(),
                  wins=wins, of=len(recent))


def e_scored_in(team, pool, name, **_):
    known = [m for m in pool if m.get("goals_for") is not None]
    run = _run(known, lambda m: m["goals_for"] > 0)
    if run < MIN_WINDOW:
        return None
    return _claim("scored_in", "colour", COLOUR,
                  _sentence(name, f"have scored in {run} straight"), run,
                  _strength("colour", COLOUR, _run_effect(run), run),
                  predicate=f"have scored in {run} straight", run=run)


def e_losing_run(team, pool, name, venue=None, **_):
    vp = [m for m in _venue_pool(pool, venue) if _ft(m) is not None]
    run = _run(vp, lambda m: _ft(m) == -1)
    if run < MIN_WINDOW:
        return None
    where = "at home" if venue == "home" else "away" if venue == "away" else ""
    return _claim("losing_run", "colour", COLOUR,
                  f"{name} have lost their last {run} {where}.".replace("  ", " "),
                  run, _strength("colour", COLOUR, _run_effect(run), run),
                  predicate=f"have lost their last {run} {where}".strip(), run=run)


def d_opp_clean_sheets(team, pool, name, opp_pool=None, opp_name=None, **_):
    """The opponent's clean-sheet run.

    WHY THIS IS STATED AND NOT EXPLAINED. The obvious reading is that a side which has
    not conceded in ten is about to protect a lead, the other side gets desperate, and
    the corners pile up at one end. That is a mechanism, not a measurement, and it could
    equally go the other way: a defence nobody breaks down may simply be facing nobody
    who gets near the box.

    Which it is, is answerable from the data we hold — corners conceded split by result
    is already computed by team_state_splits — and until it HAS been answered this line
    reports the run and stops. See measure_state_corners.py. The causal clause goes in
    only if the number supports it, and then it carries the number."""
    known = [m for m in (opp_pool or []) if m.get("goals_against") is not None]
    run = _run(known, lambda m: m["goals_against"] == 0)
    if run < MIN_WINDOW:
        return None
    pred = f"have not conceded a goal in {run} straight games"
    return _claim("opp_clean_sheets", "opponent", EVIDENCE,
                  _sentence(opp_name, pred), run,
                  _strength("opponent", EVIDENCE, _run_effect(run), run),
                  subject="opponent", predicate=pred, run=run)


GENERATORS = (
    a_corner_run, a_corner_run_plain, a_corner_rate, a_corner_avg, a_corner_string,
    a_out_cornered, a_double_figures,
    b_blocked, b_shots, b_opp_blocks, b_dangerous, b_fouls,
    c_trailed_ht, c_second_half_goals, c_opp_led_ht, c_comeback, c_btts,
    c_opp_conceded_two,
    d_opp_concedes, d_opp_concedes_run, d_opp_shots_faced, d_opp_quiet_attack,
    d_opp_clean_sheets,
    e_unbeaten, e_no_clean_sheet, e_venue_wins, e_scored_in, e_losing_run,
)

GROUP_ORDER = ("corners", "pressure", "state", "opponent", "colour")


def _compound(claims: List[dict], subject: str, name: str,
              limit: int = MAX_COMPOUND) -> Optional[dict]:
    """Join facts about ONE side into one line, as a person would say them.

    "Boro have won 5+ in 9 of 10 and conceded in each of their last five" reads as one
    thought. The same two facts as separate sentences, both opening with the same name,
    read as a list being padded.

    ONE FACT PER GROUP. Two corner facts joined with "and" is the same fact twice in a
    longer sentence, which is worse than printing it once — it sounds like corroboration
    and is not. The compound's tier is the WEAKEST of its parts, so a line that is half
    colour cannot be published as evidence."""
    parts, groups = [], set()
    for c in claims:
        if c["subject"] != subject or not c.get("predicate"):
            continue
        if c["group"] in groups:
            continue
        parts.append(c)
        groups.add(c["group"])
        if len(parts) >= limit:
            break
    if len(parts) < 2:
        return None
    tier = EVIDENCE if all(c["tier"] == EVIDENCE for c in parts) else COLOUR
    return {"key": "compound_" + subject,
            "group": parts[0]["group"], "tier": tier,
            "subject": subject,
            "text": name + " " + " and ".join(c["predicate"] for c in parts) + ".",
            "n": min(c["n"] for c in parts),
            "strength": max(c["strength"] for c in parts),
            "ambiguous": any(c["ambiguous"] for c in parts),
            "parts": [c["key"] for c in parts]}


def _headline(claims: List[dict], name: str, opp_name: str) -> Optional[str]:
    """The strongest fact about each side, in one two-sided line.

    This is the shape that carries a pick best, because the two halves are about
    different teams and so cannot be the same fact wearing two hats."""
    mine = next((c for c in claims if c["subject"] == "team" and c.get("predicate")), None)
    theirs = next((c for c in claims
                   if c["subject"] == "opponent" and c.get("predicate")), None)
    if not mine or not theirs:
        return None
    return (f"{name} {mine['predicate']}. {opp_name} {theirs['predicate']}.")


def pick_context(team: dict, opp: dict, venue: str, league_avg: float = 0.0,
                 refs: Optional[dict] = None, limit: int = 3) -> dict:
    """Every context line that can be verified for this pick, ranked.

    EVERY GENERATOR RUNS. The caller gets `lines` (the chosen few) and `all` (the lot),
    because the decision about how many to print is a layout decision and belongs to
    whatever is doing the printing — but a page that prints all of them buries the pick,
    so `limit` defaults low and `selected` spreads across groups rather than taking the
    top three corner lines.

    `venue` is the team's venue in the fixture being picked; the opponent's is the other
    one, which is what the opponent-side lines are measured on."""
    pool = _ordered(team)
    opp_pool = _ordered(opp)
    name = (team or {}).get("name") or "This side"
    opp_name = (opp or {}).get("name") or "Their opponent"
    opp_venue = "away" if venue == "home" else "home" if venue == "away" else None

    kw = dict(team=team, pool=pool, name=name, venue=venue, league_avg=league_avg,
              refs=refs or {}, opp=opp, opp_pool=opp_pool, opp_name=opp_name,
              opp_venue=opp_venue)

    found = []
    for gen in GENERATORS:
        try:
            c = gen(**kw)
        except Exception:
            # A single malformed match must not take the whole panel down with it. The
            # pick still renders; this line just is not there.
            c = None
        if c:
            found.append(c)

    # one of each alias set, strongest kept
    drop = set()
    for group in ALIASES:
        present = [c for c in found if c["key"] in group]
        for c in sorted(present, key=lambda x: -x["strength"])[1:]:
            drop.add(c["key"])
    found = [c for c in found if c["key"] not in drop]

    found.sort(key=lambda c: (c["tier"] != EVIDENCE, -c["strength"]))

    # Spread the chosen lines over groups: a reader wants the run, the reason and the
    # opponent, not three different ways of saying the corner count is high.
    selected, used = [], set()
    for want in GROUP_ORDER:
        if len(selected) >= limit:
            break
        best = next((c for c in found if c["group"] == want and c["tier"] == EVIDENCE), None)
        if best:
            selected.append(best)
            used.add(best["key"])
    for c in found:                      # top up from whatever is left, strongest first
        if len(selected) >= limit:
            break
        if c["key"] not in used:
            selected.append(c)
            used.add(c["key"])

    return {"team": name, "opponent": opp_name, "venue": venue,
            "games_on_file": len(pool), "thin": len(pool) < THIN_SEASON,
            "lines": selected, "all": found,
            # Two facts about one side, said as one sentence. Built from the ranked list,
            # so the compound is the strongest pair rather than the first pair found.
            "compound": [c for c in (_compound(found, "team", name),
                                     _compound(found, "opponent", opp_name)) if c],
            # One line, both sides. The two halves are about different teams, so they
            # cannot be the same fact twice.
            "headline": _headline(found, name, opp_name),
            "counts": {g: sum(1 for c in found if c["group"] == g) for g in GROUP_ORDER}}
