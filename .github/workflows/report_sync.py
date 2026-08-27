"""Read /api/sync/runs from stdin and turn it into a readable Actions log line.

Kept as a file rather than inlined in the workflow YAML: the reporting needs quoting
that is painful to escape inside `python3 -c '...'` in a YAML block, and a mis-escaped
one-liner fails silently as a green tick, which is the exact failure this step exists to
prevent.

Exit codes: 0 for running / success / partial / unknown, 1 only for an outright failure.
A sync started 90 seconds ago is usually still `running` — that is normal, not a problem.
"""
import json
import sys
from datetime import datetime, timezone

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


def main() -> int:
    try:
        runs = json.load(sys.stdin).get("runs", [])
    except Exception as e:
        print(f"::warning::could not read /api/sync/runs ({e})")
        return 0
    if not runs:
        print("::warning::no sync runs recorded — the sync may not have started")
        return 0

    for r in runs:
        errs = r.get("error_count")
        tail = f"  errors={errs}" if errs else ""
        print(f"{r.get('started_at', '?')}  {str(r.get('trigger', '?')):8}  "
              f"{r.get('status', '?')}{tail}")

    newest = runs[0]
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
