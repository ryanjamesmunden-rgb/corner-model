"""Getting a paying member into the paid channel.

Two failures matter. One is a shareable invite: a link that more than one person can use is
a paid room with unpaid people in it, and no way to tell which is which. The other is losing
the thread between a Telegram account and a subscription — without it a lapsed member cannot
be removed, because nobody knows which member they are.
"""
import os
import sys
import importlib

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _bot(vip="-1001234567890", token="123:abc"):
    os.environ["TELEGRAM_BOT_TOKEN"] = token
    os.environ["TELEGRAM_VIP_CHAT_ID"] = vip
    os.environ["TELEGRAM_WEBHOOK_SECRET"] = "s3cret"
    import telegram_bot
    return importlib.reload(telegram_bot)


def join(link="https://t.me/+abc", uid=555, username="someone",
         was="left", now="member"):
    return {"update_id": 1, "chat_member": {
        "chat": {"id": -1001234567890, "type": "channel"},
        "old_chat_member": {"status": was, "user": {"id": uid}},
        "new_chat_member": {"status": now, "user": {"id": uid, "username": username}},
        **({"invite_link": {"invite_link": link}} if link else {}),
    }}


class TestConfigured:
    def test_needs_both_a_token_and_a_channel(self):
        assert _bot().vip_configured() is True
        assert _bot(vip="").vip_configured() is False
        assert _bot(token="").vip_configured() is False


class TestInviteLabel:
    def test_it_prefers_the_name_on_the_card(self):
        b = _bot()
        assert b.invite_label({"billing_name": "Jane Smith", "email": "j@x.com"}) == "Jane Smith"

    def test_falling_back_to_the_email_when_stripe_gave_no_name(self):
        b = _bot()
        assert b.invite_label({"email": "j@x.com"}) == "j@x.com"

    def test_and_to_something_rather_than_nothing(self):
        b = _bot()
        assert b.invite_label({}) == "member"
        assert b.invite_label(None) == "member"

    def test_it_is_cut_to_telegrams_limit(self):
        # Telegram answers a name over 32 characters with an error rather than truncating,
        # so a member with a long email would get no invite at all.
        b = _bot()
        long = "a" * 40 + "@averylongdomainname.example.com"
        assert len(b.invite_label({"email": long})) == 32


class TestJoinedVia:
    def test_a_join_through_one_of_our_links_is_recognised(self):
        b = _bot()
        link, user = b.joined_via(join(link="https://t.me/+xyz", uid=99))
        assert link == "https://t.me/+xyz"
        assert user["id"] == 99

    def test_a_join_with_no_invite_link_still_reports_the_person(self):
        # Added by hand in the Telegram app rather than through a link this site issued.
        # The caller has to be able to tell that apart from "not a join", because an
        # arrival nobody can account for is also what an unpaid member looks like.
        b = _bot()
        link, user = b.joined_via(join(link=None))
        assert link is None
        assert user["id"] == 555

    def test_leaving_is_not_joining(self):
        b = _bot()
        assert b.joined_via(join(was="member", now="left")) == (None, None)
        assert b.joined_via(join(was="member", now="kicked")) == (None, None)

    def test_a_promotion_of_someone_already_in_is_not_a_join(self):
        # They were a member and became an admin. Nobody arrived, and treating it as an
        # arrival would rewrite the mapping for a link that was spent long ago.
        b = _bot()
        assert b.joined_via(join(was="member", now="administrator")) == (None, None)

    def test_anything_that_is_not_a_membership_change_is_ignored(self):
        b = _bot()
        assert b.joined_via({"message": {"text": "hello"}}) == (None, None)
        assert b.joined_via({}) == (None, None)


class TestCreateInvite:
    def test_the_link_is_single_use(self, monkeypatch):
        # THE WHOLE DESIGN. A shared link gets forwarded and screenshotted, and there is
        # then no way to tell who in the channel paid.
        import asyncio
        b = _bot()
        sent = {}

        class _Resp:
            status_code = 200
            text = ""
            @staticmethod
            def json():
                return {"ok": True, "result": {"invite_link": "https://t.me/+new"}}

        class _Client:
            def __init__(self, **kw): pass
            async def __aenter__(self): return self
            async def __aexit__(self, *a): return False
            async def post(self, url, json=None):
                sent.update(json or {})
                return _Resp()

        monkeypatch.setattr(b.httpx, "AsyncClient", _Client)
        link = asyncio.get_event_loop().run_until_complete(
            b.create_invite({"billing_name": "Jane Smith"}))
        assert link == "https://t.me/+new"
        assert sent["member_limit"] == 1
        assert sent["name"] == "Jane Smith"

    def test_telegram_refusing_gives_none_rather_than_raising(self, monkeypatch):
        # The caller is an endpoint a paying member is looking at. "Could not create your
        # invite, here is how to reach me" is recoverable; a 500 on the page that delivers
        # the product is not.
        import asyncio
        b = _bot()

        class _Resp:
            status_code = 400
            text = "not enough rights to manage chat invite link"
            @staticmethod
            def json(): return {"ok": False}

        class _Client:
            def __init__(self, **kw): pass
            async def __aenter__(self): return self
            async def __aexit__(self, *a): return False
            async def post(self, url, json=None): return _Resp()

        monkeypatch.setattr(b.httpx, "AsyncClient", _Client)
        assert asyncio.get_event_loop().run_until_complete(b.create_invite({})) is None

    def test_an_unconfigured_channel_makes_no_call_at_all(self):
        import asyncio
        b = _bot(vip="")
        assert asyncio.get_event_loop().run_until_complete(b.create_invite({})) is None


class TestWebhookAsksForMemberUpdates:
    def test_chat_member_is_in_allowed_updates(self):
        # Telegram NEVER sends chat_member unless it is asked for by name, even to an admin
        # bot, and its absence is silent — the mapping would simply never be recorded.
        import inspect
        b = _bot()
        src = inspect.getsource(b.set_webhook)
        assert '"chat_member"' in src
