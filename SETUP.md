# The Corner Model 2.0 — Self-Hosting / Handover Guide

This is everything needed to run the app on your own hosting after exporting the code.

## Stack
- **Frontend**: React (Create React App) + Tailwind + shadcn/ui. Talks to the backend via `REACT_APP_BACKEND_URL`.
- **Backend**: FastAPI (Python). All routes are prefixed with `/api`.
- **Database**: MongoDB.
- **Scheduler**: APScheduler cron inside the backend (data sync at 07:00 & 19:00 UTC, plus a self-heal sync on boot).

---

## 1. Environment variables

### `backend/.env`
| Key | Required | What it is |
|---|---|---|
| `MONGO_URL` | ✅ | MongoDB connection string (e.g. `mongodb://localhost:27017` or an Atlas SRV URL). |
| `DB_NAME` | ✅ | Database name (any name, e.g. `corner_model`). |
| `API_FOOTBALL_KEY` | ✅ | Your API-Football key (see §3). Without it, no real data syncs. |
| `API_FOOTBALL_SEASON` | ✅ | Season year the sync should target (e.g. `2026`). |
| `CORS_ORIGINS` | ✅ | Comma-separated list of allowed frontend origins, e.g. `https://your-site.com`. Use `*` only for quick testing. |
| `ANTHROPIC_API_KEY` | optional | Enables the "Why this angle?" explainer (see §4). Without it that one endpoint returns 503. |

> Deployment (Railway + Vercel), the scheduled jobs, and the `/api/health` check are documented in [DEPLOY.md](DEPLOY.md).

### `frontend/.env`
| Key | Required | What it is |
|---|---|---|
| `REACT_APP_BACKEND_URL` | ✅ | Public base URL of your backend, **without** a trailing `/api` (the app appends `/api`). E.g. `https://api.your-site.com`. |

> Note: On this platform an ingress routes `/api/*` to the backend and everything else to the frontend. On your own host you must reproduce that: either run frontend + backend behind one domain with `/api` proxied to the backend, or point `REACT_APP_BACKEND_URL` directly at the backend's public URL and set `CORS_ORIGINS` to the frontend origin.

---

## 2. Running it

```bash
# Backend
cd backend
pip install -r requirements.txt
uvicorn server:app --host 0.0.0.0 --port 8001

# Frontend
cd frontend
yarn install
yarn start          # dev
# or: yarn build    # production build in frontend/build
```

On first boot with real data missing/stale, the backend auto-launches the API-Football sync. To force a full sync manually:
```bash
cd backend && python sync_real.py            # all leagues
cd backend && python sync_real.py eng-pl      # one league
```

---

## 3. External dependency #1 — API-Football (REQUIRED)

