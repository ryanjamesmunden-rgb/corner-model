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

# The paid channel. Numeric and usually negative for a channel (-100...), and the bot has
# to be an ADMIN of it with "invite users via link" — createChatInviteLink is refused
# otherwise, which is the one setup mistake worth expecting.
VIP_CHAT_ID = os.environ.get("TELEGRAM_VIP_CHAT_ID", "").strip()

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
            # woken for edits and reactions that go straight in the bin.
            #
            # `chat_member` HAS TO BE ASKED FOR EXPLICITLY — Telegram never sends it by
            # default, even to an admin bot, and its absence is silent. It carries the
            # invite link somebody joined through, which is the only thread connecting a
            # Telegram account to a subscription; without it the channel has no way to know
            # which of its members paid, and no way to remove the right one when they stop.
            "allowed_updates": ["message", "chat_member"],
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


# ----------------------------- Getting a subscriber into the channel -----------------------------
#
# THE GAP THIS CLOSES. Stripe checkout unlocked the SITE and nothing at all handed the new
# subscriber the Telegram channel — the half of the product they are actually paying for.
# That was a manual add per person, and on a ten-day trial it is worse than it sounds: a
# signup at 11pm added the following afternoon has burned a day of the window that exists
# specifically to convince them.
#
# ONE LINK PER PERSON, USABLE ONCE. `member_limit=1` is the whole design. A single shared
# invite posted on the account page would be forwarded, screenshotted and eventually
# public, and there would be no way to tell which of the people in the channel had paid.
# A link that dies the moment one person walks through it cannot be shared usefully.
#
# NAMED, so the channel's own invite-link list becomes the answer to "who is this". Telegram
# shows the name against the link and against the member who joined with it.


def vip_configured() -> bool:
    """Can an invite be issued at all? Both halves: a token to call the API with, and a
    channel to invite anybody to."""
    return bool(BOT_TOKEN and VIP_CHAT_ID)


def invite_label(user: dict) -> str:
    """What the link is called in the channel's admin list.

    TELEGRAM CAPS THIS AT 32 CHARACTERS and answers a longer one with an error rather than
    truncating, so it is cut here. Their name if Stripe gave us one, otherwise the email —
    whichever makes the admin list readable to a person scanning it.
    """
    label = (user or {}).get("billing_name") or (user or {}).get("name") \
        or (user or {}).get("email") or (user or {}).get("user_id") or "member"
    return str(label).strip()[:32]


async def create_invite(user: dict) -> Optional[str]:
    """A single-use invite to the paid channel, or None when it could not be made.

    NONE RATHER THAN AN EXCEPTION, because the caller is an endpoint a paying member is
    looking at: "we could not create your invite, here is how to reach me" is a recoverable
    moment, and a 500 on the page that is supposed to deliver the product is not.
    """
    if not vip_configured():
        return None
    body = {
        "chat_id": VIP_CHAT_ID,
        "name": invite_label(user),
        # ONE PERSON. Not a shared link with a big limit — see the note above.
        "member_limit": 1,
        # NO EXPIRY, deliberately. The link dies when it is used, so the thing an expiry
        # would protect against is already handled; what an expiry WOULD do is break the
        # link for somebody who signed up on a Friday and opened the email on Monday.
    }
    try:
        async with httpx.AsyncClient(timeout=20) as hc:
            r = await hc.post(
                f"https://api.telegram.org/bot{BOT_TOKEN}/createChatInviteLink", json=body)
        data = r.json() if r.status_code == 200 else {}
        if not data.get("ok"):
            # The body names the cause — "not enough rights to manage chat invite link" is
            # the one to expect, and it means the bot is not an admin of the channel.
            logger.warning("telegram createChatInviteLink %s: %s",
                           r.status_code, r.text[:300])
            return None
        return (data.get("result") or {}).get("invite_link")
    except Exception:
        logger.exception("telegram createChatInviteLink failed")
        return None


