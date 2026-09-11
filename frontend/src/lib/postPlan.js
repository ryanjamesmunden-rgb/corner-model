// Which board goes out on which day.
//
// This lives here, next to shareText, rather than as a case statement in the workflow's
// bash — for the same reason the post format does. Logic in a YAML `run:` block can only
// be tested by pushing it and waiting until Thursday, so the one part of a daily poster
// that is easy to get quietly wrong is the part nothing can check.
//
// THE WEEK HAS A SHAPE AND KEEPS IT. A poster whose pattern moves is one nobody learns to
// expect, and the whole value of posting daily is that people know when to look:
//
//   Mon  picks        how the angles posted to the channel actually landed
//   Tue  game         the midweek fixture with the strongest angle on it
//   Wed  streaks      what is trending, and the weekend card to the channel
//   Thu  —            nothing. A day off, deliberately
//   Fri  game         the best game of the weekend, and freeze the streaks
//   Sat  game         what is on today
//   Sun  game         what is on today
//
// THURSDAY IS SILENT ON PURPOSE. Every other scheduling instinct says fill the slot, and
// filling it is how an account starts posting things nobody needed to read. A day with
// nothing worth saying is worth more than a day of filler, and a gap in the week also
// makes Friday land harder.
//
// THE WEEKEND IS PREPPED ON WEDNESDAY, POSTED ON FRIDAY. Wednesday is roughly when the
// weekend's prices appear, so that is when the paid channel gets the card — two clear days
// before anything public names those games. See extraForDay.
//
// SATURDAY AND SUNDAY LOOK ONE DAY AHEAD, not three. On a Saturday morning the useful
// question is "what is on today", and a three-day window answers it with a list mostly
// made of games nobody has priced yet. Tuesday looks two days, which is the midweek card
// and not the weekend.

/** 1 = Monday … 7 = Sunday, matching `date +%u`. */
export const MONDAY = 1;
export const THURSDAY = 4;
export const FRIDAY = 5;
export const SATURDAY = 6;

/**
 * What to post on a given weekday: which board, and how far ahead it looks.
 *
 * `board: null` means POST NOTHING — see Thursday above. Callers have to handle it, which
 * is the point: a silent day should be a decision the code states, not something that
 * happens because a board came back empty.
 *
 * `fallbacks` are the boards to try when the first has nothing, IN ORDER, and only Monday
 * has any. Its chain is picks → results → streaks, which is a ranking of evidence: angles
 * a person named in advance are a stronger claim than the model's board, and the model's
 * board is stronger than "here is what is running". Each can be empty through nobody's
 * fault — no picks logged, a weekend never snapshotted, results not yet synced — so Monday
 * walks down until something has rows.
 *
 * Every other day being empty means there is genuinely nothing worth posting, and the
 * answer then is silence rather than reaching for a different board to fill the slot.
 */
export const boardForDay = (weekday) => {
  switch (Number(weekday)) {
    case 1: return { board: "picks", days: 3, fallbacks: ["results", "streaks"] };
    case 2: return { board: "game", days: 2, fallbacks: [] };
    case 3: return { board: "streaks", days: 3, fallbacks: [] };
    case 4: return { board: null, days: 0, fallbacks: [] };
    case 5: return { board: "game", days: 3, fallbacks: [] };
    case 6: return { board: "game", days: 1, fallbacks: [] };
    case 7: return { board: "game", days: 1, fallbacks: [] };
    // `date +%u` should never hand this a 0 or an 8, but a poster that throws on an
    // unexpected day is a poster that goes silent for a reason nobody looks for.
    default: return { board: "streaks", days: 3, fallbacks: [] };
  }
};

/** A day the week says nothing on. Thursday, and only Thursday. */
export const isQuietDay = (weekday) => boardForDay(weekday).board === null;

/**
 * Friday freezes the weekend's streaks so Monday has something honest to grade.
 *
 * LAST MOMENT BEFORE KICK-OFF, not the day the card goes out. A snapshot is a record of
 * what was being claimed while it was still a prediction, so it wants to be as late as
 * possible and still before the first whistle. Wednesday would freeze a board that then
 * has two more days to change.
 */
export const freezesSnapshot = (weekday) => Number(weekday) === FRIDAY;

/**
 * A SECOND thing one day sends, to the paid channel rather than to X.
 *
 * WEDNESDAY, because that is roughly when the weekend's prices appear. The public post
 * about those games does not go out until Friday, so a member gets two clear days on a
 * price before anyone reading free has been told the game exists. The product is earlier
 * information, not different information — and a schedule that posts publicly first
 * quietly gives that away.
 *
 * Null on every other day: the weekend is the only block of fixtures far enough ahead to
 * be worth sending early, and a "card" of one midweek game is just the post again.
 */
export const extraForDay = (weekday) => (Number(weekday) === 3 ? "weekend" : null);

/** Monday is the only day that can report on a weekend that has finished. */
export const gradesWeekend = (weekday) => Number(weekday) === MONDAY;
