"""/review: a played fixture keeps its prices, and they get settled.

THE TEST THAT MATTERS HERE is that the EV actually arrives. The endpoint builds the model
for each reviewed game inside a try/except — one unpriceable fixture must not take the week
down — and the first version passed `home` both positionally and by keyword. That raises
TypeError, the except swallowed it, and every line came back with `ev: None`: a review that
looked like a quiet week rather than a broken one.
"""
import asyncio
import os
import sys
from datetime import datetime, timedelta, timezone

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "test_corner_model")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import server  # noqa: E402


class FakeCursor:
    def __init__(self, docs):
        self._docs = docs

    def sort(self, field, direction=1):
        self._docs.sort(key=lambda d: d.get(field) or "", reverse=direction < 0)
        return self

    async def to_list(self, n):
        return self._docs[:n]


class FakeColl:
    def __init__(self, docs, key):
        self._docs, self._key = docs, key

    def find(self, q=None, proj=None):
        docs = list(self._docs)
        ids = ((q or {}).get(self._key) or {}).get("$in") if q else None
        if ids is not None:
            docs = [d for d in docs if d.get(self._key) in ids]
        date = ((q or {}).get("date") or {}).get("$gte") if q else None
        if date:
            docs = [d for d in docs if str(d.get("date") or "") >= date]
        lid = (q or {}).get("league_id") if q else None
        if isinstance(lid, str):
            docs = [d for d in docs if d.get("league_id") == lid]
        return FakeCursor(docs)


class FakeDB:
    def __init__(self, played, odds, teams, leagues, feed=None):
        self.fixtures_played = FakeColl(played, "fixture_id")
        self.odds = FakeColl(odds, "fixture_id")
        self.odds_feed = FakeColl(list(feed or []), "fixture_id")
        self.teams = FakeColl(teams, "team_id")
        self.leagues = FakeColl(leagues, "league_id")


MEMBER = {"member": True}
NOW = datetime.now(timezone.utc)


def run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def ago(days):
    return (NOW - timedelta(days=days)).isoformat()


def played(fid="fx1", hc=7, ac=4, days=2, league="eng-l1"):
    return {"fixture_id": fid, "league_id": league, "date": ago(days),
            "home_team_id": "t1", "away_team_id": "t2",
            "home_name": "Bradford", "away_name": "Barnsley",
            "home_corners": hc, "away_corners": ac,
            "total_corners": None if hc is None or ac is None else hc + ac,
            "corners_known": hc is not None and ac is not None}


def install(monkeypatch, *, fixtures=None, odds=None, markets=None):
    fixtures = fixtures if fixtures is not None else [played()]
    stored = odds if odds is not None else {"home_over_4.5": 1.80,
                                            "total_over_9.5": 2.10}
    monkeypatch.setattr(server, "db", FakeDB(
        fixtures,
        [{"fixture_id": f["fixture_id"], "odds": dict(stored), "source": "manual",
          "updated_at": NOW.isoformat()} for f in fixtures],
        [{"team_id": "t1", "real_matches": []}, {"team_id": "t2", "real_matches": []}],
        [{"league_id": "eng-l1", "name": "League One", "avg_shots": 11.0}]))
    ladder = markets if markets is not None else [
        {"key": "home_over_4.5", "group": "home", "group_label": "Home Team",
         "label": "Over 4.5", "line": 4.5, "book_odds": 1.80, "fair_odds": 1.47,
         "prob": 68.0, "ev": 22.4, "tier": "strong"},
        {"key": "total_over_9.5", "group": "total", "group_label": "Total",
         "label": "Over 9.5", "line": 9.5, "book_odds": 2.10, "fair_odds": 1.67,
         "prob": 60.0, "ev": 26.0, "tier": "strong"}]
    monkeypatch.setattr(server, "fixture_model_from",
                        lambda h, a, lg, o: {"markets": ladder,
                                             "confidence": {"score": 70, "label": "High"},
                                             "lambdas": {"total": 11.0, "home": 6.0,
                                                         "away": 5.0}})


