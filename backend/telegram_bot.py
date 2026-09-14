"""The inbound half of the Telegram bot.

WHAT THIS IS FOR. The bot has only ever been able to SEND — the scheduled job POSTs to
sendMessage and that is the whole relationship. Nothing listens, so a message typed at it
sits in Telegram's queue and is never read. This is the part that listens.

STEP ONE ON PURPOSE, and the scope is the point. It answers /start and /help and nothing
else. Everything interesting — /value, /game, /streaks — needs to know WHO is asking, and
there is currently no link between a Telegram account and a member row. Building the
commands first would mean either leaving the paid boards open to anyone who finds the bot,
or inventing an identity scheme under time pressure. So the pipe gets proven first:
delivery, the secret, and de-duplication.

WHAT /help SAYS IS WHAT WORKS. It lists two commands because two commands exist. Listing
the planned ones would repeat the mistake already sitting in the daily angle menu, which
ends "Reply with a number and I'll write that one up" at a bot that cannot hear it.

SECURITY. The webhook URL is not a secret — it is on the public internet and anyone can
POST to it. Telegram's `secret_token` is: it is set when the webhook is registered, sent
back as a header on every delivery, and compared here. Without that check a stranger could
forge updates and make the bot answer as though a real person had typed.
"""
import os
import re
import asyncio
import logging
import secrets
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
# Separate from the bot token on purpose. The bot token can send messages as you; this one
# only proves an inbound request came from Telegram. They should not be the same string,
# because this one is handed to Telegram to echo back on every delivery.
WEBHOOK_SECRET = os.environ.get("TELEGRAM_WEBHOOK_SECRET", "").strip()
SECRET_HEADER = "x-telegram-bot-api-secret-token"

# Telegram caps a message at 4096 characters and answers a longer one with HTTP 400 and
# nothing else. Same limit that silently ate the weekend card twice.
MAX_MESSAGE = 4096


def configured() -> bool:
    """Can this bot both hear and answer? Both halves are needed and they fail differently:
    no secret means anyone could forge an update, no token means it cannot reply."""
    return bool(BOT_TOKEN and WEBHOOK_SECRET)


def verify(header_value: Optional[str]) -> bool:
    """Did this really come from Telegram?

    compare_digest rather than `==` for the same reason the membership code uses it: a
    plain comparison returns faster on an early mismatch, and that is a side channel that
    narrows a secret one character at a time."""
    if not WEBHOOK_SECRET or not header_value:
        return False
    return secrets.compare_digest(header_value, WEBHOOK_SECRET)


async def send(chat_id, text: str, reply_to: Optional[int] = None) -> bool:
    """One reply. Plain text, NO parse_mode — deliberately.

    Team names carry slashes, underscores and accents, and both Markdown and HTML treat
    some of those as syntax. A message that fails to parse is a message that never
    arrives, and the failure looks identical to the bot being broken. The scheduled job
    made the same choice for the same reason."""
    if not BOT_TOKEN:
        return False
    body = {"chat_id": chat_id, "text": text[:MAX_MESSAGE],
            "disable_web_page_preview": True}
    if reply_to:
        body["reply_to_message_id"] = reply_to
    try:
        async with httpx.AsyncClient(timeout=20) as hc:
            r = await hc.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                              json=body)
        if r.status_code != 200:
            # The body says WHY — "chat not found", "bot was blocked" — and none of it
            # contains the token, which is in the URL rather than the payload.
            logger.warning("telegram sendMessage %s: %s", r.status_code, r.text[:300])
        return r.status_code == 200
    except Exception:
        logger.exception("telegram sendMessage failed")
        return False


async def set_webhook(url: str) -> dict:
    """Point Telegram at us, with the secret it must echo back.

    `drop_pending_updates` clears whatever queued up while nothing was listening. That
    backlog is every message anyone sent the bot before today, and replaying it would mean
    answering questions from weeks ago as though they had just been asked."""
    if not BOT_TOKEN:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is not set")
    if not WEBHOOK_SECRET:
        raise RuntimeError("TELEGRAM_WEBHOOK_SECRET is not set")
    async with httpx.AsyncClient(timeout=30) as hc:
        r = await hc.post(f"https://api.telegram.org/bot{BOT_TOKEN}/setWebhook", json={
            "url": url,
            "secret_token": WEBHOOK_SECRET,
            "drop_pending_updates": True,
            # Only what is actually handled. Asking for every update type means being
            # woken for edits, reactions and member joins that go straight in the bin.
            "allowed_updates": ["message"],
        })
    return r.json()


async def webhook_info() -> dict:
    if not BOT_TOKEN:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is not set")
    async with httpx.AsyncClient(timeout=20) as hc:
        r = await hc.get(f"https://api.telegram.org/bot{BOT_TOKEN}/getWebhookInfo")
    return r.json()


# ----------------------------- reading a message -----------------------------

