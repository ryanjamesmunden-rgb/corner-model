"""The record reads as weeks, and counts only what the site actually claimed.

TWO THINGS BROKE WHEN THE SNAPSHOT WENT DAILY, and neither raised.

It read as days. Every snapshot became its own section under a heading that still said
"week", so a month of football arrived as thirty blocks.

It counted a quota. The snapshot freezes the top 25 of the board every night. On a Saturday
with sixty fixtures that is a selection; on a Tuesday with ten it is the whole board
including the bottom of it. So a quiet midweek contributed as many claims as a full weekend
and they were the weakest on offer — the site published nothing that night and the record
wrote down twenty-five picks.

The fix has one rule that matters and these tests exist to hold it: a row is counted under
the rule in force WHEN IT WAS FROZEN, never re-judged by today's.
"""
import os
import sys
from datetime import date

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "test_corner_model")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import record_view as rv  # noqa: E402


def snap(tag, entries=()):
    return {"tag": tag, "entries": list(entries)}


def entry(name="Boro", **kw):
    return {"name": name, **kw}


class TestAWeekIsAWeek:
    def test_days_in_one_week_collapse_into_one_block(self):
        # Mon 14 Sep 2026 through Sun 20 Sep 2026.
        snaps = [snap("2026-09-14"), snap("2026-09-16"), snap("2026-09-20")]
        out = rv.group_by_week(snaps)
        assert len(out) == 1
        assert out[0]["week"] == "2026-09-14"
        assert len(out[0]["days"]) == 3

    def test_the_week_starts_on_monday(self):
        # Sunday belongs to the week that began six days earlier, not to the one starting
        # tomorrow — which is how a weekend ends up split across two blocks.
        assert rv.week_of("2026-09-20") == "2026-09-14"
        assert rv.week_of("2026-09-21") == "2026-09-21"

    def test_separate_weeks_stay_separate(self):
        out = rv.group_by_week([snap("2026-09-20"), snap("2026-09-21")])
        assert [b["week"] for b in out] == ["2026-09-21", "2026-09-14"]

    def test_newest_week_first_and_newest_day_within_it(self):
        out = rv.group_by_week([snap("2026-09-14"), snap("2026-09-16")])
        assert [s["tag"] for s in out[0]["days"]] == ["2026-09-16", "2026-09-14"]

    def test_an_unreadable_tag_is_dropped_rather_than_crashing_the_page(self):
        out = rv.group_by_week([snap("not-a-date"), snap("2026-09-16")])
        assert len(out) == 1

    def test_a_missing_tag_is_not_a_week(self):
        assert rv.week_of(None) is None
        assert rv.group_by_week([{"entries": []}]) == []


class TestTheLabelPlacesTheWeekWithoutArithmetic:
    TODAY = date(2026, 9, 16)      # a Wednesday

    def test_the_current_week_says_so(self):
        assert rv.label("2026-09-14", self.TODAY) == "This week"

    def test_the_one_before_says_so(self):
        assert rv.label("2026-09-07", self.TODAY) == "Last week"

    def test_anything_older_gets_a_date_rather_than_a_countback(self):
        # "3 weeks ago" makes a reader do arithmetic to place a result.
        assert rv.label("2026-08-31", self.TODAY) == "Week of 31 August 2026"

    def test_nothing_is_an_empty_string_not_the_word_undefined(self):
        assert rv.label(None) == ""
        assert rv.label("nonsense") == "nonsense"


class TestOnlyWhatTheSiteStoodBehindIsCounted:
    def test_a_row_the_site_declined_to_publish_is_not_a_claim(self):
        # The board had it; the site did not put its name to it. Counting it records a
        # pick that was never made.
        assert rv.counted(entry(qualified=False)) is False

    def test_a_published_row_is(self):
        assert rv.counted(entry(qualified=True)) is True

    def test_a_row_frozen_before_the_bar_existed_still_counts(self):
        # THE DEFAULT IS THE WHOLE POINT. `qualified` is absent on every row frozen before
        # the corroboration bar, and for those the board WAS the claim. Treating absence as
        # "not qualified" would erase the record overnight and read as the site deleting
        # its own history.
        assert rv.counted(entry()) is True

    def test_old_rows_are_not_re_judged_by_the_new_bar(self):
        # Scoring yesterday's calls under a rule they were never made under is the same
        # look-ahead the snapshot exists to prevent, pointed the other way.
        old = [entry("a"), entry("b")]
        published, held = rv.split(old)
        assert len(published) == 2 and held == []

    def test_a_quiet_night_publishes_few_and_holds_the_rest(self):
        night = [entry("good", qualified=True)] + \
                [entry(f"filler{i}", qualified=False) for i in range(24)]
        published, held = rv.split(night)
        assert len(published) == 1
        assert len(held) == 24

    def test_both_halves_come_back_because_both_are_shown(self):
        # Dropping the held half would hide that the board had more on it than the site
        # chose to publish, and on a quiet midweek that gap is the story.
        published, held = rv.split([entry("a", qualified=True), entry("b", qualified=False)])
        assert [e["name"] for e in published] == ["a"]
        assert [e["name"] for e in held] == ["b"]

    def test_an_empty_night_is_not_an_error(self):
        assert rv.split([]) == ([], [])


