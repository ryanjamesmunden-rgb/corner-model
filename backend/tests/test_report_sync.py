"""The scheduled sync's alarm has to say WHY, not just that something is wrong.

The site sat five days behind while every run reported `failed errors=28`. That line was
true and useless: 28-of-28 is an account-level problem (key, plan, daily quota) and needs
the provider dashboard, whereas a scatter of different messages is a bug in the sync and
needs a commit. The payload already carried the per-league error strings — it just never
printed them, so the two cases looked identical from the Actions log.

These pin the reporting, and the exit codes, since a warning here exits 0 and a green
tick over a broken check is the original failure this script exists to prevent."""
import importlib.util
import io
import json
import os
import sys
from contextlib import redirect_stdout
from datetime import datetime, timedelta, timezone

_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))), ".github", "workflows", "report_sync.py")
_spec = importlib.util.spec_from_file_location("report_sync", _PATH)
report_sync = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(report_sync)


def _run(payload):
    """Drive the script exactly as the workflow does — JSON on stdin — and capture both."""
    buf = io.StringIO()
    stdin, sys.stdin = sys.stdin, io.StringIO(json.dumps(payload))
    try:
        with redirect_stdout(buf):
            code = report_sync.main()
    finally:
        sys.stdin = stdin
    return code, buf.getvalue()


def _now(hours_ago=0.0):
    return (datetime.now(timezone.utc) - timedelta(hours=hours_ago)).isoformat()


def _run_doc(status="failed", started=None, leagues=None, **extra):
    return {"started_at": started or _now(), "trigger": "scheduled", "status": status,
            "leagues": leagues or [], **extra}


QUOTA = "/leagues -> {'requests': 'You have reached the request limit for the day'}"


def _all_failed(msg=QUOTA, n=28):
    return [{"league_id": f"lg-{i}", "status": "error", "error": msg} for i in range(n)]


def test_the_provider_message_reaches_the_log():
    """The whole point: the reason is in the payload, so it must be in the output."""
    code, out = _run([_run_doc(leagues=_all_failed(), error_count=28)])
    assert code == 1
    assert "request limit for the day" in out


def test_identical_failures_collapse_to_one_line_with_the_count():
    code, out = _run([_run_doc(leagues=_all_failed(), error_count=28)])
    assert out.count("request limit for the day") == 1
    assert "28 league(s)" in out


def test_distinct_failures_stay_distinct():
    """A scatter of messages is the signal that this is a code bug, not the account."""
    leagues = _all_failed(n=3) + [
        {"league_id": "nor-d1", "status": "error", "error": "name 'odds_docs' is not defined"}]
    _, out = _run([_run_doc(leagues=leagues, error_count=4)])
    assert "odds_docs" in out and "request limit" in out


def test_a_league_that_failed_without_a_message_still_gets_a_line():
    _, out = _run([_run_doc(leagues=[{"league_id": "eng-pl", "status": "error"}])])
    assert "eng-pl" in out and "no message recorded" in out


def test_successful_leagues_are_not_reported_as_failures():
    ok = [{"league_id": "eng-pl", "status": "ok", "teams": 20}]
    _, out = _run([_run_doc(status="partial", leagues=ok + _all_failed(n=1), error_count=1)])
    assert "eng-pl" not in out


def test_a_run_still_going_reports_the_failures_it_has_already_hit():
    """`leagues` is written as the sync walks the list, so a running job is diagnosable
    90 seconds in — which is when the workflow actually looks."""
    code, out = _run([_run_doc(status="running", leagues=_all_failed(n=5))])
    assert code == 0
    assert "5 league(s)" in out


def test_a_clean_success_says_nothing_extra_and_passes():
    code, out = _run([_run_doc(status="success", leagues=[
        {"league_id": "eng-pl", "status": "ok"}])])
    assert code == 0
    assert "league(s)" not in out


def test_stale_data_fails_even_when_the_last_run_succeeded():
    code, out = _run([_run_doc(status="success", started=_now(hours_ago=40))])
    assert code == 1
    assert "stale" in out


