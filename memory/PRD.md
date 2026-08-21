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
- Frontend: React (JS) + Tailwind + shadcn/ui. Pages: Login, Scanner (Value Finder home), QuickScan, Picks, Dashboard (Leagues), Streaks, FixtureDetail. Context: AuthContext, LeagueContext. Components: HomeInsights, IntroBanner, MatchupTable, StreakFinder, TrendFinder, BacktestPanel, ToolsPanel, SyncPanel, CornerLeagueTable, ExportMenu.
- Backend: FastAPI (`server.py`, large ~1350 lines). NB engine, EV/confidence, scanner/streaks/matchups/trends/mismatches, picks, backtester, Claude explainer, bets/bankroll+Kelly, APScheduler cron (07:00 & 19:00 UTC), self-heal boot sync. `sync_real.py` (API-Football ingest + permanent fixture_stats cache). Seed/util scripts: seed_picks, seed_manual_picks, settle_picks, reseed_odds, seed_team_odds, backfill_goals, backfill_rounds, tune_model, probe_leagues.
- DB: MongoDB (leagues, teams w/ real_matches, fixtures, odds, users, user_sessions, picks, bets, sync_runs, fixture_stats, explanations, meta).
- Auth: Emergent Google OAuth, httpOnly session_token cookie (7-day).

## Model
- Model **v3 (live)**: Negative-Binomial (r=11) for team-corner probs; totals still Poisson. λ nudged by **blocked-shots-intent** (weight 0.15) × first-half-goal form, **falling back to v2's shots-intent** for any team with fewer than `MIN_BLOCKED_GAMES` (5) games carrying blocked shots. Backtester: Brier 0.2226→0.2219, calibration gap 0.80→0.71 (at weight 0.10); 0.15 swept to 0.2214/0.68. v2 lineage: Proven on 3,174 matches via backtester (Brier 0.2255→0.2226, calibration gap 2.06%→0.80%). Do NOT revert to Poisson without re-running the backtester.
- Managed leagues: 27 across 20 countries (`MANAGED_LEAGUE_IDS` in server.py — startup deletes unlisted leagues).

## Key API endpoints
- Auth: POST /api/auth/session, GET /api/auth/me, POST /api/auth/logout
- GET /api/scanner (market: team|all|total|home|away; `team`=home+away combined), /api/best-bets, /api/top-mismatches, /api/streaks (direction=over|under, subject=team|match, side, window, min_hits, min_streak, threshold, min_line, max_line, within_days), /api/trends
- GET /api/leagues, /api/leagues/{id}/teams|fixtures|matchups|corner-table, /api/fixtures/{id}, POST /api/fixtures/{id}/odds
- GET /api/features/coverage?league_id — fill rate per league of the shot-volume features and of `goal_events` (goal detail). Captured data, NOT in the projection.
- GET /api/fixture-board?days&per_day&league_id — best upcoming FIXTURES (not teams), grouped by kickoff day, capped per day. Home page (/scanner).
- GET /api/picks (record incl. profit/staked/roi/unpriced_wins + per-pick profit), POST /api/picks/settle
- POST /api/explain (Claude Sonnet 4.6 via Emergent LLM key, server-side cache + throttle)
- GET /api/backtest?model=v1|v2|v3&blocked_weight (v3 = candidate, backtest-only; a v3 run also returns `v2_same_sample` scored on identical rows), /api/sync/runs, POST /api/sync/refresh-all, /api/leagues/{id}/refresh
- GET /api/export, /api/export/csv?type=teams|fixtures, /api/export/streaks?days&window&min_hits&side&league_id (fixture-first streak markdown, overs + unders, team + match)
- Bets/bankroll (built, frontend deferred): GET/PUT /api/bankroll, CRUD /api/bets, GET /api/bets/stats

## Changelog (recent, newest first)

### STATS_CAP 400 → 250: fit the first sync inside a day's quota (2026-08-21)
Only **uncached** fixtures cost an API call, so raising `STATS_CAP` costs
`(new cap − what is already cached)` per league, once. From the old 120 that is:
- at **400** — ~280 calls/league, **~7.6k** across 27 leagues
- at **250** — ~130 calls/league, **~3.5k**