- The app's real corner/shots/goals data comes from **API-Football** (https://www.api-football.com/). You need your own key.
- Set `API_FOOTBALL_KEY` and `API_FOOTBALL_SEASON` in `backend/.env`.
- A **Pro plan** is recommended (the app syncs 27 leagues twice daily; the free tier's daily request cap is too low). The app already minimises calls with a permanent `fixture_stats` cache (finished games are fetched once) — so recurring syncs are cheap, but the initial full sync is heavy.
- League set is defined in `backend/sync_real.py` (`LEAGUE_META`) and `MANAGED_LEAGUE_IDS` in `backend/server.py`. Trim these if you want fewer leagues / fewer API calls.

## 4. External dependency #2 — Claude explainer (OPTIONAL)

The "Why this angle?" button on Quick Scan uses Claude, through the **official Anthropic
SDK** (`anthropic`, already in `requirements.txt`). Set `ANTHROPIC_API_KEY` to enable it —
get a key at https://console.anthropic.com/.

Without the key the endpoint returns 503 and nothing else is affected: Best Teams,
Streaks, Chase Board, Picks and the Daily 2 ledger all work without it.

Implementation notes (`explain_pick` in `backend/server.py`): one shared
`AsyncAnthropic` client, `claude-opus-5` at `effort: "low"` (the answer is two
sentences, so low effort keeps a per-pick endpoint cheap), server-side refusal
fallbacks enabled, responses cached in `db.explanations` by a server-derived stats
hash, and a 20/minute per-user throttle on uncached calls.

> The Emergent LLM key and the `emergentintegrations` library are gone — they only ever
> worked inside Emergent, and the library was never in `requirements.txt`, so this
> endpoint was failing on any independent host.

> Emergent auth has also been removed: the app is public, with no sign-in. See §6 if you
> want to reintroduce accounts.

---

## 5. Seed / utility scripts (in `backend/`)
- `sync_real.py` — pulls real teams/fixtures/stats from API-Football (the main data job).
- `seed_picks.py` / `seed_manual_picks.py` — seed the Picks board.
- `settle_picks.py` — auto-settles picks Win/Loss from real results.
- `backfill_fh.py` / `backfill_goals.py` / `backfill_rounds.py` — one-off DB backfills (no API calls).
- `backfill_shots.py` — fills shot-volume features (shots, shots on target, blocked shots, dangerous attacks) onto this season's cached fixtures, then projects them onto `teams.real_matches`. **Spends one statistics call per un-filled fixture**, so it is capped per league (`--limit N`) and resumable; `--project-only` re-runs the DB half with no API calls.
- `reseed_odds.py` / `seed_team_odds.py` — placeholder-odds generators (optional; not needed since the app now leads with averages/streaks).
- `tune_model.py` / `probe_leagues.py` — analysis helpers.
- `measure_features.py` — offline walk-forward test of whether the shot-volume features (blocked shots, shots on target) improve corner prediction against the live v2 model. DB-only, no API calls, changes nothing. Guards against the three ways this measurement lies to you: same-sample scoring, mean-neutral intent terms, and a shuffled-feature placebo.

## 6. Auth note (important for independent hosting)
This build authenticates via **Emergent-managed Google OAuth** (`EMERGENT_SESSION_URL` in `server.py`). That endpoint is Emergent-only. For your own site, replace `/api/auth/session` with your own OAuth/JWT flow and keep the existing session-cookie pattern (`session_token` httpOnly cookie, `user_sessions` collection). Everything downstream reads the user from `get_current_user`, so only that one function + the login page need changing.

## 7. Data model (MongoDB collections)
`leagues`, `teams` (with `real_matches`), `fixtures`, `odds`, `users`, `user_sessions`, `picks`, `bets`, `sync_runs`, `fixture_stats` (permanent finished-match cache), `explanations` (LLM cache), `meta` (sync lock).

## 8. Payments, the free trial, and the Telegram bot

Everything in this section is set on the BACKEND host (Render). None of it is compiled into
the frontend — the page reads it from `/api/config` at runtime, which is deliberate: a page
advertising an offer the checkout cannot grant is the failure this whole area is designed
against, and build-time values drift from the server that enforces them.

### 8.1 Stripe (required for subscriptions)

| Key | Required | What it is |
|---|---|---|
| `STRIPE_SECRET_KEY` | ✅ | Secret key, `sk_live_…`. From [dashboard.stripe.com/apikeys](https://dashboard.stripe.com/apikeys). |
| `STRIPE_PRICE_ID` | ✅ | The recurring PRICE, `price_…` — not the product, which is `prod_…`. From the product's page. |
| `STRIPE_WEBHOOK_SECRET` | ✅ | Signing secret, `whsec_…`, created with the endpoint below. |
| `JOIN_URL` | fallback | A bare Stripe Payment Link, used ONLY while the three above are unset. |

**Until all three are set, `/api/config` reports `stripe_ready: false`** and the join page
falls back to `JOIN_URL`. That link is configured in the Stripe dashboard, so it carries no
trial and cannot be tied to an account — which means the trial, the signup window and the
account-linked channel invite are all unreachable, because every one of them hangs off the
Checkout Session the Payment Link bypasses. The page is honest about this and stops
advertising the trial (see `lib/trialOffer`), but the fix is to set the keys.

**The webhook endpoint.** In Stripe → Developers → Webhooks, add
`https://<your-backend>/api/billing/webhook` and subscribe to exactly:

- `checkout.session.completed`
- `customer.subscription.created`
- `customer.subscription.updated`
- `customer.subscription.deleted`

The signature check is not optional and has no unsigned fallback — this endpoint grants and
revokes paid access and is open to the internet by necessity, so without `STRIPE_WEBHOOK_SECRET`
it refuses everything.

### 8.2 The trial and the signup window

| Key | Default | What it is |
|---|---|---|
| `TRIAL_DAYS` | `7` | Free days on a first subscription. `0` turns the trial off. |
| `SIGNUP_DAY` | `1` (Monday) | ISO weekday the door is open, so trials start as a weekly cohort. `0` = always open. |
| `SIGNUP_SCOPE` | `trial` | `trial` gates only checkouts that would start one; `all` gates everybody. |

**Leave all three unset.** Each defaults to the intended policy, and an explicit value only
creates something that can drift out of step later. They exist to be changed deliberately,
not to be set on day one.

One trial per account, keyed on whether a Stripe customer has ever existed for it —
cancelling and resubscribing does not earn another. A different Google account does; that is
a known and accepted gap (see `billing.trial_days_for`).

### 8.3 Telegram

| Key | Required for | What it is |
|---|---|---|
| `TELEGRAM_BOT_TOKEN` | everything | From @BotFather. |
| `TELEGRAM_WEBHOOK_SECRET` | inbound | Any long random string. NOT the bot token — it is handed to Telegram to echo back. |
| `TELEGRAM_CHAT_ID` | the daily posts | Where drafts and the angle menu are sent. |
| `TELEGRAM_VIP_CHAT_ID` | channel invites | The paid channel, `-100…`. The bot must be an ADMIN of it with "invite users via link". |
| `TELEGRAM_SLIP_CHAT_ID` | optional | A separate channel for the morning board. Falls back to `TELEGRAM_CHAT_ID`. |

After setting these, register once:

```
POST https://<your-backend>/api/telegram/register?token=<TOOLS_TOKEN>
```

That one call does three things: points Telegram at the webhook, asks for `chat_member`
updates, and publishes the bot's menu. `chat_member` has to be requested by name and its
absence is silent — without it nothing records which Telegram account joined on which
invite, and a lapsed member cannot be removed because nobody knows which member they are.

### 8.4 Checking it

```
GET https://<your-backend>/api/config                      # public
GET https://<your-backend>/api/telegram/status?token=…     # tools token
```

`/api/config` should report `stripe_ready: true` and `trial_days: 7`.
`/api/telegram/status` should report `vip_channel.can_invite: true` and
`member_updates: true`. The channel check asks Telegram rather than guessing, and reports
"in the channel but not an admin" separately from "an admin without the invite permission",
because those fail identically and have different fixes.

---

### TL;DR of what you must supply on the new host
1. A **MongoDB** (Atlas free tier is fine to start).
2. Your **API-Football key** + season → `backend/.env`.
3. Set `REACT_APP_BACKEND_URL` (frontend) and `CORS_ORIGINS` (backend) to your domains.
4. Optional: your **Anthropic key** if you keep the Claude explainer (else drop it).
5. Replace the Emergent Google-auth session endpoint with your own auth.