def review(**kw):
    kw.setdefault("user", MEMBER)
    return run(server.price_review_board(**kw))


# --- the fixture stays up ---------------------------------------------------------------

def test_a_played_game_still_has_its_prices(monkeypatch):
    install(monkeypatch)
    out = review()
    # `games` is the list; `fixtures` is the tally's count. They collided once.
    assert out["fixtures"] == 1
    fx = out["games"][0]
    assert fx["home_name"] == "Bradford"
    assert fx["priced"] == 2
    assert fx["home_corners"] == 7 and fx["away_corners"] == 4


def test_the_ev_arrives_rather_than_being_swallowed(monkeypatch):
    # THE REGRESSION. The model call sits in a try/except so one bad fixture cannot take
    # the week down; a TypeError in the call itself therefore looked like a quiet week.
    install(monkeypatch)
    lines = review()["games"][0]["lines"]
    assert all(ln["ev"] is not None for ln in lines), lines
    assert {ln["ev"] for ln in lines} == {22.4, 26.0}


def test_each_line_is_settled_against_the_right_number(monkeypatch):
    install(monkeypatch)                      # 7-4: home 5+ yes, total 11 over 9.5 yes
    got = {ln["key"]: ln["result"] for ln in review()["games"][0]["lines"]}
    assert got["home_over_4.5"] == "won"
    assert got["total_over_9.5"] == "won"


def test_a_losing_line_is_reported_as_readily_as_a_winner(monkeypatch):
    install(monkeypatch, fixtures=[played(hc=2, ac=1)])
    got = {ln["key"]: ln["result"] for ln in review()["games"][0]["lines"]}
    assert got["home_over_4.5"] == "lost" and got["total_over_9.5"] == "lost"


def test_a_model_that_throws_leaves_the_fixture_gradeable(monkeypatch):
    install(monkeypatch)

    def boom(*a, **kw):
        raise ValueError("no history")
    monkeypatch.setattr(server, "fixture_model_from", boom)
    fx = review()["games"][0]
    assert fx["priced"] == 2                       # still settled
    assert all(ln["ev"] is None for ln in fx["lines"])   # just no opinion attached


# --- the week ----------------------------------------------------------------------------

def test_the_scoreboard_counts_the_ev_plus_lines(monkeypatch):
    install(monkeypatch, fixtures=[played("a", 7, 4), played("b", 1, 1)])
    out = review()
    assert out["graded"] == 2
    assert out["ev_plus"] == 4 and out["ev_plus_landed"] == 2
    assert out["ev_plus_rate"] == 50.0


def test_the_best_landed_are_ranked_by_edge(monkeypatch):
    install(monkeypatch, fixtures=[played("a", 9, 6)])
    best = review()["best"]
    assert [b["key"] for b in best] == ["total_over_9.5", "home_over_4.5"]


def test_a_game_awaiting_its_corner_count_is_not_a_loss(monkeypatch):
    install(monkeypatch, fixtures=[played("a", None, None)])
    out = review()
    assert out["awaiting_corners"] == 1 and out["graded"] == 0
    assert out["ev_plus_rate"] is None


def test_the_window_is_capped_by_what_the_store_keeps(monkeypatch):
    install(monkeypatch)
    assert review(days=9999)["days"] == server.PLAYED_KEEP_DAYS


def test_a_game_outside_the_window_is_not_reviewed(monkeypatch):
    install(monkeypatch, fixtures=[played("old", days=20)])
    assert review(days=7)["games"] == []


def test_a_league_filter_narrows_it(monkeypatch):
    install(monkeypatch, fixtures=[played("a"), played("b", league="esp-ll")])
    assert len(review(league_id="eng-l1")["games"]) == 1


