// How old the data is, and whether to admit it.
//
// The header badge used to be hardcoded green — a pulsing dot and the word LIVE
// regardless of age — so when the provider account was suspended the site showed
// "LIVE · 5d ago" for five days. Green and a pulse are what a reader takes in; the
// number beside them does not cancel either. This is the part that can say no.
//
// Pure and separate from Layout so the thresholds can be tested without a DOM: they
// have to agree with the server, and a silent drift between them is how a stale site
// looks healthy again.

// Matches server.py's SCREEN_STALE_HOURS — one 12-hourly cycle plus slack, so a
// scheduled run landing a few minutes late is not an alarm.
export const FRESH_HOURS = 13;
// Matches report_sync.py's STALE_AFTER_HOURS — a whole cycle missed. Past this the
// schedule is not recovering on its own and something needs a person.
export const MISSED_HOURS = 26;

const LIVE = {
  key: "live", label: "LIVE", pulse: true,
  cls: "bg-emerald-500/10 border-emerald-500/25", dot: "bg-emerald-400",
  text: "text-emerald-300",
};
const LATE = {
  key: "late", label: "STALE", pulse: false,
  cls: "bg-amber-500/10 border-amber-500/30", dot: "bg-amber-400",
  text: "text-amber-300",
};
const STALE = {
  key: "stale", label: "STALE", pulse: false,
  cls: "bg-red-500/10 border-red-500/30", dot: "bg-red-400",
  text: "text-red-300",
};

/** Presentation for a data age in hours; null when nothing has ever synced. */
export function dataHealth(ageHours) {
  if (ageHours === null || ageHours === undefined || Number.isNaN(ageHours)) return null;
  if (ageHours < FRESH_HOURS) return LIVE;
  if (ageHours < MISSED_HOURS) return LATE;
  return STALE;
}

/** Tooltip. The stale ones say what it means for the numbers, not just that time passed. */
export function healthTitle(key, lastSynced) {
  const at = new Date(lastSynced).toLocaleString();
  if (key === "live") return `Fixtures & stats auto-refresh every 12h · last update ${at}`;
  if (key === "late") {
    return `A refresh was due and has not landed — last update ${at}. `
         + `Numbers below do not include anything since then.`;
  }
  return `No refresh for over a day — last update ${at}. `
       + `Treat everything below as out of date; recent results are missing.`;
}

/** "12m ago" / "6h ago" / "5d ago". */
export function freshnessLabel(lastSynced, now) {
  if (!lastSynced) return null;
  const mins = Math.max(0, Math.round((now - lastSynced) / 60000));
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.round(mins / 60);
  if (hrs < 48) return `${hrs}h ago`;
  return `${Math.round(hrs / 24)}d ago`;
}
