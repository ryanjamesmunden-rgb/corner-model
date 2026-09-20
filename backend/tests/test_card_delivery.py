"""The card that gets SENT has to be the card that gets frozen and graded.

TWO THINGS DRIFTED APART AND NEITHER FAILED.

The card system publishes twice a week — midweek on Monday, weekend on Wednesday. The
freeze step ran on both, so both cards were snapshotted and both were graded into the
published record. The SEND step was gated on Wednesday alone, so the midweek card was
computed, frozen, scored, shown on the site, and posted to nobody. There was no error
anywhere: there was simply no step for it, and a missing step raises nothing.

The second drift was the window. The channel card was built from a `--days` scan passed in
from the workflow, while the site asked angle_of_day which card was live and what dates it
covered. On a Wednesday those disagree: the weekend card covers Friday to Monday, and a
three-day scan cannot reach Sunday or Monday at all — while Thursday's games, which belong
to the MIDWEEK card, were eligible for it. Two definitions of one window, kept in step by
hand, in two languages.

These are source-level assertions because the failure is structural: the code was correct,
ran green, and did the wrong thing. There is nothing to catch at runtime — the only
evidence was a card that never arrived.
"""
import os
import re
import sys

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "test_corner_model")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import angle_of_day  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
WORKFLOW = os.path.join(ROOT, ".github", "workflows", "social_draft.yml")
TOOL = os.path.join(ROOT, "tools", "social_draft.mjs")


def workflow():
    return open(WORKFLOW, encoding="utf-8").read()


def step(name):
    """One step's YAML block, from its `- name:` to the next one."""
    src = workflow()
    start = src.index(f"- name: {name}")
    rest = src[start + 1:]
    nxt = rest.find("\n      - name:")
    return rest[:nxt] if nxt != -1 else rest


class TestBothCardsAreSent:
    def test_the_send_is_gated_on_a_card_existing_not_on_a_weekday(self):
        """`weekday == '3'` sent the weekend card and silently never sent the midweek one.
        `card != ''` is true on exactly the days a card is published."""
        block = step("Send the card to the channel")
        assert "steps.when.outputs.card != ''" in block
        assert "weekday == '3'" not in block

    def test_the_send_and_the_freeze_agree_on_when_a_card_exists(self):
        """THE ACTUAL INVARIANT. A card that is frozen is graded in the published record,
        so a card frozen but not sent means the record contains claims no member was ever
        shown. The two steps must fire together or the record describes a different
        product from the one being delivered."""
        send = step("Send the card to the channel")
        freeze = step("Freeze the card")

        def gate(block):
            """The step's `if:`, including the folded form.

            Parsed rather than pulled out with one regex because `if: >-` puts the
            condition on the NEXT line, and a regex that stops at the end of the `if:`
            line returns ">-" — which contains none of the strings this asserts on, so
            the test fails while the workflow is correct.

            Deliberately NOT done with PyYAML: it is not in requirements.txt, so a test
            importing it passes here and does something else entirely in CI. This repo
            has already lost 27 tests to exactly that.
            """
            m = re.search(r"^(\s*)if:[ \t]*(.*)$", block, re.M)
            if not m:
                return ""
            indent, val = len(m.group(1)), m.group(2).strip()
            if val not in (">", ">-", "|", "|-"):
                return val
            out = []
            for line in block[m.end():].splitlines():
                if not line.strip():
                    continue
                if len(line) - len(line.lstrip()) <= indent:
                    break                      # dedented: this is the next key
                out.append(line.strip())
            return " ".join(out)

        assert "steps.when.outputs.card != ''" in gate(send)
        assert "steps.when.outputs.card != ''" in gate(freeze)

    def test_the_weekday_map_publishes_on_exactly_the_cards_days(self):
        """The workflow's own case statement against angle_of_day, which is the only
        place the schedule is really defined. Cron weekdays are 1=Mon; CARDS uses
        0=Mon."""
        src = workflow()
        for card, spec in angle_of_day.CARDS.items():
            cron_day = spec["publish_weekday"] + 1
            assert re.search(rf"^\s*{cron_day}\)\s*echo \"card={card}\"", src, re.M), \
                f"{card} is published on weekday {cron_day} and the workflow does not say so"