def parse_command(text: str) -> tuple[Optional[str], str]:
    """"/team Viking FK" -> ("team", "Viking FK"). Not a command -> (None, "").

    THE @MENTION IS STRIPPED. In a group, Telegram delivers "/help@TheCornerModelBot" —
    addressed to this bot specifically — and a router matching on the raw string would
    treat that as an unknown command, so the bot would answer in a DM and go silent in
    exactly the place several people can see it.
    """
    t = (text or "").strip()
    if not t.startswith("/"):
        return None, ""
    head, _, rest = t.partition(" ")
    name = head[1:].split("@", 1)[0].lower()
    return (name or None), rest.strip()


def is_private(update: dict) -> bool:
    """A one-to-one chat, as opposed to a group or channel.

    Nothing branches on this yet — /start and /help are free and can be answered anywhere.
    It is here because the next step needs it: a member running /value in a group would
    publish the paid board to whoever is in the room, so gated commands have to answer in
    a DM and say so in the group.
    """
    return ((update.get("message") or {}).get("chat") or {}).get("type") == "private"


HELP = (
    "🎯 The Corner Model\n"
    "\n"
    "Reply to the daily angle menu with its number:\n"
    "\n"
    "  3              the game, and a link to write it up\n"
    "  3 @ 1.80       logs it at that price\n"
    "  3 @ 1.80 1.5u  price and stake\n"
    "\n"
    "A stake needs the u — a bare second number is read as the price.\n"
    "\n"
    "Logging the price is what lets the results cards report units. Without one they can "
    "only ever report a hit rate.\n"
    "\n"
    "/help — this message\n"
    "\n"
    "Stats commands are still being built. I would rather list what works than what is "
    "planned."
)


def reply_for(update: dict) -> Optional[str]:
    """What to say back, or None to stay silent.

    SILENCE IS A REAL ANSWER, and which silence depends on where the message came from.
    In a group, replying to anything that is not a command is how a bot gets muted — it
    would answer every conversation it was sitting in. In a DM there is no one else to
    annoy and a message is unambiguously addressed to the bot, so an unrecognised one gets
    pointed at /help rather than dropped into a void.
    """
    msg = update.get("message") or {}
    text = msg.get("text") or ""
    name, _args = parse_command(text)

    if name in ("start", "help"):
        return HELP
    if name:
        return (f"I don't know /{name} yet. /help lists what I can do."
                if is_private(update) else None)
    return PICK_HELP if is_private(update) else None


def chat_id_of(update: dict):
    return ((update.get("message") or {}).get("chat") or {}).get("id")


# ----------------------------- Picking from the menu -----------------------------
#
# The daily angle menu ends "Reply with a number and I'll write that one up", and until now
# that was addressed to a bot that could not hear. This is the half that listens for it.
#
# IT ALSO CAPTURES THE PRICE, which is the part worth more than the convenience. A posted
# angle with no price can be graded for a hit rate and nothing else — settlement.pick_profit
# answers None for a win at an unknown price rather than 0 — so every results card was stuck
# reporting "4 of 4" with no units behind it. Sending "3 @ 1.80 1.5u" logs the angle, the
# price and the stake in the one message that was going to be sent anyway, and the day card
# fills its own units in.

PICK_HELP = ("Reply with the number from the menu.\n"
             "\n"
             "  3              just the write-up\n"
             "  3 @ 1.80       logs it at that price\n"
             "  3 @ 1.80 1.5u  price and stake\n"
             "\n"
             "A stake needs the u — a bare second number is read as the price.\n"
             "\n"
             "/help for everything else.")


def parse_pick_reply(text: str):
    """"3 @ 1.80 1.5u" -> {"n": 3, "price": 1.8, "stake": 1.5}, or None.

    FORGIVING ABOUT SHAPE, STRICT ABOUT MEANING. The @ and the u are optional decoration
    and the order is fixed: index, then price, then stake. What it will not do is guess —
    a stake has to carry its `u`, because "3 2" is genuinely ambiguous between "pick 3 at
    2.0" and "pick 3, two units", and a wrong reading there writes a wrong price into the
    record that later becomes a units figure on a graphic.

    A price at or below evens is refused rather than stored. 1.0 is how an empty field
    arrives and below evens is not a bet; either would compute a return.
    """
    t = (text or "").strip().lstrip("/")
    if t.lower().startswith("pick"):
        t = t[4:].strip()
    m = re.match(r"^(\d{1,2})\b(.*)$", t)
    if not m:
        return None
    n = int(m.group(1))
    if n < 1:
        return None
    rest = m.group(2)

    stake = None
    # The stake is claimed FIRST, by its unit marker, so it cannot be mistaken for a price
    # further down.
    su = re.search(r"(\d+(?:\.\d+)?)\s*u\b", rest, re.I)
    if su:
        stake = float(su.group(1))
        rest = rest[:su.start()] + rest[su.end():]

    price = None
    pm = re.search(r"(\d+(?:\.\d+)?)", rest)
    if pm:
        p = float(pm.group(1))
        price = p if p > 1 else None
    return {"n": n, "price": price, "stake": stake if (stake or 0) > 0 else None}
