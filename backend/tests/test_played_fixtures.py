"""Keeping a fixture on the site after it has been played, with its result and corners.

WHY A SEPARATE STORE AT ALL. Twenty-two call sites read db.fixtures and only five test
`status`. The one that sorts ascending on date to find each team's NEXT game would have
returned a game from last week; the boards that walk every row would have handed a
finished fixture a projection. db.fixtures_played keeps results where a board asking
"what is on" cannot pick them up — the same reasoning that keeps db.odds_feed out of
db.odds.

THESE TESTS SOURCE-SLICE RATHER THAN IMPORT. sync_real reads API_FOOTBALL_KEY at module
scope and imports httpx, neither of which exists in the test container, so
test_upcoming_status's technique is the only one available: compile the pure region and
exec it with its dependencies injected. It also means the constant-drift check below
needs no import at all, which is the point — the two files cannot be imported together.
"""
import ast
import os
import re
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import cups  # noqa: E402

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _src(name):
    with open(os.path.join(HERE, name)) as fh:
        return fh.read()


def _slice(name, start, end, extra=None):
    src = _src(name)
    ns = {"datetime": datetime, "timedelta": timedelta, "timezone": timezone}
    ns.update(extra or {})
    exec(compile(src[src.index(start):src.index(end)], f"sliced:{name}", "exec"), ns)
    return ns


# fixture_dt through result_fields — the pure status-and-outcome helpers.
NS = _slice("sync_real.py", "def fixture_dt(", "# Shot-volume stats")
is_recently_played = NS["is_recently_played"]
result_fields = NS["result_fields"]
FINISHED = NS["FINISHED_STATUSES"]
KEEP_DAYS = NS["PLAYED_KEEP_DAYS"]

# cup_fixture_docs needs `cups` for the resolution rules and `_round_label` for the round
# string. The label helper is stubbed to a passthrough: these cases are about `status` and
# about which ties survive resolution, not about how a round is spelled.
CUP = _slice("sync_real.py", "def cup_fixture_docs(", "async def sync_cup(",
             {"cups": cups, "_round_label": lambda r: r})
cup_fixture_docs = CUP["cup_fixture_docs"]

NOW = datetime(2026, 11, 11, 9, 0, tzinfo=timezone.utc)


def fixture(short="FT", days_ago=1, hc=None, ac=None, goals=(1, 0), fid=900):
    dt = NOW - timedelta(days=days_ago)
    return {"fixture": {"id": fid, "date": dt.isoformat(), "status": {"short": short}},
            "goals": {"home": goals[0], "away": goals[1]},
            "league": {"round": "Group A"},
            "teams": {"home": {"id": 1, "name": "Barnet"},
                      "away": {"id": 2, "name": "Leyton Orient"}}}


def stats(hc, ac, fid=900):
    return {"_id": fid, "home_corners": hc, "away_corners": ac}


# --- the retention window --------------------------------------------------------------

def test_a_game_played_yesterday_is_kept():
    assert is_recently_played(fixture(days_ago=1), now=NOW) is True


def test_a_game_played_inside_the_window_is_kept():
    assert is_recently_played(fixture(days_ago=KEEP_DAYS - 1), now=NOW) is True


def test_a_game_older_than_the_window_is_dropped():
    assert is_recently_played(fixture(days_ago=KEEP_DAYS + 1), now=NOW) is False


def test_a_fixture_not_yet_played_is_not_a_result():
    for short in ("NS", "TBD", "PST"):
        assert is_recently_played(fixture(short=short), now=NOW) is False, short


def test_a_tie_decided_in_extra_time_or_on_penalties_is_kept():
    """THE ONE THE LEAGUE FILTER WOULD HAVE LOST. The league syncs keep `status == "FT"`,
    which is right for a league and wrong for a cup: an EFL Trophy tie level after ninety
    minutes goes to penalties and the provider marks it AET or PEN. Dropping those is a
    biased hole, not a random one — a drawn game is a different game from a decided one.
    """
    assert is_recently_played(fixture(short="AET"), now=NOW) is True
    assert is_recently_played(fixture(short="PEN"), now=NOW) is True
    assert set(FINISHED) == {"FT", "AET", "PEN"}


def test_an_abandoned_game_is_not_a_result():
    for short in ("ABD", "CANC", "SUSP", "INT", "WO"):
        assert is_recently_played(fixture(short=short), now=NOW) is False, short


def test_a_fixture_with_no_readable_date_is_dropped():
    f = fixture()
    f["fixture"]["date"] = "not a date"
    assert is_recently_played(f, now=NOW) is False


# --- the result and the corners --------------------------------------------------------

def test_the_score_and_corners_are_carried():
    r = result_fields(fixture(goals=(2, 1)), stats(7, 4))
    assert r["home_goals"] == 2 and r["away_goals"] == 1
    assert r["home_corners"] == 7 and r["away_corners"] == 4
    assert r["total_corners"] == 11
    assert r["corners_known"] is True
    assert r["status"] == "played"


