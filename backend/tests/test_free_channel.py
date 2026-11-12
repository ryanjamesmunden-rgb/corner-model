"""The free channel: every EV+ bet at 1.60 or more, staked by the edge, settled in public.

Driven through the real endpoints with a fake db and a fake Telegram, so the send, the
record it writes and the results post that reads it back are tested as one loop.
"""
import asyncio
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "test_corner_model")

import server  # noqa: E402
import telegram_bot  # noqa: E402


def run(coro):
    # Not asyncio.run: it clears the thread's event loop on exit, which breaks later
    # tests in the same worker that call asyncio.get_event_loop().
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


class Cursor:
    def __init__(self, docs):
        self.docs = docs

    async def to_list(self, n):
        return list(self.docs)[:n]


def _match(doc, q):
    for k, v in (q or {}).items():
        if isinstance(v, dict) and "$in" in v:
            if doc.get(k) not in v["$in"]:
                return False
        elif doc.get(k) != v:
            return False
    return True


class Coll:
    def __init__(self, docs=None):
        self.docs = {d.get("_id", i): d for i, d in enumerate(docs or [])}

    def find(self, q=None, proj=None):
        return Cursor([{k: v for k, v in d.items() if k != "_id" or not proj}
                       for d in self.docs.values() if _match(d, q)])

    async def update_one(self, q, upd, upsert=False):
        _id = q["_id"]
        d = self.docs.get(_id)
        if d is None:
            d = {"_id": _id, **upd.get("$setOnInsert", {})}
            self.docs[_id] = d
        d.update(upd.get("$set", {}))


class DB:
    def __init__(self, teams):
        self.bot_value_sent = Coll()
        self.free_picks = Coll()
        self.teams = Coll(teams)


def rung(group, line, odds, ev):
    return {"group": group, "key": f"{group}_over_{line}", "line": line,
            "book_odds": odds, "fair_odds": round(odds / (1 + ev / 100), 2),
            "prob": 60.0, "ev": ev}


LADDER = [rung("home", 3.5, 1.45, 8.0),    # under 1.60: never sent
          rung("home", 4.5, 1.70, 7.0),    # THE free line
          rung("home", 5.5, 2.40, 12.0),   # longer, bigger EV: not a second bet
          rung("home", 7.5, 10.0, 30.0)]

BOARD = [{"status": "ok", "fixture_id": "fx1", "home_name": "Reading",
          "away_name": "Hull", "home_team_id": "rea", "away_team_id": "hul",
          "league_id": "eng-l1", "league_name": "League One",
          "date": "2026-11-11T19:45:00+00:00", "odds_source": "api",
          "best": LADDER[3], "alternatives": LADDER[:3], "ladder": LADDER}]


@pytest.fixture
def env(monkeypatch):
    teams = [{"_id": "rea", "team_id": "rea", "real_matches": [
        {"opponent": "Hull", "date": "2026-11-11", "corners_for": 6, "corners_against": 3}]}]
    fake = DB(teams)
    sent = []

    async def board(**kw):
        return BOARD

    async def send(chat, text):
        sent.append((chat, text))
        return True

    monkeypatch.setattr(server, "db", fake)
    monkeypatch.setattr(server, "value_board", board)
    monkeypatch.setattr(server, "_check_tools_token", lambda token: None)
    monkeypatch.setattr(telegram_bot, "send", send)
    monkeypatch.setattr(telegram_bot, "FREE_CHAT_ID", "-100free")
    return fake, sent


def test_free_send_posts_the_lowest_line_at_1_60_with_a_stake(env):
    fake, sent = env
    out = run(server.telegram_value(token="t", to="free"))
    assert out["sent"] and sent[0][0] == "-100free"
    text = sent[0][1]
    assert "Reading 5+ @ 1.70" in text and "💸 suggested stake 1.25u" in text
    assert "1u = 1% of your betting bank" in text
    assert "4+" not in text and "6+" not in text and "8+" not in text
    assert list(fake.free_picks.docs) == ["fx1:home_over_4.5"]
    assert list(fake.bot_value_sent.docs) == ["free:fx1:home_over_4.5"]


def test_the_free_channel_does_not_repeat_itself(env):
    fake, sent = env
    run(server.telegram_value(token="t", to="free"))
    out = run(server.telegram_value(token="t", to="free"))
    assert len(sent) == 1 and out["new"] == 0


def test_a_send_to_the_owner_does_not_silence_the_free_channel(env, monkeypatch):
    fake, sent = env
    monkeypatch.setattr(telegram_bot, "OWNER_CHAT_ID", "-1owner")
    run(server.telegram_value(token="t", to="owner"))
    run(server.telegram_value(token="t", to="free"))
    assert [c for c, _ in sent] == ["-1owner", "-100free"]


def test_results_settle_from_corners_and_post_the_running_total(env):
    fake, sent = env
    run(server.telegram_value(token="t", to="free"))
    out = run(server.telegram_free_results(token="t", day="2026-11-11"))
    assert out["sent"] and out["bets"] == 1
    text = sent[-1][1]
    assert "✅ Reading 5+ team @ 1.70: +0.88u" in text
    assert "1W-0L" in text
    assert out["all_time"]["units"] == pytest.approx(0.875, abs=0.01)
    assert out["all_time"]["roi"] == pytest.approx(70.0, abs=0.5)


def test_a_day_with_no_bets_posts_nothing(env):
    fake, sent = env
    out = run(server.telegram_free_results(token="t", day="2026-11-01"))
    assert out["sent"] is False and sent == []


def test_an_unknown_destination_is_refused(env):
    with pytest.raises(server.HTTPException):
        run(server.telegram_value(token="t", to="everyone"))


def test_the_channel_can_be_set_without_typing_the_at():
    ref = telegram_bot._chat_ref
    assert ref("TCMevPLUS") == "@TCMevPLUS"
    assert ref("@TCMevPLUS") == "@TCMevPLUS"
    assert ref("https://t.me/TCMevPLUS") == "@TCMevPLUS"
    assert ref("t.me/TCMevPLUS/") == "@TCMevPLUS"
    assert ref(" -1001234567890 ") == "-1001234567890"
    assert ref("987654321") == "987654321"
    assert ref("") == ""
