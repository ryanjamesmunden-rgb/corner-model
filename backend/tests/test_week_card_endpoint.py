"""/week-card: one London day, both sides of every game, the bet and the evidence.

The pure merge is tested in test_week_card.py. This is about the wiring: that the day
filter means a LONDON day, that both halves of a card get their own game-state verdict,
that the counts say what was left out, and that a day already played is an error rather
than an empty board.
"""
import asyncio
import os
import sys
from datetime import datetime, timedelta, timezone

import pytest

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "test_corner_model")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import server  # noqa: E402
from fastapi import HTTPException  # noqa: E402


class FakeCursor:
    def __init__(self, docs):
        self._docs = docs

    def sort(self, field, direction=1):
        present = [d for d in self._docs if d.get(field) is not None]
        missing = [d for d in self._docs if d.get(field) is None]
        present.sort(key=lambda d: d[field], reverse=direction < 0)
        self._docs = present + missing if direction < 0 else missing + present
        return self

    async def to_list(self, n):
        return self._docs[:n]


class FakeCollection:
    def __init__(self, docs, key):
        self._docs, self._key = docs, key

    def find(self, q=None, proj=None):
        docs = list(self._docs)
        ids = ((q or {}).get(self._key) or {}).get("$in") if q else None
        if ids is not None:
            docs = [d for d in docs if d[self._key] in ids]
        # HONOURED RATHER THAN IGNORED. The played-day query narrows on league_id in
        # Mongo, and a fake that drops the clause makes that filter untestable — the
        # test passes in the fake and the filter could be missing in the code.
        lid = (q or {}).get("league_id") if q else None
        if isinstance(lid, str):
            docs = [d for d in docs if d.get("league_id") == lid]
        date = (q or {}).get("date") if q else None
        if isinstance(date, dict):
            lo, hi = date.get("$gte"), date.get("$lte")
            if lo:
                docs = [d for d in docs if str(d.get("date") or "") >= lo]
            if hi:
                docs = [d for d in docs if str(d.get("date") or "") <= hi]
        return FakeCursor(docs)


class FakeDB:
    def __init__(self, odds, fixtures, teams, leagues, feed=None, played=None):
        self.odds = FakeCollection(odds, "fixture_id")
        self.odds_feed = FakeCollection(list(feed or []), "fixture_id")
        self.fixtures = FakeCollection(fixtures, "fixture_id")
        self.teams = FakeCollection(teams, "team_id")
        self.leagues = FakeCollection(leagues, "league_id")
        # The card reaches back as well as forward now; a day in the past is sourced
        # from here rather than from the upcoming list.
        self.fixtures_played = FakeCollection(list(played or []), "fixture_id")


MEMBER = {"member": True}
NOW = datetime.now(timezone.utc)


def run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def today_london():
    return server.local_day(NOW.isoformat())


# EVERY TEST FIXTURE IS TOMORROW'S GAME, not today's. A game at noon today has already
# kicked off whenever the suite runs after noon, and the board drops kicked-off rows —
# so a card built on today's date passed in the morning and failed in the afternoon.
DAY_OFFSET = 1


def the_day():
    return (datetime.fromisoformat(today_london())
            + timedelta(days=DAY_OFFSET)).date().isoformat()


def at_noon(day_offset=DAY_OFFSET):
    """Noon UTC on a day, which is the same London calendar day in either offset."""
    base = datetime.fromisoformat(today_london()) + timedelta(days=day_offset)
    return base.replace(hour=12, tzinfo=timezone.utc).isoformat().replace("+00:00", "Z")


def rung(group, line, ev, book, cred="credible"):
    return {"key": f"{group}_over_{line - 0.5}", "group": group, "group_label": group.title(),
            "label": f"Over {line - 0.5}", "line": line, "book_odds": book,
            "fair_odds": 1.6, "prob": 62.0, "ev": ev, "tier": "small",
            "credibility": cred}


