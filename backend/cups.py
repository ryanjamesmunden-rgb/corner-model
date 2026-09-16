"""Cup ties, where the two sides come from different leagues.

THE ONE IDEA. A cup has no teams of its own. Its fixtures point at the team documents the
domestic syncs already built, so Arsenal v Bayern reads Arsenal's Premier League form and
Bayern's Bundesliga form — twenty games each — instead of the three or four a side has
played in the competition itself. See the long note above CUP_META in leagues_meta.py for
what happens if a cup is added as a league instead.

WHAT THAT BREAKS, AND WHY THESE FUNCTIONS EXIST. Four places in the app look up a league
reference with the FIXTURE's league id and use it for both teams:

    lg  = leagues.get(fx["league_id"])            -> avg_shots / avg_blocked -> lambda
    avg = league_avg.get(fx["league_id"]) or 10.0 -> the "is this busy?" yardstick
    mismatch_angle(..., league_for_avg.get(fx["league_id"], 5.0), ...)
    lg_teams = db.teams.find({"league_id": fx["league_id"]})  -> the fixture page's traits

Every one of them is correct while both sides share a league and silently wrong the moment
they do not. For a domestic fixture the helpers here return exactly what that code returned
before, so nothing changes for the 27 leagues; for a cross-league tie they blend or split.

THREE LIMITS, STATED RATHER THAN MODELLED AWAY.

  COVERAGE. A side from a league this app does not sync has no record at all. Those ties
  are not shown — not shown with a caveat, not shown with a default, not shown. Half a
  fixture is worse than no fixture, because the half that is present looks authoritative.

  TRANSFER. Corners won against Fulham say less about a tie with Bayern than about one
  with Brentford. The number is still the best available evidence, and it is still
  measured against the wrong opposition. `cross_league` rides on the row so the page can
  say so, and `transfer_note` is the sentence.

  ROTATION. Cup weeks are when managers rest players, and nothing in a corner count sees a
  changed team sheet. There is no fix for this here. It is a caveat on every row.
"""
from leagues_meta import CUP_IDS, CUP_META, LEAGUE_META

# How much domestic history each side needs before a cup tie is stored at all.
#
# HIGHER THAN THE BOARD'S OWN BAR ON PURPOSE. BOARD_MIN_GAMES filters what gets shown; this
# filters what gets WRITTEN, and a cup fixture that no screen can honestly use is just a row
# to explain away later. Eight games is roughly the point at which a team's venue split has
# anything in it — below that `expected_lambdas` falls back to the overall average for that
# side, and a tie priced from two fallbacks is a guess wearing a projection's clothes.
CUP_MIN_GAMES = 8


def is_cup(league_id) -> bool:
    """Is this id a cup rather than one of the 27 leagues?"""
    return league_id in CUP_IDS


def competition_name(league_id) -> str:
    meta = CUP_META.get(league_id) or LEAGUE_META.get(league_id) or {}
    return meta.get("name") or str(league_id or "")


def verify_identity(entry, meta) -> str:
    """Does the provider agree this api id is the competition we think it is?

    Returns a complaint, or "" when it checks out.

    THIS IS THE nor-d2 GUARD, AUTOMATED. An id was once added to this repo from memory,
    the probe came back MISMATCH, and the entry was pulled — but the only thing that
    caught it was somebody remembering to run the probe by hand, once, before shipping.
    A cup sync calls /leagues for the season anyway, so the answer is already in the
    response: checking it costs nothing and happens on every run rather than once.

    MATCHED ON A SUBSTRING, NOT EQUALITY. Providers rename competitions for sponsors and
    reshuffle their prefixes ("UEFA Champions League", "Champions League"), and a sync
    that fails on a cosmetic rename is a sync people learn to bypass. A substring is
    still decisive against the failure that matters: a completely different tournament.
    """
    league = (entry or {}).get("league") or {}
    name = str(league.get("name") or "").strip().lower()
    kind = str(league.get("type") or "").strip().lower()
    want_name = str(meta.get("verify_name") or "").strip().lower()
    want_type = str(meta.get("verify_type") or "").strip().lower()
    if not name:
        return f"api id {meta.get('api')} returned no league — cannot confirm identity"
    if want_name and want_name not in name:
        return (f"api id {meta.get('api')} is '{league.get('name')}', which is not "
                f"'{meta.get('name')}' — refusing to sync it under that name")
    if want_type and want_type != kind:
        return (f"api id {meta.get('api')} is type '{league.get('type')}', expected "
                f"'{meta.get('verify_type')}'")
    return ""


