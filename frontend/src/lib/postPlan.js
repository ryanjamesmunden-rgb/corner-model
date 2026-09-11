// Which board goes out on which day.
//
// This lives here, next to shareText, rather than as a case statement in the workflow's
// bash — for the same reason the post format does. Logic in a YAML `run:` block can only
// be tested by pushing it and waiting until Thursday, so the one part of a daily poster
// that is easy to get quietly wrong is the part nothing can check.
//
// THE WEEK IS BUILT AROUND WHAT IS WORTH SAYING THAT DAY, not around variety for its own
// sake. Monday is the only day of the week that can report a result, so Monday reports
// results. Friday through Sunday is when people are actually looking for games, so those
// days carry the fixture board. Tuesday and Thursday carry streaks, which are the thing
// that makes someone click through to a site rather than just read a tweet.
//
// SATURDAY AND SUNDAY LOOK ONE DAY AHEAD, not three. On a Saturday morning the useful
// question is "what is on today", and a three-day window answers it with a list mostly
// made of games that have not been priced yet.

/** 1 = Monday … 7 = Sunday, matching `date +%u`. */
export const MONDAY = 1;
export const SATURDAY = 6;

/**
 * What to post on a given weekday: which board, and how far ahead it looks.
 *
 * `fallback` is the board to use when the first one has nothing — only Monday has one,
 * because only Monday's board can be empty for a reason that is nobody's fault (a weekend
 * that was never snapshotted, or results not yet synced). Every other day's board being
 * empty means there is genuinely nothing worth posting, and the right answer then is to
 * post nothing rather than to reach for a different board to fill the slot.
 */
export const boardForDay = (weekday) => {
  switch (Number(weekday)) {
    case 1: return { board: "results", days: 3, fallback: "streaks" };
    case 2: return { board: "streaks", days: 3, fallback: null };
    case 3: return { board: "game", days: 3, fallback: null };
    case 4: return { board: "streaks", days: 3, fallback: null };
    case 5: return { board: "game", days: 3, fallback: null };
    case 6: return { board: "game", days: 1, fallback: null };
    case 7: return { board: "game", days: 1, fallback: null };
    default: return { board: "streaks", days: 3, fallback: null };
  }
};

/** Friday freezes the weekend's streaks so Monday has something honest to grade. */
export const freezesSnapshot = (weekday) => Number(weekday) === 5;

/**
 * A SECOND thing Friday sends, to the paid channel rather than to X.
 *
 * The public post goes out on the day of the game, which is the worst moment to hear
 * about it — by Saturday lunchtime the market has found the same game and the price has
 * gone. A member should see Sunday's card on Friday, while it is still there to take.
 * The product is earlier information, not different information, and a daily-only
 * schedule quietly gives that away.
 *
 * Null on every other day: the weekend is the only block of fixtures far enough ahead to
 * be worth sending early, and a "card" of one midweek game is just the post again.
 */
export const extraForDay = (weekday) => (Number(weekday) === 5 ? "weekend" : null);

/** Monday is the only day that can report on a weekend that has finished. */
export const gradesWeekend = (weekday) => Number(weekday) === MONDAY;
