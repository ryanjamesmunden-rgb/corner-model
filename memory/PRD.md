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

## League Set Update (2026-07-25)
- Reconfigured to 14 leagues (dropped Finland/Sweden; kept Norway). API-Football IDs in `sync_real.py` LEAGUE_META:
  England: Premier League 39, Championship 40, League One 41, League Two 42, National League 43;
  Netherlands: Eredivisie 88, Eerste Divisie 89; Brazil: Série A 71, Série B 72;
  Italy Serie A 135, France Ligue 1 61, Spain La Liga 140, Norway Eliteserien 103, Australia A-League 188.
- `sync_real.py` now upserts league docs (name/country) and has 429 rate-limit backoff (15s retry + 0.25s pacing).
- All 14 leagues synced with real data (data_source: real, season 2026).

## Corner Streak Finder + Real-Data Model (2026-07-25)
- New **Corner Streak Finder** on the dashboard home: finds teams that hit a team-corner threshold consistently over recent REAL games (presets 5/5, 8/10, 9/10, 10/10; Home/Away/Overall; auto-best-line or fixed 3+..7+; per-league or all-leagues). Shows hit rate, avg, color-coded recent games, and the team's next fixture (click → fixture detail to paste odds). Backend: GET /api/streaks.
- **Accuracy fix**: `sync_real.py` now stores `real_matches` per team and the Poisson model uses REAL games only (synthetic padding only as fallback for teams with <5 real games). STATS_CAP raised to 120 for deeper real coverage. Probabilities/confidence now reflect actual corner data.
- Streaks and form use `real_matches`; teams need ≥window real games on the chosen side to appear (honest sampling).
- Streak rows now include the **next opponent's corners-conceded** rate (real, venue-specific) and a **model fair-odds** for the team to hit its line next game: λ = (team corners-won on venue + opponent corners-conceded on their venue)/2 → Poisson P(≥line) → fair odds. Surfaces corner mismatches to price up before the bookies move.
- (2026-07-25) Streak finder gained a live **Edge %** column (EV vs pasted team-corner odds, market key `{venue}_over_{line-0.5}`) and a **timeframe filter** (`within_days`: next 3/7/14 days) to focus on imminent fixtures.
- (2026-07-25) **Value Scanner** now has a view toggle: "Total & Team Value" (existing scanner) and "Streak Picks" (reuses StreakFinder) — both edge signals on the home scan view.
- (2026-07-25) Fixture drill-down now shows a **per-game breakdown** of each team's recent real games (date, opponent, H/A, corners won/conceded/total) with a Last 5/10 toggle that respects the Home/Away/Overall split. Backend `/api/fixtures/{id}` returns `recent` + `real_samples` per team.

## App Restructure — 3 Tabs (2026-07-25)
- Nav is now **Value Finder** (home `/scanner`, root redirects here), **Leagues** (`/dashboard`), **Streaks** (`/streaks`). Login/AuthCallback land on `/scanner`. Removed the in-Scanner streak toggle.
- **Leagues** page: new **Top Corner Teams & Next Matchup** table (`MatchupTable`) with a **Home/Away/Overall** toggle; ranks teams by corners-won on the chosen venue, shows next fixture + opponent-conceded + proj λ + model line/odds, and highlights rows GREEN ("Mismatch") when a strong corner team meets a leaky defence, amber ("Lean") otherwise. Team Corner Form table kept below. Backend `GET /api/leagues/{id}/matchups?side=`.
- **Streaks** page: **Hot Form** tab (`TrendFinder`, teams averaging more corners than their season baseline; Home/Away/Overall, Last 3/5/10, Total vs Won metric, league scope) + **Consistency** tab (existing StreakFinder). Backend `GET /api/trends?side=&window=&metric=`.
- **Away form** supported across matchups, trends, streaks and per-game breakdown (some teams win corners regardless of venue).

## Value Finder Home Insights (2026-07-25)
- **Best Bets Today** strip (3 cards): top value bet, top mismatch, top streak — the standout from each signal, each clickable to its fixture. Backend `GET /api/best-bets`.
- **Top Mismatches This Week**: cross-league table (all leagues, next 7 days) of strong corner-team vs leaky-defence matchups, ranked by projected λ, with team/g, opp-conceded, proj λ, and model line@odds. Backend `GET /api/top-mismatches?within_days=&limit=` (per-league averages used for the mismatch threshold).
- Both rendered at the top of the Value Finder (`HomeInsights` component) above the ranked value table.