def index_by_api_id(teams) -> dict:
    """{provider team id: team document}, for resolving a cup side to its domestic row.

    DETERMINISTIC WHEN A TEAM APPEARS TWICE. It should not — a club plays in one league
    per season and the sync rebuilds each league's teams wholesale — but a half-finished
    sync or a club that moved division can leave two rows behind, and "whichever Mongo
    returned last" is the kind of tie-break that produces a different board on every
    request. Most real games first, then the higher division, then the id, so the answer
    is the same every time and is the row with the most evidence behind it.
    """
    best = {}
    for t in teams:
        api_id = t.get("api_team_id")
        if api_id is None:
            continue
        current = best.get(api_id)
        if current is None or _team_rank(t) > _team_rank(current):
            best[api_id] = t
    return best


def _team_rank(t) -> tuple:
    tier = (LEAGUE_META.get(t.get("league_id")) or {}).get("tier") or 99
    return (t.get("real_samples") or 0, -tier, str(t.get("team_id") or ""))


def real_games(team) -> int:
    """How many REAL matches are behind this side. Synthetic filler does not count.

    `matches` is padded with generated games for sparse teams so the maths has something
    to work on; `real_samples` is what was actually observed. A bar read off `matches`
    would pass a team with three real games and five invented ones, which is the precise
    shape of "looks like evidence, is not".
    """
    if not team:
        return 0
    n = team.get("real_samples")
    if n is None:
        n = len(team.get("real_matches") or [])
    return int(n or 0)


def resolve_tie(home_api_id, away_api_id, by_api, min_games=CUP_MIN_GAMES):
    """One cup fixture -> (home doc, away doc, reason it was dropped).

    Exactly one of (a pair) and (a reason) is ever returned, so a caller cannot half-use
    the result. The reason is a short tag rather than a sentence because the sync counts
    them to report why a round came out smaller than the fixture list.

    BOTH SIDES OR NEITHER. A tie where only Arsenal is known could be shown "for the
    Arsenal angle", and that is the trap: the projection needs the opponent's conceded
    rate, so the half that is missing is not decoration, it is an input. Without it the
    model falls back to a league default and prints a number with nothing behind it.
    """
    home, away = by_api.get(home_api_id), by_api.get(away_api_id)
    if not home or not away:
        return None, None, "unknown_side"
    if home["team_id"] == away["team_id"]:
        return None, None, "same_team"
    if min(real_games(home), real_games(away)) < min_games:
        return None, None, "thin_history"
    return home, away, ""


def cross_league(home, away) -> bool:
    """Do these two sides come from different leagues?

    Not the same question as "is this a cup". Two English clubs meeting in Europe share a
    league, so their form IS directly comparable and the transfer caveat does not apply;
    an all-Spanish tie is likewise just La Liga somewhere else. The caveat belongs to the
    mismatch between the sides, not to the competition they are playing in.
    """
    if not home or not away:
        return False
    return home.get("league_id") != away.get("league_id")


def blend(a, b, fallback):
    """One yardstick for a tie whose sides are measured against two different ones.

    THE MEAN, AND DELIBERATELY NOTHING CLEVERER. A tie between a league averaging 9.6
    corners and one averaging 11.4 has no true "league average" — the match belongs to
    neither — and any weighting invents a precision the data cannot support. The mean is
    the honest midpoint, it degrades to the single value when both sides share a league
    (which is every domestic fixture, so nothing changes for them), and it is obviously
    approximate rather than convincingly wrong.

    A missing side falls back to the one that is present, and only both-missing reaches
    the caller's default — the same default those call sites already used.
    """
    vals = [v for v in (a, b) if v is not None]
    if not vals:
        return fallback
    return sum(vals) / len(vals)


def transfer_note(home, away) -> str:
    """What to say on a cross-league row, or "" when there is nothing to warn about."""
    if not cross_league(home, away):
        return ""
    hl = (LEAGUE_META.get(home.get("league_id")) or {}).get("name") or "their league"
    al = (LEAGUE_META.get(away.get("league_id")) or {}).get("name") or "their league"
    return (f"Form is from each side's own league — {hl} and {al} — so the two records "
            f"were earned against different opposition. Cup weeks also bring rotation, "
            f"which no corner count can see.")
