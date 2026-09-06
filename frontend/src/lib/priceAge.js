// How old the price behind an edge is.
//
// A value board ranks fixtures by the gap between the model and a price someone typed
// in by hand. That makes the number only as current as the typing: an edge computed
// against Tuesday's price is arithmetic about a price that no longer exists, and it
// looks exactly like a live one on screen. So every row says how old its price is, and
// the older it gets the louder the row says it.

const MIN = 60e3, HOUR = 60 * MIN, DAY = 24 * HOUR;

/** Rough age in words. Deliberately coarse — "2h ago" is the decision, not "2h 14m". */
export const priceAge = (iso, now = Date.now()) => {
  if (!iso) return null;
  const t = new Date(iso).getTime();
  if (!Number.isFinite(t)) return null;
  const ms = Math.max(0, now - t);
  if (ms < 90 * MIN) return { ms, label: ms < 2 * MIN ? "just now" : `${Math.round(ms / MIN)}m ago` };
  if (ms < DAY) return { ms, label: `${Math.round(ms / HOUR)}h ago` };
  const days = Math.round(ms / DAY);
  return { ms, label: days === 1 ? "yesterday" : `${days}d ago` };
};

// Under two hours a price is worth acting on; past six it is a lead at best; past a day
// the edge is about a number nobody has checked since. The thresholds are judgement
// rather than measurement, and are set where a punter would agree rather than where the
// arithmetic changes.
export const FRESH = 2 * HOUR;
export const STALE = 6 * HOUR;

export const priceFreshness = (iso, now = Date.now()) => {
  const age = priceAge(iso, now);
  if (!age) return { key: "unknown", label: "no timestamp", cls: "text-muted-foreground/60",
                     note: "This price was entered before the site started recording when — re-enter it to be sure." };
  if (age.ms < FRESH) return { key: "fresh", label: age.label, cls: "text-muted-foreground", note: "" };
  if (age.ms < STALE) return { key: "ageing", label: age.label, cls: "text-amber-400",
                               note: "Worth re-checking before you stake." };
  return { key: "stale", label: age.label, cls: "text-red-400",
           note: "Old enough that the price has probably moved — re-enter it before trusting this edge." };
};
