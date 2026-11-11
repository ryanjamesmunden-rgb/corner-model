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


# --- /team-form: several teams at once for the multi-line page -------------------------
import asyncio  # noqa: E402

import pytest  # noqa: E402
from fastapi import HTTPException  # noqa: E402


class _Coll:
    def __init__(self, rows=None):
        self.rows = list(rows or [])

    @staticmethod
    def _match(r, q):
        for k, v in q.items():
            if isinstance(v, dict) and "$in" in v:
                if r.get(k) not in v["$in"]:
                    return False
            elif r.get(k) != v:
                return False
        return True

    def find(self, q, *a, **k):
        hits = [dict(r) for r in self.rows if self._match(r, q)]

        class C:
            async def to_list(self, n): return hits[:n]
        return C()


def _team(tid, lid, wons):
    return {"team_id": tid, "league_id": lid, "name": tid.upper(),
            "real_matches": [_m(f"2026-09-{i + 1:02d}", w) for i, w in enumerate(wons)]}


@pytest.fixture
def form_db(monkeypatch):
    monkeypatch.setattr(server.db, "teams", _Coll([
        _team("a", "nl2", [3, 3]), _team("b", "nl2", [8, 8]), _team("c", "eng", [5]),
        {"team_id": "empty", "league_id": "nl2", "name": "E", "real_matches": []}]))
    monkeypatch.setattr(server.db, "leagues", _Coll([{"league_id": "nl2", "name": "Eerste"}]))
    monkeypatch.setattr(server.db, "favourite_teams", _Coll([
        {"user_id": "u1", "team_id": "c", "created_at": "2026-01-02"},
        {"user_id": "u1", "team_id": "a", "created_at": "2026-01-01"},
        {"user_id": "u2", "team_id": "b", "created_at": "2026-01-01"}]))
    monkeypatch.setattr(server.db, "tracked_teams", _Coll([
        {"user_id": "u1", "team_id": "b", "created_at": "2026-10-01"},
        {"user_id": "u1", "team_id": "c", "created_at": "2026-11-01"},
        {"user_id": "u2", "team_id": "a", "created_at": "2026-10-01"}]))


def _go(**k):
    return asyncio.new_event_loop().run_until_complete(server.multi_team_form(**k))


U1 = {"user_id": "u1"}
GUEST = {"user_id": server.PUBLIC_USER_ID}


def test_favourites_are_mine_only_oldest_follow_first(form_db):
    out = _go(source="favourites", league_id=None, user=U1)
    assert [t["team_id"] for t in out["teams"]] == ["a", "c"]


def test_tracking_is_my_own_trial_list_with_when_it_started(form_db):
    out = _go(source="tracking", league_id=None, user=U1)
    assert [t["team_id"] for t in out["teams"]] == ["b", "c"]
    assert out["teams"][0]["tracked_at"] == "2026-10-01"


def test_league_is_every_team_with_games_best_corner_side_first(form_db):
    out = _go(source="league", league_id="nl2", user=GUEST)
    assert [t["team_id"] for t in out["teams"]] == ["b", "a"]
    assert out["teams"][0]["league_name"] == "Eerste"


def test_signed_out_gets_an_empty_list_not_an_error(form_db):
    out = _go(source="favourites", league_id=None, user=GUEST)
    assert out["teams"] == [] and out["signed_in"] is False


def test_bad_source_and_missing_league_are_refused(form_db):
    with pytest.raises(HTTPException):
        _go(source="nope", league_id=None, user=U1)
    with pytest.raises(HTTPException):
        _go(source="league", league_id=None, user=U1)


class _WColl(_Coll):
    async def find_one(self, q, *a, **k):
        return next((r for r in self.rows if self._match(r, q)), None)

    async def update_one(self, q, upd, upsert=False, **k):
        if not any(self._match(r, q) for r in self.rows) and upsert:
            self.rows.append({**q, **upd.get("$setOnInsert", {})})

    async def delete_one(self, q):
        self.rows = [r for r in self.rows if not self._match(r, q)]


def test_track_is_idempotent_and_promote_moves_it_to_favourites(monkeypatch):
    teams, tracked, favs = _WColl([{"team_id": "a"}]), _WColl(), _WColl()
    monkeypatch.setattr(server.db, "teams", teams)
    monkeypatch.setattr(server.db, "tracked_teams", tracked)
    monkeypatch.setattr(server.db, "favourite_teams", favs)
    run = lambda c: asyncio.new_event_loop().run_until_complete(c)  # noqa: E731
    run(server.add_tracked_team("a", U1))
    run(server.add_tracked_team("a", U1))
    assert len(tracked.rows) == 1
    run(server.promote_tracked_team("a", U1))
    assert tracked.rows == [] and [r["team_id"] for r in favs.rows] == ["a"]
    with pytest.raises(HTTPException):
        run(server.add_tracked_team("ghost", U1))
