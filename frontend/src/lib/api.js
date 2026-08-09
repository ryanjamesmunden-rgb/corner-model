import axios from "axios";

export const API = `${process.env.REACT_APP_BACKEND_URL}/api`;
axios.defaults.withCredentials = true;

export const api = {
  leagues: () => axios.get(`${API}/leagues`).then((r) => r.data),
  teams: (id, split, window) => axios.get(`${API}/leagues/${id}/teams`, { params: { split, window } }).then((r) => r.data),
  fixtures: (id) => axios.get(`${API}/leagues/${id}/fixtures`).then((r) => r.data),
  fixture: (id) => axios.get(`${API}/fixtures/${id}`).then((r) => r.data),
  setOdds: (id, odds) => axios.post(`${API}/fixtures/${id}/odds`, { odds }).then((r) => r.data),
  scanner: (params) => axios.get(`${API}/scanner`, { params }).then((r) => r.data),
  streaks: (params) => axios.get(`${API}/streaks`, { params }).then((r) => r.data),
  matchups: (id, side) => axios.get(`${API}/leagues/${id}/matchups`, { params: { side } }).then((r) => r.data),
  cornerTable: (id) => axios.get(`${API}/leagues/${id}/corner-table`).then((r) => r.data),
  trends: (params) => axios.get(`${API}/trends`, { params }).then((r) => r.data),
  bestBets: () => axios.get(`${API}/best-bets`).then((r) => r.data),
  topMismatches: (params) => axios.get(`${API}/top-mismatches`, { params }).then((r) => r.data),
  exportMarkdown: () => axios.get(`${API}/export`, { responseType: "text" }).then((r) => r.data),
  exportCsv: (type) => axios.get(`${API}/export/csv`, { params: { type }, responseType: "text" }).then((r) => r.data),
  refresh: (id) => axios.post(`${API}/leagues/${id}/refresh`).then((r) => r.data),
  refreshAll: () => axios.post(`${API}/sync/refresh-all`).then((r) => r.data),
  syncRuns: (limit = 8) => axios.get(`${API}/sync/runs`, { params: { limit } }).then((r) => r.data),
  picks: () => axios.get(`${API}/picks`).then((r) => r.data),
  settlePicks: () => axios.post(`${API}/picks/settle`).then((r) => r.data),
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
