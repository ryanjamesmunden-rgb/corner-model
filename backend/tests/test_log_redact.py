"""Credentials must not reach the log, and this is the only thing checking.

THE TWO THAT LEAKED, BOTH BY DEFAULT BEHAVIOUR RATHER THAN BY MISTAKE.

Telegram authenticates by putting the bot token in the URL PATH, and httpx logs every
request it makes at INFO as "HTTP Request: POST <url>". server.py calls basicConfig(INFO),
so the full token went to the log on every message the bot sent.

Twenty-nine endpoints take `?token=`, and an access log records the query string.

The tests that matter here are the ones asserting the SECRET IS ABSENT from the output,
rather than that some pattern matched. A redactor that scrubs a slightly different string
than the one that leaked passes every pattern test and still publishes the token.
"""
import io
import logging
import os
import sys

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "test_corner_model")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import log_redact  # noqa: E402

BOT = "8123456789:AAH9xQVeryRealLookingBotTokenHere_01"
TOOLS = "s3cr3t-tools-token-value-here"
ENV = {"TELEGRAM_BOT_TOKEN": BOT, "TOOLS_TOKEN": TOOLS}


def captured(record_fn, env=None):
    """Log something through a handler carrying the filter, and read what came out."""
    buf = io.StringIO()
    handler = logging.StreamHandler(buf)
    log = logging.getLogger(f"test-{id(buf)}")
    log.handlers = [handler]
    log.propagate = False
    log.setLevel(logging.INFO)
    log_redact.install(log)
    record_fn(log)
    handler.flush()
    return buf.getvalue()


class TestTheLeaksThatHappened:
    def test_the_bot_token_does_not_survive_an_httpx_request_line(self, monkeypatch):
        # THE EXACT SHAPE httpx PRODUCES: the URL is an ARGUMENT, not part of the message.
        # A filter that only rewrote record.msg would leave the token sitting in args and
        # the formatter would put it straight back — which is the version that looks
        # correct in review and fixes nothing.
        for k, v in ENV.items():
            monkeypatch.setenv(k, v)
        out = captured(lambda log: log.info(
            'HTTP Request: POST %s "HTTP/1.1 200 OK"',
            f"https://api.telegram.org/bot{BOT}/sendMessage"))
        assert BOT not in out
        assert "bot<redacted>" in out
        # Still readable — the point is a usable log, not a blank one.
        assert "sendMessage" in out and "200 OK" in out

    def test_the_tools_token_does_not_survive_an_access_log_line(self, monkeypatch):
        for k, v in ENV.items():
            monkeypatch.setenv(k, v)
        out = captured(lambda log: log.info(
            '%s - "GET /api/streaks/snapshot?token=%s&days=2 HTTP/1.1" 200',
            "10.0.0.1", TOOLS))
        assert TOOLS not in out
        assert "token=<redacted>" in out
        assert "days=2" in out, "the rest of the query string is still worth reading"

    def test_a_secret_in_a_traceback_is_scrubbed_too(self, monkeypatch):
        # exc_text is a separate field, formatted from the exception tuple. Everything that
        # rewrites the message leaves it untouched.
        for k, v in ENV.items():
            monkeypatch.setenv(k, v)

        def boom(log):
            try:
                raise ValueError(f"refused for token {TOOLS}")
            except ValueError:
                log.exception("call failed")

        out = captured(boom)
        assert TOOLS not in out


class TestWhatElseItCatches:
    def test_a_stripe_secret_key(self):
        assert redacted("sk_live_51QabcdEFGH1234567890") == "sk_live_<redacted>"

    def test_a_restricted_key_too(self):
        assert "rk_test_<redacted>" in log_redact.redact("rk_test_ABCdef123456789", [])

    def test_a_publishable_key_is_left_alone(self):
        # pk_ keys are public by design. Redacting them makes a log harder to read and
        # protects nothing.
        text = "pk_live_51QabcdEFGH1234567890"
        assert log_redact.redact(text, []) == text

    def test_credentials_inside_a_connection_string(self):
        out = log_redact.redact("mongodb+srv://appuser:hunter2password@c0.mongodb.net/db", [])
        assert "hunter2password" not in out
        assert "appuser" in out and "c0.mongodb.net" in out

    def test_a_bearer_header(self):
        out = log_redact.redact("Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.abc.def", [])
        assert "eyJhbGciOiJIUzI1NiJ9" not in out

    def test_any_secret_shaped_query_parameter(self):
        for name in ("token", "api_key", "secret", "password", "signature"):
            out = log_redact.redact(f"/x?{name}=supersecretvalue&ok=1", [])
            assert "supersecretvalue" not in out, name
            assert "ok=1" in out


