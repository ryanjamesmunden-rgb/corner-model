"""Settlement engine — grades pending picks against final match statistics.

Two deliberate design choices:

* Grading is pure and free of I/O so it can be tested exhaustively. Asian
  quarter-lines (half-win / half-loss) and whole-line pushes are the parts that
  are easy to get subtly wrong, so they are isolated here and unit-tested.
* Nothing is ever guessed. A pick that cannot be graded is reported with a
  reason and left pending; only an abandoned fixture, or one whose corner data
  is still missing well after kick-off, is voided.

Re-running is safe: only picks still 'pending' are considered, and each pick is
written exactly once to a terminal status.

Top-level imports are stdlib only — the grading half of this module must import
without motor/httpx so it can be tested standalone.
"""
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict, Any, Tuple

logger = logging.getLogger(__name__)

WON, LOST, VOID = "won", "lost", "void"
HALF_WON, HALF_LOST = "half_won", "half_lost"
PENDING = "pending"

TERMINAL = (WON, LOST, VOID, HALF_WON, HALF_LOST)

# Fraction of stake returned as profit/loss, before applying odds to the winning part.
PROFIT_FACTOR = {WON: 1.0, HALF_WON: 0.5, VOID: 0.0, HALF_LOST: -0.5, LOST: -1.0}

_OUTCOME_BY_SCORE = {1.0: WON, 0.5: HALF_WON, 0.0: VOID, -0.5: HALF_LOST, -1.0: LOST}

# API-Football fixture status codes.
FINISHED = {"FT", "AET", "PEN"}
ABANDONED = {"ABD", "CANC", "PST", "SUSP", "AWD", "WO", "INT"}

# How long after kick-off we wait for corner data before calling a fixture unsettleable.
MISSING_DATA_VOID_HOURS = 48


# --------------------------------------------------------------------------
# Pure grading
# --------------------------------------------------------------------------

def _grade_simple(value: float, line: float, direction: str) -> float:
    """+1 win / 0 push / -1 loss for a single whole-or-half line."""
    diff = (value - line) if direction == "over" else (line - value)
    if diff > 0:
        return 1.0
    if diff < 0:
        return -1.0
    return 0.0


def is_quarter_line(line: float) -> bool:
    """True for x.25 / x.75 lines, which split the stake over two half-lines."""
    return round(line * 4) % 2 == 1


def grade_line(value: float, line: float, direction: str = "over") -> str:
    """Grade `value` against `line`.

    Whole lines can push (exact hit → void). Half lines cannot. Quarter lines
    split the stake across the two adjacent half-lines, which is what produces
    half-wins and half-losses.
    """
    if direction not in ("over", "under"):
        raise ValueError(f"direction must be 'over' or 'under', got {direction!r}")
    if is_quarter_line(line):
        score = (_grade_simple(value, line - 0.25, direction)
                 + _grade_simple(value, line + 0.25, direction)) / 2
    else:
        score = _grade_simple(value, line, direction)
    return _OUTCOME_BY_SCORE[score]


def pick_profit(status: str, odds: Optional[float]) -> Optional[float]:
    """Profit in units at a flat 1u stake.

    Losses and pushes are price-independent. A win at an unknown price has no
    computable return, so it is None rather than 0 — counting it as 0 would
    quietly understate a winning record.
    """
    factor = PROFIT_FACTOR.get(status)
    if factor is None:
        return None
    if factor > 0:
        if not odds:
            return None
        return round(factor * (odds - 1.0), 4)
    return factor


def resolve_market(pick: Dict[str, Any], team_corners: int, opp_corners: int
                   ) -> Optional[Tuple[float, float, str]]:
    """Map a pick onto (value, line, direction) for grading.

    Returns None when the market isn't one we can grade from full-match corner
    counts, so the caller can report it rather than guess.
    """
    market = (pick.get("market") or "team_corners").lower()
    line = pick.get("line")
    if line is None:
        return None
    line = float(line)
    direction = (pick.get("direction") or "over").lower()
    total = team_corners + opp_corners

    if market == "team_corners":
        # Stored as "X+" (e.g. 6 means 6 or more), which is Over (X - 0.5).
        return float(team_corners), line - 0.5, "over"
    if market in ("match_total", "asian_total", "total_corners"):
        return float(total), line, direction
    if market in ("asian_handicap", "corner_handicap"):
        # Pick wins if (team - opp) + handicap > 0, i.e. margin over -handicap.
        return float(team_corners - opp_corners), -line, "over"
    return None