def install(monkeypatch, *, ladder=None, fixtures=None, combined_rows=None, feed=None,
            with_odds=True, played=None):
    fixtures = fixtures if fixtures is not None else [
        {"fixture_id": "fx1", "league_id": "eng-l1", "date": at_noon(),
         "home_team_id": "t1", "away_team_id": "t2",
         "home_name": "Bradford", "away_name": "Barnsley", "round": "R18"}]
    monkeypatch.setattr(server, "db", FakeDB(
        [{"fixture_id": f["fixture_id"], "odds": {"home_over_4.5": 1.8},
          "source": "manual", "updated_at": NOW.isoformat()}
         for f in (fixtures if with_odds else [])],
        fixtures,
        [{"team_id": "t1", "real_matches": []}, {"team_id": "t2", "real_matches": []}],
        [{"league_id": "eng-l1", "name": "League One", "avg_shots": 11.0}],
        feed=feed, played=played))
    ladder = ladder if ladder is not None else [
        rung("home", 5, 9.0, 1.80), rung("home", 6, 25.0, 2.40),
        rung("away", 4, 2.0, 1.65), rung("total", 11, 5.0, 1.83)]
    monkeypatch.setattr(server, "fixture_model_from",
                        lambda h, a, lg, o: {"markets": ladder,
                                             "confidence": {"score": 70, "label": "High"},
                                             "lambdas": {"total": 10.4}})

    async def fake_combined(**kw):
        return list(combined_rows or [])
    monkeypatch.setattr(server, "_combined_rows", fake_combined)


def board(**kw):
    kw.setdefault("user", MEMBER)
    kw.setdefault("day", the_day())
    return run(server.week_card_board(**kw))


def streak_row(team_id="t1", fixture_id="fx1", line=5, hits=9, settled=10):
    return {"team_id": team_id, "name": "Bradford", "boards": ["streaks", "quick_scan"],
            "warnings": [], "next_fixture": {"fixture_id": fixture_id, "date": at_noon(),
                                             "opponent": "Barnsley", "is_home": True},
            "streak": {"side": "home", "line": line, "line_label": f"{line}+",
                       "hits": hits, "settled": settled, "floor": 4, "length": 6}}


# --- the day ------------------------------------------------------------------------

def test_no_day_means_today_in_london(monkeypatch):
    install(monkeypatch)
    assert run(server.week_card_board(user=MEMBER))["day"] == today_london()


def test_a_day_already_played_is_an_error_not_an_empty_board(monkeypatch):
    # An empty board reads as "nothing on". Asking for yesterday is a different thing.
    install(monkeypatch)
    with pytest.raises(HTTPException) as e:
        board(day="2020-01-01")
    assert e.value.status_code == 400


def test_a_day_past_the_horizon_says_so(monkeypatch):
    install(monkeypatch)
    far = (datetime.fromisoformat(today_london())
           + timedelta(days=server.WEEK_CARD_MAX_AHEAD + 1)).date().isoformat()
    with pytest.raises(HTTPException) as e:
        board(day=far)
    assert e.value.status_code == 400 and "days ahead" in e.value.detail


def test_a_day_that_is_not_a_date_is_refused(monkeypatch):
    install(monkeypatch)
    with pytest.raises(HTTPException) as e:
        board(day="saturday")
    assert e.value.status_code == 400


def test_another_days_game_is_not_on_this_days_card(monkeypatch):
    install(monkeypatch, fixtures=[
        {"fixture_id": "wanted", "league_id": "eng-l1", "date": at_noon(DAY_OFFSET),
         "home_team_id": "t1", "away_team_id": "t2",
         "home_name": "Bradford", "away_name": "Barnsley"},
        {"fixture_id": "the-day-after", "league_id": "eng-l1",
         "date": at_noon(DAY_OFFSET + 1),
         "home_team_id": "t1", "away_team_id": "t2",
         "home_name": "Reading", "away_name": "Wrexham"}])
    assert [c["fixture_id"] for c in board()["cards"]] == ["wanted"]


# --- the card -----------------------------------------------------------------------

def test_a_card_carries_both_sides_and_the_match_line(monkeypatch):
    install(monkeypatch)
    card = board()["cards"][0]
    assert card["home"]["name"] == "Bradford" and card["away"]["name"] == "Barnsley"
    assert card["away"]["pick"]["line"] == 4
    assert card["total"]["line"] == 11
    assert card["league_name"] == "League One"


