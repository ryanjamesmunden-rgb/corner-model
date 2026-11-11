"""The followed-team form graph's data: last 20 REAL games, oldest first."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "test")

import server  # noqa: E402


def _m(date, cf, ca=4, home=True, **k):
    return {"date": date, "corners_for": cf, "corners_against": ca, "home": home,
            "opponent": "X", "goals_for": 1, "goals_against": 0, **k}


def test_oldest_first_whatever_the_stored_order():
    t = {"real_matches": [_m("2026-10-03", 7), _m("2026-09-01", 3), _m("2026-09-20", 5)]}
    out = server._favourite_team_form(t)
    assert [g["won"] for g in out] == [3, 5, 7]


def test_capped_at_the_most_recent_twenty():
    t = {"real_matches": [_m(f"2026-08-{d:02d}", d) for d in range(1, 26)]}
    out = server._favourite_team_form(t)
    assert len(out) == 20
    assert out[0]["won"] == 6 and out[-1]["won"] == 25


def test_padded_synthetic_games_never_appear():
    """`matches` can hold invented games for a thin side; the graph reads real ones only."""
    t = {"matches": [_m("2026-09-01", 99)], "real_matches": [_m("2026-09-02", 4)]}
    assert [g["won"] for g in server._favourite_team_form(t)] == [4]


def test_total_and_venue_carried_and_a_missing_concede_is_not_zero():
    out = server._favourite_team_form({"real_matches": [
        _m("2026-09-01", 6, 3, home=False), _m("2026-09-02", 5, None)]})
    assert out[0] == {**out[0], "won": 6, "conceded": 3, "total": 9, "home": False}
    assert out[1]["conceded"] is None and out[1]["total"] is None


def test_a_team_with_nothing_on_file_is_an_empty_graph():
    assert server._favourite_team_form({}) == []
    assert server._favourite_team_form(None) == []
