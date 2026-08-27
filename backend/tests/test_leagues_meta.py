"""The league list is shared, not copied.

server.py deletes any league in the DB that is not in MANAGED_LEAGUE_IDS, on every boot.
When that set was a hand-typed duplicate of sync_real's LEAGUE_META, adding a league to
the sync alone meant its data was wiped on restart — silently, and looking exactly like
"that league just never appears". These pin that the two can no longer drift apart."""
import os
import sys

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "test_corner_model")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from leagues_meta import LEAGUE_META, MANAGED_LEAGUE_IDS  # noqa: E402
from server import MANAGED_LEAGUE_IDS as SERVER_IDS  # noqa: E402


def test_managed_ids_are_derived_from_the_league_list():
    assert MANAGED_LEAGUE_IDS == set(LEAGUE_META)


def test_the_server_uses_that_same_set():
    """If this ever fails, boot cleanup is deleting leagues the sync is populating."""
    assert SERVER_IDS == set(LEAGUE_META)


def test_every_league_has_the_fields_the_sync_reads():
    for lid, meta in LEAGUE_META.items():
        assert isinstance(meta.get("api"), int), lid
        assert meta.get("name") and meta.get("country"), lid


def test_api_ids_are_unique():
    """Two keys sharing an id would sync the same competition twice under two names."""
    ids = [m["api"] for m in LEAGUE_META.values()]
    assert len(ids) == len(set(ids)), [i for i in ids if ids.count(i) > 1]


def test_league_keys_are_url_safe():
    """They travel as league_id path/query params."""
    for lid in LEAGUE_META:
        assert lid == lid.strip().lower()
        assert all(c.isalnum() or c == "-" for c in lid), lid


def test_norway_carries_only_the_confirmed_tiers():
    """103 and 104 are confirmed by probe_leagues.py against live data.

    105 was added as "2. divisjon" from memory and the probe returned MISMATCH — it is
    not the Norwegian third tier. It stays OUT until the country listing names the real
    id: shipping a wrong one would sync some other competition under a Norwegian label,
    and nothing downstream would ever flag it."""
    nor = {k: v for k, v in LEAGUE_META.items() if v["country"] == "Norway"}
    assert set(nor) == {"nor-el", "nor-d1"}
    assert [nor[k]["api"] for k in ("nor-el", "nor-d1")] == [103, 104]
    assert 105 not in {m["api"] for m in LEAGUE_META.values()}
