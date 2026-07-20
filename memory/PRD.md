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

## Backlog / Remaining
- P1: Wire real football stats API (Sportmonks/API-Football) + scheduled sync job to replace mock data.
- P2: Backtesting module per league; bet tracking + Kelly staking; line-movement & morning email alerts; automated corner-odds feed.

## Next Tasks
- Integrate live data API when key is available; add background scheduler for auto-refresh.
