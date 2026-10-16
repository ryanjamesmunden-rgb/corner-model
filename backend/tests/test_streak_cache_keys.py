"""The streak board's cache has to cover the requests that are actually made.

THE BUG THIS PINS. The screen was built with side="home" and the guard demanded
side="home", so the Streaks page's first paint was instant — it opens on Home — and
tapping Away or Overall fell through to a full walk of every team with nothing in the
response to say so. Worse, the endpoint's own signature defaults to side="overall", so
the plainest call anyone could make, /api/streaks with no arguments, took the slowest
path available. A probe hunting a production outage spent sixty seconds on exactly that
while a fresh cache of the same board sat unused.

Nothing failed when that was true, which is why it survived: a cache miss is not an
error, it is just slow, and slow only becomes visible when the database is having a bad
day. So the invariants get asserted instead.
"""
import inspect
import os
import sys

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "test_corner_model")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import server  # noqa: E402


class TestEveryVenueIsCached:
    def test_all_three_tabs_have_a_screen(self):
        # All three are one tap apart on the page, so one being fast and two slow is the
        # arrangement most likely to be mistaken for the site being broken.
        assert set(server.STREAK_SCREENS) == {"home", "away", "overall"}

    def test_each_screen_is_registered_and_buildable(self):
        for name in server.STREAK_SCREENS.values():
            assert name in server.SCREENS, f"{name} is not in SCREENS"
            assert callable(server.SCREENS[name])

    def test_the_names_are_distinct(self):
        # Two sides pointing at one screen would serve home's rows under away's heading —
        # true numbers about the wrong games, which is worse than being slow.
        names = list(server.STREAK_SCREENS.values())
        assert len(names) == len(set(names))

    def test_home_keeps_its_original_screen_name(self):
        # /api/health reports screens_fresh keyed on these, and the existing one is
        # "streaks". Renaming it would silently change that payload for anything reading
        # it, for no gain.
        assert server.STREAK_SCREENS["home"] == "streaks"


class TestTheDefaultRequestIsTheFastOne:
    def test_the_endpoint_default_side_is_a_cached_side(self):
        """THE BUG, STATED. `streaks(side="overall")` is the signature and the cache held
        only "home", so the plainest possible call took the slowest possible path."""
        default = inspect.signature(server.streaks).parameters["side"].default
        assert default in server.STREAK_SCREENS, (
            f"the endpoint defaults to side={default!r}, which has no cached screen — a "
            "bare /api/streaks call would recompute the whole board")

    def test_the_other_guard_defaults_match_what_the_screen_builds(self):
        """Every other condition on the cache guard has to agree with the arguments the
        screen is built with, or the guard admits a request the cache cannot answer.

        Checked against the SIGNATURE rather than repeated as literals: if someone
        changes a default here, this notices, which is the whole point.
        """
        p = inspect.signature(server.streaks).parameters
        assert p["window"].default == 5
        assert p["min_hits"].default == 5
        assert p["min_line"].default == 3
        assert p["direction"].default == "over"
        assert p["subject"].default == "team"
        assert p["threshold"].default is None
        assert p["within_days"].default is None
        assert p["max_line"].default is None
        assert p["min_streak"].default == server.MIN_STREAK_LEN


class TestTheFrontDoorIsCachedToo:
    def test_browse_has_a_screen(self):
        # The home page went a week rebuilding every board on every visit because it was
        # the one heavy endpoint nobody had registered.
        assert "browse" in server.SCREENS

    def test_browse_guard_defaults_match_the_screen(self):
        # _screen_browse builds days=7, show="all", day=None, min_run=PANEL_MIN_RUN, and
        # the guard admits exactly that. A default drifting from the built payload is a
        # miss on every single request.
        p = inspect.signature(server.browse).parameters
        assert p["days"].default == 7
        assert p["show"].default == "all"
        assert p["day"].default is None
        assert p["min_run"].default == server.PANEL_MIN_RUN
