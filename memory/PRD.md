# The Corner Model 2.0 — PRD

## Original Problem Statement
Multi-league corner value betting web app. Rebuilds a spreadsheet corner model into an auto-updating tool: pulls team corner stats & fixtures, calculates "correct odds"/probabilities via a Poisson engine, and surfaces only value bets through a daily Value Scanner. 7 leagues, team form tracking, EV%, confidence ratings, quick-paste bookmaker odds.

## User Choices
- Data: MOCK seeded data now (wire real Sportmonks/API-Football later)
- Bookmaker odds: manual quick-paste
- Scanner delivery: in-app only
- Theme: dark mode primary
- Auth: Emergent-managed Google login

## Architecture
- Frontend: React (JS) + Tailwind + shadcn/ui. Pages: Login, Dashboard, Scanner, FixtureDetail. Context: AuthContext, LeagueContext.
- Backend: FastAPI. Poisson engine (poisson_ge, fair_odds, ev_percent, tier_for_ev), confidence scoring, mock data seeding.
- DB: MongoDB (leagues, teams w/ match logs, fixtures, odds, users, user_sessions).
- Auth: Emergent Google OAuth, httpOnly session_token cookie (7-day).

## User Personas
- Sharp bettor tracking corner markets across lower-variance leagues to find value before the market moves.

## Core Requirements (static)
- 7 leagues switchable; team form (Home/Away/Overall × Last 3/5/10/Season).
- Poisson probabilities for total + team corner thresholds; fair odds vs book odds → EV%.
- Confidence rating (sample size + form stability + home/away consistency).
- Value Scanner: ranked bets, color tiers (strong/small/none), filters (league, market, min edge).
- Quick-paste odds per fixture → instant EV.

## Implemented (2026-07-20)
- Full backend Poisson engine + EV/confidence + 7-league mock seed (70 teams, 35 fixtures, ~28 pre-seeded with odds).
- Google OAuth login, protected routes, session management.
- Dashboard (fixtures + form tables w/ split & window tabs, league switcher).
- Value Scanner (ranked, filters, tier chips, row → fixture nav).
- Fixture detail (lambdas, confidence, quick-paste + inline odds, 3 market tables, team breakdowns).
- Tested: 100% backend (14 pytest), 100% frontend flows.

## Real Data Integration (2026-07-25)
- Integrated **API-Football (Pro plan)** — key in backend/.env (API_FOOTBALL_KEY).
- `sync_real.py` pulls REAL teams, REAL upcoming fixtures (current season 2026), and REAL corner stats (season 2026 + prior season fallback) into the app's schema. All 7 leagues synced (`data_source: real`).
- Corner form built from real per-fixture "Corner Kicks" statistics; teams with sparse samples topped up synthetically around real league averages.
- POST /api/leagues/{id}/refresh now launches a real re-sync (background subprocess) for that league.
- League IDs: ned-ed=89, nor-el=103, aus-al=188, bra-sa=71, fin-vk=244, swe-al=113, eng-pl=39.
- NOTE: seeded bookmaker odds are PLACEHOLDER (model-derived) so the scanner isn't empty — user pastes REAL corner odds per fixture for true EV.

## Backlog / Remaining
- P1: (done 2026-07-25) "Refresh data" button on dashboard → triggers live re-sync.
- P1: (done 2026-07-25) APScheduler auto-refresh of all leagues every 12h.
- P2: Backtesting per league; bet tracking + Kelly staking (backend endpoints built, frontend page pending — user deferred); email alerts; automated corner-odds feed.

## Next Tasks
- Integrate live data API when key is available; add background scheduler for auto-refresh.
