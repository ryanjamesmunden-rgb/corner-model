# The Corner Model 2.0 — PRD

## Original Problem Statement
Multi-league corner value betting web app. Rebuilds a spreadsheet corner model into an auto-updating tool: pulls team corner stats & fixtures, calculates "correct odds"/probabilities via a statistical engine (now Negative-Binomial), and surfaces only value bets through a daily Value Scanner. Team form tracking, EV%, confidence ratings, quick-paste bookmaker odds.

## User Choices
- Data: REAL via API-Football (Pro plan).
- Bookmaker odds: manual quick-paste per fixture; model-derived placeholders seed the scanner so it's never empty.
- Scanner delivery: in-app only.
- Theme: dark mode primary (cyan primary, hsl 187 100% 50%).
- Auth: Emergent-managed Google login.
- Staking: flat 1u per bet (picks board). User does NOT want aggregate P/L shown (misleading with no-odds picks) — strike rate only.

## Architecture
- Frontend: React (JS) + Tailwind + shadcn/ui. Pages: Login, Scanner (Value Finder home), QuickScan, Picks, Dashboard (Leagues), Streaks, FixtureDetail. Context: AuthContext, LeagueContext. Components: HomeInsights, IntroBanner, MatchupTable, StreakFinder, TrendFinder, BacktestPanel, SyncPanel, CornerLeagueTable, ExportMenu.
- Backend: FastAPI (`server.py`, large ~1350 lines). NB engine, EV/confidence, scanner/streaks/matchups/trends/mismatches, picks, backtester, Claude explainer, bets/bankroll+Kelly, APScheduler cron (07:00 & 19:00 UTC), self-heal boot sync. `sync_real.py` (API-Football ingest + permanent fixture_stats cache). Seed/util scripts: seed_picks, seed_manual_picks, settle_picks, reseed_odds, seed_team_odds, backfill_goals, backfill_rounds, tune_model, probe_leagues.
- DB: MongoDB (leagues, teams w/ real_matches, fixtures, odds, users, user_sessions, picks, bets, sync_runs, fixture_stats, explanations, meta).
- Auth: Emergent Google OAuth, httpOnly session_token cookie (7-day).

## Model
- Model v2 (live): Negative-Binomial (r=11) for team-corner probs; totals still Poisson. λ nudged by shots-intent × first-half-goal form. Proven on 3,174 matches via backtester (Brier 0.2255→0.2226, calibration gap 2.06%→0.80%). Do NOT revert to Poisson without re-running the backtester.
- Managed leagues: 27 across 20 countries (`MANAGED_LEAGUE_IDS` in server.py — startup deletes unlisted leagues).

## Key API endpoints
- Auth: POST /api/auth/session, GET /api/auth/me, POST /api/auth/logout
- GET /api/scanner (market: team|all|total|home|away; `team`=home+away combined), /api/best-bets, /api/top-mismatches, /api/streaks, /api/trends
- GET /api/leagues, /api/leagues/{id}/teams|fixtures|matchups|corner-table, /api/fixtures/{id}, POST /api/fixtures/{id}/odds
- GET /api/features/coverage?league_id — fill rate of the shot-volume features per league (see changelog; these are captured but NOT yet in the projection)
- GET /api/picks (record incl. profit/staked/roi/unpriced_wins + per-pick profit), POST /api/picks/settle
- POST /api/explain (Claude Sonnet 4.6 via Emergent LLM key, server-side cache + throttle)
- GET /api/backtest?model=v1|v2, /api/sync/runs, POST /api/sync/refresh-all, /api/leagues/{id}/refresh
- GET /api/export, /api/export/csv?type=teams|fixtures
- Bets/bankroll (built, frontend deferred): GET/PUT /api/bankroll, CRUD /api/bets, GET /api/bets/stats

## Changelog (recent, newest first)

