"""The conceded-run candidates, and the floor they have to clear.

WHY THIS FILE EXISTS AT ALL. measure_chase_board has falsified eight rankings, and one of
them — `consistency_only` — nearly got through: +7.9 against a shuffled control near zero
reads as a finding. It was not one. A ranking built from a team's RECENT REALISED COUNTS can
separate the buckets with no market edge whatsoever, because lambda is estimated from ten
games and such a ranking corrects that estimate. The check that caught it was synthetic data
with no edge by construction, which still yielded 7.5 — and that number lived in a docstring
with nothing in the repo able to reproduce it.

So what is pinned here is the machinery that makes the number reproducible, and the two
properties it rests on:

  - THE NULL HAS NO EDGE IN IT. Every team gets one fixed true rate, so nothing varies over
    time and there is nothing for any ranking to discover. If synthesise() leaked the real
    outcomes through, the "floor" would contain the very effect it is meant to bound, and
    every candidate would be measured against itself.
  - A STREAK IS COUNTED FROM THE NEWEST GAME. Counting from the front measures a run that
    ended some time ago and reports it as one running into this fixture — the difference
    between the angle and a historical curiosity.
"""
import os
import sys

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "test_corner_model")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import measure_chase_board as mcb  # noqa: E402


def match(date, h, a, hc, ac, shots=14):
    return {"date": f"{date}T15:00:00Z", "league_id": "eng-pl", "home_id": h, "away_id": a,
            "home_corners": hc, "away_corners": ac,
            "home_shots": shots, "away_shots": shots,
            "home_blocked_shots": 4, "away_blocked_shots": 4,
            "home_fh_goals": 1, "away_fh_goals": 0}


class TestTheRunIsCountedFromTheNewestGame:
    def test_an_unbroken_run_at_the_end_is_the_run(self):
        # Chronological, newest last: the last three cleared 5.
        assert mcb._run_from_end([2, 3, 6, 7, 5], 5) == 3

    def test_a_run_that_ended_is_not_reported_as_running(self):
        """THE LOAD-BEARING CASE. Counting from the front gives 3 here and the row would
        claim a live streak that broke two games ago."""
        assert mcb._run_from_end([6, 7, 8, 1, 2], 5) == 0

    def test_a_miss_in_the_newest_game_ends_it_at_zero(self):
        assert mcb._run_from_end([6, 6, 6, 4], 5) == 0

    def test_every_game_clearing_it_is_the_whole_pool(self):
        assert mcb._run_from_end([5, 6, 7], 5) == 3

    def test_an_empty_pool_is_no_run_rather_than_an_error(self):
        assert mcb._run_from_end([], 5) == 0

    def test_a_value_exactly_on_the_line_counts(self):
        # These are `line+` claims: 5 clears 5+.
        assert mcb._run_from_end([5], 5) == 1