def test_the_run_pulls_the_pick_onto_its_own_line(monkeypatch):
    # 6+ pays more (+25% against +9%), but the run is a 5+ run, so 5+ is the bet and the
    # 9/10 beside it is a record of that bet.
    install(monkeypatch, combined_rows=[streak_row(line=5)])
    card = board()["cards"][0]
    assert card["home"]["pick"]["line"] == 5
    assert card["home"]["run"]["hits"] == 9
    assert card["home"]["run_matches_pick"] is True


def test_without_a_run_the_best_credible_rung_leads(monkeypatch):
    install(monkeypatch)
    assert board()["cards"][0]["home"]["pick"]["line"] == 6


def test_both_sides_get_their_own_game_state_verdict(monkeypatch):
    # The value board asks for one side, because it shows one line. A card shows two.
    install(monkeypatch)
    seen = []

    def fake_state(best, home, away, lg, match_odds=None):
        seen.append(best.get("group"))
        return {"verdict": "chase_spot" if best.get("group") == "away" else "caution",
                "flags": [], "reasons": [], "measured": False}
    monkeypatch.setattr(server, "_game_state_for", fake_state)
    card = board()["cards"][0]
    assert sorted(set(seen)) == ["away", "home"]
    assert card["home"]["game_state"]["verdict"] == "caution"
    assert card["away"]["game_state"]["verdict"] == "chase_spot"


def test_the_rows_own_verdict_is_reused_rather_than_recomputed(monkeypatch):
    # value_board already worked one out, for the side its headline line is on. Asking
    # again walks the same forty matches twice per card.
    install(monkeypatch)
    calls = []

    def fake_state(best, home, away, lg, match_odds=None):
        calls.append(best.get("group"))
        return {"verdict": "neutral", "flags": [], "reasons": [], "measured": False}
    monkeypatch.setattr(server, "_game_state_for", fake_state)
    board()
    # Once inside value_board for the headline side, once here for the other one.
    assert len(calls) == 2


def test_the_match_winner_price_reaches_the_verdict(monkeypatch):
    # game_state uses how short the OPPONENT is; it lives on the feed document.
    install(monkeypatch,
            feed=[{"fixture_id": "fx1", "match_odds": {"home": 0.62, "away": 0.21}}])
    got = {}

    def fake_state(best, home, away, lg, match_odds=None):
        got[best.get("group")] = match_odds
        return None
    monkeypatch.setattr(server, "_game_state_for", fake_state)
    board()
    assert got["home"] == {"home": 0.62, "away": 0.21}


# --- what was left out ---------------------------------------------------------------

def test_a_filtered_board_says_how_many_it_considered(monkeypatch):
    # A short list after a filter and a quiet day look identical otherwise.
    install(monkeypatch, combined_rows=[streak_row(hits=4, settled=10)])
    out = board(min_run=8)
    assert out["considered"] == 1 and out["fixtures"] == 0


def test_min_run_keeps_a_card_whose_run_clears_it(monkeypatch):
    install(monkeypatch, combined_rows=[streak_row(hits=9, settled=10)])
    assert board(min_run=8)["fixtures"] == 1


def test_a_game_with_a_run_and_no_price_is_still_on_the_card(monkeypatch):
    # THE RESEARCH LIST. value_board walks stored prices, so a fixture nobody has quoted
    # produces no row at all — and those are exactly the games you sit down to look up.
    install(monkeypatch, ladder=[], combined_rows=[streak_row()])
    out = board()
    assert out["fixtures"] == 1
    card = out["cards"][0]
    assert card["status"] == "no_price"
    assert card["home"]["run"]["hits"] == 9
    assert card["league_name"] == "League One"


def test_an_unpriced_game_still_gets_the_models_own_line(monkeypatch):
    # "No line" is not the answer to "what is the bet on this game". The model needs the
    # two sides and the league, not a book price, so the research card carries a fair
    # price — and nothing on it can be mistaken for a price somebody is offering.
    install(monkeypatch, with_odds=False, combined_rows=[streak_row(line=5)])
    monkeypatch.setattr(server, "fixture_model_from",
                        lambda h, a, lg, o: {"markets": [
                            {**rung("home", 5, None, None), "group_label": "Bradford",
                             "label": "Over 4.5", "fair_odds": 1.58, "prob": 63.0}],
                            "confidence": {"score": 55, "label": "Fair"},
                            "lambdas": {"total": 9.9}})
    card = board()["cards"][0]
    assert card["status"] == "no_price"
    assert card["home"]["pick"]["fair_odds"] == 1.58
    assert card["home"]["pick"]["book_odds"] is None
    assert card["home"]["pick"]["ev"] is None
    assert card["home"]["run_matches_pick"] is True


