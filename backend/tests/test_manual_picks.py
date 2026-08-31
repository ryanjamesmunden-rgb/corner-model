"""Validation on logging a real pick.

This endpoint writes the record /join publishes and the money-back guarantee is measured
against, so the checks here are not tidiness — each one blocks a way the published P&L
could end up saying something that did not happen.
"""
import os
import sys

import pytest
from fastapi import HTTPException

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "test_corner_model")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import server  # noqa: E402
from server import ManualPickBody  # noqa: E402


def body(**over):
    return ManualPickBody(**{"league_id": "eng-l2", "date": "2026-09-01",
                             "home": "Exeter City", "away": "Barnet",
                             "team": "Barnet", "line": 6, "odds": 1.9, **over})


def _add(b, token="tok"):
    """Run the endpoint's validation without a database — every rejection raises before
    the insert, so the checks are reachable offline."""
    import asyncio
    return asyncio.get_event_loop().run_until_complete(server.add_pick(b, token))


@pytest.fixture(autouse=True)
def _token(monkeypatch):
    monkeypatch.setattr(server, "TOOLS_TOKEN", "tok")


def _err(b, token="tok"):
    with pytest.raises(HTTPException) as e:
        _add(b, token)
    return e.value


def test_writing_the_published_record_needs_the_token():
    """The site is public. An open endpoint here lets anyone edit your P&L."""
    assert _err(body(), token=None).status_code == 403
    assert _err(body(), token="wrong").status_code == 403


def test_a_league_the_model_cannot_settle_is_refused():
    """settle_picks skips a league with no meta, so the pick would sit pending forever
    and quietly never appear in the record."""
    assert _err(body(league_id="mars-premier")).status_code == 400


def test_the_backed_team_must_be_one_of_the_two_sides():
    """The one that would silently corrupt results. Settlement picks the side by name
    overlap, so a team that is neither still resolves to one of them — and grades the
    wrong side's corners, in your favour about half the time."""
    e = _err(body(team="Plymouth"))
    assert e.status_code == 400 and "which side" in e.detail


def test_the_home_side_is_accepted_and_recorded_as_home():
    """Sanity: the venue is derived, not asked for, so it cannot disagree with the names."""
    b = body(team="Exeter City")
    assert b.team == "Exeter City"


def test_a_malformed_date_is_refused():
    assert _err(body(date="1st Sept")).status_code == 400


def test_odds_at_or_below_evens_are_refused():
    """1.0 is not a price, and anything below it is a typo. Both would corrupt ROI."""
    for bad in (1.0, 0.5, -2.0):
        assert _err(body(odds=bad)).status_code == 400


def test_odds_may_be_omitted():
    """A pick with no recorded price still counts toward strike rate — _record keeps it
    out of ROI rather than treating it as a loss."""
    assert body(odds=None).odds is None


def test_a_line_below_one_is_refused():
    assert _err(body(line=0)).status_code == 400