class TestTheNullHasNoEdgeInIt:
    # Two teams that in the REAL data are wildly streaky: one alternates 9 and 1 corners.
    # If synthesise leaked outcomes, that pattern would survive.
    REAL = [match(f"2026-0{1 + i // 9}-{1 + i % 9:02d}", 1, 2,
                  9 if i % 2 == 0 else 1, 4)
            for i in range(18)]

    def test_the_fixtures_dates_and_pairings_are_preserved(self):
        out = mcb.synthesise(self.REAL, 7)
        assert len(out) == len(self.REAL)
        assert [r["date"] for r in out] == [r["date"] for r in self.REAL]
        assert [(r["home_id"], r["away_id"]) for r in out] \
            == [(r["home_id"], r["away_id"]) for r in self.REAL]

    def test_the_corner_counts_are_redrawn_and_not_copied(self):
        out = mcb.synthesise(self.REAL, 7)
        real = [r["home_corners"] for r in self.REAL]
        drawn = [r["home_corners"] for r in out]
        assert drawn != real, "the null is the real outcomes wearing a different name"

    def test_the_alternating_pattern_does_not_survive(self):
        """THE PROPERTY THE FLOOR RESTS ON. In the real rows every other game is a 9 and
        the rest are 1s — a pattern any consistency-shaped ranking would find. Drawing from
        one fixed rate per team has to destroy it, or the floor contains the effect it is
        supposed to bound."""
        drawn = [r["home_corners"] for r in mcb.synthesise(self.REAL, 7)]
        alternating = sum(1 for i in range(0, len(drawn) - 1, 2)
                          if drawn[i] > drawn[i + 1] + 4)
        assert alternating < len(drawn) // 4

    def test_it_is_deterministic_for_a_seed(self):
        # The floor has to be reproducible, or two runs disagree about whether a candidate
        # cleared it.
        a = [r["home_corners"] for r in mcb.synthesise(self.REAL, 11)]
        b = [r["home_corners"] for r in mcb.synthesise(self.REAL, 11)]
        assert a == b

    def test_a_different_seed_draws_differently(self):
        a = [r["home_corners"] for r in mcb.synthesise(self.REAL, 11)]
        b = [r["home_corners"] for r in mcb.synthesise(self.REAL, 12)]
        assert a != b

    def test_the_drawn_mean_tracks_the_teams_true_rate(self):
        # Team 1 wins ~9 and 1 alternately, so a mean near 5; team 2 concedes ~4.
        # The draw's mean should land in that region rather than anywhere at all.
        out = mcb.synthesise(self.REAL * 6, 3)
        mean = sum(r["home_corners"] for r in out) / len(out)
        assert 2.0 < mean < 9.0

    def test_a_row_with_no_team_ids_passes_through_untouched(self):
        odd = [{"date": "2026-01-01T15:00:00Z", "home_id": None, "away_id": None}]
        assert mcb.synthesise(odd, 1) == odd


class TestTheSampler:
    def test_it_returns_a_count_in_range(self):
        import random
        rng = random.Random(4)
        vals = [mcb._nb_sample(5.0, rng) for _ in range(300)]
        assert all(isinstance(v, int) and v >= 0 for v in vals)

    def test_its_mean_is_the_lambda_it_was_given(self):
        # Drawn by inverse CDF off nb_pmf, so this is really asserting the null is drawn
        # from the distribution the MODEL prices with — not some other one.
        import random
        rng = random.Random(5)
        vals = [mcb._nb_sample(6.0, rng) for _ in range(4000)]
        assert 5.5 < sum(vals) / len(vals) < 6.5

    def test_a_zero_lambda_draws_zero(self):
        import random
        assert mcb._nb_sample(0.0, random.Random(1)) == 0


class TestTheRegistryOfFloors:
    def test_the_conceded_candidates_are_in_the_estimator_family(self):
        """They read the opponent's recent realised counts, so the shuffled control is the
        WRONG floor for them — that is exactly how +7.9 was once misread."""
        assert "opp_conc_consistency" in mcb.ESTIMATOR_FAMILY
        assert "opp_conc_run" in mcb.ESTIMATOR_FAMILY

    def test_consistency_only_is_too_since_it_is_the_original_case(self):
        assert "consistency_only" in mcb.ESTIMATOR_FAMILY

    def test_the_control_is_not(self):
        # RANDOM correlates with nothing; holding it to the estimator floor would let a
        # broken harness off.
        assert "RANDOM" not in mcb.ESTIMATOR_FAMILY

    def test_every_family_member_is_a_ranking_that_exists(self):
        keys = {k for k, _ in mcb.RANKINGS}
        assert mcb.ESTIMATOR_FAMILY <= keys, mcb.ESTIMATOR_FAMILY - keys

    def test_every_lambda_derived_ranking_is_in_it_too(self):
        """THE CLASSIFICATION THE FIRST REAL RUN CORRECTED.

        The family was hand-typed as the six rankings that read realised counts, which left
        out every ranking built from LAMBDA — and lambda is itself estimated from a ten-game
        window. Held against the shuffled control those five came back "INVERTED past its
        floor"; held against their own nulls, which are more inverted still, each is at its
        floor and the inversion is regression in the estimate."""
        for key in ("chase_score", "lambda_only", "no_opp_fh", "no_consistency", "slack"):
            assert key in mcb.ESTIMATOR_FAMILY, key

    def test_it_is_derived_rather_than_typed(self):
        """One less hand-maintained list to get wrong — the same failure mode as the three
        tool registries, which broke three times before a test closed it."""
        assert mcb.ESTIMATOR_FAMILY == {k for k, _ in mcb.RANKINGS} - {"RANDOM"}


