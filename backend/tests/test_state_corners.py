"""The clean-sheet / corners-conceded measurement.

WHAT THESE GUARD. This number decides whether a published context line is allowed to
claim a mechanism, so the arithmetic has to be right in BOTH directions and it has to be
willing to say "no". A measurement that can only confirm is not a measurement.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from state_corners import MIN_BUCKET, bucket_state_corners, report  # noqa: E402


def m(cf, ca, gf, ga, fh=(0, 0)):
    return {"corners_for": cf, "corners_against": ca, "goals_for": gf,
            "goals_against": ga, "fh_goals_for": fh[0], "fh_goals_against": fh[1],
            "home": True, "date": "2026-09-01"}


def teams(rows):
    return [{"name": "T", "real_matches": rows}]


class TestItCanSayYes:
    def test_more_corners_conceded_in_clean_sheets_reads_as_support(self):
        rows = [m(5, 9, 1, 0) for _ in range(MIN_BUCKET)]      # clean sheets, 9 conceded
        rows += [m(5, 4, 1, 2) for _ in range(MIN_BUCKET)]     # leaked, 4 conceded
        v = bucket_state_corners(teams(rows))["verdict"]
        assert v["direction"] == "supports", v
        assert v["gap"] == 5.0


class TestItCanSayNo:
    def test_fewer_corners_conceded_in_clean_sheets_reads_as_contradiction(self):
        # The outcome the claim does not expect, and the one a measurement must be able
        # to report: a clean sheet as an easy night rather than a siege.
        rows = [m(5, 3, 1, 0) for _ in range(MIN_BUCKET)]
        rows += [m(5, 8, 1, 2) for _ in range(MIN_BUCKET)]
        v = bucket_state_corners(teams(rows))["verdict"]
        assert v["direction"] == "contradicts", v
        assert "wrong way" in v["says"]

    def test_a_small_gap_is_unclear_rather_than_a_finding(self):
        rows = [m(5, 5.0 if False else 5, 1, 0) for _ in range(MIN_BUCKET)]
        rows += [m(5, 5, 1, 2) for _ in range(MIN_BUCKET)]
        v = bucket_state_corners(teams(rows))["verdict"]
        assert v["direction"] == "unclear", v
        assert "not supported, and not refuted" in v["says"]

    def test_a_thin_bucket_gets_no_verdict(self):
        rows = [m(5, 9, 1, 0) for _ in range(3)]
        rows += [m(5, 4, 1, 2) for _ in range(3)]
        v = bucket_state_corners(teams(rows))["verdict"]
        assert v["direction"] == "insufficient" and v["gap"] is None


class TestTheBucketing:
    def test_a_match_missing_goals_is_excluded_not_counted_as_a_clean_sheet(self):
        # goals_against None must never fall into the clean-sheet bucket: that would
        # turn every uncovered fixture into evidence for the claim.
        rows = [m(5, 6, 1, 0) for _ in range(4)]
        bad = m(5, 6, 1, 0)
        bad["goals_against"] = None
        rows.append(bad)
        agg = bucket_state_corners(teams(rows))
        assert agg["team_games"] == 4
        assert agg["clean_sheet"]["games"] == 4

    def test_results_split_three_ways_and_add_up(self):
        rows = [m(5, 5, 2, 0), m(5, 5, 1, 1), m(5, 5, 0, 3)]
        agg = bucket_state_corners(teams(rows))
        got = {k: v["games"] for k, v in agg["by_result"].items()}
        assert got == {"won": 1, "drew": 1, "lost": 1}
        assert sum(got.values()) == agg["team_games"]

    def test_half_time_state_uses_first_half_goals(self):
        rows = [m(5, 5, 1, 1, fh=(1, 0)), m(5, 5, 1, 1, fh=(0, 1)), m(5, 5, 1, 1, fh=(0, 0))]
        agg = bucket_state_corners(teams(rows))
        got = {k: v["games"] for k, v in agg["by_half_time_state"].items()}
        assert got == {"leading": 1, "level": 1, "trailing": 1}

    def test_both_sides_of_a_fixture_are_separate_observations(self):
        # a 1-0 contributes the winner's clean sheet AND the loser's defeat
        winner = {"name": "W", "real_matches": [m(4, 8, 1, 0)]}
        loser = {"name": "L", "real_matches": [m(8, 4, 0, 1)]}
        agg = bucket_state_corners([winner, loser])
        assert agg["team_games"] == 2
        assert agg["clean_sheet"]["games"] == 1
        assert agg["conceded_a_goal"]["games"] == 1

    def test_an_empty_pool_does_not_divide_by_zero(self):
        agg = bucket_state_corners([])
        assert agg["team_games"] == 0
        assert agg["baseline"]["conceded"] is None
        assert agg["verdict"]["direction"] == "insufficient"


class TestTheWiring:
    """Source-level: server.py needs a database to import, and what is guarded here is
    visible in the text."""

    @staticmethod
    def src():
        here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        with open(os.path.join(here, "server.py")) as fh:
            return fh.read()

    def test_the_endpoint_exists_and_is_token_gated(self):
        s = self.src()
        assert '@api_router.get("/tools/state_corners")' in s
        block = s.split('@api_router.get("/tools/state_corners")')[1].split("@api_router")[0]
        assert "_check_tools_token(token)" in block, "the tools endpoints are gated"
        assert "state_corners.bucket_state_corners" in block

    def test_the_caveat_travels_with_the_number(self):
        # the figure will be quoted; the thing it cannot settle has to go with it
        s = self.src()
        block = s.split('@api_router.get("/tools/state_corners")')[1].split("@api_router")[0]
        assert "caveat" in block and "issue #260" in block

    def test_the_context_line_does_not_assert_the_mechanism_yet(self):
        # Parsed, not split on text: the function's own docstring explains the mechanism
        # at length on purpose, so a line-based strip leaves the word "desperate" in and
        # tests nothing. What matters is the CODE — the string that gets printed.
        import ast
        here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        with open(os.path.join(here, "pick_context.py")) as fh:
            tree = ast.parse(fh.read())
        fn = next(n for n in tree.body
                  if isinstance(n, ast.FunctionDef) and n.name == "d_opp_clean_sheets")
        body = list(fn.body)
        if (body and isinstance(body[0], ast.Expr)
                and isinstance(body[0].value, ast.Constant)
                and isinstance(body[0].value.value, str)):
            body = body[1:]                      # drop the docstring node
        literals = [n.value for n in ast.walk(ast.Module(body=body, type_ignores=[]))
                    if isinstance(n, ast.Constant) and isinstance(n.value, str)]
        printed = " ".join(literals)
        assert "have not conceded a goal in" in printed, printed
        for word in ("desperate", "because", "which means", "so they"):
            assert word not in printed.lower(), f"the line asserts a mechanism: {word}"


class TestTheReportIsReadable:
    def test_it_names_the_verdict_and_the_counts(self):
        rows = [m(5, 9, 1, 0) for _ in range(MIN_BUCKET)]
        rows += [m(5, 4, 1, 2) for _ in range(MIN_BUCKET)]
        text = report(bucket_state_corners(teams(rows)))
        assert "VERDICT" in text and "team-games" in text
        assert "clean_sheet" in text and "by_half_time_state" in text
