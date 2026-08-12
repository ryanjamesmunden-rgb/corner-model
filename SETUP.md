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
| `ANTHROPIC_API_KEY` | optional | Only if you keep the "Why this angle?" explainer (see §4). Replaces the Emergent key. |
| `EMERGENT_LLM_KEY` | ❌ (drop it) | Emergent-platform-only key. **Does not work off-platform** — remove and use `ANTHROPIC_API_KEY` instead. |

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

The "Why this angle?" button on Quick Scan uses Claude. On this platform it goes through the **Emergent LLM key** via the `emergentintegrations` library — **that library and key only work inside Emergent.** Off-platform you have two choices:

**Option A — Drop the feature.** The explainer is not core; everything else (Best Teams, Streaks, Chase Board, Picks) works without it. Just leave `/api/explain` unused / remove the button.

**Option B — Swap to the official Anthropic SDK.** In `backend/server.py`, replace the emergentintegrations call inside `explain_pick` with:

```python
# requirements.txt: add  anthropic
import anthropic
client = anthropic.AsyncAnthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

msg = await client.messages.create(
    model="claude-sonnet-4-5",          # use a current Claude model your account has
    max_tokens=300,
    system="You are a sharp, concise football corners betting analyst. You only use the numbers provided.",
    messages=[{"role": "user", "content": prompt}],
)
text = msg.content[0].text.strip()
```

Then remove `from emergentintegrations.llm.chat import LlmChat, UserMessage`, drop `emergentintegrations` from `requirements.txt`, and set `ANTHROPIC_API_KEY` in `.env`. Get a key at https://console.anthropic.com/.

> There is **no other Emergent dependency** in the app. Auth in this build uses Emergent Google OAuth (`/api/auth/session` hits an Emergent session endpoint). If you host independently you'll want to replace that with your own auth (e.g. standard Google OAuth or a JWT login) — see §6.

---

## 5. Seed / utility scripts (in `backend/`)
- `sync_real.py` — pulls real teams/fixtures/stats from API-Football (the main data job).
- `seed_picks.py` / `seed_manual_picks.py` — seed the Picks board.
- `settle_picks.py` — auto-settles picks Win/Loss from real results.
- `backfill_fh.py` / `backfill_goals.py` / `backfill_rounds.py` — one-off DB backfills (no API calls).
- `backfill_shots.py` — fills shot-volume features (shots, shots on target, blocked shots, dangerous attacks) onto this season's cached fixtures, then projects them onto `teams.real_matches`. **Spends one statistics call per un-filled fixture**, so it is capped per league (`--limit N`) and resumable; `--project-only` re-runs the DB half with no API calls.
- `reseed_odds.py` / `seed_team_odds.py` — placeholder-odds generators (optional; not needed since the app now leads with averages/streaks).
- `tune_model.py` / `probe_leagues.py` — analysis helpers.

## 6. Auth note (important for independent hosting)
This build authenticates via **Emergent-managed Google OAuth** (`EMERGENT_SESSION_URL` in `server.py`). That endpoint is Emergent-only. For your own site, replace `/api/auth/session` with your own OAuth/JWT flow and keep the existing session-cookie pattern (`session_token` httpOnly cookie, `user_sessions` collection). Everything downstream reads the user from `get_current_user`, so only that one function + the login page need changing.

## 7. Data model (MongoDB collections)
`leagues`, `teams` (with `real_matches`), `fixtures`, `odds`, `users`, `user_sessions`, `picks`, `bets`, `sync_runs`, `fixture_stats` (permanent finished-match cache), `explanations` (LLM cache), `meta` (sync lock).

---

### TL;DR of what you must supply on the new host
1. A **MongoDB** (Atlas free tier is fine to start).
2. Your **API-Football key** + season → `backend/.env`.
3. Set `REACT_APP_BACKEND_URL` (frontend) and `CORS_ORIGINS` (backend) to your domains.
4. Optional: your **Anthropic key** if you keep the Claude explainer (else drop it).
5. Replace the Emergent Google-auth session endpoint with your own auth.
