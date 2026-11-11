"""When to start or stop tracking: fixture difficulty and form."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "test")

import server  # noqa: E402


def _t(tid, wons=(), conceded_home=None, conceded_away=None, lid="L"):
    rms = [{"date": f"2026-08-{i + 1:02d}", "corners_for": w, "corners_against": 4,
            "home": i % 2 == 0} for i, w in enumerate(wons)]
    for i, c in enumerate(conceded_home or []):
        rms.append({"date": f"2026-07-{i + 1:02d}", "corners_for": 4, "corners_against": c, "home": True})
    for i, c in enumerate(conceded_away or []):
        rms.append({"date": f"2026-06-{i + 1:02d}", "corners_for": 4, "corners_against": c, "home": False})
    return {"team_id": tid, "name": tid, "league_id": lid, "real_matches": rms}


def _fx(home, away, day):
    return {"fixture_id": f"{home}-{away}", "home_team_id": home, "away_team_id": away,
            "home_name": home, "away_name": away, "date": f"2026-11-{day:02d}", "league_id": "L"}


def test_difficulty_uses_the_opponent_at_the_opposite_venue():
    me = _t("me", [5] * 10)
    # Leaky AWAY (where they will be when we are at home), stingy at home.
    leaky_away = _t("opp", conceded_home=[2] * 6, conceded_away=[7] * 6)
    o = server._team_outlook(me, [_fx("me", "opp", 15)], {"opp": leaky_away}, {"L": 5.0})
    assert o["next"][0]["opp_conceded"] == 7 and o["next"][0]["ratio"] == 1.4
    assert o["schedule_label"] == "soft"
    o2 = server._team_outlook(me, [_fx("opp", "me", 15)], {"opp": leaky_away}, {"L": 5.0})
    assert o2["next"][0]["ratio"] == 0.4 and o2["schedule_label"] == "tough"


def test_thin_opponent_is_unrated_not_guessed():
    me = _t("me", [5] * 10)
    thin = _t("opp", conceded_away=[9, 9])
    o = server._team_outlook(me, [_fx("me", "opp", 15)], {"opp": thin}, {"L": 5.0})
    assert o["next"][0]["ratio"] is None and o["schedule_label"] == "unknown"


def test_form_delta_and_live_run():
    me = _t("me", [4] * 15 + [8, 8, 8, 8, 8])     # l20 avg 5, last five 8
    o = server._team_outlook(me, [], {}, {"L": 5.0})
    assert o["l5"] == 8 and o["l20"] == 5 and o["form_delta"] == 3
    assert o["line"] == 5 and o["run"] == 5
    assert server._in_form(o)


def test_flags():
    base = {"form_delta": 0, "run": 0}
    assert server._outlook_flag({**base, "schedule_label": "tough"}) == "tough_run"
    assert server._outlook_flag({**base, "schedule_label": "soft", "run": 3}) == "good_spot"
    assert server._outlook_flag({**base, "schedule_label": "soft"}) is None
    assert server._outlook_flag({**base, "schedule_label": "normal", "form_delta": -1.5}) == "cooling"
