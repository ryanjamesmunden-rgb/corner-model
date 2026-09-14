"""The bot's inbound half.

Two failures are worth guarding against and neither is a crash. One is a forged update
being answered as though a person had typed it — the webhook URL is public, so the shared
secret is the only thing separating the two. The other is the bot talking when it should be
quiet: a bot that replies to every message in a group is a bot that gets muted, and then
nobody notices it has also stopped answering the commands that matter.
"""
import os
import sys
import importlib

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _bot(secret="s3cret", token="123:abc"):
    """A freshly imported module, so the env is read rather than inherited from whatever
    imported it first."""
    os.environ["TELEGRAM_WEBHOOK_SECRET"] = secret
    os.environ["TELEGRAM_BOT_TOKEN"] = token
    import telegram_bot
    return importlib.reload(telegram_bot)


def msg(text, chat_type="private", chat_id=42, update_id=1):
    return {"update_id": update_id,
            "message": {"message_id": 7, "text": text,
                        "chat": {"id": chat_id, "type": chat_type}}}


class TestSecret:
    def test_the_right_secret_passes_and_a_wrong_one_does_not(self):
        b = _bot(secret="s3cret")
        assert b.verify("s3cret") is True
        assert b.verify("s3cre") is False
        assert b.verify("S3CRET") is False

    def test_no_header_is_refused(self):
        # An attacker who finds the URL sends no header at all. That must not pass.
        b = _bot(secret="s3cret")
        assert b.verify(None) is False
        assert b.verify("") is False

    def test_an_unset_secret_refuses_everything(self):
        # The dangerous failure mode: no secret configured, so every check passes and the
        # bot answers anyone. It must fail CLOSED.
        b = _bot(secret="")
        assert b.verify("anything") is False
        assert b.verify("") is False
        assert b.configured() is False

    def test_configured_needs_both_halves(self):
        # They fail differently: no secret means forged updates get answered, no token
        # means nothing can be replied to at all.
        assert _bot(secret="x", token="").configured() is False
        assert _bot(secret="", token="y").configured() is False
        assert _bot(secret="x", token="y").configured() is True


class TestParsing:
    def test_command_and_argument(self):
        b = _bot()
        assert b.parse_command("/team Viking FK") == ("team", "Viking FK")
        assert b.parse_command("/help") == ("help", "")

    def test_the_at_mention_is_stripped(self):
        # In a group Telegram delivers "/help@TheCornerModelBot". Matching the raw string
        # means the bot answers in DMs and goes silent in exactly the place several people
        # can see it.
        b = _bot()
        assert b.parse_command("/help@TheCornerModelBot") == ("help", "")
        assert b.parse_command("/team@TheCornerModelBot Brann") == ("team", "Brann")

    def test_plain_text_is_not_a_command(self):
        b = _bot()
        assert b.parse_command("what are the streaks") == (None, "")
        assert b.parse_command("") == (None, "")
        assert b.parse_command(None) == (None, "")

    def test_case_and_whitespace_do_not_matter(self):
        b = _bot()
        assert b.parse_command("  /HELP  ") == ("help", "")


