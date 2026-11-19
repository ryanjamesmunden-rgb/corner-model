// What the value board's "when" control means, and the query it turns into.
//
// IN A LIB RATHER THAN IN THE COMPONENT because two things ask the same question: the
// board, which renders the rows, and the Copy-the-day button, which posts them. Built
// twice they drift, and the way they drift is the worst possible one — a card headed
// "Saturday" carrying a different day's games from the screen it was pressed on.
//
// Pure, so it is tested like the rest of this folder rather than needing a browser.

/** 'YYYY-MM-DD' for a Date, in London — the day the server files a kick-off under. */
export const londonDay = (d) =>
  new Intl.DateTimeFormat("en-CA", { timeZone: "Europe/London" }).format(d);

/**
 * The value select's options: a day picker with the two ranges at the ends.
 *
 * A DAY, NOT A WINDOW, and that is the point rather than a relabelling. This control used
 * to offer "next 3 days / 7 / 14", which are CUMULATIVE — "next 3 days" is today AND
 * tomorrow AND the day after. That is the right shape for browsing and the wrong one for
 * the job the board grew into, which is posting the day's EV+ card to the channel. A
 * cumulative window carries Saturday's games into Sunday's post, and the only way to stop
 * it was to read the kick-off on every row and leave the rest out by hand.
 *
 * "All upcoming" stays because "what have I priced at all" is still a real question and a
 * day picker cannot answer it.
 */
export const dayOptions = (now = new Date()) => {
  const named = (d) => new Intl.DateTimeFormat("en-GB", {
    timeZone: "Europe/London", weekday: "short", day: "numeric", month: "short",
  }).format(d);
  const out = [{ v: "all", l: "All upcoming" }];
  for (let i = 0; i < 7; i += 1) {
    const d = new Date(now.getTime() + i * 86400000);
    out.push({ v: `d:${londonDay(d)}`,
               l: i === 0 ? "Today" : i === 1 ? "Tomorrow" : named(d) });
  }
  out.push({ v: "w:7", l: "Next 7 days" });
  return out;
};

/** The day a "when" value names, or "" when it names a range. */
export const dayOf = (when) =>
  String(when || "").startsWith("d:") ? String(when).slice(2) : "";

/**
 * A "when" value and a floor -> the params /value-board takes.
 *
 * "all" sends NEITHER, which is what makes it mean all upcoming: within_days is optional
 * on the server and omitting it is how the horizon is switched off. Sending 0 would read
 * as a zero-day horizon and return nothing.
 */
export const boardParams = (when, floor, extra = {}) => {
  const params = { min_ev: Number(floor), limit: 40, ...extra };
  const day = dayOf(when);
  if (day) params.day = day;
  else if (String(when).startsWith("w:")) params.within_days = Number(String(when).slice(2));
  return params;
};
