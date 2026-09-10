import axios from "axios";

// Falls back to the deployed backend so a missing build-time env var can't
// ship a bundle that requests "undefined/api". Not a secret — the URL is
// baked into the client bundle either way.
const BACKEND = process.env.REACT_APP_BACKEND_URL || "https://corner-model.onrender.com";

export const API = `${BACKEND}/api`;

// SESSION TOKEN. Kept in localStorage rather than a cookie because the frontend and the
// backend are on different origins (Vercel and Render), which makes a cookie need
// SameSite=None, Secure and CORS credentials on every call — three things to get wrong
// for no gain here. A bearer header is simpler and does the same job.
const TOKEN_KEY = "cm2_session";
export const getToken = () => { try { return localStorage.getItem(TOKEN_KEY); } catch { return null; } };
export const setToken = (t) => { try { t ? localStorage.setItem(TOKEN_KEY, t) : localStorage.removeItem(TOKEN_KEY); } catch { /* private mode */ } };

// Attach the session to every call. Signed out simply sends nothing, and the backend
// answers as the guest — the site is public, so that is an ordinary request, not a
// refused one.
axios.interceptors.request.use((cfg) => {
  const t = getToken();
  if (t && String(cfg.url || "").startsWith(API)) {
    cfg.headers = { ...(cfg.headers || {}), Authorization: `Bearer ${t}` };
  }
  return cfg;
});

// Preview metadata rides on the RESPONSE HEADERS, not in the body.
//
// The paid boards return a list, and half a dozen components already destructure that
// list. Wrapping it in {rows, preview, total} to carry two extra facts would have meant
// touching every one of them, so the facts travel beside the body and are attached to it
// here: `.length`, `.map` and every existing read keep working, and a component that
// does not care never notices.
//
// `total` is how many rows a MEMBER would have got. When the headers are missing — an
// older backend, or a CORS policy that has not caught up — this falls back to "not a
// preview", which shows whatever arrived rather than inventing a wall over real data.
const withPreview = (r) => {
  const body = r.data;
  if (body && typeof body === "object") {
    const total = Number(r.headers?.["x-total-rows"]);
    body.preview = r.headers?.["x-preview"] === "true";
    body.total = Number.isFinite(total) ? total : undefined;
  }
  return body;
};