class TestTheWindowHasOneDefinition:
    def test_the_card_post_does_not_take_a_day_window_from_the_workflow(self):
        """Passing --days here is what let the channel and the site cover different days.
        The tool asks the backend instead."""
        # COMMENT LINES STRIPPED FIRST. The step explains at length why it passes no
        # window, so a plain substring search finds `--days` in the prose that exists
        # because it is not in the command — a test that fails on its own explanation.
        block = step("Send the card to the channel")
        code = "\n".join(l for l in block.splitlines() if not l.strip().startswith("#"))
        assert "--board card" in code
        assert "--days" not in code

    def test_the_tool_reads_the_card_from_the_endpoint_the_site_renders(self):
        src = open(TOOL, encoding="utf-8").read()
        assert "/api/angles/card" in src
        # And NOT from the scan the old path used, which had no idea which card was live.
        card_block = src[src.index('if (BOARD === "card")'):]
        card_block = card_block[:card_block.index("process.exit(0)")]
        assert "share/rows" not in card_block

    def test_the_label_comes_from_the_backend(self):
        """A card headed "Weekend" on a Monday tells a paying member the wrong three days
        are covered. The heading is one renderer serving two cards, so it cannot be a
        constant."""
        src = open(TOOL, encoding="utf-8").read()
        assert "label: a.label" in src

    def test_every_card_has_a_label_to_send(self):
        for card, spec in angle_of_day.CARDS.items():
            assert spec.get("label"), card


class TestTheEndpointSaysWhereItsTimeWent:
    """It stopped answering inside the caller's timeout and nothing could say which board
    was slow — the two candidates do very different amounts of work, so guessing means
    optimising the wrong one and finding out from a post that did not go."""

    def test_share_rows_reports_a_timing_per_board(self):
        import inspect
        import server
        src = inspect.getsource(server.share_rows)
        assert "timings_ms" in src
        # Every board, not just the one that happened to be suspected.
        for board in server.SHARE_BOARDS:
            assert f'timed("{board}"' in src, board

    def test_the_timings_ride_on_the_response_rather_than_only_the_log(self):
        """A server-side log line is not reachable from the Actions run that failed —
        which is the only place anyone is looking when a post does not arrive."""
        import inspect
        import server
        assert 'out["timings_ms"] = timings' in inspect.getsource(server.share_rows)

    def test_the_caller_prints_them(self):
        src = open(TOOL, encoding="utf-8").read()
        assert "timings_ms" in src


class TestTheCallerSurvivesOneSlowAnswer:
    def test_there_is_more_than_one_attempt(self):
        """A single 60s try meant one slow answer lost the day's post entirely, twice
        running."""
        src = open(TOOL, encoding="utf-8").read()
        m = re.search(r"const FETCH_MS = \[([^\]]+)\]", src)
        assert m, "no retry schedule"
        waits = [int(x.strip()) for x in m.group(1).split(",")]
        assert len(waits) >= 2
        assert waits[-1] > waits[0], "the retry must give it longer, not the same again"

    def test_a_config_error_is_not_retried(self):
        """A bad token answers identically however many times it is asked, so retrying
        only doubles the wait before the same message — under a "retrying" line implying
        it might be transient."""
        src = open(TOOL, encoding="utf-8").read()
        block = src[src.index("const getOnce"):src.index("/** Like get")]
        for code in ("503", "403"):
            i = block.index(f"res.status === {code}")
            assert "fail(" in block[i:i + 400], f"{code} must be fatal immediately"


class TestACardCanBeBuiltOffSchedule:
    """The schedule publishes on two days. Wanting the card on a third — because the games
    are tonight and Monday's drop is no use — had no route at all, and a card is exactly
    the thing somebody asks for at short notice."""

    def test_a_manual_card_run_reaches_the_step(self):
        block = step("Send the card to the channel")
        assert "inputs.board == 'card'" in block

    def test_the_scheduled_gate_still_stands_on_its_own(self):
        """Adding the manual route must not have replaced the schedule with it."""
        block = step("Send the card to the channel")
        assert "steps.when.outputs.card != ''" in block

    def test_a_manual_run_does_not_publish_unless_asked(self):
        """A card posted to the paid channel cannot be unposted, and 'I want to see it' and
        'send it to everyone who pays' are different requests. The scheduled run is
        untouched — this only governs one somebody started by hand."""
        code = "\n".join(l for l in step("Send the card to the channel").splitlines()
                         if not l.strip().startswith("#"))
        assert 'inputs.send' in code
        assert "exit 0" in code

    def test_the_card_is_readable_without_being_sent(self):
        """Otherwise 'build but do not publish' produces nothing anyone can read, which is
        the same as not running it."""
        assert "GITHUB_STEP_SUMMARY" in step("Send the card to the channel")

    def test_the_size_is_not_redefined_in_the_tool(self):
        """Blank means the backend's COUNT — the number the schedule publishes and the site
        shows. A default here would be a second opinion about how big a card is."""
        src = open(TOOL, encoding="utf-8").read()
        block = src[src.index('if (BOARD === "card")'):]
        block = block[:block.index("process.exit(0)")]
        assert 'arg("count", null)' in block