API-Football's Pro plan allows on the order of 7,500 requests a day, so the 400 version
would have run the quota dry mid-sync and left the job half done. 250 still gives ~25
games a team — comfortably past the 20 that `team.real_matches` keeps, and roughly double
the old ~12-13 — while fitting inside one day's allowance.
A run that stops early **resumes** rather than repeats, because the cache is permanent.
`STATS_CAP` is an env var, so it can go back up once the first pass has settled — no
deploy needed. `backfill_goal_events.py` takes its default `--limit` from the same
constant, so its per-league cap drops with it, which is the same quota argument.

### Fixture board: an absolute bar, and more games a day (2026-08-21)
The first version was a **top-N per day**, which is not the same as a quality board.
Sort-and-take-N *always* promotes something, so a Tuesday with one fixture on crowned that
fixture by default — "best of the day" out of one. Fixed by putting an **absolute bar**
in front of the per-day ceiling.
- `fixture_qualifies()` — three hurdles, none of which depend on the rest of the card, so
  the same fixture passes or fails identically on a quiet Tuesday and a ten-game Saturday:
  **CONTEXT** (`BOARD_MIN_GAMES = 6` real matches behind *each* side), **PROJECTION**
  (`BOARD_MIN_EDGE = 1.0` — at or above that league's actual average), **EVIDENCE** (at
  least one angle that is strong, not merely present).
