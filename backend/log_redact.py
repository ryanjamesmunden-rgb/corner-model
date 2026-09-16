"""Keep credentials out of the logs.

TWO LEAKS, BOTH OF THEM ROUTINE RATHER THAN EXOTIC.

THE BOT TOKEN IS IN A URL PATH. Telegram authenticates by putting the token in the path —
`https://api.telegram.org/bot<TOKEN>/sendMessage` — and httpx logs every request it makes at
INFO level, as "HTTP Request: POST <url> ...". server.py calls logging.basicConfig(INFO), so
the full token was written to the log on every message the bot sent. That is many times a
day, for months, into whatever Render retains.

THE TOOLS TOKEN IS IN A QUERY STRING. Twenty-nine endpoints take `?token=`, and an access
log records the path with its query string attached. Same outcome by a different route.

Neither needed a mistake to happen. Both are what those libraries do by default.

WHY A FILTER AND NOT JUST A LOG LEVEL. Raising httpx to WARNING fixes the case we found,
and only that case. A filter on the root handler covers every logger in the process —
httpx, httpcore, uvicorn.access, our own, and whatever is added next year by somebody who
does not read this file. Both are applied: the level stops the record being created, the
filter catches anything that gets made anyway.

PATTERNS *AND* EXACT VALUES. The patterns catch credentials shaped like credentials,
including ones belonging to services this file has never heard of. The exact-value pass
catches this deployment's own secrets wherever they appear, in any shape, including inside a
Mongo connection string or an exception message nobody anticipated. Either alone leaves a
gap the other closes.

Pure functions plus a filter class, so the rule can be tested without a logger.
"""
import logging
import os
import re

# What gets redacted, and it is deliberately wider than what leaked. A pattern list is only
# useful if it covers the credential somebody adds next, not just the two found today.
PATTERNS = (
    # Telegram: the token lives in the PATH, which is why a URL alone is enough to lose it.
    (re.compile(r"(bot)\d+:[A-Za-z0-9_\-]{20,}"), r"\1<redacted>"),
    # Any secret-looking query parameter, whatever the endpoint calls it.
    (re.compile(r"((?:token|api_key|apikey|key|secret|password|pwd|sig|signature)=)"
                r"[^&\s\"'<>]+", re.IGNORECASE), r"\1<redacted>"),
    # Stripe secret and restricted keys. Publishable pk_ keys are deliberately NOT here —
    # they are public by design, and redacting them makes a log harder to read for nothing.
    (re.compile(r"\b((?:sk|rk)_(?:live|test)_)[A-Za-z0-9]{8,}"), r"\1<redacted>"),
    # Bearer tokens, which arrive in headers and in anything that echoes one.
    (re.compile(r"(Bearer\s+)[A-Za-z0-9._\-]{8,}", re.IGNORECASE), r"\1<redacted>"),
    # Credentials inside a connection string — mongodb://user:password@host.
    (re.compile(r"(://[^:/\s]+:)[^@/\s]+(@)"), r"\1<redacted>\2"),
)

# This deployment's own secrets, redacted by exact value wherever they turn up. Named rather
# than discovered, because a rule like "every variable ending in _KEY" would eventually
# scrub something harmless and make a log unreadable.
SECRET_VARS = (
    "TELEGRAM_BOT_TOKEN",
    "TELEGRAM_WEBHOOK_SECRET",
    "TOOLS_TOKEN",
    "STRIPE_SECRET_KEY",
    "STRIPE_WEBHOOK_SECRET",
    "SESSION_SECRET",
    "ANTHROPIC_API_KEY",
    "API_FOOTBALL_KEY",
    "MONGO_URL",
)

# Below this, a value is too short to redact safely. A secret set to "1" — or, far more
# likely, to "" — would otherwise match everywhere and turn every log line into confetti.
# It also means a truncated or placeholder secret is left alone, which is correct: that is
# not a credential, and hiding it would hide the misconfiguration.
MIN_SECRET_LENGTH = 12


def secret_values(env=None):
    """The concrete values worth redacting, longest first.

    Longest first so a secret that contains another one — a Mongo URL holding a password
    also set on its own — is replaced whole rather than leaving the tail of it behind.
    """
    env = os.environ if env is None else env
    vals = {v for name in SECRET_VARS
            for v in [(env.get(name) or "").strip()]
            if len(v) >= MIN_SECRET_LENGTH}
    return sorted(vals, key=len, reverse=True)