class TestSendFalseMeansNothingIsSent:
    """The flag governed one of the TWO places this workflow sends.

    `board: card` was also picked up by the draft path, which builds whatever board it is
    given and delivers it unconditionally. So a manual run asking to SEE a card posted
    one: the card step said "built, NOT sent" in the same job that had already sent it
    thirty seconds earlier. A flag that covers half the sends is worse than no flag,
    because it is believed.
    """

    def test_the_draft_path_does_not_build_a_card(self):
        assert "inputs.board != 'card'" in step("Build the day's draft")

    def test_and_does_not_send_one(self):
        assert "inputs.board != 'card'" in step("Send it to Telegram")

    def test_exactly_one_step_sends_the_card(self):
        """Two steps that can both deliver a card is the shape of the bug, whatever the
        conditions on them say today."""
        src = workflow()
        senders = [n for n in ("Build the day's draft", "Send it to Telegram",
                               "Send the card to the channel")
                   if "--board card" in step(n) or "card.json" in step(n)]
        assert senders == ["Send the card to the channel"], senders

    def test_the_card_reaches_the_job_log_not_only_the_summary(self):
        """The step summary is a separate artefact the job log does not contain, so a card
        'built but not sent' was unreadable from the place anyone actually looks."""
        block = step("Send the card to the channel")
        assert "cat card.md" in block
        assert "GITHUB_STEP_SUMMARY" in block
        # ...and to stdout, which is what lands in the log.
        assert "----- card -----" in block


class TestTheIssueFallbackNeedsADraftToRescue:
    """It exists to catch a draft Telegram would not take. It was gated only on "Telegram
    did not send" — and a SKIPPED Telegram step passes that test exactly as a failed one
    does. On a card run the draft is skipped, nothing is written, and the fallback fired
    anyway and died on `--body-file draft.md: no such file`.

    A rescue step that fails the run when there was nothing to rescue turns a working card
    into a red job, which is worse than the loss it was written to prevent.
    """

    def test_both_fallback_steps_require_the_build_to_have_run(self):
        for name in ("Make sure the label exists", "File it as an issue instead"):
            assert "steps.build.outcome == 'success'" in step(name), name

    def test_they_still_require_telegram_to_have_missed_it(self):
        """The widening must not have turned the fallback into a second delivery that
        files an issue for every draft Telegram took."""
        for name in ("Make sure the label exists", "File it as an issue instead"):
            assert "steps.telegram.outputs.sent != 'true'" in step(name), name


SLATE = os.path.join(ROOT, ".github", "workflows", "daily_slip.yml")


def slate_step(name):
    src = open(SLATE, encoding="utf-8").read()
    start = src.index(f"- name: {name}")
    rest = src[start + 1:]
    nxt = rest.find("\n      - name:")
    return rest[:nxt] if nxt != -1 else rest


class TestThePreviewDoesNotPublish:
    """`day` exists to preview TOMORROW. Posting tomorrow's board today hands members a
    slate headed with a date that has not happened, and then the 07:00 run posts it again
    in the morning — two messages, one of them early and neither explaining the other."""

    def test_a_manual_run_does_not_send_unless_asked(self):
        assert "inputs.send" in slate_step("Send it")

    def test_the_schedule_still_sends_every_morning(self):
        """The guard must key on the run being MANUAL. Gating the send on an input alone
        would silence the 07:00 job, where that input is never set."""
        assert "github.event_name != 'workflow_dispatch'" in slate_step("Send it")

    def test_the_slate_reaches_the_job_log(self):
        """It went only to the step summary, a separate artefact the log does not carry —
        so on a preview run, which sends nothing by design, the board was readable
        nowhere at all."""
        block = slate_step("Build today's slate")
        assert "GITHUB_STEP_SUMMARY" in block
        assert "----- slate -----" in block