def test_a_model_that_cannot_price_a_game_does_not_take_the_day_down(monkeypatch):
    # No stored odds at all, so the game reaches the card only through the research
    # list — and the model is the only thing that could price it.
    install(monkeypatch, with_odds=False, combined_rows=[streak_row()])

    def boom(*a, **kw):
        raise ValueError("no history")
    monkeypatch.setattr(server, "fixture_model_from", boom)
    out = board()
    assert out["fixtures"] == 1
    assert out["cards"][0]["home"]["pick"] is None


def test_a_game_with_neither_a_price_nor_a_run_never_appears(monkeypatch):
    # What keeps a 118-game Saturday down to a card.
    install(monkeypatch, ladder=[], combined_rows=[])
    assert board()["fixtures"] == 0


def test_priced_only_drops_a_card_nobody_has_quoted(monkeypatch):
    install(monkeypatch, ladder=[], combined_rows=[streak_row()])
    assert board()["fixtures"] == 1
    assert board(priced_only=True)["fixtures"] == 0


def test_with_runs_counts_the_cards_that_have_evidence(monkeypatch):
    install(monkeypatch, combined_rows=[streak_row()])
    out = board()
    assert out["with_runs"] == 1 and out["fixtures"] == 1


def test_a_run_from_a_different_fixture_does_not_attach(monkeypatch):
    install(monkeypatch, combined_rows=[streak_row(fixture_id="some-other-game")])
    assert board()["cards"][0]["home"]["run"] is None


# --- route order ----------------------------------------------------------------------

def test_a_literal_fixtures_route_is_registered_before_the_parameterised_one():
    """/api/fixtures/played must not resolve as fixture_id="played".

    FastAPI matches in registration order. With /fixtures/{fixture_id} first, the played
    endpoint answered 404 "Fixture not found" in production — unreachable, and the 404
    read like a bad id rather than a route that could never be hit. This pins the order so
    the next literal /fixtures/<word> route cannot reintroduce it silently.
    """
    paths = [r.path for r in server.app.routes
             if getattr(r, "path", "").startswith("/api/fixtures")]
    assert "/api/fixtures/played" in paths
    assert paths.index("/api/fixtures/played") < paths.index("/api/fixtures/{fixture_id}")


# --- a day that has been played ---------------------------------------------------------
#
# The card used to be a forecast that vanished at kick-off, and asking for yesterday was a
# 400. The day you most want to look at a card is the day after it: the same games, the
# same lines, the same prices, with the corner count beside each one.

def played_fx(fid="pf1", hc=7, ac=4, day_offset=-1, league="eng-l1", goals=(2, 1)):
    base = datetime.fromisoformat(today_london()) + timedelta(days=day_offset)
    return {"fixture_id": fid, "league_id": league,
            "date": base.replace(hour=15, tzinfo=timezone.utc).isoformat().replace("+00:00", "Z"),
            "home_team_id": "t1", "away_team_id": "t2",
            "home_name": "Bradford", "away_name": "Barnsley",
            "home_goals": goals[0], "away_goals": goals[1],
            "home_corners": hc, "away_corners": ac,
            "total_corners": None if hc is None else hc + ac,
            "corners_known": hc is not None, "finished_as": "FT"}


def yesterday():
    return (datetime.fromisoformat(today_london()) - timedelta(days=1)).date().isoformat()


def test_yesterday_is_a_card_rather_than_an_error(monkeypatch):
    install(monkeypatch, played=[played_fx()])
    out = board(day=yesterday())
    assert out["fixtures"] == 1 and out["played"] == 1


def test_the_card_carries_the_final_score_and_the_corner_count(monkeypatch):
    install(monkeypatch, played=[played_fx(hc=7, ac=4)])
    card = board(day=yesterday())["cards"][0]
    assert card["result"]["home_goals"] == 2 and card["result"]["away_goals"] == 1
    assert card["result"]["home_corners"] == 7 and card["result"]["away_corners"] == 4
    assert card["result"]["total_corners"] == 11
    assert card["result"]["finished_as"] == "FT"


