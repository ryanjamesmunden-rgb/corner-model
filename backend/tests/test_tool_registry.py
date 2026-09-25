"""The harness's two registries have to agree.

FOUND LIVE, TWICE. Running a harness crosses three lists that are maintained by hand:

    harness.yml  dropdown option  ->  MEASURE_MODES key  ->  TOOL_SCRIPTS key  ->  a file

Nothing checks that a new entry was added to all of them, and each gap fails differently
and late — only when somebody runs it:

  - `settle_audit` in the workflow against `settlement_audit` in MEASURE_MODES gave an
    HTTP 400 naming the valid modes. Loud, at least.
  - `bet_audit` in MEASURE_MODES with no TOOL_SCRIPTS entry gave `runner error: 'audit_bets'`
    — a bare KeyError, reported as the harness having FAILED rather than as the harness not
    existing. The audit had never run, and the message did not say so.

The second is the one worth a test. A mode that names a script the runner has never heard
of is a broken deployment, not a failed measurement, and the distinction disappears in the
output.

WHAT IS NOT CHECKED HERE: the workflow's dropdown. It is a YAML file this suite does not
parse, and PyYAML is deliberately not in requirements.txt. That gap is real and stays — but
it is the loud one, and the quiet one is closed.
"""
import os
import sys
from pathlib import Path

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "test_corner_model")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import server  # noqa: E402

BACKEND = Path(__file__).parent.parent


class TestEveryModeCanActuallyRun:
    def test_every_measure_mode_names_a_registered_script(self):
        # THE REGRESSION GUARD. Missing here, `bet_audit` reached production and failed as
        # `runner error: 'audit_bets'` — which reads as the audit having run and gone wrong.
        missing = {mode: script for mode, (script, _, _) in server.MEASURE_MODES.items()
                   if script not in server.TOOL_SCRIPTS}
        assert not missing, (
            f"these modes name a script the runner cannot start: {missing}. "
            f"Add each to TOOL_SCRIPTS — a mode without one fails as a KeyError that "
            f"looks like the harness itself failing.")

    def test_every_registered_script_exists_on_disk(self):
        # One layer further out: a correct entry pointing at a file that was renamed or
        # never committed fails the same way, at the same moment, for a different reason.
        missing = {name: f for name, f in server.TOOL_SCRIPTS.items()
                   if not (BACKEND / f).is_file()}
        assert not missing, f"registered but not on disk: {missing}"

    def test_the_new_audits_are_reachable(self):
        # Named rather than only covered by the sweep above, so deleting one from a
        # registry fails with the name of what stopped working.
        for mode in ("calibration", "settlement_audit", "pick_line_audit", "bet_audit",
                     "watchlist"):
            assert mode in server.MEASURE_MODES, f"{mode} is not a harness mode"
            script = server.MEASURE_MODES[mode][0]
            assert script in server.TOOL_SCRIPTS, f"{mode} -> {script} is not registered"

    def test_a_mode_that_takes_no_league_says_so(self):
        # bet_audit reads db.bets, which has no league filter. Declaring it league-aware
        # would accept `--league` and pass it to a script that does not take one.
        assert server.MEASURE_MODES["bet_audit"][2] is False
