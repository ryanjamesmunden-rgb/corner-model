# Deployment

Frontend on **Vercel** (static build), backend on **Railway**, database on **MongoDB Atlas**.

## Why Railway (and the one rule)

The backend runs an **in-process APScheduler** with three jobs:

| Job | Schedule (UTC) | What breaks without it |
|---|---|---|
| `sync_all` | 07:00, 19:00 | Corner stats and fixtures go stale |
| `daily_picks` | 07:30 | The Daily 2 never get locked in, so no track record accrues |
| `settle` | hourly, :20 | Picks never resolve to won/lost |

A host that sleeps the process on idle (e.g. Render's free tier) runs none of them.
Railway does not force-sleep paid services, which is the reason for the move.

> **Keep `numReplicas` at 1.** The scheduler lives inside the web process, so a second
> replica means every job fires twice — double syncs (burning API-Football quota) and
> duplicate Daily 2 picks. Scale up only after moving the scheduler into its own
> worker service.

## Railway setup

1. New project → **Deploy from GitHub repo** → `ryanjamesmunden-rgb/corner-model`.
2. Service **Settings → Root Directory: `backend`**. This is required — the repo is a
   monorepo and `railway.json` lives in `backend/`.
3. Add the environment variables below.
4. Deploy, then copy the generated public URL (`https://<service>.up.railway.app`).
5. Point the frontend at it: in **Vercel → Settings → Environment Variables**, set
   `REACT_APP_BACKEND_URL` to the Railway URL (no trailing `/api` — the app appends it),
   then redeploy the frontend.
6. Set `CORS_ORIGINS` on Railway to your Vercel domain.

Build and start are already declared in `backend/railway.json`; no dashboard build
command is needed.

### Environment variables

| Variable | Required | Notes |
|---|---|---|
| `MONGO_URL` | ✅ | Atlas connection string. Allow Railway's egress in Atlas Network Access (or `0.0.0.0/0` while testing). |
| `DB_NAME` | ✅ | Database name. |
| `API_FOOTBALL_KEY` | ✅ | API-Football (Pro plan — the free cap is too low for 27 leagues). |
| `CORS_ORIGINS` | ✅ | Comma-separated frontend origins. Avoid `*`: the browser rejects `*` on credentialed requests. |
| `ANTHROPIC_API_KEY` | optional | Enables the `/api/explain` Claude explainer. Without it the endpoint returns 503 and nothing else is affected. |
| `API_FOOTBALL_SEASON` | optional | Season fallback when the API doesn't report a current season. |
| `PORT` | — | Injected by Railway; don't set it. |

## Verifying a deploy

`GET /api/health` reports liveness, database reachability, whether the explainer is
configured, and **every scheduled job with its next run time**:

```bash
curl https://<your-railway-url>/api/health
```

If `scheduler_running` is false or `jobs` is empty, the scheduled work is not running
even though the site looks fine — that is the failure this endpoint exists to catch.

## Settlement without a scheduler

`POST /api/settle` is idempotent and safe to call repeatedly, so an external cron
(e.g. cron-job.org) can drive settlement on any host, including a sleeping one:

```
POST https://<your-backend>/api/settle    hourly
```

This is the £0 fallback if you ever move back to a sleeping tier. It does not replace
the sync jobs.