def redact(text, values=None):
    """Strip credentials from one string. Never raises — see SecretFilter."""
    if not text:
        return text
    out = str(text)
    for value in (secret_values() if values is None else values):
        if value:
            out = out.replace(value, "<redacted>")
    for pattern, replacement in PATTERNS:
        out = pattern.sub(replacement, out)
    return out


class SecretFilter(logging.Filter):
    """Redact every record passing through, whoever logged it.

    ATTACHED TO THE HANDLER, NOT TO A LOGGER. A filter on a logger only sees that logger's
    records; on the handler it sees everything on its way out, which is the only placement
    that covers libraries nobody has thought about yet.

    THE MESSAGE IS FLATTENED HERE. A record carries `msg` and `args` separately and is only
    joined at format time, so redacting `msg` alone leaves a secret sitting in `args` — and
    httpx logs its URL as an argument, which is precisely the case that matters. Rendering
    first and clearing args is the only version that actually works.

    NEVER RAISES. A filter that throws takes logging down with it, and a process that cannot
    log is worse off than one logging too much. Anything unexpected is dropped in favour of
    letting the record through unmodified — with one exception: if rendering fails there is
    no message to inspect, and the record is passed as-is rather than guessed at.
    """

    def filter(self, record):
        try:
            values = secret_values()
            rendered = record.getMessage()
            cleaned = redact(rendered, values)
            if cleaned != rendered:
                record.msg = cleaned
                record.args = ()
            # THE TRACEBACK IS BUILT AFTER THIS RUNS, which is the trap. A filter sees
            # `exc_info` (a tuple) and an empty `exc_text`; the Formatter renders the
            # tuple later, long past any chance to scrub it. So the rendering happens
            # HERE and the result is cached on the record — logging reuses a populated
            # `exc_text` rather than formatting again, so the redacted version is the one
            # that reaches the log.
            #
            # It matters more than the message does: half the logger.exception calls in
            # this codebase are around Stripe and Telegram, and a raised client error
            # routinely quotes the request it failed on.
            if record.exc_info and not record.exc_text:
                record.exc_text = logging.Formatter().formatException(record.exc_info)
            if record.exc_text:
                record.exc_text = redact(record.exc_text, values)
        except Exception:      # noqa: BLE001 — see the docstring
            pass
        return True


# HTTPX AND HTTPCORE LOG EVERY REQUEST URL AT INFO. That is the leak that started this, and
# the filter above already neutralises it — but a secret that is never written is safer than
# one written and scrubbed, and these two produce a line per outbound call that nobody has
# ever read on purpose. WARNING keeps the failures and drops the noise.
NOISY_AT_INFO = ("httpx", "httpcore", "httpcore.http11", "httpcore.connection")


def _protect(log):
    """Attach the filter to this logger's own handlers, once each."""
    for handler in getattr(log, "handlers", ()):
        if not any(isinstance(f, SecretFilter) for f in handler.filters):
            handler.addFilter(SecretFilter())


def install(root=None):
    """Attach the filter to EVERY logger's handlers, and quieten the request loggers.

    NOT JUST THE ROOT, and this is the part that decides whether the access-log leak is
    actually fixed. Uvicorn configures `uvicorn.access` with its own handler and
    `propagate=False`, so those records never reach a root filter at all — and the access
    log is precisely where the tools token appears, in the query string of twenty-nine
    endpoints. A root-only install would have looked right, passed every test written
    against a logger of our own, and left the leak running.

    CALLED TWICE ON PURPOSE. Uvicorn configures logging BEFORE it imports the app, so the
    call at import time already finds its handlers; the second call from the startup event
    catches anything configured after. Idempotent, so the pair costs nothing.

    `root` is for tests: given a logger, only that one is touched.
    """
    if root is not None:
        _protect(root)
        for name in NOISY_AT_INFO:
            logging.getLogger(name).setLevel(logging.WARNING)
        return root

    _protect(logging.getLogger())
    # Snapshot the dict first: getLogger() on a placeholder would mutate it mid-iteration.
    for name in list(logging.root.manager.loggerDict):
        obj = logging.root.manager.loggerDict.get(name)
        if isinstance(obj, logging.Logger):
            _protect(obj)
    for name in NOISY_AT_INFO:
        logging.getLogger(name).setLevel(logging.WARNING)
    return logging.getLogger()