### Shot-volume features captured (data only — NOT in the projection) (2026-08-12)
- `sync_real.py` now pulls **shots, shots on target, blocked shots and dangerous attacks** out of `/fixtures/statistics` per team per fixture, via `parse_team_stats()` + a normalised alias table (`STAT_TYPES`) because the provider labels these inconsistently. Stored on `fixture_stats` as `home_/away_{feature}` plus a `features_at` stamp, and on `teams.real_matches` as `{feature}_for/_against`.
- **A stat the provider didn't report is stored as `None`, never 0** — a blank must not read as "zero blocked shots" when this is fitted on later. The one exception is `shots_for/_against`, coerced to int because the live v2 λ already consumes `shots_for` and must not start seeing None.
- **Coverage is first-class**: `team_features()` returns each average with the number of games it was actually computed from (`covered`), sync prints per-league coverage and records it in `sync_runs.feature_coverage`, and `GET /api/features/coverage` reports fill rates per league. **Expect dangerous attacks to be sparse** — API-Football only returns it where the league's coverage includes it, so check this endpoint before reading anything into that feature.
- Exposed alongside the corner inputs on `/api/leagues/{id}/teams` (`features`), `/api/leagues/{id}/corner-table` (`shots_on_target`, `blocked_shots`, `dangerous_attacks` + `features`) and `/api/fixtures/{id}` (per-split `features` + per-match values on `recent`).
- **Ingest fix that came with it**: a fixture whose statistics carry no Corner Kicks value used to be cached as 0-0 corners (the old parser coerced a null to 0) and fed the model as a real 0-0 game. It is now skipped. A genuine 0 still parses as 0, so only truly uncovered fixtures are dropped — expect the cached fixture count to be slightly lower than before on leagues with patchy coverage.
- **The projection is deliberately unchanged** — `v2_lambda`, `expected_lambdas`, `build_markets` and the backtester are untouched, so model output is byte-identical. Wiring these in is a separate decision once the backtester says they help.
- `backfill_shots.py`: fills this season's cached fixtures (one statistics call each, `--limit N` per league, resumable via `features_at`, `--project-only` for the DB-only half), then projects onto `teams.real_matches` on the `(api_team_id, day)` join `backfill_fh.py` uses.
- `backend/tests/test_shot_features.py`: 20 offline unit tests (alias/percent/null parsing, None-vs-zero, venue/window aggregation, coverage counts).

### Value Finder rebuilt: Best Teams & Streaks front-and-centre (2026-08-09)
- Team-corner odds aren't available, so the home now leads with raw signals in a **tabbed Value Finder** (`Scanner.jsx`): **Best Teams** (default) | **Hot Form** | **Streaks** | **Chase Board**, above the Best Bets strip + intro.
- New `GET /api/top-corner-teams?side&window&limit&league_id`: teams ranked cross-league by avg corners WON on a venue/window (season/last5/last10), min 3 games, with next fixture. `limit` capped 1..100. Component `BestTeams.jsx` (best-teams, best-team-row, best-side-*, best-win-*, best-scope) with a bar viz.
- Hot Form reuses `TrendFinder` (highest recent avg vs baseline); Streaks reuses `StreakFinder` (Home/Away/Overall consistency); Chase Board reuses `ChaseBoard`.
- Verified `/app/test_reports/iteration_10.json`: backend 16/16 pytest (`test_top_corner_teams.py`), frontend 100% (tabs, side/window toggles, row navigation, picks regression). No console errors.

### Weekly Chase Board — trimmed value shortlist (2026-08-09)
- Replaced the 600+ placeholder-EV scanner with a **Weekly Chase Board** on the Value Finder: top ~25 team-corner chase spots for the next 7 days. Backend `_chase_board()` + `GET /api/chase-board?within_days&limit&league_id`. Ranked by composite `chase_score = λ × (1 + 0.4·opp_fh) × (0.6 + 0.4·consistency)` where opp_fh = opponent's first-half-goal rate (chase catalyst: our team falls behind early → chases → more corners), consistency = last-5 same-venue hit rate at the line. λ already blends team corners won + opponent corners conceded (equal weight, per user).
- **Cleared all placeholder odds** (db.odds emptied, 1459 docs) so nothing shows a fake edge; the board's "Your edge" shows "add odds" until the user pastes real bookmaker odds on the fixture (then true EV + book shown via market_key `{venue}_over_{line-0.5}`).
- **`backfill_fh.py`**: backfilled `fh_goals_for`/goals onto team.real_matches from fixture_stats (was missing — only fixture_stats had FH data). 5472 matches / 447 teams. This also makes the live v2 λ fh-form multiplier actually work.
- Frontend: `ChaseBoard.jsx` (chase-board, chase-row, chase-ev, chase-add-odds), `Scanner.jsx` rebuilt (filters: filter-scope/-window/-limit), `HomeInsights.jsx` "Top Chase" card (best-top-chase) fed by best-bets `chase`. Picks strike-rate tile label fixed.
- Verified `/app/test_reports/iteration_9.json`: chase-board 12/12 pytest, full backend 93/94 (1 pre-existing eng-nl shots gap), frontend 100% (filters, paste→EV, team-name routing, picks regression). opp_fh_rate populated (mean ~59%).

