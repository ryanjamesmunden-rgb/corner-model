"""Read /api/sync/runs from stdin and turn it into a readable Actions log line.

Kept as a file rather than inlined in the workflow YAML: the reporting needs quoting
that is painful to escape inside `python3 -c '...'` in a YAML block, and a mis-escaped
one-liner fails silently as a green tick, which is the exact failure this step exists to
prevent.

Exit codes: 0 for running / success / partial / unknown, 1 only for an outright failure.
A sync started 90 seconds ago is usually still `running` — that is normal, not a problem.
"""
import json
import os
import sys
from datetime import datetime, timezone


def _cup_ids():
    """The cup ids, from leagues_meta — the same list the sync dispatches on.

    Imported rather than typed out here for the reason the whole file exists: a
    hand-copied duplicate of that list drifts, and the way it would drift is this script
    quietly saying nothing about a competition that had just been added. The file has no
    imports and no env vars of its own, so this is safe from here.

    Returns () if it cannot be found, and the report simply omits the cup section rather
    than failing — this is a reporter, and it must not turn a working sync red.
    """
    try:
        sys.path.insert(0, os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
            "backend"))
        from leagues_meta import CUP_IDS
        return tuple(sorted(CUP_IDS))
    except Exception:                                        # noqa: BLE001
        return ()

STILL_GOING = ("running",)
BAD = ("failed", "error")
# If the newest run is older than this, the data is stale and nothing is fixing it.
# This is the check that was missing: the site sat two days behind, twice, with no
# signal anywhere. A warning in a scheduled run is that signal.
STALE_AFTER_HOURS = 26          # a little over one 12-hourly cycle, so one miss is fine


def _age_hours(iso):
    try:
        started = datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
    except Exception:
        return None
    if started.tzinfo is None:
        started = started.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - started).total_seconds() / 3600


def _failures(run):
    """{error message: [league_id, ...]} for the leagues that failed in one run.

    `leagues` is written incrementally as the sync walks the list, so this reports
    usefully on a run that is still going, not only on a finished one."""
    out = {}
    for lg in run.get("leagues") or []:
        if str(lg.get("status", "")).lower() == "error":
            out.setdefault(str(lg.get("error") or "(no message recorded)"),
                           []).append(str(lg.get("league_id", "?")))
    return out


def _report_cups(run):
    """What the cups did, called out on their own line.

    A CUP CAN SUCCEED AND STORE NOTHING, which is the state no other part of this report
    can describe. Its sides have to resolve to teams from leagues the app syncs and clear
    a games bar, so a run that answers `ok` with `fixtures: 0` is a real outcome — every
    tie in the window involved a side this app has no record of — and in every existing
    line of this report it is indistinguishable from a competition that synced fine.

    "Where are the European games" is then unanswerable from the log, which is exactly
    the position this workflow's own history says not to be in. So the count is printed
    whatever it is, and a zero says so in words.
    """
    ids = _cup_ids()
    if not ids:
        return
    rows = {str(lg.get("league_id")): lg for lg in (run.get("leagues") or [])
            if str(lg.get("league_id")) in ids}
    if not rows:
        # Not an error: a run that predates the cups, or one still working through the
        # leagues, legitimately has no cup entries yet. Cups sync LAST, on purpose.
        print(f"cups: none of {', '.join(ids)} in this run yet (they sync last)")
        return
    for cid in ids:
        lg = rows.get(cid)
        if lg is None:
            print(f"  {cid:5} not reached yet")
            continue
        if str(lg.get("status", "")).lower() == "error":
            continue                       # already printed, with its message, above
        n = lg.get("fixtures", 0)
        skipped = lg.get("skipped") or {}
        why = ("  skipped: " + ", ".join(f"{k}={v}" for k, v in sorted(skipped.items()))
               if skipped else "")
        print(f"  {cid:5} {n} fixture(s) stored{why}")
        if not n:
            print(f"::warning::{cid} stored no fixtures — every tie in the window had a "
                  f"side from a league this app does not sync, or too little history. "
                  f"That is the coverage bar working, not a failure.")


def main() -> int:
    raw = sys.stdin.read()
    try:
        payload = json.loads(raw)
    except Exception as e:
        # FAIL, do not warn. A warning here exits 0, which is a green tick over a broken
        # check — the exact silent failure this script exists to catch. It cost four days.
        print(f"::error::could not parse /api/sync/runs ({e}). First 300 chars:\n{raw[:300]}")
        return 1
    # The endpoint returns a BARE LIST. This script assumed {"runs": [...]} and swallowed
    # the AttributeError as a warning, so every run was green while nothing was checked.
    # Accept both shapes so a later change to either side cannot resurrect that.
    if isinstance(payload, list):
        runs = payload
    elif isinstance(payload, dict):
        runs = payload.get("runs", [])
    else:
        print(f"::error::unexpected /api/sync/runs shape: {type(payload).__name__}")
        return 1
    if not runs:
        print("::error::no sync runs recorded at all — the sync has never run")
        return 1

    for r in runs:
        errs = r.get("error_count")
        tail = f"  errors={errs}" if errs else ""
        print(f"{r.get('started_at', '?')}  {str(r.get('trigger', '?')):8}  "
              f"{r.get('status', '?')}{tail}")

    newest = runs[0]

    # WHY it failed, not just that it did. The per-league error strings ride along in this
    # same payload and were going unprinted, so "errors=28" looked identical whether the
    # cause was an expired provider key, a blown daily quota, or a bug in sync_real.py —
    # and the next move is completely different in each case. Grouping by message keeps
    # 28 identical lines down to one, which is itself the tell: one message across every
    # league is an account-level problem, a scatter of different ones is not.
    for msg, lids in sorted(_failures(newest).items(), key=lambda kv: -len(kv[1])):
        where = ", ".join(lids[:4]) + (f" +{len(lids) - 4} more" if len(lids) > 4 else "")
        print(f"  {len(lids):>2} league(s) [{where}]: {msg}")
    _report_cups(newest)
    status = str(newest.get("status", "")).lower()

    age = _age_hours(newest.get("started_at"))
    if age is None:
        print("::warning::could not read the newest run's timestamp")
    elif age > STALE_AFTER_HOURS:
        # The failure this whole workflow exists to prevent, now visible.
        print(f"::error::no sync has run for {age:.0f} hours — the data is stale. "
              f"Waking the backend did not start one, so check that the backend is up "
              f"and that its startup sync is firing.")
        return 1
    else:
        print(f"newest run started {age:.1f}h ago")

    if status in BAD:
        print(f"::error::most recent sync run reports {status}")
        return 1
    if status == "partial":
        print(f"::warning::partial sync — {newest.get('error_count', '?')} league(s) failed")
    elif status in STILL_GOING:
        print("::notice::sync still running (expected — it is a detached process)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