class TestReplies:
    def test_start_and_help_both_answer(self):
        b = _bot()
        assert b.reply_for(msg("/start")) == b.HELP
        assert b.reply_for(msg("/help")) == b.HELP

    def test_help_lists_only_what_exists(self):
        # The daily angle menu already ends "Reply with a number and I'll write that one
        # up" at a bot that cannot hear it. Listing /value here before /value exists would
        # be the same mistake in the other direction.
        b = _bot()
        assert "/help" in b.HELP
        for unbuilt in ("/value", "/game", "/streaks", "/weekend"):
            assert unbuilt not in b.HELP

    def test_a_group_gets_silence_for_anything_it_did_not_ask_for(self):
        # A bot that replies to every message in a group is one that gets removed.
        b = _bot()
        assert b.reply_for(msg("morning all", chat_type="group")) is None
        assert b.reply_for(msg("/nonsense", chat_type="group")) is None

    def test_but_a_known_command_still_answers_in_a_group(self):
        b = _bot()
        assert b.reply_for(msg("/help@TheCornerModelBot", chat_type="group")) == b.HELP

    def test_a_dm_never_goes_into_a_void(self):
        # In a DM there is nobody else to annoy and the message is unambiguously for the
        # bot, so an unrecognised one gets pointed somewhere rather than dropped.
        b = _bot()
        assert "/help" in b.reply_for(msg("hello?"))
        assert "/help" in b.reply_for(msg("/value"))

    def test_an_unknown_command_does_not_pretend_to_know_it(self):
        b = _bot()
        out = b.reply_for(msg("/value"))
        assert "don't know" in out and "value" in out

    def test_a_message_with_no_text_does_not_throw(self):
        # A sticker, a photo, a joined-the-group notice. All arrive here.
        b = _bot()
        assert b.reply_for({"update_id": 2, "message": {"chat": {"id": 1, "type": "group"}}}) is None
        assert b.reply_for({}) is None

    def test_chat_id_is_found_or_none(self):
        b = _bot()
        assert b.chat_id_of(msg("/help", chat_id=99)) == 99
        assert b.chat_id_of({}) is None

    def test_help_fits_in_one_telegram_message(self):
        # Over 4096 and Telegram answers HTTP 400 with nothing else — the failure that ate
        # the weekend card twice.
        b = _bot()
        assert len(b.HELP) <= b.MAX_MESSAGE


class TestPickReply:
    """Reading "3 @ 1.80 1.5u".

    The dangerous failure is not a rejected message — it is a MISREAD one. A number read
    as a price when it was meant as a stake writes a wrong price into the record, and that
    record later becomes a units figure on a results graphic.
    """

    def parse(self, t):
        return _bot().parse_pick_reply(t)

    def test_just_a_number(self):
        assert self.parse("3") == {"n": 3, "price": None, "stake": None}

    def test_price_with_and_without_the_at(self):
        assert self.parse("3 @ 1.80")["price"] == 1.8
        assert self.parse("3 1.80")["price"] == 1.8

    def test_price_and_stake(self):
        got = self.parse("3 @ 1.80 1.5u")
        assert got == {"n": 3, "price": 1.8, "stake": 1.5}

    def test_a_stake_must_carry_its_u(self):
        # "3 2" is genuinely ambiguous between "pick 3 at 2.0" and "pick 3, two units".
        # It resolves to a price, and the help text says so — guessing the other way
        # writes a wrong price that later becomes units on a graphic.
        assert self.parse("3 2") == {"n": 3, "price": 2.0, "stake": None}
        assert self.parse("3 2u") == {"n": 3, "price": None, "stake": 2.0}

    def test_the_stake_is_claimed_before_the_price_is_looked_for(self):
        # Otherwise "3 1.5u" reads 1.5 as a price and the stake vanishes.
        assert self.parse("3 1.5u") == {"n": 3, "price": None, "stake": 1.5}

    def test_a_price_at_or_below_evens_is_not_a_price(self):
        assert self.parse("3 @ 1.00")["price"] is None
        assert self.parse("3 @ 0.90")["price"] is None

    def test_slash_and_the_word_pick_are_both_accepted(self):
        assert self.parse("/pick 3 @ 1.8")["n"] == 3
        assert self.parse("pick 3")["n"] == 3

    def test_things_that_are_not_a_pick(self):
        assert self.parse("/help") is None
        assert self.parse("hello") is None
        assert self.parse("") is None
        assert self.parse(None) is None
        assert self.parse("0") is None          # menus are 1-indexed

    def test_the_help_names_the_ambiguity_it_refuses_to_resolve(self):
        b = _bot()
        assert "u" in b.PICK_HELP
        assert "price" in b.PICK_HELP.lower()