export const api = {
  config: () => axios.get(`${API}/config`).then((r) => r.data),
  signInWithGoogle: (credential) =>
    axios.post(`${API}/auth/google`, { credential }).then((r) => r.data),
  me: () => axios.get(`${API}/auth/me`).then((r) => r.data),
  redeemCode: (code) => axios.post(`${API}/membership/redeem`, { code }).then((r) => r.data),
  // Billing. Both return a Stripe-hosted URL to send the browser to — checkout starts a
  // subscription, portal is where cancelling actually happens.
  billingCheckout: () => axios.post(`${API}/billing/checkout`).then((r) => r.data),
  billingPortal: () => axios.post(`${API}/billing/portal`).then((r) => r.data),
  // cancel:false resumes a subscription that was set to end.
  billingCancel: (cancel = true) => axios.post(`${API}/billing/cancel`, { cancel }).then((r) => r.data),
  favourites: () => axios.get(`${API}/favourites`).then((r) => r.data),
  addFavourite: (fixtureId) => axios.post(`${API}/favourites/${fixtureId}`).then((r) => r.data),
  removeFavourite: (fixtureId) => axios.delete(`${API}/favourites/${fixtureId}`).then((r) => r.data),
  // Followed TEAMS, separate from starred fixtures: a fixture star is spent once the
  // game kicks off, a team follow is meant to outlive seasons.
  favouriteTeams: (withinDays = 30) =>
    axios.get(`${API}/favourites/teams`, { params: { within_days: withinDays } }).then((r) => r.data),
  addFavouriteTeam: (teamId) => axios.post(`${API}/favourites/teams/${teamId}`).then((r) => r.data),
  removeFavouriteTeam: (teamId) => axios.delete(`${API}/favourites/teams/${teamId}`).then((r) => r.data),
  leagues: () => axios.get(`${API}/leagues`).then((r) => r.data),
  teams: (id, split, window) => axios.get(`${API}/leagues/${id}/teams`, { params: { split, window } }).then((r) => r.data),
  fixtures: (id) => axios.get(`${API}/leagues/${id}/fixtures`).then((r) => r.data),
  fixture: (id) => axios.get(`${API}/fixtures/${id}`).then((r) => r.data),
  setOdds: (id, odds) => axios.post(`${API}/fixtures/${id}/odds`, { odds }).then((r) => r.data),
  scanner: (params) => axios.get(`${API}/scanner`, { params }).then((r) => r.data),
  valueBoard: (params) => axios.get(`${API}/value-board`, { params }).then(withPreview),
  streaks: (params) => axios.get(`${API}/streaks`, { params }).then(withPreview),
  matchups: (id, side) => axios.get(`${API}/leagues/${id}/matchups`, { params: { side } }).then((r) => r.data),
  cornerTable: (id) => axios.get(`${API}/leagues/${id}/corner-table`).then((r) => r.data),
  trends: (params) => axios.get(`${API}/trends`, { params }).then(withPreview),
  bestBets: () => axios.get(`${API}/best-bets`).then((r) => r.data),
  // Wagers. Every one of these needs a signed-in account — see the note on create_bet.
  bets: () => axios.get(`${API}/bets`).then((r) => r.data),
  placeBet: (body) => axios.post(`${API}/bets`, body).then((r) => r.data),
  deleteBet: (id) => axios.delete(`${API}/bets/${id}`).then((r) => r.data),
  betsWeek: (days) => axios.get(`${API}/bets/week`, { params: { days } }).then((r) => r.data),
  chaseBoard: (params) => axios.get(`${API}/chase-board`, { params }).then(withPreview),
  fixtureBoard: (params) => axios.get(`${API}/fixture-board`, { params }).then((r) => r.data),
  topCornerTeams: (params) => axios.get(`${API}/top-corner-teams`, { params }).then((r) => r.data),
  perfectGames: (params) => axios.get(`${API}/perfect-games`, { params }).then(withPreview),
  topMismatches: (params) => axios.get(`${API}/top-mismatches`, { params }).then(withPreview),
  exportMarkdown: () => axios.get(`${API}/export`, { responseType: "text" }).then((r) => r.data),
  exportStreaks: (days = 7) => axios.get(`${API}/export/streaks`, { params: { days }, responseType: "text" }).then((r) => r.data),
  exportCsv: (type) => axios.get(`${API}/export/csv`, { params: { type }, responseType: "text" }).then((r) => r.data),
  // Token-gated, unconditional. The scheduled workflow uses /sync/if-stale instead,
  // which needs no token because it only acts when the data is actually old.
  toolSyncNow: (token) => axios.post(`${API}/sync/refresh-all`, null, { params: { token } }).then((r) => r.data),
  syncRuns: (limit = 8) => axios.get(`${API}/sync/runs`, { params: { limit } }).then((r) => r.data),
  // No UI calls these since the Picks page was removed. Kept because the manual pick
  // path is how /join eventually publishes a record built from settled results rather
  // than typed figures — see the note at the top of Join.jsx.
  picks: () => axios.get(`${API}/picks`).then((r) => r.data),
  settlePicks: () => axios.post(`${API}/picks/settle`).then((r) => r.data),
  // OPEN. No token, no account — see public_results. The record is the argument for
  // paying, and an argument nobody can read persuades nobody.
  results: (weeks) => axios.get(`${API}/results`, { params: { weeks } }).then((r) => r.data),
  // Token-gated write. The backend stamps before_kickoff from its own clock — the caller
  // cannot send it, which is what keeps the public rate honest.
  logPostedAngle: (token, body) => axios.post(`${API}/angles/posted`, body, { params: { token } }).then((r) => r.data),
  ledger: () => axios.get(`${API}/ledger`).then((r) => r.data),
  snapshotLedger: () => axios.post(`${API}/ledger/snapshot`).then((r) => r.data),
  backtest: (leagueId = "all", model = "v1") => axios.get(`${API}/backtest`, { params: { league_id: leagueId, model } }).then((r) => r.data),
  explain: (payload) => axios.post(`${API}/explain`, payload).then((r) => r.data),
  toolRuns: (token, script) => axios.get(`${API}/tools/runs`, { params: { token, script } }).then((r) => r.data),
  toolMeasure: (token, mode, leagueId) => axios.post(`${API}/tools/measure`, null, { params: { token, mode, league_id: leagueId } }).then((r) => r.data),
  toolBackfill: (token, { limit, leagueId, project_only } = {}) => axios.post(`${API}/tools/backfill-shots`, null, { params: { token, limit, league_id: leagueId, project_only } }).then((r) => r.data),
  toolBackfillGoals: (token, { limit, leagueId, project_only } = {}) => axios.post(`${API}/tools/backfill-goals`, null, { params: { token, limit, league_id: leagueId, project_only } }).then((r) => r.data),
  toolProbeHalves: (token) => axios.post(`${API}/tools/probe-halves`, null, { params: { token } }).then((r) => r.data),
  toolProbeStatTypes: (token) => axios.post(`${API}/tools/probe-stat-types`, null, { params: { token } }).then((r) => r.data),
  toolProbeLeagues: (token, leagueId, country) => axios.post(`${API}/tools/probe-leagues`, null, { params: { token, league_id: leagueId, country } }).then((r) => r.data),
};

export const tierMeta = {
  strong: { label: "Strong Value", dot: "bg-emerald-500", text: "text-emerald-400", chip: "bg-emerald-500/15 text-emerald-400 border-emerald-500/30" },
  small: { label: "Small Edge", dot: "bg-amber-500", text: "text-amber-400", chip: "bg-amber-500/15 text-amber-400 border-amber-500/30" },
  none: { label: "No Edge", dot: "bg-red-500", text: "text-red-400", chip: "bg-red-500/15 text-red-400 border-red-500/30" },
};

export const confMeta = {
  High: "bg-emerald-500/15 text-emerald-400 border-emerald-500/30",
  Medium: "bg-amber-500/15 text-amber-400 border-amber-500/30",
  Low: "bg-zinc-500/15 text-zinc-400 border-zinc-500/30",
};