def test_each_pick_is_settled_against_what_happened(monkeypatch):
    # The stubbed ladder is home_over_4.5, away_over_3.5 and total_over_10.5, so 7-4
    # lands all three. The point is that each is settled against ITS OWN number — the
    # home count, the away count and the total — not against the same one three times.
    install(monkeypatch, played=[played_fx(hc=7, ac=4)])
    card = board(day=yesterday())["cards"][0]
    assert card["home"]["pick"]["result"] == "won" and card["home"]["pick"]["actual"] == 7
    assert card["away"]["pick"]["result"] == "won" and card["away"]["pick"]["actual"] == 4
    assert card["total"]["result"] == "won" and card["total"]["actual"] == 11
    assert card["settled"] == 3 and card["landed"] == 3


def test_a_pick_that_missed_is_reported_as_readily(monkeypatch):
    install(monkeypatch, played=[played_fx(hc=1, ac=1)])
    card = board(day=yesterday())["cards"][0]
    assert card["home"]["pick"]["result"] == "lost"
    assert card["away"]["pick"]["result"] == "lost"
    assert card["landed"] == 0 and card["settled"] == 3


def test_the_day_reports_its_own_score(monkeypatch):
    install(monkeypatch, played=[played_fx("a", 7, 4), played_fx("b", 1, 1)])
    out = board(day=yesterday())
    assert out["played"] == 2
    # 7-4 lands all three; 1-1 lands none.
    assert out["picks_settled"] == 6 and out["picks_landed"] == 3


def test_a_game_whose_statistics_never_arrived_is_not_a_loss(monkeypatch):
    # 0-0 corners is a real result; "nobody fetched it" is not, and they must not render
    # the same way or settle the same way.
    install(monkeypatch, played=[played_fx(hc=None, ac=None)])
    card = board(day=yesterday())["cards"][0]
    assert card["result"]["corners_known"] is False
    assert card.get("settled") in (0, None)
    assert card["home"]["pick"].get("result") is None


def test_an_upcoming_card_carries_no_result_at_all(monkeypatch):
    install(monkeypatch)
    card = board()["cards"][0]
    assert card["result"] is None
    assert card.get("settled") in (0, None)


def test_a_day_further_back_than_the_results_are_kept_says_so(monkeypatch):
    install(monkeypatch)
    far = (datetime.fromisoformat(today_london())
           - timedelta(days=server.PLAYED_KEEP_DAYS + 2)).date().isoformat()
    with pytest.raises(HTTPException) as e:
        board(day=far)
    assert e.value.status_code == 400 and "kept" in e.value.detail


def test_a_played_game_is_not_listed_twice(monkeypatch):
    # A fixture can sit in both stores around kick-off; the upcoming row wins.
    install(monkeypatch, played=[played_fx("fx1")])
    out = board()
    assert [c["fixture_id"] for c in out["cards"]].count("fx1") == 1


def test_another_days_result_is_not_on_this_card(monkeypatch):
    install(monkeypatch, played=[played_fx("a", day_offset=-1),
                                 played_fx("b", day_offset=-3)])
    assert [c["fixture_id"] for c in board(day=yesterday())["cards"]] == ["a"]


def test_a_league_filter_still_narrows_a_played_day(monkeypatch):
    install(monkeypatch, played=[played_fx("a"), played_fx("b", league="esp-ll")])
    assert len(board(day=yesterday(), league_id="eng-l1")["cards"]) == 1


def test_a_model_that_cannot_price_a_played_game_still_shows_the_result(monkeypatch):
    # No stored odds, so the value board has nothing to price and the played path is the
    # only caller of the model. (value_board builds its model before the day filter and
    # has no guard of its own — that is its behaviour, not this one's.)
    install(monkeypatch, with_odds=False, played=[played_fx()])

    def boom(*a, **kw):
        raise ValueError("no history")
    monkeypatch.setattr(server, "fixture_model_from", boom)
    card = board(day=yesterday())["cards"][0]
    assert card["result"]["home_corners"] == 7       # the score survives
    assert card["home"]["pick"] is None              # just nothing to settle
