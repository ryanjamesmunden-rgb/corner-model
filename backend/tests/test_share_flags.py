"""Every league the app syncs has a flag for the share buttons.

The flags live in frontend/src/lib/countryFlag.js, keyed by the three-letter country
prefix of the league id. Adding a league to LEAGUE_META and forgetting the flag is
silent — the row still shares, it just goes out with a bare bullet while every other
line carries a country. This is the only place the two sides can be checked together."""
import os
import re
import sys

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "test_corner_model")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from leagues_meta import LEAGUE_META  # noqa: E402

FLAGS_JS = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))), "frontend", "src", "lib", "countryFlag.js")


def _prefixes_with_a_flag():
    """The keys of the CODES map in the JS file."""
    src = open(FLAGS_JS, encoding="utf-8").read()
    body = src[src.index("const CODES = {"):]
    body = body[:body.index("};")]
    return {m.group(1) for m in re.finditer(r"^\s{2}(\w{3}):", body, re.M)}


def test_every_synced_league_has_a_country_flag():
    flagged = _prefixes_with_a_flag()
    missing = sorted({lid.split("-")[0] for lid in LEAGUE_META} - flagged)
    assert not missing, (f"no flag for {missing} — add the country to CODES in "
                         f"frontend/src/lib/countryFlag.js")


def test_league_ids_start_with_a_country_prefix():
    """The flag lookup slices the first three characters, so the shape has to hold."""
    for lid in LEAGUE_META:
        assert re.match(r"^[a-z]{3}-", lid), lid