### Quick-paste team-corner odds (2026-08-09)
- Upgraded `FixtureDetail.jsx` quick-paste from Totals-only to **Total / Home / Away** targeting so users can bulk-enter real bookmaker TEAM-corner odds (the chase market). Segmented target buttons (`paste-target-home|away|total`), auto-routes a line to a team when the team name appears in it, and reads "5+" as 5-or-more (Over 4.5) alongside decimal "4.5" lines. Inline per-row odds inputs (auto-save on blur/Enter) unchanged. Verified: pasting into Ham-Kam corners recalculated EV correctly (Over 4.5 @2.20 → +41.5%).

### Value Finder intro + team-corner default (2026-08-09)
- **IntroBanner** (`components/IntroBanner.jsx`) on the Value Finder home: explains what the app does + the corner-chase thesis ("back a team's corner line when they're set up to chase the game — strong attack vs leaky defence forces corners; going behind → chase → more corners"), and points to Best Bets / Quick Scan / Streaks. Dismissible (localStorage `cm2_intro_dismissed`) with a reopen link (`intro-reopen`). Testids: intro-banner, intro-dismiss, intro-reopen.
- **Value Finder now defaults to Team Corners (chase)**: `Scanner.jsx` market default `team`; new filter option "Team Corners (chase)". Backend `/api/scanner` supports `market=team` (home+away groups). `best-bets` "value" pick now also uses team market.
- **`seed_team_odds.py`**: seeds model-derived placeholder odds for home/away team-corner lines (TEAM_LINES) across all fixtures so the team scanner isn't empty (mirrors totals placeholders). EV capped ~15%. Verified: 1047 team rows (694 strong / 353 small). NOTE: placeholders — user pastes real bookmaker corner odds per fixture for a true edge.

### Manual Picks + Odds + strike-rate (2026-08-09)
- Seeded 7 user historical picks (`seed_manual_picks.py`, `source:manual`, `date:null`) with own results — untouched by settle_picks (only settles `pending`). Shown in a "Manually tracked" group.
- Picks cards show odds badge (`pick-odds`) + result. `GET /api/picks` computes per-pick profit at flat 1u (backend still returns profit/staked/roi/unpriced_wins) BUT per user request the UI shows Won/Lost/Pending/**Strike rate** only — aggregate P/L removed from the strip and per-pick profit chip removed (misleading with no-odds wins). Null-date grouping/sort made safe.

### Picks board (2026-08-09)
- `/picks` public board of curated team-corner picks that auto-settle Win/Loss via `settle_picks.py` (token-overlap to real API-Football fixture, compares Corner Kicks vs line, reuses fixture_stats cache). Runs after each sync + manual POST /api/picks/settle (120s throttle).

### Model rework Phases 1–3 (2026-08-09)
- Backtester (`/api/backtest`, `BacktestPanel.jsx`), Model v2 (NB + shots/FH-goal form), Claude explainer on Quick Scan ("Why this angle?", `POST /api/explain`). All live. Tested iterations 6/7/8 (100%).

### Sync efficiency + observability (2026-08-05)
- Permanent `fixture_stats` cache (finished games fetched once). Cron 07:00 & 19:00 UTC + self-heal boot sync (sync_lock). sync_runs log; "Refresh all" + Data & Sync panel.

### League expansion + Quick Scan + Corner table (2026-08-05)
- 27 leagues. Quick Scan tab (H2H mismatch cards). Corner League Table sidebar on Leagues.

### Earlier
- Real API-Football integration; Streak/Trend/Matchup finders; Best Bets strip; Top Mismatches; export (md/CSV, Copy-for-Claude); data-freshness badge; deployment-ready (deployment_agent PASS). Bet-tracking + Kelly endpoints built, frontend page deferred by user.

## Open requests / backlog
- P1: Bankroll & staking (Kelly) frontend page — endpoints exist, UI deferred.
- P2: Automated corner-odds feed (hands-off EV); line-movement alerts.
- Nice-to-have (declined for now): in-app "Add Pick" form / bulk paste — user prefers current flow.
- Maint: `server.py` very large (~1350 lines); refactor deferred.

## Notes for next agent
- API-Football: use cache; never re-fetch historical stats. Pro plan (renew before expiry). Env: API_FOOTBALL_KEY, API_FOOTBALL_SEASON.
- Emergent LLM key (`EMERGENT_LLM_KEY`) powers /api/explain (Claude Sonnet 4.6). Rate-limited + cached.
- QA session for tests: `session_token = qa-test-token-123` (see /app/memory/test_credentials.md). Screenshot authed pages by injecting this cookie via page.context.add_cookies.
- Production deployed — do NOT mention preview URLs to user; tell them to redeploy for changes to reach production.
