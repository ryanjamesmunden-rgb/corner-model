"""The harness's registries have to agree — ALL of them.

FOUND LIVE, THREE TIMES, each one further down the same chain of hand-maintained lists:

    harness.yml option -> MEASURE_MODES -> TOOL_SCRIPTS -> a file
                                        -> TOOL_COOLDOWN

  - `settle_audit` in the workflow against `settlement_audit` in MEASURE_MODES gave an
    HTTP 400 naming the valid modes. Loud, at least.
  - `bet_audit` in MEASURE_MODES with no TOOL_SCRIPTS entry gave `runner error: 'audit_bets'`
    — a bare KeyError, reported as the harness having FAILED rather than as never existing.
  - and then, with THAT fixed, no TOOL_COOLDOWN entry gave a bare HTTP 500. The guard only
    reaches the cooldown lookup once a PREVIOUS run exists, so the tool worked exactly once
    and returned "Internal Server Error" every time after. Nothing in the message named the
    script, the registry, or the missing key.

THE THIRD ONE HAPPENED AFTER THIS FILE WAS WRITTEN TO PREVENT IT. The first version checked
MEASURE_MODES against TOOL_SCRIPTS and stopped there — it closed the gap that had just been
found rather than the class of gap, and the next list along failed the next day. So the rule
now is: every registry a script must appear in is checked here, and adding a registry means
adding it to this test.

WHAT IS NOT CHECKED: the workflow's dropdown. It is YAML this suite does not parse, and
PyYAML is deliberately not in requirements.txt. That gap is real and stays — but it is the
loud one.
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

    def test_every_registered_script_has_a_cooldown(self):
        # THE ONE THIS FILE MISSED. A script with no cooldown entry raised a bare KeyError
        # inside _tool_guard, served as a 500 — and only on the SECOND run, because the
        # guard skips that line when there is no previous run to compare against. So a new
        # tool worked once and was permanently broken afterwards, with an error naming
        # nothing.
        missing = sorted(set(server.TOOL_SCRIPTS) - set(server.TOOL_COOLDOWN))
        assert not missing, (
            f"registered with no cooldown: {missing}. TOOL_COOLDOWN_DEFAULT stops this "
            f"being a 500, but an explicit value is required — the default is a safety "
            f"net, not a decision about how often this tool should run.")

    def test_no_cooldown_is_set_for_a_script_that_does_not_exist(self):
        # The reverse direction. A stale entry is harmless at runtime but it is the trail
        # somebody follows when deciding whether a tool is still wired up.
        stray = sorted(set(server.TOOL_COOLDOWN) - set(server.TOOL_SCRIPTS))
        assert not stray, f"cooldowns for scripts that are not registered: {stray}"

    def test_the_guard_cannot_raise_on_a_missing_cooldown(self):
        # Belt and braces for the failure mode itself rather than for one instance of it:
        # the lookup must degrade, because the next registry gap should be a slow tool and
        # not a dead endpoint.
        import inspect
        src = inspect.getsource(server._tool_guard)
        assert "TOOL_COOLDOWN[" not in src, \
            "the cooldown is looked up by subscript again — a missing entry becomes a 500"
        assert server.TOOL_COOLDOWN_DEFAULT > 0

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
