"""Shared test setup.

AN EVENT LOOP FOR EVERY TEST. Several files drive coroutines with
`asyncio.get_event_loop().run_until_complete(...)`. That works when the test runs first
in its process, and raises "There is no current event loop" once any earlier test has
used `asyncio.run()`, which closes its loop and leaves none set. So whether those tests
passed depended on what ran before them, which is the worst kind of flaky. Giving each
test a fresh loop makes them independent of order and of how xdist splits the files.
"""
import asyncio

import pytest


@pytest.fixture(autouse=True)
def _fresh_event_loop():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    yield loop
    asyncio.set_event_loop(None)
    loop.close()