## Pre-Launch Hardening (2026-07-25)
- Full regression test passed (54/54 backend, all frontend flows) — `/app/test_reports/iteration_2.json`.
- Fixes: Login copy "7"→"14" leagues; mobile header made responsive (flex-wrap, narrower switcher); `/refresh` now has a 120s per-league throttle (`_last_refresh`) to protect API quota under multi-user load.
- Startup now: removes non-managed/legacy leagues (`MANAGED_LEAGUE_IDS`), and if no `data_source:real` leagues exist (fresh production DB) it auto-launches the initial API-Football sync. Removed the old mock `seed_data()` call from startup.
- `reseed_odds.py`: realigned placeholder demo odds against the current real-data model so displayed EV edges are realistic (max ~16%, was showing stale +125% outliers).
- LAUNCH NOTE: ensure `API_FOOTBALL_KEY` + `API_FOOTBALL_SEASON` env vars are set in the production environment so the scheduled/first-boot sync works after redeploy.
- (2026-07-25) **Model now uses REAL matches everywhere** via `_src()` helper (form tables, fixture splits, Poisson λ, confidence) — synthetic data is fallback only for teams with zero real games. A **real-sample badge** ("N real" / "0 real · est.") on each fixture-detail team shows how much real data backs the figures.
- P1: (done 2026-07-25) "Refresh data" button on dashboard → triggers live re-sync.
- P1: (done 2026-07-25) APScheduler auto-refresh of all leagues every 12h.
- P2: Backtesting per league; bet tracking + Kelly staking (backend endpoints built, frontend page pending — user deferred); email alerts; automated corner-odds feed.

## Next Tasks
- Integrate live data API when key is available; add background scheduler for auto-refresh.

## Go-Live Hardening + Auto-Update (2026-08-02)
- **Self-healing boot sync**: `on_startup` now refreshes on boot when data is missing OR stale (>12h old), guarded by a `meta.sync_lock` (20-min window) so frequent hot-reload restarts don't spawn overlapping syncs. Fixes the prior weakness where the interval-only scheduler reset its 12h timer on every restart and rarely fired — data had gone 8 days stale. Verified end-to-end: boot detected stale data → launched sync → all 14 leagues refreshed with current fixtures & stats (real, API-Football).
- **Data-freshness badge**: header now shows a pulsing "LIVE · X ago" badge (`data-testid=data-freshness`, desktop/md+ only) derived from the newest league `synced_at`; ticks every 60s; tooltip explains the 12h auto-refresh. Gives public users confidence data is current.
- **Export menu verified** (built prior session, now UI-tested): Copy-for-Claude markdown, Download .md, teams CSV, fixtures CSV — all endpoints 200, toasts fire. `/api/export`, `/api/export/csv?type=teams|fixtures`.
- **Deployment readiness: PASS** (deployment_agent) — no hardcoded secrets, env vars correct, /api prefix, ports 8001/3000, CORS ok. Ready to Deploy. Ensure `API_FOOTBALL_KEY` + `API_FOOTBALL_SEASON` are set in the production env.
- API-Football account: Pro plan, active until 2026-08-25, ~3.5k/7500 req/day used at time of sync. Backup: renew plan before expiry to keep auto-updates flowing.
- Tested: `/app/test_reports/iteration_3.json` — 6/6 frontend flows + endpoint checks PASS.

## Fixture Round / Matchday (2026-08-02)
- Fixtures now carry the real **round** from API-Football (`sync_real.py` captures `league.round`, prettified "Regular Season - N" → "Round N"; `_round_label`). Displayed across the app: Ranked Value Bets table (`scanner-row-round`), Leagues matchup "Next fixture" cell, Top Mismatches fixture cell, and Fixture Detail header (`fixture-round`). Sentinel "Upcoming" (round unknown) is hidden.
- Backend exposes `round` via `/api/scanner` and every `next_fixture` (`_next_fixtures`, streaks). Existing preview data backfilled cheaply via `backend/backfill_rounds.py` (one /fixtures call per league, no stats calls).
- Verified `/app/test_reports/iteration_4.json` — 100% (eng-nl=Round 1, bra-sa=Round 22 across scanner/matchups/mismatches/detail).
- OBSERVATION (pre-existing, out of scope): National League (eng-nl) matchup table shows 0.00 corners/'est' with no projections — the league's new season hasn't started and API-Football corner stats for that tier appear unavailable, so the model has no real samples yet.