def test_an_empty_week_answers_rather_than_breaking(monkeypatch):
    install(monkeypatch, fixtures=[])
    out = review()
    assert out["games"] == [] and out["best"] == [] and out["ev_plus_rate"] is None


# --- what the line did last time ----------------------------------------------------------

import pytest  # noqa: E402
from fastapi import HTTPException  # noqa: E402


def hist(monkeypatch, games):
    monkeypatch.setattr(server, "db", FakeDB(
        games,
        [{"fixture_id": g["fixture_id"], "odds": dict(g.pop("_odds", {})),
          "source": "manual", "updated_at": NOW.isoformat()} for g in games],
        [{"team_id": "t1", "real_matches": []}],
        [{"league_id": "eng-l1", "name": "League One"}]))


def line(**kw):
    kw.setdefault("user", MEMBER)
    return run(server.line_history(**kw))


def game(fid, hc, ac, days, price=None, home=True):
    g = played(fid, hc, ac, days)
    if not home:
        g["home_team_id"], g["away_team_id"] = "t2", "t1"
    g["_odds"] = {"home_over_4.5": price} if price else {}
    return g


def test_it_reports_the_last_time_that_exact_line_was_priced(monkeypatch):
    hist(monkeypatch, [game("g3", 7, 2, 3, price=1.62),
                       game("g2", 3, 5, 10, price=1.75)])
    out = line(team_id="t1", key="home_over_4.5")
    assert out["last"]["fixture_id"] == "g3"
    assert out["last"]["result"] == "won" and out["last"]["book_odds"] == 1.62
    assert out["found"] == 2 and out["landed"] == 1


def test_a_miss_is_reported_as_readily_as_a_win(monkeypatch):
    hist(monkeypatch, [game("g2", 3, 5, 10, price=1.75)])
    assert line(team_id="t1", key="home_over_4.5")["last"]["result"] == "lost"


def test_a_game_with_no_price_for_that_key_is_skipped(monkeypatch):
    # "It landed" with no price attached answers half the question.
    hist(monkeypatch, [game("g3", 9, 1, 3), game("g2", 6, 2, 10, price=1.75)])
    assert line(team_id="t1", key="home_over_4.5")["last"]["fixture_id"] == "g2"


def test_a_game_awaiting_its_corner_count_is_skipped(monkeypatch):
    hist(monkeypatch, [game("g3", None, None, 3, price=1.62),
                       game("g2", 6, 2, 10, price=1.75)])
    assert line(team_id="t1", key="home_over_4.5")["last"]["fixture_id"] == "g2"


def test_it_says_which_side_of_each_game_the_team_was_on(monkeypatch):
    # A run of home_over_4.5 results is a run of HOME games, and that should be visible.
    hist(monkeypatch, [game("g3", 7, 2, 3, price=1.62),
                       game("g2", 4, 6, 10, price=1.75, home=False)])
    sides = [g["was_home"] for g in line(team_id="t1", key="home_over_4.5")["games"]]
    assert sides == [True, False]


def test_a_team_with_no_priced_history_answers_emptily(monkeypatch):
    hist(monkeypatch, [game("g3", 7, 2, 3)])
    out = line(team_id="t1", key="home_over_4.5")
    assert out["last"] is None and out["games"] == [] and out["found"] == 0


def test_a_market_it_cannot_settle_is_refused_rather_than_answered_blank(monkeypatch):
    # An empty answer would read as "never landed", which is a claim about the team.
    hist(monkeypatch, [game("g3", 7, 2, 3, price=1.62)])
    with pytest.raises(HTTPException) as e:
        line(team_id="t1", key="first_half_over_3.5")
    assert e.value.status_code == 400


def test_the_prices_seen_are_collected_so_a_drift_is_visible(monkeypatch):
    hist(monkeypatch, [game("g3", 7, 2, 3, price=1.62),
                       game("g2", 6, 2, 10, price=1.75)])
    assert line(team_id="t1", key="home_over_4.5")["prices_seen"] == [1.62, 1.75]
