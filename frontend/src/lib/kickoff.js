// When the next game actually kicks off.
//
// A streak row is only actionable if you know whether the game is tonight or next
// Sunday — "Bodø/Glimt 5+ in 5 of 5" is a reason to look at a price, but only once you
// know there is a price to look at. The date alone doesn't settle it either: at 6pm the
// difference between a 19:45 kick-off and one that started an hour ago is the whole
// decision.
//
// TIMEZONES. Every time here is the READER'S local clock, which is right on screen and
// a trap in shared text — the poster's 19:45 is someone else's 20:45, and a corner
// market is exactly the sort of thing people get wrong by an hour. On screen that needs
// no label, because it is already your own clock; anything leaving the browser has to
// carry timeZoneLabel() somewhere, which is why it is exported separately rather than
// baked into the time.

const parse = (iso) => {
  if (!iso) return null;
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? null : d;
};

const HHMM = { hour: "2-digit", minute: "2-digit" };

/** "19:45" — the kick-off on the reader's own clock. */
export const kickoffTime = (iso) => {
  const d = parse(iso);
  return d ? d.toLocaleTimeString(undefined, HHMM) : "";
};

/**
 * "Today" / "Tomorrow" / "Sat 6 Sep". Relative naming only reaches as far as tomorrow —
 * past that it stops being easier to read than the date and starts being harder.
 */
export const kickoffDay = (iso) => {
  const d = parse(iso);
  if (!d) return "";
  const days = Math.round((new Date(d.toDateString()) - new Date(new Date().toDateString())) / 86400000);
  if (days === 0) return "Today";
  if (days === 1) return "Tomorrow";
  return d.toLocaleDateString(undefined, { weekday: "short", day: "numeric", month: "short" });
};

/** "Today 19:45" — day and time, for a row that has room for both. */
export const kickoffLabel = (iso) => {
  const d = parse(iso);
  return d ? `${kickoffDay(iso)} ${kickoffTime(iso)}` : "";
};

/** "BST", or "GMT+1" where the platform has no abbreviation for the zone. */
export const timeZoneLabel = () => {
  try {
    const parts = new Intl.DateTimeFormat(undefined, { timeZoneName: "short" }).formatToParts(new Date());
    return parts.find((p) => p.type === "timeZoneName")?.value || "";
  } catch {
    return "";
  }
};
