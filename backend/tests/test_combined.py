"""The combined board: Quick Scan, Streaks and Perfect Games merged on team + fixture."""
import math
import os
import sys

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "test_corner_model")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import combined  # noqa: E402


def poisson_ge(k, lam):
    return 1 - sum(math.exp(-lam) * lam ** i / math.factorial(i) for i in range(k))


def fx(fid="f1", home=True, opp="o1"):
    return {"fixture_id": fid, "date": "2026-11-21T15:00:00+00:00", "is_home": home,
            "opponent": "Opp", "opponent_team_id": opp}


def mismatch(team="t1", lam=7.0, opp_games=10, **kw):
    return {"team_id": team, "name": "Team", "league_id": "l", "league_name": "L",
            "next_fixture": kw.get("nf", fx()), "lambda": lam, "line": 6, "prob": 60.0,
            "fair_odds": 1.67, "team_for": 7.0, "opp_conceded": 7.0, "real_samples": 20,
            "evidence": {"opponent": {"games": opp_games}}}


def run(team="t1", side="home", floor=5, nf=None):
    return {"team_id": team, "name": "Team", "league_id": "l", "league_name": "L",
            "next_fixture": nf or fx(), "side": side, "line": 6, "line_label": "6+",
            "hits": 5, "settled": 5, "avg": 7.2, "min_won": floor,
            "streak": {"length": 5}, "recent": [{"corners": 7}],
            "projection": {"lambda": 6.5}}


TEAMS = {"t1": {"team_id": "t1", "real_samples": 20}, "o1": {"team_id": "o1", "real_samples": 20}}


def test_merges_boards_on_team_and_fixture_and_prices_5_and_6():
    odds = {"f1": {"home_over_5.5": 2.0, "home_over_4.5": 1.3}}
    rows = combined.combine_boards([mismatch()], [run()], [], TEAMS, odds, poisson_ge)
    assert len(rows) == 1
    r = rows[0]
    assert r["boards"] == ["quick_scan", "streaks"]
    assert [a["line"] for a in r["angles"]] == [5, 6]
    six = r["angles"][1]
    assert six["market_key"] == "home_over_5.5" and six["book_odds"] == 2.0
    assert six["prob"] == round(poisson_ge(6, 7.0) * 100, 1)
    assert r["best"]["line"] == 6 and r["value"] is True
    assert r["streak"]["floor"] == 5


def test_single_board_rows_are_dropped_by_default():
    assert combined.combine_boards([mismatch()], [], [], TEAMS, {}, poisson_ge) == []
    rows = combined.combine_boards([mismatch()], [], [], TEAMS, {}, poisson_ge, min_boards=1)
    assert len(rows) == 1 and "no bookmaker price for 5+/6+ yet" in rows[0]["warnings"]


def test_thin_samples_are_dropped_and_thin_opponents_flagged():
    thin = {**TEAMS, "t1": {"team_id": "t1", "real_samples": 12}}
    assert combined.combine_boards([mismatch()], [run()], [], thin, {}, poisson_ge) == []
    rows = combined.combine_boards([mismatch(opp_games=7)], [run()], [], TEAMS, {}, poisson_ge)
    assert "opponent's venue record is 7 games" in rows[0]["warnings"]


def test_away_fixture_uses_away_run_and_away_market():
    nf = fx(home=False)
    odds = {"f1": {"away_over_5.5": 2.2}}
    rows = combined.combine_boards([mismatch(nf=nf)],
                                   [run(side="home", nf=nf, floor=1),
                                    run(side="away", nf=nf, floor=6)],
                                   [], TEAMS, odds, poisson_ge)
    assert rows[0]["streak"]["side"] == "away" and rows[0]["streak"]["floor"] == 6
    assert rows[0]["angles"][1]["book_odds"] == 2.2


def test_value_rows_sort_first():
    a = mismatch(team="t1")
    b = {**mismatch(team="t2"), "next_fixture": fx(fid="f2")}
    teams = {**TEAMS, "t2": {"team_id": "t2", "real_samples": 20}}
    odds = {"f2": {"home_over_5.5": 3.0}}
    rows = combined.combine_boards([a, b], [run(team="t1"), run(team="t2", nf=fx(fid="f2"))],
                                   [], teams, odds, poisson_ge)
    assert [r["team_id"] for r in rows] == ["t2", "t1"]


def test_promoted_sides_are_flagged_and_sink_below_established_ones():
    flagged = {**mismatch(team="t2"), "next_fixture": fx(fid="f2"),
               "league_change": {"status": "promoted", "label": "newly promoted"}}
    teams = {**TEAMS, "t2": {"team_id": "t2", "real_samples": 20}}
    odds = {"f1": {"home_over_5.5": 2.0}, "f2": {"home_over_5.5": 2.0}}
    rows = combined.combine_boards([flagged, mismatch()],
                                   [run(team="t2", nf=fx(fid="f2")), run()], [],
                                   teams, odds, poisson_ge)
    assert [r["team_id"] for r in rows] == ["t1", "t2"]
    assert "Team newly promoted: price less reliable" in rows[1]["warnings"]


def frozen(team="t1", fid="f1", day="2026-11-22", line=6, **kw):
    return {"team_id": team, "name": kw.get("name", "Team"), "league_id": "l",
            "league_name": "L", "line": line, "direction": kw.get("direction", "over"),
            "subject": kw.get("subject", "team"), "fixture_id": fid,
            "kickoff": f"{day}T15:00:00+00:00", "opponent": "Opp", "is_home": True}


def test_rebuild_keeps_pairs_on_two_boards_inside_the_dates():
    by_board = {
        "quick_scan": [frozen(), frozen(team="t2", fid="f2"), frozen(team="t3", fid="f3",
                                                                      day="2026-11-24")],
        "streaks": [frozen(line=5), frozen(team="t3", fid="f3", day="2026-11-24")],
        "perfect_games": [frozen(team="t2", fid="f2", subject="match")],
    }
    out = combined.rebuild_from_snapshots(by_board, "2026-11-21", "2026-11-22")
    # t1 is on two boards; t2's perfect row is a match total so it does not count;
    # t3 is outside the dates.
    assert {e["team_id"] for e in out} == {"t1"}
    assert [e["line"] for e in out] == [5, 6]
    assert out[0]["boards"] == ["quick_scan", "streaks"]
    assert out[0]["board_lines"] == {"quick_scan": 6, "streaks": 5}


def test_snapshot_entries_one_per_line_with_the_boards():
    rows = combined.combine_boards([mismatch()], [run()], [], TEAMS, {"f1": {"home_over_4.5": 1.8}},
                                   prob_ge=poisson_ge)
    out = combined.snapshot_entries(rows)
    assert [e["line"] for e in out] == [5, 6]
    assert out[0]["book_odds"] == 1.8 and out[1]["book_odds"] is None
    assert all(e["boards"] == ["quick_scan", "streaks"] and e["subject"] == "team"
               for e in out)
