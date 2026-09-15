"""Whether the Stripe setup actually works, as opposed to being filled in.

THE FAILURE THESE EXIST FOR. `STRIPE_SECRET_KEY` on the live backend was `sk_live_` and
nothing else — a copy that took the prefix the dashboard shows and left the secret behind.
Every check said the setup was fine, because every check asked whether the variable was
non-empty, and it was. The first thing to report the truth was Stripe, in a red toast on
the join page, to somebody trying to start a free trial.

So: a key is checked for being a plausible key before anything is asked of Stripe, and
checked against Stripe before anybody is told checkout is live.
"""
import os
import sys
import importlib
from unittest.mock import MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# A real one is about this long. Nothing here needs it to be valid, only key-shaped.
FULL_KEY = "sk_live_" + "51NqRvW" * 14


def _billing(key=FULL_KEY, price="price_123", webhook="whsec_1",
             site="https://thecornermodel.com", **env):
    """Freshly imported, so the module-level environment reads happen again."""
    os.environ["STRIPE_SECRET_KEY"] = key
    os.environ["STRIPE_PRICE_ID"] = price
    os.environ["STRIPE_WEBHOOK_SECRET"] = webhook
    os.environ["SITE_URL"] = site
    for k, v in env.items():
        os.environ[k] = v
    import billing
    return importlib.reload(billing)


def _stripe(price=None, account=None, key_error=None, price_error=None):
    """A stand-in for the Stripe library, which is not installed in the test env."""
    mod = MagicMock()
    mod.Account.retrieve.side_effect = key_error
    if not key_error:
        mod.Account.retrieve.return_value = account or {
            "id": "acct_1", "settings": {"dashboard": {"display_name": "Corner Model"}}}
    mod.Price.retrieve.side_effect = price_error
    if not price_error:
        mod.Price.retrieve.return_value = price or {
            "unit_amount": 2000, "currency": "gbp", "active": True, "livemode": True,
            "recurring": {"interval": "month"}}
    return mod


class TestTheKeyIsKeyShaped:
    """No network involved. These are the ones that catch a bad paste."""

    def test_the_live_failure_a_key_that_is_only_its_prefix(self):
        # Exactly what was in the environment.
        b = _billing(key="sk_live_")
        out = b.check()
        assert out["ok"] is False
        assert out["key"]["truncated"] is True
        assert "cut off" in out["error"]

    def test_and_such_a_key_does_not_count_as_configured(self):
        # WHAT THIS CHANGES ON THE PAGE. `configured()` is /api/config's `stripe_ready`,
        # and the join page falls back to the old payment link when it is false. While it
        # answered "yes" to a key that cannot work, that fallback was never reached: the
        # page advertised a trial, sent people into a checkout that could not start, and
        # left them at a red error over a payment form with nowhere to go.
        assert _billing(key="sk_live_").configured() is False
        assert _billing(key=FULL_KEY[:20] + "\n" + FULL_KEY[20:]).configured() is False

    def test_a_real_key_still_counts_as_configured(self):
        # And it switches back on by itself the moment the right key is pasted in — no
        # deploy, no second setting to remember.
        assert _billing().configured() is True

    def test_the_shape_test_makes_no_network_call(self, monkeypatch):
        # Runs on every page load. A deterministic local test cannot flap — a blip at
        # Stripe must never quietly reshape the join page.
        b = _billing()
        stripe = MagicMock()
        monkeypatch.setattr(b, "_stripe", stripe)
        b.configured()
        stripe.assert_not_called()

    def test_nothing_set_is_still_not_configured(self):
        assert _billing(key="", price="").configured() is False
        assert _billing(key=FULL_KEY, price="").configured() is False

    def test_and_it_says_so_without_asking_stripe(self, monkeypatch):
        # Stripe answers a truncated key with "Invalid API Key", which reads as "this key
        # is wrong, get a new one" and sends somebody to roll a key that was fine. The
        # length is the useful fact and it is free, so it is checked first.
        b = _billing(key="sk_live_")
        called = MagicMock()
        monkeypatch.setattr(b, "_stripe", called)
        b.check()
        called.assert_not_called()

    def test_a_full_key_is_not_flagged(self):
        assert _billing().key_shape()["truncated"] is False

    def test_a_key_with_a_line_break_in_it(self):
        # Survives the strip() at import because it is in the middle, and fails every call
        # with nothing on screen to suggest why.
        out = _billing(key=FULL_KEY[:40] + "\n" + FULL_KEY[40:]).check()
        assert out["ok"] is False
        assert "one piece" in out["error"]

    def test_the_key_itself_is_never_in_the_output(self):
        # This endpoint is token-gated, but its output gets pasted into chats and logs.
        out = _billing().check()
        assert FULL_KEY not in repr(out)
        assert out["key"]["prefix"] == "sk_live_"
        assert out["key"]["mode"] == "live"

    def test_something_that_is_not_a_stripe_key_at_all(self):
        # A price id in the key box, say. Reported by its first characters so the mistake
        # is visible without the value being printed.
        shape = _billing(key="price_1NqRvWabcdefghijklmnop").key_shape()
        assert shape["mode"] == ""
        assert shape["prefix"] == "price_1N…"

    def test_a_restricted_key_is_flagged_as_one(self):
        # rk_ keys work until they hit a permission they were not given, which happens at
        # checkout rather than at boot.
        assert _billing(key="rk_live_" + "x" * 40).key_shape()["restricted"] is True

    def test_nothing_set_at_all_names_the_variables(self):
        out = _billing(key="", price="").check()
        assert out["ok"] is False
        assert "STRIPE_SECRET_KEY" in out["error"] and "STRIPE_PRICE_ID" in out["error"]


