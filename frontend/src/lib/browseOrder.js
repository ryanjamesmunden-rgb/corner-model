/**
 * Re-grouping the front door's one payload into the two orders people read it in.
 *
 * COUNTRY ORDER answers "what is on in England". TIME ORDER answers "what is on today,
 * and what is next". Neither is a worse version of the other — they are the two ways
 * anybody reads a fixture list — and the server sends a tree that only directly supports
 * the first. This flattens that tree and regroups it, in the browser, from the payload
 * already in hand.
 *
 * WHY NOT ASK THE SERVER FOR THE OTHER ORDER. Because then the two orders could disagree:
 * two requests a second apart can straddle a sync, and "the Saturday list has eleven" in
 * one order and ten in the other is a bug nobody would be able to reproduce. Regrouping
 * what is already here makes them the same games by construction, and instant.
 */

/** How many day sections of a time-ordered list start open. */
export const OPEN_DAYS = 2;

/**
 * Every game in the tree, each carrying where it came from.
 *
 * TIME ORDER HAS NO HEADERS TO INHERIT FROM. Under "England › Championship" a row needs
 * to say neither; pulled out of that tree it is two team names and a clock, and
 * "Reading v Bradford" means something different in the Championship from what it means
 * in a cup. So the country, the competition and the league id travel with the row — the
 * id because the flag is derived from it and not from the country's name (see
 * countryFlag.js for why that distinction is load-bearing).
 */
export function flattenGames(countries = []) {
  return (countries || []).flatMap((c) =>
    (c?.leagues || []).flatMap((l) =>
      (l?.games || []).map((g) => ({
        ...g,
        country: c.country,
        league_id: l.league_id,
        league_name: l.name,
        is_cup: !!l.is_cup,
      }))));
}

/**
 * Games grouped by the day they are played, earliest day first, kick-off order within.
 *
 * KEYED ON `day`, WHICH THE SERVER COMPUTED IN LONDON, not on the ISO timestamp. A 20:00
 * kick-off in Brazil is 23:00 UTC the same day and a 01:30 one is the NEXT day in UTC, so
 * grouping on the timestamp here would scatter half the South American card into a day
 * the reader is not in — the same trap the day filter already avoids, and it has to be
 * avoided the same way or the two would disagree.
 */
export function byDay(games = []) {
  const days = new Map();
  (games || []).forEach((g) => {
    if (!g || !g.day) return;
    if (!days.has(g.day)) days.set(g.day, []);
    days.get(g.day).push(g);
  });
  return [...days.entries()]
    .sort((a, b) => (a[0] < b[0] ? -1 : 1))
    .map(([day, list]) => ({
      day,
      games: [...list].sort((a, b) => ((a.date || "") < (b.date || "") ? -1 : 1)),
    }));
}

/**
 * Whether a day section is open: clicked state if there is one, otherwise by position.
 *
 * DERIVED RATHER THAN STORED, so changing the window or the filter re-derives it instead
 * of leaving yesterday's clicks applied to a different list. Today and tomorrow start
 * open because that is the question time order is for; twenty-eight days rendered open
 * is several hundred rows nobody asked for.
 */
export function dayIsOpen(openDays, day, index) {
  const chosen = (openDays || {})[day];
  return chosen === undefined ? index < OPEN_DAYS : !!chosen;
}
