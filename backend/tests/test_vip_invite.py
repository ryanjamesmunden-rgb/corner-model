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

# server.py reads these at import time. Set before anything imports it, the same way
# every other suite here does.
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "test_corner_model")


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


class TestRemoveMember:
    """Taking a lapsed subscriber back out of the channel."""

    def _client(self, monkeypatch, b, calls, ban_ok=True, unban_status=200):
        class _Resp:
            def __init__(self, path):
                self.path = path
                self.status_code = 200 if ("ban" not in path or ban_ok) else 400
                if "unbanChatMember" in path:
                    self.status_code = unban_status
                self.text = ""

            def json(self):
                return {"ok": self.status_code == 200}

        class _Client:
            def __init__(self, **kw): pass
            async def __aenter__(self): return self
            async def __aexit__(self, *a): return False
            async def post(self, url, json=None):
                calls.append((url.rsplit("/", 1)[-1], json))
                return _Resp(url)

        monkeypatch.setattr(b.httpx, "AsyncClient", _Client)

    def test_the_ban_is_followed_by_an_unban(self, monkeypatch):
        # THE UNBAN IS NOT OPTIONAL. banChatMember alone removes them AND blocks them
        # forever, so someone who cancels in March and resubscribes in June could never
        # get back in — and it would look like a broken invite rather than a ban.
        import asyncio
        b = _bot()
        calls = []
        self._client(monkeypatch, b, calls)
        assert asyncio.get_event_loop().run_until_complete(b.remove_member(555)) is True
        assert [c[0] for c in calls] == ["banChatMember", "unbanChatMember"]
        assert calls[0][1]["user_id"] == 555
        # only_if_banned so the unban cannot touch anybody the ban did not catch.
        assert calls[1][1]["only_if_banned"] is True

    def test_a_failed_unban_still_reports_them_removed(self, monkeypatch):
        # They are out, which was the point. Reporting failure would have the caller retry
        # the whole removal for something already done.
        import asyncio
        b = _bot()
        calls = []
        self._client(monkeypatch, b, calls, unban_status=400)
        assert asyncio.get_event_loop().run_until_complete(b.remove_member(555)) is True

    def test_a_failed_ban_reports_failure_and_does_not_unban(self, monkeypatch):
        # Unbanning somebody who was never banned would be a no-op at best; the point is
        # that the caller has to hear that the removal did not happen.
        import asyncio
        b = _bot()
        calls = []
        self._client(monkeypatch, b, calls, ban_ok=False)
        assert asyncio.get_event_loop().run_until_complete(b.remove_member(555)) is False
        assert [c[0] for c in calls] == ["banChatMember"]

    def test_nothing_is_called_without_a_telegram_id_or_a_channel(self, monkeypatch):
        import asyncio
        calls = []
        b = _bot()
        self._client(monkeypatch, b, calls)
        loop = asyncio.get_event_loop()
        assert loop.run_until_complete(b.remove_member(None)) is False
        assert loop.run_until_complete(b.remove_member(0)) is False
        b2 = _bot(vip="")
        self._client(monkeypatch, b2, calls)
        assert loop.run_until_complete(b2.remove_member(555)) is False
        assert calls == []


class TestRemovalIsKeyedOnAccessNotStatus:
    """The webhook must remove people only when access actually ended."""

    def test_it_keys_on_the_membership_apply_subscription_settled_on(self):
        # A grandfathered account keeps access when a later subscription lapses, and so
        # does a comp with a lapsed one. `past_due` is still a member — a failed renewal is
        # a retry window, and kicking somebody out over a card blip turns a payment problem
        # into a cancellation. Keying on sub.status would remove all of them.
        import inspect
        import server
        src = inspect.getsource(server.billing_webhook)
        assert 'result.get("member") is False' in src
        assert 'result.get("matched")' in src
        # ...and specifically NOT on the Stripe status.
        assert 'status") == "canceled"' not in src

    def test_the_stored_invite_is_cleared_so_a_resubscribe_gets_a_fresh_one(self):
        # The endpoint returns the stored link when there is one, so leaving a spent or
        # revoked link behind would hand a returning customer a dead button.
        import inspect
        import server
        src = inspect.getsource(server._revoke_channel_access)
        assert '"$unset"' in src and "vip_invite_link" in src

    def test_a_telegram_failure_cannot_fail_the_webhook(self):
        # Stripe retries a non-2xx, and the retry would re-run apply_subscription to reach
        # the same failure — marking the endpoint unhealthy over a Telegram outage.
        import inspect
        import server
        src = inspect.getsource(server._revoke_channel_access)
        assert "except Exception" in src