class TestTheReplayScoresTheNewCandidates:
    def build(self, rows):
        return mcb.build_spots(rows, window=10, min_games=5)

    def rows(self):
        """Enough history for the replay's bars: both sides need 5 games and 3 on venue."""
        out = []
        day = 1
        for i in range(24):
            # Team 1 at home to 2, then away, alternating, so both build venue pools.
            h, a = (1, 2) if i % 2 == 0 else (2, 1)
            out.append(match(f"2026-{1 + day // 28:02d}-{1 + day % 28:02d}", h, a, 7, 6))
            day += 3
        return out

    def test_a_spot_carries_both_conceded_candidates(self):
        spots = self.build(self.rows())
        assert spots, "the replay produced no spots, so nothing below is tested"
        for key in ("opp_conc_consistency", "opp_conc_run", "opp_pool"):
            assert key in spots[-1], key

    def test_the_run_is_capped_by_the_venue_pool_it_was_read_from(self):
        spots = self.build(self.rows())
        for s in spots:
            assert s["opp_conc_run"] <= s["opp_pool"]

    def test_a_thin_opponent_pool_scores_zero_rather_than_guessing(self):
        # Scored 0, and `opp_pool` is what lets the run report how often that happened
        # instead of leaving those rows looking measured.
        spots = self.build(self.rows())
        thin = [s for s in spots if s["opp_pool"] < mcb.MIN_VENUE_GAMES]
        for s in thin:
            assert s["opp_conc_run"] == 0 and s["opp_conc_consistency"] == 0.0


class TestTheVerdictReadsTheSign:
    """A SMOKE TEST CAUGHT THIS FILE CLAIMING a -13.7 spread had "cleared its floor by
    +7.4". The verdict was computed off abs(spread), so an ordering that put the WORST
    spots on top read as the strongest finding on the board.

    The claim a ranking makes is that its TOP bucket beats its BOTTOM one. Only a positive
    spread supports that; a large negative one is the score's sign being wrong."""

    def test_a_positive_spread_above_the_floor_clears_it(self):
        v = mcb._verdict("opp_conc_run", 12.0, 5.0, True)
        assert "clears its floor" in v

    def test_the_same_magnitude_negative_does_not(self):
        v = mcb._verdict("opp_conc_run", -12.0, 5.0, True)
        assert "clears" not in v
        assert "INVERTED" in v

    def test_a_spread_inside_the_floor_is_not_a_finding_either_way(self):
        assert "not a finding" in mcb._verdict("opp_conc_run", 4.0, 5.0, True)
        assert "not a finding" in mcb._verdict("opp_conc_run", -4.0, 5.0, True)

    def test_a_spread_only_just_over_the_floor_is_still_not_a_finding(self):
        # The floor is a floor, not a threshold to be grazed.
        assert "not a finding" in mcb._verdict("opp_conc_run", 5.5, 5.0, True)

    def test_an_estimator_candidate_with_no_null_is_unreadable_rather_than_passing(self):
        # --no-null must not turn a floor-bound candidate into a finding by omission.
        assert "unreadable" in mcb._verdict("opp_conc_run", 20.0, 0.0, False)

    def test_the_control_is_labelled_as_one_whatever_it_did(self):
        assert mcb._verdict("RANDOM", 20.0, 1.0, True) == "control"

    def test_without_a_null_nothing_but_the_control_is_readable(self):
        """The honest consequence of deriving the family: every ranking here is built from
        estimated quantities, so --no-null leaves the whole table unreadable. That makes the
        flag a fast structural check and not a shortcut to an answer, which is better than a
        flag that prints numbers nobody can interpret."""
        for key in ("chase_score", "lambda_only", "opp_conc_run", "slack"):
            assert "unreadable" in mcb._verdict(key, 12.0, 2.0, False), key
        assert mcb._verdict("RANDOM", 12.0, 2.0, False) == "control"
