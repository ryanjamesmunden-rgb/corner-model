# Rotating the bot token and the tools token

## Why this exists

Two credentials were written to Render's logs for months, in the ordinary course of both
libraries doing what they do by default:

- **The Telegram bot token is in a URL path.** Telegram authenticates by putting it there —
  `https://api.telegram.org/bot<TOKEN>/sendMessage` — and httpx logs every request it makes
  at INFO. `server.py` calls `logging.basicConfig(INFO)`, so the full token was written on
  every message the bot sent, many times a day.
- **The tools token is in a query string.** Twenty-nine endpoints take `?token=`, and an
  access log records the path with its query string attached.

`backend/log_redact.py` closed both leaks going forward. **It does not undo the ones already
written.** Anything that read those logs before the fix has both credentials, so they have
to be replaced.

Neither is catastrophic on its own — the bot token can post as the bot and read its updates,
the tools token can start harnesses and re-register the webhook — but between them they are
the operator's whole surface, and there is no reason to leave them out.

## What is NOT affected

`TELEGRAM_WEBHOOK_SECRET` travels in an HTTP **header** (`X-Telegram-Bot-Api-Secret-Token`),
never in a URL, so it was never logged. It does not need rotating on these grounds. Leave it
alone: changing it means re-registering the webhook for a reason that does not exist.

Stripe keys are unaffected for the same reason — they go in an `Authorization` header.

## Order matters

Rotate the **tools token first**. Step 6 re-registers the Telegram webhook and is gated by
the tools token, so doing it the other way round means doing that step with a credential you
are about to replace.

## The steps

### 1. Generate a new tools token

Any long random string. On any machine:

```
python3 -c "import secrets; print(secrets.token_urlsafe(32))"
```

### 2. Put it in Render

Render dashboard → the backend service → **Environment** → edit `TOOLS_TOKEN` → save.
Render redeploys. Wait for it to go live before step 3, or the harness will reject the new
token while the old one is still serving.

### 3. Put it in GitHub

Repo → **Settings** → **Secrets and variables** → **Actions** → `TOOLS_TOKEN` → update.

The workflows that need it: `harness.yml`, `social_draft.yml`. Both read it as
`secrets.TOOLS_TOKEN`, so there is nothing to edit in the files themselves.

### 4. Revoke the bot token

Telegram → **@BotFather** → `/revoke` → pick the bot. It issues a new token and the old one
stops working **immediately**.

> The bot is down from this moment until step 5's redeploy finishes. That is a few minutes
> of the channel not receiving posts and `/`-commands not answering. Nothing is lost —
> the workflows that post run on a cron and the next one picks up the new token — but do
> not do this five minutes before a card is due.

### 5. Put the new bot token in both places

- Render → **Environment** → `TELEGRAM_BOT_TOKEN` → save, and let it redeploy.
- GitHub → **Actions secrets** → `TELEGRAM_BOT_TOKEN` → update.

Both are needed and they are used by different things: the backend sends from Render, and
the draft workflows send from Actions.

### 6. Re-register the webhook

**This step is the one that gets forgotten.** Telegram stores the webhook against the token,
so a new token has no webhook and the bot will send fine while receiving nothing — which
looks like the bot working.

```
curl -X POST "https://corner-model.onrender.com/api/telegram/register?token=<NEW_TOOLS_TOKEN>"
```

No body needed: `url` defaults to the request's own origin, which is also the address least
likely to be typed wrong.

### 7. Check it

- `curl "https://corner-model.onrender.com/api/telegram/status?token=<NEW_TOOLS_TOKEN>"` —
  reports whether the bot token and webhook secret are set.
- Send the bot a `/` command in Telegram. A reply means the webhook is registered; silence
  means step 6 did not take.
- Run any harness from the Actions tab. A 401 means the GitHub secret in step 3 is stale.

## Afterwards

Nothing in the repo holds either value, so there is nothing to commit. If Render offers to
purge historical logs, that is worth doing as well — the redaction stops new records being
written, it does not rewrite old ones.