async def revoke_invite(link: str) -> bool:
    """Kill a link that has not been used yet. For a subscription that lapsed before the
    person ever joined — otherwise the invite outlives the thing it was issued for."""
    if not vip_configured() or not link:
        return False
    try:
        async with httpx.AsyncClient(timeout=20) as hc:
            r = await hc.post(f"https://api.telegram.org/bot{BOT_TOKEN}/revokeChatInviteLink",
                              json={"chat_id": VIP_CHAT_ID, "invite_link": link})
        return r.status_code == 200 and (r.json() or {}).get("ok") is True
    except Exception:
        logger.exception("telegram revokeChatInviteLink failed")
        return False


def joined_via(update: dict) -> tuple[Optional[str], Optional[dict]]:
    """Did somebody just join the channel through one of our links?

    Returns (invite_link, telegram_user) for a join, and (None, None) for everything else
    a `chat_member` update covers — leaving, being removed, a promotion.

    THIS IS THE ONLY WAY TO MAP A TELEGRAM ACCOUNT TO A SUBSCRIPTION. Nothing else connects
    them: the person pays on the website as one identity and appears in the channel as
    another, and the invite link is the single thread running between the two. Without
    recording it there is no way to remove the right person when a subscription ends, which
    is the whole reason a paid channel leaks.
    """
    cm = update.get("chat_member") or {}
    new = cm.get("new_chat_member") or {}
    old = cm.get("old_chat_member") or {}
    # "member" covers joining; restricted-but-present counts too. What matters is that they
    # were NOT in before and are now, so a promotion of an existing member is not a join.
    was_in = old.get("status") in ("member", "administrator", "creator")
    is_in = new.get("status") in ("member", "administrator", "creator")
    if was_in or not is_in:
        return None, None
    link = (cm.get("invite_link") or {}).get("invite_link")
    return link, (new.get("user") or None)


async def remove_member(tg_user_id) -> bool:
    """Take a lapsed subscriber out of the paid channel.

    BAN THEN IMMEDIATELY UNBAN, and the unban is not optional. `banChatMember` on its own
    removes them AND blocks them forever — so somebody who cancels in March and resubscribes
    in June could never get back in, and the failure would look like a broken invite link
    rather than a ban nobody remembers setting. Unbanning straight afterwards leaves them
    removed but free to rejoin, which is the actual intent: they stopped paying, they did
    not do anything wrong.

    Their old invite cannot let them back in regardless — it was single-use and spent the
    moment they joined.

    THE BAN IS THE PART THAT MATTERS, so its result is what is returned. `only_if_banned`
    keeps the unban from touching anybody the ban did not catch.
    """
    if not vip_configured() or not tg_user_id:
        return False
    try:
        async with httpx.AsyncClient(timeout=20) as hc:
            banned = await hc.post(
                f"https://api.telegram.org/bot{BOT_TOKEN}/banChatMember",
                json={"chat_id": VIP_CHAT_ID, "user_id": tg_user_id})
            ok = banned.status_code == 200 and (banned.json() or {}).get("ok") is True
            if not ok:
                logger.warning("telegram banChatMember %s: %s",
                               banned.status_code, banned.text[:300])
                return False
            # Best effort, and deliberately not allowed to change the answer: they are out,
            # which was the point. A failed unban leaves them unable to rejoin later, which
            # is worth the warning it writes but is not worth reporting the removal as
            # failed and having the caller retry the whole thing.
            un = await hc.post(
                f"https://api.telegram.org/bot{BOT_TOKEN}/unbanChatMember",
                json={"chat_id": VIP_CHAT_ID, "user_id": tg_user_id, "only_if_banned": True})
            if un.status_code != 200:
                logger.warning("telegram unbanChatMember %s: %s — %s is removed but cannot "
                               "rejoin until this is undone by hand",
                               un.status_code, un.text[:300], tg_user_id)
        return True
    except Exception:
        logger.exception("telegram remove_member failed")
        return False