class TestItDoesNotEatTheLog:
    def test_an_unset_secret_redacts_nothing(self, monkeypatch):
        # The trap: a secret read as "" would match at every position and turn every line
        # into confetti.
        for name in log_redact.SECRET_VARS:
            monkeypatch.delenv(name, raising=False)
        assert log_redact.secret_values() == []
        assert log_redact.redact("a normal line") == "a normal line"

    def test_a_short_or_placeholder_secret_is_ignored(self, monkeypatch):
        # A truncated secret is a misconfiguration, not a credential — hiding it would hide
        # the very thing somebody is trying to debug.
        #
        # Asserted on ABSENCE rather than on an empty list: other variables are legitimately
        # set in this process, and a test demanding nothing at all is set is a test about
        # the environment rather than about the rule.
        monkeypatch.setenv("TOOLS_TOKEN", "abc")
        assert "abc" not in log_redact.secret_values()

    def test_ordinary_text_is_untouched(self):
        line = "froze 12 streaks as tag 2026-09-16"
        assert log_redact.redact(line, []) == line

    def test_the_longest_secret_is_replaced_first(self, monkeypatch):
        # A Mongo URL containing a password that is ALSO its own variable: replacing the
        # short one first leaves the rest of the URL behind, still identifying.
        #
        # Asserted as RELATIVE ORDER rather than "index 0": other secret variables are
        # legitimately set in this process, and whether one of them happens to be longer is
        # a fact about the environment, not about the rule. Pinning the index passed alone
        # and failed in the full suite, which is the worse of the two ways to be wrong.
        monkeypatch.setenv("MONGO_URL", "mongodb://u:longpasswordhere@host/db")
        monkeypatch.setenv("SESSION_SECRET", "longpasswordhere")
        vals = log_redact.secret_values()
        assert vals.index("mongodb://u:longpasswordhere@host/db") < vals.index("longpasswordhere")

        # And the consequence it exists for: the whole URL goes, not just the password,
        # leaving nothing that still identifies the cluster.
        out = log_redact.redact("connecting to mongodb://u:longpasswordhere@host/db", vals)
        assert "longpasswordhere" not in out and "host/db" not in out

    def test_nothing_is_not_an_error(self):
        assert log_redact.redact(None) is None
        assert log_redact.redact("") == ""


class TestTheFilterIsSafeToInstall:
    def test_it_never_raises_whatever_the_record(self, monkeypatch):
        # A filter that throws takes logging down with it, and a process that cannot log is
        # worse off than one logging too much.
        f = log_redact.SecretFilter()

        class Awkward(logging.LogRecord):
            def getMessage(self):
                raise RuntimeError("cannot render")

        rec = Awkward("x", logging.INFO, __file__, 1, "msg", (), None)
        assert f.filter(rec) is True

    def test_it_always_lets_the_record_through(self):
        f = log_redact.SecretFilter()
        rec = logging.LogRecord("x", logging.INFO, __file__, 1, "hello", (), None)
        assert f.filter(rec) is True
        assert rec.getMessage() == "hello"

    def test_installing_twice_does_not_stack_filters(self):
        log = logging.getLogger("install-twice")
        log.handlers = [logging.StreamHandler(io.StringIO())]
        log_redact.install(log)
        log_redact.install(log)
        filters = [f for f in log.handlers[0].filters
                   if isinstance(f, log_redact.SecretFilter)]
        assert len(filters) == 1

    def test_the_request_loggers_are_quietened(self):
        log_redact.install(logging.getLogger("quieten-check"))
        for name in log_redact.NOISY_AT_INFO:
            assert logging.getLogger(name).level == logging.WARNING, name


class TestTheServerInstallsIt:
    def test_server_calls_install_and_does_so_before_anything_can_log(self):
        """A leak on the first outbound call is still a leak. Installing later would mean
        whatever happened during import went out in the clear."""
        import inspect

        import server
        src = inspect.getsource(server)
        assert "log_redact.install()" in src
        basic = src.index("logging.basicConfig")
        install = src.index("log_redact.install()")
        assert install > basic, "there are no handlers to filter before basicConfig"
        assert install - basic < 600, \
            "install has drifted away from basicConfig — anything logged between the two " \
            "goes out unredacted"


def redacted(text):
    return log_redact.redact(text, [])


class TestTheAccessLogIsActuallyCovered:
    """The leak that a root-only filter would have missed entirely.

    Uvicorn configures `uvicorn.access` with its own handler and `propagate=False`, so those
    records never reach a filter on the root logger — and the access log is exactly where
    the tools token appears, in the query string of twenty-nine endpoints. A root-only
    install looks right, passes every test written against a logger of our own, and leaves
    the leak running.
    """

    def test_a_non_propagating_logger_with_its_own_handler_is_filtered(self, monkeypatch):
        monkeypatch.setenv("TOOLS_TOKEN", TOOLS)
        buf = io.StringIO()
        access = logging.getLogger("uvicorn.access")
        access.handlers = [logging.StreamHandler(buf)]
        access.propagate = False          # what uvicorn actually sets
        access.setLevel(logging.INFO)

        log_redact.install()              # the real, no-argument call

        access.info('1.2.3.4 - "GET /api/results?token=%s HTTP/1.1" 200', TOOLS)
        access.handlers[0].flush()
        out = buf.getvalue()
        assert TOOLS not in out
        assert "token=<redacted>" in out

    def test_install_walks_every_logger_not_just_the_root(self):
        import inspect
        src = inspect.getsource(log_redact.install)
        assert "loggerDict" in src, \
            "install only covers the root, so uvicorn.access — which does not propagate " \
            "— goes unfiltered, and that is where the tools token is"

    def test_the_server_reinstalls_on_startup(self):
        """Uvicorn configures logging before importing the app, but a reload or a
        programmatic run can land the other way round."""
        import inspect
        import server
        src = inspect.getsource(server.on_startup)
        assert "log_redact.install()" in src
