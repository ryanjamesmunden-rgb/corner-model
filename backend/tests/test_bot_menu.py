"""The bot's menu button.

TAPPING A MENU ITEM SENDS THAT COMMAND IMMEDIATELY, which is what makes this list different
from a help text. A menu offering something the bot does not handle has people send it and
be told it does not exist — the bot looks broken at the exact moment somebody first explores
it, which is worse than having no menu at all.

So the guard is not "does setMyCommands succeed". It is: every command in the menu is
answered, and a bare command — which is precisely what the button sends — is answered too.
"""
import os
import sys
import importlib

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _bot():
    os.environ["TELEGRAM_BOT_TOKEN"] = "123:abc"
    os.environ["TELEGRAM_WEBHOOK_SECRET"] = "s3cret"
    import telegram_bot
    return importlib.reload(telegram_bot)


def msg(text, chat_type="private"):
    return {"update_id": 1,
            "message": {"message_id": 1, "text": text, "chat": {"id": 7, "type": chat_type}}}


class TestEveryMenuItemIsAnswered:
    def test_the_bare_command_gets_a_real_answer(self):
        # THE ONE THAT MATTERS. The menu button inserts "/pick" with nothing after it, and
        # plenty of people send it as-is to see what happens. This used to answer "I don't
        # know /pick yet" — about the most useful thing the bot does.
        b = _bot()
        for cmd in b.COMMANDS:
            out = b.reply_for(msg(f"/{cmd['command']}"))
            assert out, f"/{cmd['command']} is in the menu and answers nothing"
            assert "don't know" not in out, f"/{cmd['command']} is in the menu and is unknown"

    def test_pick_with_an_argument_still_parses_as_a_pick(self):
        # The bare form answering help must not have broken the form that does the work.
        b = _bot()
        assert b.parse_pick_reply("/pick 3 @ 1.80 1.5u") == {"n": 3, "price": 1.8, "stake": 1.5}

    def test_bare_pick_is_not_mistaken_for_a_pick(self):
        # It has no number, so it must fall through to the help rather than logging
        # something. parse_pick_reply is consulted first in the reply path.
        b = _bot()
        assert b.parse_pick_reply("/pick") is None

    def test_the_pick_answer_explains_the_syntax(self):
        b = _bot()
        out = b.reply_for(msg("/pick"))
        assert "@" in out and "u" in out

    def test_help_still_answers(self):
        b = _bot()
        assert b.reply_for(msg("/help")) == b.HELP
        assert b.reply_for(msg("/start")) == b.HELP


class TestTheListIsWhatWorks:
    def test_nothing_unbuilt_is_advertised(self):
        # Same rule the help text follows. A menu is a stronger promise than a help line,
        # because the item is tappable.
        b = _bot()
        names = {c["command"] for c in b.COMMANDS}
        for unbuilt in ("value", "game", "streaks", "weekend", "board", "results"):
            assert unbuilt not in names

    def test_telegrams_own_limits_are_respected(self):
        # Lowercase, 1-32 chars, description 1-256. Telegram rejects the whole call on any
        # one bad entry, so the menu would simply never appear.
        b = _bot()
        assert b.COMMANDS, "an empty menu is not a menu"
        for c in b.COMMANDS:
            name = c["command"]
            assert name == name.lower()
            assert 1 <= len(name) <= 32
            assert all(ch.isalnum() or ch == "_" for ch in name)
            assert 1 <= len(c["description"]) <= 256

    def test_a_description_says_what_it_does_rather_than_repeating_the_name(self):
        b = _bot()
        for c in b.COMMANDS:
            assert c["description"].lower() != c["command"].lower()
            assert len(c["description"]) > len(c["command"])


class TestScope:
    def test_the_menu_is_private_chats_only(self, monkeypatch):
        # /pick is meaningless in a group: a pick is logged against whoever sent it, and the
        # bot deliberately ignores numbers typed in a group because "3" there is somebody
        # talking. Offering a command in a room where it is ignored is the same
        # broken-looking failure the list exists to avoid.
        import asyncio
        b = _bot()
        sent = {}

        class _Resp:
            status_code = 200
            text = ""
            @staticmethod
            def json(): return {"ok": True, "result": True}

        class _Client:
            def __init__(self, **kw): pass
            async def __aenter__(self): return self
            async def __aexit__(self, *a): return False
            async def post(self, url, json=None):
                sent.update(json or {})
                return _Resp()

        monkeypatch.setattr(b.httpx, "AsyncClient", _Client)
        asyncio.get_event_loop().run_until_complete(b.set_my_commands())
        assert sent["scope"] == {"type": "all_private_chats"}
        assert [c["command"] for c in sent["commands"]] == [c["command"] for c in b.COMMANDS]

    def test_a_group_still_gets_silence_for_things_it_did_not_ask_for(self):
        b = _bot()
        assert b.reply_for(msg("morning all", chat_type="group")) is None
        assert b.reply_for(msg("just chatting", chat_type="group")) is None

    def test_pick_in_a_group_is_redirected_rather_than_explained(self):
        # Printing the syntax in a room where picks are ignored invites somebody to try
        # something that then does nothing. One line, and it names where it does work.
        b = _bot()
        out = b.reply_for(msg("/pick", chat_type="group"))
        assert "direct message" in out
        # Short: a bot that talks in a group is a bot that gets removed from it.
        assert len(out) < 120
        # And it must NOT be the full syntax block.
        assert out != b.PICK_HELP


class TestRegistrationPutsTheMenuUp:
    def test_register_sets_the_menu_as_well_as_the_webhook(self):
        # The two are one setup step in practice, and a separate command nobody remembers
        # to run is a menu that never appears — the state this bot sat in for weeks.
        import inspect
        os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
        os.environ.setdefault("DB_NAME", "test_corner_model")
        import server
        src = inspect.getsource(server.telegram_register)
        assert "set_my_commands" in src

    def test_but_a_menu_failure_does_not_fail_the_registration(self):
        # The webhook is what makes the bot work; the menu only makes it findable. Failing
        # the whole thing over the decoration would leave a bot that cannot hear at all.
        import inspect
        import server
        src = inspect.getsource(server.telegram_register)
        assert "except Exception" in src