class TestWhereStripeSendsPeopleBack:
    """SITE_URL has no default, and checkout cannot work without it."""

    def test_unset_is_caught_before_anybody_tries_to_pay(self, monkeypatch):
        # create_checkout_session builds "{SITE_URL}/account?checkout=success". Unset, that
        # is a relative path, and Stripe refuses it — for a reason that has nothing to do
        # with the key or the price, so nothing else here would have pointed at it.
        b = _billing(site="")
        out = b.check()
        assert out["ok"] is False
        assert "SITE_URL" in out["error"]

    def test_a_bare_domain_is_not_enough(self):
        # "thecornermodel.com" reads as correct and is not a URL.
        assert "SITE_URL" in _billing(site="thecornermodel.com").check()["error"]

    def test_checked_alongside_the_key_rather_than_after_it(self, monkeypatch):
        # Finding one blocker at a time is how a ten-minute job takes three days. This runs
        # before the Stripe calls, so a broken SITE_URL surfaces on the same run as a good
        # key rather than on the next one.
        b = _billing(site="")
        stripe = MagicMock()
        monkeypatch.setattr(b, "_stripe", stripe)
        b.check()
        stripe.assert_not_called()

    def test_it_is_reported_even_when_the_key_is_the_blocking_problem(self):
        # The flaw in the first version of this check, and the exact thing it existed to
        # prevent. The SITE_URL test sat below the key checks, so while the key was broken
        # the field was never set and the checklist could not print the row — fix the key,
        # redeploy, only then find out about SITE_URL, redeploy again.
        out = _billing(key="sk_live_", site="").check()
        assert out["site_url_ok"] is False        # reported, not skipped
        assert "cut off" in out["error"]          # while the key is still the headline
        assert _billing(key="sk_live_").check()["site_url_ok"] is True

    def test_a_proper_url_passes(self, monkeypatch):
        b = _billing(site="https://thecornermodel.com/")
        monkeypatch.setattr(b, "_stripe", lambda: _stripe())
        assert b.check()["ok"] is True


class TestWhatStripeSays:
    def test_a_working_setup(self, monkeypatch):
        b = _billing()
        monkeypatch.setattr(b, "_stripe", lambda: _stripe())
        out = b.check()
        assert out["ok"] is True
        assert out["key_valid"] is True and out["price_valid"] is True
        # The price is read back in full, because "checkout works" and "checkout charges
        # what the page advertises" are different questions and only one of them was asked.
        assert out["price"]["amount"] == "£20.00"
        assert out["price"]["interval"] == "month"
        # Which Stripe account, for when there are two and the keys came from the old one.
        assert out["account"]["name"] == "Corner Model"

    def test_a_key_stripe_rejects(self, monkeypatch):
        b = _billing()
        monkeypatch.setattr(b, "_stripe", lambda: _stripe(key_error=Exception("Invalid API Key")))
        out = b.check()
        assert out["ok"] is False and out["key_valid"] is False

    def test_a_price_that_does_not_exist(self, monkeypatch):
        # Distinguished from a bad key, because the key was checked first and passed.
        b = _billing()
        monkeypatch.setattr(b, "_stripe", lambda: _stripe(price_error=Exception("No such price")))
        out = b.check()
        assert out["ok"] is False
        assert out["key_valid"] is True and out["price_valid"] is False

    def test_a_live_key_against_a_test_price(self, monkeypatch):
        # Stripe reports this as the price not existing, which sends you to look at the
        # price on its own — where it is plainly there.
        b = _billing()
        monkeypatch.setattr(b, "_stripe", lambda: _stripe(
            price={"unit_amount": 2000, "currency": "gbp", "active": True,
                   "livemode": False, "recurring": {"interval": "month"}}))
        out = b.check()
        assert out["ok"] is False
        assert "must match" in out["error"]

    def test_an_archived_price(self, monkeypatch):
        b = _billing()
        monkeypatch.setattr(b, "_stripe", lambda: _stripe(
            price={"unit_amount": 2000, "currency": "gbp", "active": False,
                   "livemode": True, "recurring": {"interval": "month"}}))
        assert "archived" in b.check()["error"]

    def test_a_one_off_price_on_a_subscription(self, monkeypatch):
        b = _billing()
        monkeypatch.setattr(b, "_stripe", lambda: _stripe(
            price={"unit_amount": 2000, "currency": "gbp", "active": True,
                   "livemode": True, "recurring": None}))
        assert "recurring" in b.check()["error"]

    def test_the_library_being_absent_is_reported_not_raised(self, monkeypatch):
        # Stripe is an optional dependency — the rest of the site runs without it, and a
        # diagnostic that raises a 500 tells you less than the site already does.
        b = _billing()

        def boom():
            raise ImportError("No module named 'stripe'")
        monkeypatch.setattr(b, "_stripe", boom)
        out = b.check()
        assert out["ok"] is False and "not installed" in out["error"]


class TestWhatTheVisitorIsTold:
    def test_stripes_own_words_do_not_reach_the_page(self):
        # `detail` is rendered verbatim in a toast on the join page. The live failure put
        # "Invalid API Key provided: sk_live_" in front of somebody entering card details,
        # which reads like the site has been got at.
        msg = _billing().checkout_error_message(Exception("Invalid API Key provided: sk_live_"))
        assert "API Key" not in msg and "sk_live_" not in msg

    def test_it_says_the_two_things_that_concern_them(self):
        msg = _billing().checkout_error_message(Exception("boom"))
        assert "nothing has been charged" in msg.lower()
        assert "again" in msg.lower()
