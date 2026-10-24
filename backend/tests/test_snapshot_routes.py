"""Every snapshot endpoint is wired to the function that actually snapshots.

WHY THIS FILE EXISTS. `@api_router.post("/projections/snapshot")` spent eleven days
attached to `_threshold_probs`, a pure helper that happened to be defined directly
beneath it — inserted there by a later change, which left `snapshot_projections` with no
decorator at all. The route still existed, so nothing 404'd and no import failed.

AND IT DID NOT EVEN RETURN AN ERROR, which is why it lasted. The helper's three
parameters carry no type annotations, so FastAPI took them for OPTIONAL query strings:
the sync's POST matched the route, every argument defaulted to None, both loops inside
skipped, and the endpoint answered HTTP 200 with `{}`. The workflow read no `status`
field, fell through to its catch-all, and logged a warning inside a green run. Eleven
days of projections can never be graded, because a projection recomputed after the games
is a projection made with the benefit of the result.

A test that posts to the route and asserts on the response would not have caught it
either — 200 is 200. So these assert the IDENTITY of the handler each path resolves to,
and that each one reads the request body it is documented to take. That is the property
that was actually violated, and it holds without a database, a token or a network.
"""
import os
import sys

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "test_corner_model")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest  # noqa: E402

from server import api_router  # noqa: E402

# path -> the function that must serve it. Every one freezes a board before kick-off, and
# every one is unrecoverable if it silently stops: the averages behind a board move each
# time the league plays, so a day not frozen is a day that can never be graded.
EXPECTED = {
    "/projections/snapshot": "snapshot_projections",
    "/streaks/snapshot": "snapshot_streaks",
    "/mismatches/snapshot": "snapshot_mismatches",
    "/perfect-games/snapshot": "snapshot_perfect",
}


def _post_routes():
    out = {}
    for r in api_router.routes:
        if "POST" in (getattr(r, "methods", None) or set()):
            out[r.path] = r
    return out


@pytest.mark.parametrize("path,fn", sorted(EXPECTED.items()))
def test_the_route_resolves_to_the_function_that_snapshots(path, fn):
    route = _post_routes().get(path)
    assert route is not None, f"{path} is not registered as a POST route at all"
    assert route.endpoint.__name__ == fn, (
        f"{path} resolves to {route.endpoint.__name__!r}, not {fn!r} — a decorator has "
        f"been stranded on whatever is defined beneath it"
    )


@pytest.mark.parametrize("path,fn", sorted(EXPECTED.items()))
def test_each_one_reads_a_request_body(path, fn):
    # The stranded helper took three bare query parameters and no body, so the days/limit
    # the caller asked for were discarded in silence. A snapshot route that reads no body
    # cannot honour its own horizon.
    route = _post_routes()[path]
    assert route.dependant.body_params, (
        f"{path} reads no request body — it cannot be the snapshot endpoint"
    )


@pytest.mark.parametrize("path,fn", sorted(EXPECTED.items()))
def test_no_lambda_shaped_query_parameters_leaked_in(path, fn):
    # The specific tell of this bug: an endpoint asking for lam_home/lam_away/lam_total,
    # which no caller has ever sent and which default quietly to None.
    names = {p.name for p in _post_routes()[path].dependant.query_params}
    assert not (names & {"lam_home", "lam_away", "lam_total"}), (
        f"{path} takes lambda query params — the decorator is on a probability helper"
    )


def test_a_helper_is_not_reachable_as_a_route():
    served = {r.endpoint.__name__ for r in api_router.routes
              if getattr(r, "endpoint", None)}
    assert "_threshold_probs" not in served, \
        "_threshold_probs is a pure helper and must not serve a route"


def test_every_snapshot_path_is_registered_exactly_once():
    # Two decorators on one path is the other way this breaks: the later registration
    # wins for some servers and the earlier for others, and both look fine at import.
    paths = [r.path for r in api_router.routes
             if "POST" in (getattr(r, "methods", None) or set())]
    for path in EXPECTED:
        assert paths.count(path) == 1, f"{path} is registered {paths.count(path)} times"