class TestTheEndpointStillDoesThis:
    def test_public_results_groups_by_week_and_splits(self):
        import inspect
        import server
        src = inspect.getsource(server.public_results)
        assert "record_view.group_by_week" in src, \
            "the record is back to one section per snapshot — a month reads as thirty blocks"
        assert "record_view.split" in src, \
            "unpublished board rows are being counted as claims the site made"

    def test_the_held_rows_are_returned_but_kept_out_of_the_tally(self):
        import inspect
        import server
        src = inspect.getsource(server.public_results)
        assert '"held"' in src, "unpublished board rows are no longer shown at all"
        # The counted list feeds the headline. Held rows must never reach it — and the
        # assertion is on WHAT IS EXTENDED rather than on a variable name, so a rename
        # does not fail this and a genuine mistake still does.
        counted_into = [l.strip() for l in src.splitlines() if ".extend(" in l]
        assert any(l.endswith("extend(rows)") for l in counted_into)
        assert not any("extend(held" in l for l in counted_into), \
            "held rows are being folded into the counted list — the headline would " \
            "include picks the site declined to make"

    def test_the_headline_covers_the_current_rule_only(self):
        import inspect
        import server
        src = inspect.getsource(server.public_results)
        assert "record_view.split_eras" in src, \
            "the record is back to one number spanning two selection rules"
        assert '"archive"' in src, "the earlier era is no longer published at all"


class TestTheCleanSlate:
    """The picks were chosen one way and are now chosen another.

    A single percentage spanning both describes neither — it is an average of two rules,
    and a reader has no way to know which one they are being sold. So the headline starts
    again at the change, and the earlier era is kept whole under its own heading.
    """

    def test_a_snapshot_frozen_under_the_bar_is_the_current_era(self):
        assert rv.era_of(snap("2026-09-16", [entry(qualified=True)])) == rv.ERA_CORROBORATED

    def test_one_frozen_before_it_is_not(self):
        assert rv.era_of(snap("2026-09-10", [entry(), entry()])) == rv.ERA_STREAK_ONLY

    def test_a_night_where_nothing_qualified_is_still_the_current_era(self):
        # The field is present and false. That is a night the new rule ran and published
        # nothing, which is the rule working — not a night from before it existed.
        s = snap("2026-09-16", [entry(qualified=False), entry(qualified=False)])
        assert rv.era_of(s) == rv.ERA_CORROBORATED

    def test_an_empty_snapshot_falls_to_the_earlier_era(self):
        # Nothing to read the rule from. It goes to the archive, where it affects no
        # headline either way.
        assert rv.era_of(snap("2026-09-16", [])) == rv.ERA_STREAK_ONLY

    def test_the_boundary_is_read_from_the_data_not_from_a_date(self):
        """A cutover constant would have to be the exact night a deploy landed relative to
        an 11:00 UTC job — which is how a boundary ends up a day out, silently, in
        whichever direction flatters the number."""
        import inspect
        src = inspect.getsource(rv.era_of)
        assert "qualified" in src
        assert "2026" not in src, "era_of is comparing against a hardcoded date"

    def test_the_two_eras_come_apart_cleanly(self):
        snaps = [snap("2026-09-16", [entry(qualified=True)]),
                 snap("2026-09-10", [entry()]),
                 snap("2026-09-17", [entry(qualified=False)])]
        current, earlier = rv.split_eras(snaps)
        assert [s["tag"] for s in current] == ["2026-09-16", "2026-09-17"]
        assert [s["tag"] for s in earlier] == ["2026-09-10"]

    def test_nothing_is_lost_between_them(self):
        # Every snapshot lands in exactly one era. A row that fell through the gap would be
        # a claim that was made and is now graded nowhere.
        snaps = [snap("2026-09-16", [entry(qualified=True)]), snap("2026-09-10", [entry()]),
                 snap("2026-09-11", []), snap("2026-09-17", [entry(qualified=False)])]
        current, earlier = rv.split_eras(snaps)
        assert len(current) + len(earlier) == len(snaps)

    def test_a_week_straddling_the_change_appears_in_both(self):
        # It looks odd exactly once and it is the truth: some of that week's nights were
        # picked one way and some the other.
        snaps = [snap("2026-09-15", [entry()]), snap("2026-09-17", [entry(qualified=True)])]
        current, earlier = rv.split_eras(snaps)
        assert rv.group_by_week(current)[0]["week"] == "2026-09-14"
        assert rv.group_by_week(earlier)[0]["week"] == "2026-09-14"

    def test_the_earlier_era_is_kept_rather_than_discarded(self):
        # Deleting it would end any chance of grading that period ever again: a snapshot is
        # the only evidence of what was claimed before a game was played, and recomputing
        # it afterwards counts only the survivors.
        _current, earlier = rv.split_eras([snap("2026-09-10", [entry("Boro")])])
        assert earlier[0]["entries"][0]["name"] == "Boro"

    def test_old_rows_are_still_all_counted_within_their_own_era(self):
        # In that era the board WAS the claim, so the archive's tally reads as it always
        # did rather than being retroactively thinned by a bar that did not exist.
        published, held = rv.split([entry("a"), entry("b")])
        assert len(published) == 2 and held == []