- `angle_is_strong()` — a streak needs a **live run** of `BOARD_MIN_RUN = 3` (the
  post-#13 minimum of 2 only makes it *a* streak); a chase spot needs to have hit
  **4 of its last 5** (`BOARD_MIN_CONSISTENCY = 0.8`). A streak is judged on the run
  that is alive, not the window's hit count — a 4/5 whose latest game was the miss is a
  broken streak wearing a good record.
- `per_day` raised to a ceiling of 20; UI offers **3 / 5 / 8 / All**, default 5.
- **Days where nothing qualifies are reported, not dropped** ("Nothing cleared the bar —
  4 fixtures on, none with enough behind them"). An absent day reads as missing data.
- `min_games` / `min_run` / `min_edge` are query params, so the bar is loosenable for a
  thin week without a deploy.
- Angle chips are dimmed when they are supporting rather than qualifying, so it is visible
  which one actually earned the fixture its place.

### Fixture board on the home page — best upcoming games, 2-3 a day (2026-08-21)
Every other board here is **team-first**: a row is a team and the fixture rides along as
`next_fixture`. That is the wrong shape for "what should I look at tonight", where the
unit is the match. `GET /api/fixture-board?days&per_day&league_id` is fixture-first.
- **What "best" means, stated plainly.** A fixture must carry at least one live **angle**
  (a chase spot or a streak) — a big projected total with nothing to bet on is trivia,
  not a pick. Qualifying fixtures are then ordered by **corner edge**: the projected match
  total ÷ that league's *actual* average match total. The projection is `expected_lambdas`,
  the same production call the fixture page and every price use, so this ranks by model
  conviction rather than by a new invented score.
- **What it is NOT.** Nothing here has been through the backtester *as a ranking*, so the
  order is **triage** — which games to open first — and the bet itself comes from the
  angle, which has been priced. `corner_edge` is also correlated with the chase board by
  construction (same λ), so the angle count is corroboration, not independent
  confirmation. The chase-board rank test is still the outstanding way to check this.
- **`board_days()` is pure and tested** (14 tests). The per-day cap is the whole
  requirement and dropping the wrong fixture is a silent failure, so it is pinned:
  narrowing 3→2 must be a strict subset, days read in calendar order, fixtures within a
  day read in **kickoff** order rather than score order, and `considered` reports the full
  day so the UI can honestly say "3 of 9".
- Angles are gathered from `_chase_board` plus the same four streak grids the streaks
  export walks, so the board cannot disagree with the export.
- Cost profile matches `/best-bets`, which the home page already calls — several passes
  over teams. It loads async behind skeletons, so it never blocks the rest of the page.

### Shot block on the fixture page — why v3 nudges a team's λ (2026-08-21)
The shot data has been in **pricing** since v3 went live (PR #5), but nowhere on the
site showed the numbers. Only shots/game in the corner league table was ever rendered;
`features` was served on `/api/leagues/{id}/teams` and `/api/fixtures/{id}` and the
frontend ignored all of it. That was a scoping omission — every PR from #2 on was framed
as "does this improve accuracy", so the data and the measurement shipped and the display
never did.
- **`intent_breakdown(team, venue, league_shots, league_blocked)`** reports which intent
  term the live model applies and why: `source` (blocked = v3 | shots = v2 fallback |
  none), the multiplier, the team value, the league average, the weight, the covered-game
  count, and a `reason` when v3 did **not** fire.
- **`live_lambda` is now DEFINED in terms of it** (`base × multiplier × form`). That is
  the point of the refactor: a panel built on a parallel reimplementation would drift and
  start describing a price the site does not charge. Behaviour is unchanged — pinned by a
  test that walks every branch and reproduces the priced λ to the cent.
- Served as `intent` per split on `/api/fixtures/{id}`; rendered under the corner splits
  as shots / on target / blocked per game, the coverage behind them, the resulting
  multiplier as a ±% on λ, and the fallback reason where relevant.
- **`dangerous_attacks` is deliberately not shown.** The provider returns it empty for
  these leagues (0/40 on the coverage check), so the column would only ever read "—".

### Goal detail, deeper history, and no more one-game streaks (2026-08-21)

**1. History depth — the "some teams only go back 13 games" complaint.**
`STATS_CAP` in `sync_real.py` was **120**: the number of fixtures per league whose
statistics the sync pulls. A 20-team league plays **10 fixtures a round**, so 120 fixtures
was only ~12 rounds and every team topped out at ~12-13 matches no matter how long the
season had run. Raised to **250** (~25 games a team, past the 20 `real_matches` keeps) and
made overridable with the `STATS_CAP` env var. *(Shipped at 400 first; see the quota entry
at the top of this changelog for why it came down.)*
The last-season top-up had the same shape of bug: it fired on `len(ft) < 40`, i.e. only in
the opening weeks of a season. A league 12 rounds in cleared that bar with 120 games and
was never topped up — so teams promoted or newly covered had *no* last-season history at
all. The trigger is now `len(ft) < STATS_CAP`, so the pool fills from last season whenever
this season has not yet supplied enough.
**Cost:** ~130 extra statistics calls per league at the revised cap, **once**. Past results
never change and `fixture_stats` is cached permanently, so this is a one-off spend, not a
recurring one.

**2. One-game streaks removed** (`MIN_STREAK_LEN = 2`, `streak_qualifies()`).
The old test was `hits >= 1 and hits + voids >= min_hits`. Two ways a single game reached
the board under it:
  - a line carried by **voids** — four exact-line pushes and one win passed, and displayed
    as "streak: 1";
  - a team with barely any history, whose entire record is one or two matches.
There are now three hurdles, all of which must clear: real wins ≥ floor, wins + voids ≥
`min_hits` (voids still count towards coverage — they are stake-back, not misses), and the
**currently live run** ≥ floor. Tunable per request via `min_streak`, default 2.

**3. A single game no longer sets a venue average** (`MIN_VENUE_GAMES = 3`).
`_real_avg` fell back to the full record only when a venue split was *completely* empty. A
team with one home game got a "home average" of that single match, and that number drove
its λ, its projection and its place on every board. Below three games the full record is
used instead. This moves numbers app-wide (scanner, mismatches, chase board, streak
projections) — deliberately, and always towards the larger sample.

**4. Goal detail — who scores and when.** `/fixtures/events` *does* carry minutes (unlike
the corner data, which the 1H/2H probe was built to confirm). New `goal_events.py` (pure,
14 unit tests) parses it: goals sorted, **missed penalties excluded** (API-Football files
them as type `Goal`), **own goals credited to the side that benefits** while keeping the
scorer's name. `backfill_goal_events.py` fetches and stores it, then projects onto
`team.real_matches`; it is capped, resumable (`events_at` marks a done fixture) and its
projection half is free. Surfaced as `goal_profile` on `/api/fixtures/{id}`: scorers,
goal-minute windows, first-goal timings, and **minutes spent leading/level/trailing**.
Coverage per league lands in `/api/features/coverage` as `goal_events`.
The point of the minutes: the game-state split classifies a match by its **half-time
score**, so a team a goal down from the 10th minute and one that conceded on 43 sit in the
same bucket. Minutes separate them — this is the honest version of the chase measure the
null game-state result deserved. It does **not** fix the other half (corners are still
full-match only), so it is exposed as data, **not** wired into pricing.
**Cost:** one `/fixtures/events` call per fixture, same profile as the shots backfill.
Both new tools are in the Tools panel (`POST /api/tools/backfill-goals`), so no shell.

### Tools panel covers the last two shell-only scripts (2026-08-18)
- `backfill_fh.py` (fills `fh_goals_against` — required before the corners-by-state splits show anything but `unknown_games`) is now a `measure` mode: **DB-only, no API calls**.
- `probe_corner_halves.py` gets its **own** endpoint `POST /api/tools/probe-halves` rather than a measure mode, because `/tools/measure` promises no API calls and the probe spends about six. Keeping that promise true matters more than the tidiness of one dispatch table.
- `MEASURE_MODES` entries gain an **accepts-`--league`** flag. `backfill_fh.py` takes no such argument, and appending it would have killed the run with an unrecognised-argument error; a mode that cannot take a league now returns 400 rather than failing at the subprocess. Covered by a test that walks every mode.
- With these two, nothing in the workflow needs a shell any more.

### Fixture-first streaks export + truncation fixes (2026-08-12)
- **Why leagues were missing from exports — three separate caps, all silent:**
  1. `sync_real.py` stored only the **next 10 upcoming fixtures per league** (`ns[:10]`). Every "next N days" view was capped by this at the data layer — a league with a weekend round plus a midweek round could not fit. Now `UPCOMING_FIXTURES = 40`, which costs **nothing extra in API calls** (they come from the `/fixtures` call the sync already makes).
  2. `/api/export` sliced its tables at `[:40]`/`[:60]` on globally-sorted lists, so entire lower-ranked leagues fell off the bottom. Now `EXPORT_ROWS = 250`, and any section that still truncates **says so** (`Showing the top 250 of N`).
  3. `streaks()` capped its team/fixture queries at `to_list(1000)`; 27 leagues x ~20 teams was already over half of it. Raised to 5000.
- The streaks export now reports **coverage**: fixtures in the window per league, which leagues produced angles, which had fixtures but nothing qualifying, and which have **no fixtures stored at all** (the last being the only one that is a data problem — it means that league has not synced).
- `GET /api/export/streaks?days=7` — every streak angle on the fixtures kicking off in the window, **grouped by day then fixture**, as markdown built to paste into a chat. Covers the full grid: over/under × team-corners/match-total. Each angle carries the record (with voids), average, current streak + start date, longest, the recent sequence, the model price, and book odds/edge where they exist.
- The main `/api/export` already had streak tables but they were **not tied to a fixture window and carried no kickoff or opponent**, so you could not tell which game an angle belonged to. Match-total OVERS were missing entirely.
- **Match-total angles name their source team** (`match total under 6 (via Bores's games)`). A match total is derived from ONE team's recent games, not from the fixture, so the same fixture can legitimately show an over from one side and an under from the other. Unlabelled, that reads as the model contradicting itself — caught in the first end-to-end run. The header explains it too.
- Match totals are deduped per fixture per direction (tightest under / highest over), since both teams otherwise generate near-duplicate rows.
- Match-total overs use a `min_line` floor of 7; at 3 every fixture qualifies and the export is noise.
- `ExportMenu` gains "Copy this week's streaks" and "Copy next 3 days" alongside the existing full export.

### Corners by match state — and the 1H/2H blocker (2026-08-12)
- `team_state_splits()` groups a team's corners won/conceded by **half-time state** (trailing/level/leading) and by **final result** (won/drew/lost), per venue, each bucket carrying its `games` count. Exposed on `/api/fixtures/{id}` (`state_splits` per split, plus `ht_state`/`ft_state` on each recent row) and a new `GET /api/leagues/{id}/state-splits?split=` with a pooled `league_baseline` to compare against.
- `sync_real.py` now stores `fh_goals_against` on `teams.real_matches` — without the opponent's half-time goals a team's HT state is not derivable. `backfill_fh.py` fills it onto existing docs (**DB-only, no API calls**).
- **The honest caveat, repeated at every call site**: API-Football reports corners for the WHOLE MATCH only. These are full-match corners in games where the team was in a given state — *not* corners won while in it. A chase effect concentrated in the second half reads diluted here, which may be part of why `--game-state` came back null.
- **1H/2H corners are blocked on data, not effort.** There are no corner timings post-match and no corner events in `/fixtures/events`. `probe_corner_halves.py` checks four routes on one fixture — including `?half=true`, which some API-Football versions document — and states plainly what each outcome implies. If the half parameter works, history is recoverable and this is cheap; if not, the only route is snapshotting statistics at half-time on LIVE fixtures, which accumulates going forward only and never backfills.
- A missing goal figure classifies as `unknown_games`, never silently as a draw. `backend/tests/test_state_splits.py`: 8 unit tests.

### Chase board rank-quality test (2026-08-12)
- **Result that prompted it**: `--game-state` came back `no effect` for BOTH `chase_interaction` and `opp_fh_rate`, placebo clean. The chase thesis does not predict corners beyond what corner form already captures — the effect is real descriptively, but the corner average was already carrying it. That leaves `chase_score`'s `(1 + 0.4·opp_fh)` term without evidence.
- Runnable from the Tools panel (`chase_board` mode). `measure_chase_board.py` measures the board at the job it actually does — **ordering** — rather than by probability accuracy. Walk-forward replay of every past fixture as the board would have seen it, then buckets by rank.
- **The metric is the RESIDUAL** (actual hit rate − the model's own probability), never the raw hit rate: the line moves with λ (`round(λ)-1`), so top-ranked spots sit at higher lines and hit less often by construction. Raw hit rate by rank mostly measures where the line landed.
- Isolates every term: `chase_score`, `lambda_only`, `no_opp_fh`, `no_consistency`, plus a **RANDOM control** that sets the noise floor. Two views: buckets over all rows, and **top-N per matchday** (what the board and the Daily 2 ledger actually do).
- **Interpretive caveat baked into the tool**: a gradient can be real even when the model is correctly specified, because λ is *estimated* from 10 games and `consistency` is a second independent look at the same quantity. In validation on data drawn from the model's own distribution — where no market edge exists by construction — consistency still separated buckets by 7.5 points against a 1.8 control floor. That is a statement about ESTIMATION NOISE, not about finding mispriced games, and the fix it implies is folding venue form into λ rather than betting the top of the board harder.
- Validated on two synthetic cases; `no_opp_fh` outscored the live `chase_score` in both, consistent with the opp_fh null.

### Phone-operable: v2-vs-v3 backtest panel + Tools runner (2026-08-12)
- **Fixed a false claim in the UI**: `BacktestPanel` still compared v1 vs v2 and its footer read "v2 is now live across the site", which stopped being true when v3 shipped. It now compares **v2 vs v3** off a SINGLE `?model=v3` call, using the `v2_same_sample` block — one call gives both models on identical rows, where two calls would have compared different samples. Shows `rows_using_blocked` / `rows_fell_back_to_v2` and says so plainly when a league has no blocked data yet (v3 == v2 there).
- **`ToolsPanel`** (Dashboard) runs `backfill_shots.py` and `measure_features.py` (features / sweep / game-state) from the browser, with live status and captured output — the only part of the workflow that previously needed a shell. Makes the whole loop phone-operable.
- Backend `POST /api/tools/backfill-shots`, `POST /api/tools/measure` (mode: features|sweep|game_state|chase_board, dispatched via `MEASURE_MODES` to the right script), `GET /api/tools/runs`, storing each run in `db.script_runs` (last 30 kept, output capped at 60KB).
- **Security**: the app is public and the backfill spends API credits, so these are gated behind a `TOOLS_TOKEN` env var and return **503 when it is unset** — disabled by default, opt-in only. Token compared with `secrets.compare_digest`. Every subprocess argument is built from validated values (league ids checked against `MANAGED_LEAGUE_IDS`, mode from an enum, limit clamped 1-500) — no raw user string reaches argv. Per-script cooldowns (backfill 10min, measure 2min) and a one-run-at-a-time guard.
- The frontend keeps the token in `localStorage` only (`cm2_tools_token`), with a "Forget token" control.

### v3 goes live: blocked-shots intent is now production pricing (2026-08-12)
- Backtester on the real cache, default (shipping) mode: **Brier 0.2226 → 0.2219, calibration gap 0.80 → 0.71** against `v2_same_sample`. Both metrics improved, which was the stated bar. Weight swept to **0.15** (0.2214 / 0.68), up from the inherited 0.10.
- `v2_lambda()` → **`live_lambda()`**: blocked-shots intent where the team has ≥5 games of it, otherwise v2's shots intent, unchanged. Both branches share `_intent()` with `model_lambda`, and a unit test pins that production λ and the BACKTESTER's λ agree — they are separate implementations, and if they drift the backtest stops describing production.
- **A team the backfill hasn't reached prices exactly as it did before, to the cent.** `_blocked_form()` returns None below `MIN_BLOCKED_GAMES` rather than trusting a thin sample, and never reads a missing stat as zero.
- Threaded `league_blocked` through all 7 pricing call sites (`expected_lambdas`, `_streak_projection` ×2, matchups, mismatches, chase board) via new `_league_blocked_map()`. `sync_real.py` now stores `avg_blocked` on the league doc alongside `avg_shots`.
- **Rollout wrinkle**: the team-driven surfaces (streaks, chase board, mismatches, matchups) compute the league average from `teams.real_matches` and switch to v3 the moment the code deploys, while fixture pricing (`/scanner`, fixture detail) reads `league.avg_blocked` and stays on v2 until a sync writes it. **Trigger `POST /api/sync/refresh-all` after deploying** to close that window, or the same fixture can show slightly different λ on two screens until the next 07:00/19:00 sync.
- `backend/tests/test_v3_live.py`: 13 unit tests (backtester parity, blocked term replaces shots, thin-history fallback, partial coverage, league map, `expected_lambdas` defaults). All pricing paths exercised end to end against a fake DB, including a league with blocked data and one without in the same run.

### Game-state measurement: does the chase thesis actually predict? (2026-08-12)
- `measure_features.py --game-state` tests the app's founding assumption — trail → chase → corners — which the chase board has only ever encoded as a proxy (`opp_fh_rate`) and never measured. **Needs no backfill**: it derives from goals + half-time goals, already on every cached fixture, so it runs for free on all rows rather than only the blocked-shots subset.
- Reports **corners by half-time state × venue** first (the literal "how many corners when losing at home" table). This is DESCRIPTIVE — it shows the effect exists, which is not the same as it being predictable.
- **The central modelling insight, found during validation**: a team that chases hard already averages more corners, and that is *already in its corner form*. An uncentred chase term mostly re-states what the model has. Only the deviation from a team's OWN usual chase likelihood is new information, so `chase_delta` and `chase_interaction` are centred on `p_trail_base` (how often that team actually trails).
- Second finding: chase propensity is a behavioural **trait**, not form, and cannot be estimated on the 10-match form window — only ~2 of those games involve trailing, and the shrinkage correctly erases the trait before it can be measured. It gets its own `STATE_WINDOW` (40).
- Four candidates decompose the thesis: `chase_propensity` (is it a team trait?), `opp_fh_rate` (does the existing proxy beat corner form?), `chase_delta` (league-level, unusually early-scoring opponent), `chase_interaction` (trait × deviation — the full hypothesis). Each gets a shuffled placebo.
- **Expectation management**: on synthetic data with a *deliberately absurd* effect (2.5× chase, opponents scoring 10% vs 90%), the correlation was strong (r=+0.23) and the placebo clearly worse, but the incremental Brier gain over corner form was still small. Corner form is a strong summary and absorbs most of this mechanism. Gains (`--chase-gain`, `--delta-gain`) are tunable because the right magnitude is unknown.

### v3 candidate: blocked shots replaces shots in the intent term (2026-08-12)
- Measurement result on real data (`measure_features.py`, 4,820 scored rows): **blocked shots is worth roughly what the whole v1→v2 upgrade was worth.** `+blocked_shots` on top of the live model scored dBrier **-0.0021**, and **swapping** the shots term for blocked shots scored **-0.0024** — the swap beats the addition, so the two stats are largely collinear and blocked shots is the better of the pair. Prior-form r = **+0.31**. Placebo passed, calibration gap 0.74.
- `model_lambda()` gains **v3** = v2 with the shots-intent term replaced by a blocked-shots-intent term, weight `V3_BLOCKED_WEIGHT` (0.10, copied from the shots term as a starting point — sweep it). `_intent()` factored out and shared.
- **v3 is NOT live.** `expected_lambdas`, `v2_lambda` and `build_markets` are untouched; v3 exists only in `/api/backtest?model=v3`. It ships only if it beats v2 on the backtester's Brier AND calibration — the bar v2 itself had to clear.
- **v3 falls back to v2** (not to bare λ) when a team has no blocked-shots history. Blocked shots only exist as far back as the backfill reached; shots are on every cached fixture. Without the fallback, a thinly-covered team would price off bare corner form — losing the first-half-goal term too — and come out WORSE than the model v3 replaces. The backtester skips those rows, so this would only ever have surfaced as quietly degraded production pricing.
- `/api/backtest` gains `model=v3` + `blocked_weight` + `only_covered`. Because v3 needs blocked-shots history it can only be scored where the backfill has reached, so **a v3 run also returns `v2_same_sample`** — the live model scored on those exact rows. Comparing a v3 run against a separate v2 run compares two different samples and will mislead. Two v3 modes: **default** scores every row (falling back to v2 where blocked history is short) — the SHIPPING question, with `rows_using_blocked` / `rows_fell_back_to_v2`; **`only_covered=true`** skips those rows instead — the FEATURE question, with `skipped_no_blocked_history`. Response also gains `avg_calibration_gap`.
- `measure_features.py --sweep` tries blocked-intent weights 0.05-0.30. **Watch both columns**: in testing, raising the weight kept improving Brier while the calibration gap widened. The weight with the best Brier is not automatically the one to ship, and v2 was tuned on calibration specifically.
- `backend/tests/test_v3_model.py`: 8 unit tests, the first of which pin that v1/v2 — the models that actually price bets — are unmoved by the v3 arguments.

### measure_features.py — does the shot data actually help? (2026-08-12)
- Offline walk-forward harness (sibling of `tune_model.py`, same reporting shape) testing whether **blocked shots** / **shots on target** improve corner prediction. Baseline is the LIVE v2 model, imported from `server.py` so it is the real thing, not a re-implementation. Candidates add each feature as a multiplicative intent term of the same shape the production λ uses for shots. **Changes nothing** — pure measurement, no API calls.
- **Confirmed: dangerous attacks is not available post-match.** eng-pl backfill returned `dangerous_attacks=0/40` with the other three at 40/40 — API-Football only exposes it live/in-play. It stays in the capture (costs nothing, self-populates if coverage ever appears) but is excluded from the measurement.
- Three guards, each of which was verified to matter:
  1. **Same sample** — rows lacking history for ANY feature under test are dropped for every model alike, so a candidate is never scored on an easier subset than the baseline. Drop count is reported.
  2. **Mean-neutral intent** — each intent term is divided by its own mean over the scored rows. Without this, an intent term averaging >1 scales λ up, and since the baseline under-predicts at the low lines, EVERY feature scores as an improvement. This was a real false positive caught in testing, not a hypothetical.
  3. **Shuffled placebo** — every feature is also scored with its values shuffled across rows. A placebo scoring *better* means the harness is measuring an artifact and the script says so loudly. (A placebo scoring slightly *worse* is expected — shuffling only adds noise to λ.)
- Differences are paired per-row with a 95% interval, and the script refuses to endorse a result below `MIN_ROWS` (2000) scored rows. Also reports Pearson r of prior-form feature vs corners, with `shots` shown alongside for scale.
- Validated against synthetic data with known answers: real team-level signal → `better` (r≈+0.50); true null → `no effect`; 30% coverage → rows correctly dropped, signal still found; independent latents over 60 teams → `no effect`.

### Shot-volume features captured (data only — NOT in the projection) (2026-08-12)
- `sync_real.py` now pulls **shots, shots on target, blocked shots and dangerous attacks** out of `/fixtures/statistics` per team per fixture, via `parse_team_stats()` + a normalised alias table (`STAT_TYPES`) because the provider labels these inconsistently. Stored on `fixture_stats` as `home_/away_{feature}` plus a `features_at` stamp, and on `teams.real_matches` as `{feature}_for/_against`.
- **A stat the provider didn't report is stored as `None`, never 0** — a blank must not read as "zero blocked shots" when this is fitted on later. The one exception is `shots_for/_against`, coerced to int because the live v2 λ already consumes `shots_for` and must not start seeing None.
- **Coverage is first-class**: `team_features()` returns each average with the number of games it was actually computed from (`covered`), sync prints per-league coverage and records it in `sync_runs.feature_coverage`, and `GET /api/features/coverage` reports fill rates per league. **Expect dangerous attacks to be sparse** — API-Football only returns it where the league's coverage includes it, so check this endpoint before reading anything into that feature.
- Exposed alongside the corner inputs on `/api/leagues/{id}/teams` (`features`), `/api/leagues/{id}/corner-table` (`shots_on_target`, `blocked_shots`, `dangerous_attacks` + `features`) and `/api/fixtures/{id}` (per-split `features` + per-match values on `recent`).
- **Ingest fix that came with it**: a fixture whose statistics carry no Corner Kicks value used to be cached as 0-0 corners (the old parser coerced a null to 0) and fed the model as a real 0-0 game. It is now skipped. A genuine 0 still parses as 0, so only truly uncovered fixtures are dropped — expect the cached fixture count to be slightly lower than before on leagues with patchy coverage.
- **The projection is deliberately unchanged** — `v2_lambda`, `expected_lambdas`, `build_markets` and the backtester are untouched, so model output is byte-identical. Wiring these in is a separate decision once the backtester says they help.
- `backfill_shots.py`: fills this season's cached fixtures (one statistics call each, `--limit N` per league, resumable via `features_at`, `--project-only` for the DB-only half), then projects onto `teams.real_matches` on the `(api_team_id, day)` join `backfill_fh.py` uses.
- `backend/tests/test_shot_features.py`: 20 offline unit tests (alias/percent/null parsing, None-vs-zero, venue/window aggregation, coverage counts).

### Under-line corner streaks — one streak model, two directions (2026-08-12)
- `/api/streaks` gained `direction=over|under` and `subject=team|match` (plus `max_line`) instead of a second endpoint/collection. Defaults (`over`/`team`) are byte-compatible with the old response, so `best-bets`, the export and existing tests are untouched.
- **Settlement**: `settle_streak_leg()` — an over line keeps its historic "L+" meaning (= Over L-0.5, can't push); an under is a laddered WHOLE line where below wins, **exactly on the line voids** and above loses. A void never breaks a run, is excluded from the hit-rate denominator (`settled = hits + misses`) and counts towards `min_hits`; a line carried entirely by voids is rejected.
- **Ladder**: `pick_streak_line()` walks `STREAK_LADDERS` (team 1-15, match 1-30) and picks the HIGHEST cleared line on an over, the TIGHTEST held line on an under. Under rows are capped by `UNDER_LINE_CAP` (team 8, match 12) — above that a line is true too often to mean anything.
- **Streak record**: every row carries `streak {length, start_date, last_date, voids, status: active|broken}` computed over the team's full venue history (can exceed the window) and `longest {length, start_date, end_date, is_current}` — the longest historical run at that line/direction, shown next to the live one.
- **Pricing** (`_streak_projection`): match totals use Poisson on λ(team)+λ(opp), team lines stay NB. Whole-line unders price over SETTLED outcomes (`p_win / (p_win + p_loss)`), EV credits the pushed stake back (`book·p_win + p_void − 1`), market key `{group}_under_{line}` (overs keep `{group}_over_{line-0.5}`). New `nb_pmf()`; `nb_ge()` now sums it.
- Frontend: `StreakFinder.jsx` gained an **Over/Under toggle + Team corners/Match total select in-place** (deliberately NOT a new /scanner tab) and Streak / Longest columns; recent chips colour win/void/miss; unders render in sky, overs stay emerald. Testids: `streak-direction-over|under`, `streak-subject`. Export report gained team + match under-streak tables.
- `backend/tests/test_streak_model.py`: 19 offline unit tests (settlement, voids, run tracking, ladder, push-adjusted pricing) — no backend or DB needed.

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