def test_unfetched_corners_are_null_and_never_zero():
    """A 0-0 corner count is a real result and "nobody asked the provider" is not. A
    results page that prints 0 for the second is wrong in the most believable way
    available to it, so the distinction is carried explicitly."""
    r = result_fields(fixture(), None)
    assert r["home_corners"] is None and r["away_corners"] is None
    assert r["total_corners"] is None
    assert r["corners_known"] is False


def test_a_genuine_zero_is_kept_as_a_zero():
    r = result_fields(fixture(), stats(0, 0))
    assert r["total_corners"] == 0
    assert r["corners_known"] is True, "a real 0-0 must not read as unknown"


def test_a_half_known_corner_count_is_not_totalled():
    """One side's statistics present and the other's missing is not a total of the one
    that is there — that would under-report the game and look like a real low count."""
    r = result_fields(fixture(), stats(6, None))
    assert r["home_corners"] == 6 and r["away_corners"] is None
    assert r["total_corners"] is None and r["corners_known"] is False


def test_a_boolean_corner_count_is_refused():
    """isinstance(True, int) is True, so a bool would sail in, render as 1 corner and
    settle as a 1+ hit."""
    r = result_fields(fixture(), stats(True, False))
    assert r["home_corners"] is None and r["away_corners"] is None
    assert r["corners_known"] is False


def test_how_it_finished_is_recorded():
    assert result_fields(fixture(short="PEN"), None)["finished_as"] == "PEN"
    assert result_fields(fixture(short="FT"), None)["finished_as"] == "FT"


# --- the cup path reuses one set of resolution rules -----------------------------------

def team(tid, api, league, games=20):
    return {"team_id": tid, "api_team_id": api, "league_id": league,
            "name": tid, "real_samples": games}


BY_API = {1: team("eng-l2-barnet", 1, "eng-l2"),
          2: team("eng-l2-orient", 2, "eng-l2")}


def test_a_played_tie_is_stored_as_played():
    docs, skipped = cup_fixture_docs("eflt", [fixture()], BY_API, status="played")
    assert len(docs) == 1 and not skipped
    assert docs[0]["status"] == "played"
    assert docs[0]["fixture_id"] == "eflt-900"


def test_the_default_is_still_upcoming():
    """`status` is a parameter so that one copy of the resolution rules serves both, and
    every existing caller must keep the behaviour it had."""
    docs, _ = cup_fixture_docs("eflt", [fixture(short="NS")], BY_API)
    assert docs[0]["status"] == "upcoming"


def test_both_sides_must_still_resolve_after_the_whistle():
    """A result stored against a side the app does not know is a row no page can label
    and no claim can settle against, so both-sides-or-neither holds for played ties too —
    which is what keeps the 16 under-21 academy sides out of the results view as well."""
    docs, skipped = cup_fixture_docs("eflt", [fixture()], {1: BY_API[1]}, status="played")
    assert docs == []
    assert skipped == {"unknown_side": 1}


def test_a_played_tie_keeps_the_domestic_team_ids():
    docs, _ = cup_fixture_docs("eflt", [fixture()], BY_API, status="played")
    assert docs[0]["home_team_id"] == "eng-l2-barnet"
    assert docs[0]["away_team_id"] == "eng-l2-orient"


# --- the constant the API states and the sync enforces ---------------------------------

def _module_int(name, const):
    """The literal value of a module-level int assignment, read from SOURCE.

    Parsed rather than imported because these two files cannot be imported together:
    sync_real reads API_FOOTBALL_KEY at module scope, which is the whole reason the
    constant is duplicated instead of shared.
    """
    tree = ast.parse(_src(name))
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name) and t.id == const:
                    return ast.literal_eval(node.value)
    raise AssertionError(f"{const} not found at module level in {name}")


def test_the_api_and_the_sync_agree_on_the_window():
    """THE SYNC IS WHAT ACTUALLY ENFORCES THE WINDOW — it rebuilds the collection every
    run and does not re-insert anything older. server.py only reports the number. If the
    two drift, the endpoint states a retention period the data does not have, and nothing
    anywhere would raise."""
    assert _module_int("server.py", "PLAYED_KEEP_DAYS") == \
        _module_int("sync_real.py", "PLAYED_KEEP_DAYS")


def test_the_window_is_about_a_month():
    assert 28 <= _module_int("sync_real.py", "PLAYED_KEEP_DAYS") <= 31


def test_the_played_store_is_cleaned_up_with_its_competition():
    """A competition removed from CUP_META or LEAGUE_META loses its teams and fixtures on
    boot. Its results have to go too, or a deleted competition stays visible for up to a
    month with no teams behind it to label the rows."""
    src = _src("server.py")
    block = src[src.index('stale_ids = [l["league_id"] for l in stale]'):]
    block = block[:block.index("Removed stale leagues")]
    assert "db.fixtures_played.delete_many" in block


def test_the_results_endpoint_does_not_read_the_fixtures_board():
    """The two stores exist to stay apart. If the endpoint ever read db.fixtures it would
    be answering "what is on" with a results query."""
    src = _src("server.py")
    fn = src[src.index('@api_router.get("/fixtures/played")'):]
    fn = fn[:fn.index("NEXT_FIXTURE_SCAN = ")]
    assert "db.fixtures_played.find" in fn
    assert "db.fixtures.find" not in fn
