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
                     "watchlist", "h2h_coverage"):
            assert mode in server.MEASURE_MODES, f"{mode} is not a harness mode"
            script = server.MEASURE_MODES[mode][0]
            assert script in server.TOOL_SCRIPTS, f"{mode} -> {script} is not registered"

    def test_a_mode_that_takes_no_league_says_so(self):
        # bet_audit reads db.bets, which has no league filter. Declaring it league-aware
        # would accept `--league` and pass it to a script that does not take one.
        assert server.MEASURE_MODES["bet_audit"][2] is False


class TestTheWorkflowDropdownAgreesToo:
    """THE GAP THE DOCSTRING ABOVE SAYS IS REAL — closed, and without a new dependency.

    The chain is harness.yml option -> MEASURE_MODES -> TOOL_SCRIPTS -> a file, and this
    file checked every link but the first, because the first is YAML and PyYAML is
    deliberately not in requirements.txt. That objection is about parsing YAML, and
    neither of these needs to: the dropdown is a flat list of `  - name  # comment` lines
    and the dispatcher is a flat list of `name) SCRIPT="x" ;;` lines, so a regex reads
    both exactly.

    IT STAYED OPEN LONG ENOUGH TO COST SOMETHING. Registering `line_ladder` meant editing
    five places across two files, and the only way to confirm the two in harness.yml was
    to parse server.py by hand in a scratch script. That is the check this class is.

    The failure it catches is the loud one — an unknown mode is an HTTP 400 naming the
    valid modes — but loud still means a dispatched run, a cooldown burned, and a trip to
    the Actions log to find out a dropdown entry was spelled differently.
    """

    WORKFLOW = BACKEND.parent / ".github" / "workflows" / "harness.yml"

    def _dropdown(self):
        """The `harness` input's choices. Read from the options block only, so the
        `- line_ladder` style list items elsewhere in the file cannot leak in."""
        import re
        src = self.WORKFLOW.read_text(encoding="utf-8")
        start = src.index("options:")
        body = src[start:src.index("      country:", start)]
        return [m.group(1) for m in re.finditer(r"^\s+- (\w+)", body, re.M)]

    def _dispatcher(self):
        """The modes the `case` statement maps to a SCRIPT to poll for output."""
        import re
        src = self.WORKFLOW.read_text(encoding="utf-8")
        return {m.group(1): m.group(2)
                for m in re.finditer(r'^\s+(\w+)\)\s+SCRIPT="(\w+)"', src, re.M)}

    def test_the_dropdown_is_not_empty(self):
        # If the parse above ever stops finding anything, every assertion below passes
        # vacuously and this class silently stops being a test.
        assert len(self._dropdown()) > 10

    def test_every_dropdown_option_is_a_mode_or_its_own_endpoint(self):
        """Two of them are not MEASURE_MODES at all — `country_leagues` and
        `league_probe` go to /tools/probe-leagues, which is its own endpoint because
        `measure` promises no API calls. Those are named here rather than excluded by a
        pattern, so a third one cannot appear by accident."""
        OWN_ENDPOINT = {"country_leagues", "league_probe", "corner_halves", "goal_scores"}
        unknown = [o for o in self._dropdown()
                   if o not in server.MEASURE_MODES and o not in OWN_ENDPOINT]
        assert not unknown, (
            f"these dropdown options are not harness modes: {unknown}. Dispatching one "
            f"is an HTTP 400 naming the valid modes — loud, but it costs a run and a "
            f"cooldown to find out.")

    #: What the workflow's `*)` arm sets when no explicit case matched. `sweep` relies on
    #: it legitimately — sweep is a MODE OF measure_features, so the fallback is already
    #: the right script. The danger the workflow's own comment names is the opposite case:
    #: a new harness with a script of its OWN that nobody added, which then polls
    #: measure_features, finds someone else's last run and reports it as its result.
    FALLBACK_SCRIPT = "measure_features"

    def test_every_dropdown_mode_resolves_to_the_script_it_runs(self):
        """Either an explicit case arm, or a script the fallback already happens to be.

        NOT "every mode needs an arm" — that was this test's first draft and it failed on
        `sweep`, which is correct as it stands. The invariant is that the SCRIPT polled
        must be the one the mode actually runs, however it got there, because polling the
        wrong one reports another tool's last output under this mode's heading.
        """
        cases = self._dispatcher()
        wrong = {}
        for mode in self._dropdown():
            spec = server.MEASURE_MODES.get(mode)
            if not spec:
                continue
            polled = cases.get(mode, self.FALLBACK_SCRIPT)
            if polled != spec[0]:
                wrong[mode] = (polled, spec[0])
        assert not wrong, (
            f"the workflow polls the wrong script for these modes (polled, should be): "
            f"{wrong}. Each needs a SCRIPT= case arm, or the run reports another tool's "
            f"output as its own.")

    def test_the_fallback_is_still_the_script_this_test_assumes(self):
        """FALLBACK_SCRIPT above is a copy of a value in the YAML. If the workflow's `*)`
        arm changes and this does not, the check above starts passing modes it should
        fail."""
        import re
        src = self.WORKFLOW.read_text(encoding="utf-8")
        found = re.search(r'^\s+\*\)\s+SCRIPT="(\w+)"', src, re.M)
        assert found, "the workflow has no `*)` fallback arm any more"
        assert found.group(1) == self.FALLBACK_SCRIPT

    def test_each_case_names_the_script_its_mode_actually_runs(self):
        """A case arm pointing at the wrong script polls another tool's last run and
        reports ITS output under this mode's heading — which is worse than silence,
        because it looks like an answer."""
        wrong = {}
        for mode, script in self._dispatcher().items():
            expected = server.MEASURE_MODES.get(mode)
            if expected and expected[0] != script:
                wrong[mode] = (script, expected[0])
        assert not wrong, f"case arm names the wrong script (got, want): {wrong}"

    def test_line_ladder_is_wired_end_to_end(self):
        # Named because it is the registration that exposed the gap this class closes.
        assert "line_ladder" in self._dropdown()
        assert self._dispatcher().get("line_ladder") == "line_ladder"
        assert server.MEASURE_MODES["line_ladder"][0] == "line_ladder"
        assert "line_ladder" in server.TOOL_SCRIPTS
        assert "line_ladder" in server.TOOL_COOLDOWN
