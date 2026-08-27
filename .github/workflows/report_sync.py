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

STILL_GOING = ("running",)
BAD = ("failed", "error")


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

    status = str(runs[0].get("status", "")).lower()
    if status in BAD:
        print(f"::error::most recent sync run reports {status}")
        return 1
    if status == "partial":
        print(f"::warning::partial sync — {runs[0].get('error_count', '?')} league(s) failed")
    elif status in STILL_GOING:
        print("::notice::sync still running (expected — it is a detached process)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