class TestVipPreflight:
    """The setup check. Three parts, two of them invisible from the dashboard."""

    def _resp(self, ok=True, result=None, desc=None, status=200):
        class _R:
            status_code = status
            text = desc or ""
            @staticmethod
            def json():
                return {"ok": ok, **({"result": result} if result is not None else {}),
                        **({"description": desc} if desc else {})}
        return _R()

    def _wire(self, monkeypatch, b, responses):
        class _Client:
            def __init__(self, **kw): pass
            async def __aenter__(self): return self
            async def __aexit__(self, *a): return False
            async def get(self, url, params=None):
                return responses[url.rsplit("/", 1)[-1]]
        monkeypatch.setattr(b.httpx, "AsyncClient", _Client)

    def run(self, b):
        import asyncio
        return asyncio.get_event_loop().run_until_complete(b.vip_check())

    def test_a_fully_wired_channel_reports_clean(self, monkeypatch):
        b = _bot()
        self._wire(monkeypatch, b, {
            "getChat": self._resp(result={"title": "Corner Model VIP", "type": "channel"}),
            "getMe": self._resp(result={"id": 99}),
            "getChatMember": self._resp(result={"status": "administrator",
                                                "can_invite_users": True}),
        })
        assert self.run(b) == {"chat_id_set": True, "reachable": True,
                               "title": "Corner Model VIP", "type": "channel",
                               "bot_is_admin": True, "can_invite": True, "error": None}

    def test_an_id_can_be_checked_before_it_is_configured(self, monkeypatch):
        # Setting the variable had been a guess with a redeploy attached: paste, wait, read,
        # find out it was wrong, repeat. Telegram will answer in one call.
        import asyncio
        b = _bot(vip="-100000000000")
        seen = {}

        class _Client:
            def __init__(self, **kw): pass
            async def __aenter__(self): return self
            async def __aexit__(self, *a): return False
            async def get(self, url, params=None):
                name = url.rsplit("/", 1)[-1]
                seen[name] = (params or {}).get("chat_id")
                return {
                    "getChat": TestVipPreflight._resp(self, result={
                        "title": "[VIP] TheCornerMODEL2.0", "type": "channel"}),
                    "getMe": TestVipPreflight._resp(self, result={"id": 99}),
                    "getChatMember": TestVipPreflight._resp(self, result={
                        "status": "administrator", "can_invite_users": True}),
                }[name]

        monkeypatch.setattr(b.httpx, "AsyncClient", _Client)
        out = asyncio.get_event_loop().run_until_complete(
            b.vip_check(chat_id="-1004417868848"))
        # The probed id is what Telegram was asked about, not the configured one.
        assert seen["getChat"] == "-1004417868848"
        assert out["can_invite"] is True and out["title"] == "[VIP] TheCornerMODEL2.0"
        # And the answer can never be mistaken for the live configuration's.
        assert out["probed"] == "-1004417868848"

    def test_a_plain_check_still_reads_the_configured_channel(self, monkeypatch):
        b = _bot()
        self._wire(monkeypatch, b, {
            "getChat": self._resp(result={"title": "VIP", "type": "channel"}),
            "getMe": self._resp(result={"id": 99}),
            "getChatMember": self._resp(result={"status": "administrator",
                                                "can_invite_users": True}),
        })
        assert "probed" not in self.run(b)

    def test_an_id_that_is_not_the_channel_says_so(self, monkeypatch):
        # FOUND LIVE, and it had survived two rounds of somebody checking the admin list.
        # TELEGRAM_VIP_CHAT_ID held a personal Telegram id rather than the channel's.
        # getChat succeeds for any chat the bot can see, so "reachable" was true; a private
        # chat has no title, so that row rendered blank and looked merely cosmetic; and
        # getChatMember reported no admin status, so the check said "in the channel but not
        # an admin" — about a chat that was not the channel. Every symptom pointed at the
        # permission, and the permission was fine.
        b = _bot()
        self._wire(monkeypatch, b, {
            "getChat": self._resp(result={"type": "private", "first_name": "Ryan"}),
            "getMe": self._resp(result={"id": 99}),
            "getChatMember": self._resp(result={"status": "member"}),
        })
        out = self.run(b)
        assert out["type"] == "private"
        assert "private chat" in out["error"] and "-100" in out["error"]

    def test_the_not_an_admin_message_names_what_it_looked_at(self, monkeypatch):
        # "the bot is in the channel but is not an admin of it" asserted the thing that was
        # actually wrong. It now reports what getChat said it was.
        b = _bot()
        self._wire(monkeypatch, b, {
            "getChat": self._resp(result={"title": "Corner chat", "type": "group"}),
            "getMe": self._resp(result={"id": 99}),
            "getChatMember": self._resp(result={"status": "member"}),
        })
        assert "group" in self.run(b)["error"]

    def test_an_admin_without_the_invite_right_is_reported_separately(self, monkeypatch):
        # It fails in exactly the same way as not being an admin, and the fix is different,
        # so "it doesn't work" is not a diagnosis.
        b = _bot()
        self._wire(monkeypatch, b, {
            "getChat": self._resp(result={"title": "VIP", "type": "channel"}),
            "getMe": self._resp(result={"id": 99}),
            "getChatMember": self._resp(result={"status": "administrator",
                                                "can_invite_users": False}),
        })
        out = self.run(b)
        assert out["bot_is_admin"] is True and out["can_invite"] is False
        assert "invite-users permission" in out["error"]

    def test_in_the_channel_but_not_an_admin(self, monkeypatch):
        b = _bot()
        self._wire(monkeypatch, b, {
            "getChat": self._resp(result={"title": "VIP", "type": "channel"}),
            "getMe": self._resp(result={"id": 99}),
            "getChatMember": self._resp(result={"status": "member"}),
        })
        out = self.run(b)
        assert out["bot_is_admin"] is False
        assert "not an admin" in out["error"]

    def test_a_wrong_id_says_what_telegram_said(self, monkeypatch):
        # "chat not found" almost always means the id is wrong or the bot was never added,
        # and relaying it beats inventing a friendlier message that hides the cause.
        b = _bot()
        self._wire(monkeypatch, b, {"getChat": self._resp(ok=False, desc="chat not found")})
        out = self.run(b)
        assert out["reachable"] is False and out["error"] == "chat not found"

    def test_an_unset_channel_says_which_variable(self, monkeypatch):
        b = _bot(vip="")
        out = self.run(b)
        assert out["chat_id_set"] is False
        assert "TELEGRAM_VIP_CHAT_ID" in out["error"]

    def test_the_creator_counts_as_able_to_invite(self, monkeypatch):
        # The channel owner has every right without them being listed individually.
        b = _bot()
        self._wire(monkeypatch, b, {
            "getChat": self._resp(result={"title": "VIP", "type": "channel"}),
            "getMe": self._resp(result={"id": 99}),
            "getChatMember": self._resp(result={"status": "creator"}),
        })
        out = self.run(b)
        assert out["bot_is_admin"] is True and out["can_invite"] is True
        assert out["error"] is None