def test_a_non_json_body_fails_rather_than_warning():
    buf = io.StringIO()
    stdin, sys.stdin = sys.stdin, io.StringIO("<html>502 Bad Gateway</html>")
    try:
        with redirect_stdout(buf):
            code = report_sync.main()
    finally:
        sys.stdin = stdin
    assert code == 1
    assert "502" in buf.getvalue()


def test_the_bare_list_shape_the_endpoint_actually_returns_is_understood():
    """/api/sync/runs returns a list; assuming {"runs": [...]} is what made this script
    swallow everything as a warning for four days. Both shapes must work."""
    doc = _run_doc(status="success")
    assert _run([doc])[0] == 0
    assert _run({"runs": [doc]})[0] == 0


def test_no_runs_at_all_is_a_failure():
    assert _run([])[0] == 1


# --- the cups, which can succeed and store nothing ---------------------------------
#
# A cup's sides have to resolve to teams from leagues the app syncs and clear a games
# bar, so `status: ok` with `fixtures: 0` is a real outcome — every tie in the window
# involved a side this app has no record of. In every other line of this report that is
# indistinguishable from a competition that synced perfectly, which leaves "where are the
# European games" unanswerable from the log. These pin that it is answerable.

def _cup(cid, fixtures=6, skipped=None, status="ok"):
    row = {"league_id": cid, "status": status, "teams": 0, "fixtures": fixtures}
    if skipped is not None:
        row["skipped"] = skipped
    return row


def test_a_cup_reports_how_many_fixtures_it_stored():
    _, out = _run([_run_doc(status="success", leagues=[_cup("ucl", 8)])])
    assert "ucl" in out and "8 fixture(s) stored" in out


def test_a_cup_that_stored_nothing_says_so_loudly():
    """The state no other line in this report can describe."""
    _, out = _run([_run_doc(status="success", leagues=[_cup("uecl", 0)])])
    assert "::warning::" in out
    assert "uecl" in out
    # And it says the bar worked rather than implying a fault, because it is not one.
    assert "not a failure" in out


def test_the_skip_reasons_are_printed():
    """"thirty-two ties, eleven stored" is a sentence somebody will need explained."""
    _, out = _run([_run_doc(status="success",
                            leagues=[_cup("uel", 11, {"unknown_side": 18, "thin_history": 3})])])
    assert "unknown_side=18" in out and "thin_history=3" in out


def test_a_cup_still_working_through_the_list_is_not_reported_as_empty():
    """Cups sync LAST, so a run caught mid-flight legitimately has no cup entry yet —
    and calling that zero fixtures would be an alarm about a sync that is going fine."""
    _, out = _run([_run_doc(status="running",
                            leagues=[{"league_id": "eng-pl", "status": "ok", "teams": 20}])])
    assert "they sync last" in out
    assert "::warning::" not in out


def test_a_cup_that_errored_is_not_also_reported_as_empty():
    """It already has a line, with the provider's reason on it. A second one saying
    "0 fixtures" would read as a different problem."""
    leagues = [{"league_id": "ucl", "status": "error",
                "error": "api id 2 is 'CONMEBOL Libertadores', which is not 'Champions League'"}]
    code, out = _run([_run_doc(status="failed", leagues=leagues, error_count=1)])
    assert "Libertadores" in out
    assert "0 fixture(s) stored" not in out


def test_the_cup_list_comes_from_leagues_meta_not_a_copy():
    """A hand-copied list would drift, and the way it would drift is this script saying
    nothing about a competition that had just been added."""
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from leagues_meta import CUP_IDS
    assert set(report_sync._cup_ids()) == set(CUP_IDS)


def test_the_report_survives_not_finding_leagues_meta(monkeypatch):
    """It is a reporter. A missing import must drop the cup section, never turn a
    working sync red."""
    monkeypatch.setattr(report_sync, "_cup_ids", lambda: ())
    code, out = _run([_run_doc(status="success", leagues=[_cup("ucl", 8)])])
    assert code == 0
    assert "fixture(s) stored" not in out
