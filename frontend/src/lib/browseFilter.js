/**
 * Narrowing the front door: a search box and a row of league badges.
 *
 * WHY NOT A DROPDOWN. The country tree is the right shape for browsing and the wrong one
 * for arriving with something in mind. Finding Cottbus meant knowing Germany, opening it,
 * knowing it is 2. Bundesliga, opening that, then reading. A dropdown of thirty-one
 * competitions has the same problem one level up: it is a list you have to already know
 * the answer in. Search answers "where is this team", and the badge row answers "just
 * show me this league" in one tap, with the flag doing the work the name would need a
 * sentence for.
 *
 * BOTH NARROW THE SAME TREE and are applied before either order renders, so they work
 * identically by country and by time. They compose: a league badge plus a query means
 * that query inside that league.
 *
 * AND THE COUNTS FOLLOW THEM. This is the rule the browse endpoint already keeps and the
 * one a client-side filter is most likely to break, because hiding rows is so much
 * easier than re-counting them: a league reading "12" that opens to two is worse than one
 * reading two, since the count is what a reader decides to open on. Every count here is
 * recomputed from what survived rather than carried over.
 */

/** Everything a search looks at on one game. Team names first — it is why people type. */
const haystack = (game, league, country) => [
  game.home, game.away, league.name, country.country, game.round,
].filter(Boolean).join(" ").toLowerCase();

/**
 * Does this game match what was typed?
 *
 * EVERY WORD HAS TO APPEAR, in any order and anywhere. "man utd" and "utd man" both find
 * Manchester United, and "brugge bel" narrows rather than finding nothing — a single
 * substring test fails both, and failing a search looks like having no data.
 */
export function matchesQuery(game, league, country, q) {
  const terms = String(q || "").toLowerCase().split(/\s+/).filter(Boolean);
  if (!terms.length) return true;
  const hay = haystack(game, league, country);
  return terms.every((t) => hay.includes(t));
}

/**
 * The tree, narrowed, with every count rebuilt from what is left.
 *
 * EMPTY LEAGUES AND COUNTRIES GO when a filter is on, which is the opposite of the
 * endpoint's rule and deliberately so. The endpoint keeps an empty league because the
 * tree is a stable thing you are scrolling and a row vanishing moves what you were about
 * to tap. A search result is not that: it is a list you asked for, and "England ▸
 * Championship ▸ nothing" is a row that can only be opened to be disappointed.
 */
export function filterTree(countries = [], { q = "", league = "" } = {}) {
  const hasQ = String(q || "").trim().length > 0;
  if (!hasQ && !league) return countries || [];

  const out = [];
  for (const c of countries || []) {
    const leagues = [];
    for (const l of c.leagues || []) {
      if (league && l.league_id !== league) continue;
      const games = (l.games || []).filter((g) => matchesQuery(g, l, c, q));
      if (!games.length) continue;
      leagues.push({ ...l, games, count: games.length });
    }
    if (!leagues.length) continue;
    out.push({ ...c, leagues, count: leagues.reduce((a, l) => a + l.count, 0) });
  }
  return out;
}

/** How many games are in a tree — the headline that has to agree with the rows. */
export const totalOf = (countries = []) =>
  (countries || []).reduce((a, c) => a + (c.count || 0), 0);

/**
 * The badge row: one chip per competition that has something on.
 *
 * ORDERED BY HOW MUCH IS ON, not alphabetically and not by the tree's own order. The row
 * scrolls sideways and most of it is off screen, so the first few chips are the whole
 * design — and "which leagues have a card this week" is the question somebody scanning
 * them is actually asking. Ties keep the tree's order, which is tier then name, so the
 * row does not reshuffle between two equal leagues on every render.
 *
 * COUNTS COME FROM THE TREE AS GIVEN, so when a search is running the badges say how many
 * matches each league holds rather than how big it is. A chip reading 12 beside a list of
 * two would be the same lie as a league header doing it.
 */
export function leagueChips(countries = []) {
  const chips = [];
  (countries || []).forEach((c) => {
    (c.leagues || []).forEach((l) => {
      if (!l.count) return;
      chips.push({
        league_id: l.league_id,
        name: l.name,
        country: c.country,
        count: l.count,
        is_cup: !!l.is_cup,
      });
    });
  });
  return chips.sort((a, b) => b.count - a.count);
}

/**
 * What to say when a filter removed everything.
 *
 * NAMING WHAT WAS TYPED, because an empty page is ambiguous between "no such team",
 * "nothing on in that league this week" and "the site is broken", and only the first two
 * are true here. It also says which control to clear, since with two of them on at once
 * a reader cannot tell which one emptied the page.
 */
export function emptyReason({ q = "", league = "", leagueName = "" } = {}) {
  const term = String(q || "").trim();
  if (term && league) {
    return `No games matching "${term}" in ${leagueName || "that competition"}.`;
  }
  if (term) return `No games matching "${term}".`;
  if (league) return `Nothing on in ${leagueName || "that competition"} in this window.`;
  return "";
}


/**
 * The day chips, counted against whatever is actually showing.
 *
 * THE SERVER'S CALENDAR IS BUILT BEFORE THE DAY FILTER so the chips keep saying what
 * else is on — that is right and this does not change it. But it is built before the
 * SEARCH too, because the search did not exist server-side, so with a query running the
 * chips were offering "Wed 5" next to a list of one. Tapping it would have produced one
 * game, because the query survives the day change. That is the same lie a league header
 * reading 12 above two rows would be telling.
 *
 * WITH A DAY ALREADY PICKED the tree holds only that day, so there is nothing here to
 * count the others from. Rather than print a number known to be wrong, the counts are
 * dropped and the chips stay as navigation — a chip with no count is less useful than a
 * correct one and far better than a false one.
 */
export function dayChips(countries = [], serverCalendar = [], { filtering = false,
                                                                day = "" } = {}) {
  if (!filtering) return serverCalendar || [];
  if (day) return (serverCalendar || []).map((c) => ({ day: c.day, count: null }));
  const tally = {};
  (countries || []).forEach((c) => (c.leagues || []).forEach(
    (l) => (l.games || []).forEach((g) => {
      if (g.day) tally[g.day] = (tally[g.day] || 0) + 1;
    })));
  return Object.keys(tally).sort().map((d) => ({ day: d, count: tally[d] }));
}