def grade_pick(pick: Dict[str, Any], team_corners: int, opp_corners: int
               ) -> Tuple[Optional[str], Optional[str]]:
    """(status, error). Exactly one is non-None."""
    resolved = resolve_market(pick, team_corners, opp_corners)
    if resolved is None:
        return None, f"unsupported market {pick.get('market') or 'team_corners'!r}"
    value, line, direction = resolved
    return grade_line(value, line, direction), None


# --------------------------------------------------------------------------
# I/O — resolving fixtures and applying results
# --------------------------------------------------------------------------

def _api_team_id(internal_team_id: Optional[str]) -> Optional[int]:
    """Internal team ids are '<league>-<apiTeamId>' (e.g. 'eng-pl-42')."""
    if not internal_team_id:
        return None
    tail = str(internal_team_id).rsplit("-", 1)[-1]
    try:
        return int(tail)
    except (TypeError, ValueError):
        return None


def _parse_dt(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt


def _tokens(s: Optional[str]) -> set:
    import re
    s = re.sub(r"[^a-z0-9 ]", " ", (s or "").lower())
    return {t for t in s.split() if len(t) >= 3}


def _overlap(a: Optional[str], b: Optional[str]) -> int:
    return len(_tokens(a) & _tokens(b))


async def _resolve_api_fixture(db, hc, pick: Dict[str, Any]) -> Tuple[Optional[dict], Optional[str]]:
    """Find the API-Football fixture for a pick.

    Prefers ids already stored on the pick or its fixture doc; falls back to a
    league+date lookup matched on API team ids, and only then on team names.
    """
    from sync_real import af_get, current_season, LEAGUE_META

    api_fid = pick.get("api_fixture_id")
    if api_fid and not isinstance(api_fid, str):
        resp = await af_get(hc, "/fixtures", {"id": api_fid})
        return (resp[0] if resp else None), (None if resp else f"api fixture {api_fid} not found")

    fixture_doc = None
    if pick.get("fixture_id"):
        fixture_doc = await db.fixtures.find_one({"fixture_id": pick["fixture_id"]}, {"_id": 0})
    if fixture_doc and fixture_doc.get("api_fixture_id"):
        stored = fixture_doc["api_fixture_id"]
        if isinstance(stored, str):
            return None, "fixture is synthetic (no API-Football id) and cannot be settled"
        resp = await af_get(hc, "/fixtures", {"id": stored})
        return (resp[0] if resp else None), (None if resp else f"api fixture {stored} not found")

    league_id = pick.get("league_id") or (fixture_doc or {}).get("league_id")
    meta = LEAGUE_META.get(league_id or "")
    if not meta:
        return None, f"no league meta for {league_id!r}"

    day = _parse_dt(pick.get("kickoff")) or _parse_dt(pick.get("date") and f"{pick['date']}T00:00:00+00:00")
    if not day:
        return None, "pick has no usable date"
    season = await current_season(hc, meta["api"])
    frm = (day - timedelta(days=1)).strftime("%Y-%m-%d")
    to = (day + timedelta(days=1)).strftime("%Y-%m-%d")
    candidates = await af_get(hc, "/fixtures", {"league": meta["api"], "season": season, "from": frm, "to": to})
    if not candidates:
        return None, "no API fixtures in date window"

    want_home = _api_team_id((fixture_doc or {}).get("home_team_id"))
    want_away = _api_team_id((fixture_doc or {}).get("away_team_id"))
    if want_home and want_away:
        for f in candidates:
            if f["teams"]["home"]["id"] == want_home and f["teams"]["away"]["id"] == want_away:
                return f, None

    best, best_score = None, 0
    for f in candidates:
        score = (_overlap(pick.get("home"), f["teams"]["home"]["name"])
                 + _overlap(pick.get("away"), f["teams"]["away"]["name"]))
        if score > best_score:
            best, best_score = f, score
    if best and best_score >= 2:
        return best, None
    return None, "could not match pick to an API fixture"


async def _corners_for_fixture(db, hc, api_fid: int) -> Optional[dict]:
    """{'home_id','away_id','home_corners','away_corners'} from cache or one API call."""
    cached = await db.fixture_stats.find_one({"_id": api_fid})
    if cached and cached.get("home_corners") is not None:
        return {"home_id": cached.get("home_id"), "away_id": cached.get("away_id"),
                "home_corners": cached["home_corners"], "away_corners": cached["away_corners"]}
    try:
        stats = await af_get_statistics(hc, api_fid)
    except Exception as exc:                                  # noqa: BLE001 - reported, not raised
        logger.warning("settlement: stats fetch failed for %s: %s", api_fid, exc)
        return None
    if not stats:
        return None
    corners, ids = {}, []
    for team_block in stats:
        tid = team_block["team"]["id"]
        ids.append(tid)
        value = next((s["value"] for s in team_block["statistics"] if s["type"] == "Corner Kicks"), None)
        corners[tid] = value if isinstance(value, int) else None
    if len(ids) != 2 or any(corners.get(t) is None for t in ids):
        return None
    return {"home_id": ids[0], "away_id": ids[1],
            "home_corners": corners[ids[0]], "away_corners": corners[ids[1]]}


async def af_get_statistics(hc, api_fid: int):
    from sync_real import af_get
    return await af_get(hc, "/fixtures/statistics", {"fixture": api_fid})


def _pick_side(pick: Dict[str, Any], fixture: dict, stats: dict) -> Optional[str]:
    """'home' or 'away' — which side of the fixture the pick's team is on."""
    home_name = fixture["teams"]["home"]["name"]
    away_name = fixture["teams"]["away"]["name"]
    team = pick.get("team") or pick.get("selection")
    if pick.get("venue") in ("home", "away") and not team:
        return pick["venue"]
    h, a = _overlap(team, home_name), _overlap(team, away_name)
    if h > a:
        return "home"
    if a > h:
        return "away"
    if pick.get("venue") in ("home", "away"):
        return pick["venue"]
    return None


async def settle_pending(db, hc, limit: int = 1000) -> dict:
    """Grade every pending pick whose fixture has finished. Idempotent."""
    picks = await db.picks.find({"status": PENDING}).to_list(limit)
    now = datetime.now(timezone.utc)
    settled, voided, skipped = 0, 0, []

    for pick in picks:
        label = f"{pick.get('team')} {pick.get('line')} ({pick.get('home')} v {pick.get('away')})"
        try:
            fixture, err = await _resolve_api_fixture(db, hc, pick)
        except Exception as exc:                              # noqa: BLE001
            skipped.append({"pick": label, "reason": f"fixture lookup error: {exc}"})
            continue
        if err or not fixture:
            skipped.append({"pick": label, "reason": err or "fixture not found"})
            continue

        api_fid = fixture["fixture"]["id"]
        status_short = fixture["fixture"]["status"]["short"]
        update: Dict[str, Any] = {"api_fixture_id": api_fid, "kickoff": fixture["fixture"]["date"]}

        if status_short in ABANDONED:
            update.update({"status": VOID, "settle_reason": f"fixture {status_short}",
                           "settled_at": now.isoformat()})
            await db.picks.update_one({"_id": pick["_id"]}, {"$set": update})
            voided += 1
            logger.info("settlement: VOID %s — fixture %s", label, status_short)
            continue

        if status_short not in FINISHED:
            await db.picks.update_one({"_id": pick["_id"]}, {"$set": update})
            skipped.append({"pick": label, "reason": f"not finished ({status_short})"})
            continue

        corners = await _corners_for_fixture(db, hc, api_fid)
        if not corners:
            kickoff = _parse_dt(fixture["fixture"]["date"])
            stale = kickoff and (now - kickoff) > timedelta(hours=MISSING_DATA_VOID_HOURS)
            if stale:
                update.update({"status": VOID, "settle_reason": "no corner data",
                               "settled_at": now.isoformat()})
                await db.picks.update_one({"_id": pick["_id"]}, {"$set": update})
                voided += 1
                logger.warning("settlement: VOID %s — no corner data %sh after kick-off",
                               label, MISSING_DATA_VOID_HOURS)
            else:
                await db.picks.update_one({"_id": pick["_id"]}, {"$set": update})
                skipped.append({"pick": label, "reason": "corner data not available yet"})
            continue

        side = _pick_side(pick, fixture, corners)
        if side is None:
            skipped.append({"pick": label, "reason": "could not tell which team the pick is on"})
            continue
        team_c = corners["home_corners"] if side == "home" else corners["away_corners"]
        opp_c = corners["away_corners"] if side == "home" else corners["home_corners"]

        status, grade_err = grade_pick(pick, team_c, opp_c)
        if grade_err:
            skipped.append({"pick": label, "reason": grade_err})
            continue

        update.update({"status": status, "settled_at": now.isoformat(),
                       "result_corners": team_c, "result_opp_corners": opp_c,
                       "result_total_corners": team_c + opp_c, "settled_side": side})
        await db.picks.update_one({"_id": pick["_id"]}, {"$set": update})
        settled += 1
        logger.info("settlement: %s %s -> %s (%s-%s)", status.upper(), label, status, team_c, opp_c)

    for s in skipped:
        logger.info("settlement: unsettled — %s (%s)", s["pick"], s["reason"])
    return {"considered": len(picks), "settled": settled, "voided": voided,
            "unsettled": len(skipped), "details": skipped[:50],
            "ran_at": now.isoformat()}
