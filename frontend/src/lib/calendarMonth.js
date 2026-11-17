// The month grid: six rows of seven, and what each square is allowed to say.
//
// THE SQUARE THAT MATTERS IS THE EMPTY ONE. A day with no fixtures on it means one of two
// completely different things — nobody is playing, or the provider has not published that
// far yet — and a grid that drew them the same way would show an empty Saturday three
// weeks out as a free weekend. The backend reports where its fixture list actually stops;
// this turns that into a state per square, and the page draws the two differently.
//
// WEEKS START ON MONDAY, because the thing being read is a football calendar: a weekend
// is Saturday and Sunday together at the end of a row, not split across two.

/** Monday first, as a football week is read. */
export const WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

const MONTHS = ["January", "February", "March", "April", "May", "June",
                "July", "August", "September", "October", "November", "December"];

/** What a square is. Order matters: the page styles them as a ladder. */
export const PAST = "past";
export const TODAY = "today";
export const UPCOMING = "upcoming";
/** Past the last day the fixture list reaches — empty because nobody has said yet. */
export const UNKNOWN = "unknown";
/** Not part of this month; drawn faint so the grid stays rectangular. */
export const OUTSIDE = "outside";

const pad = (n) => String(n).padStart(2, "0");

/** "2026-11-14" -> {y, m, d}, or null. Parsed by hand rather than with Date. */
export const parseDay = (iso) => {
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(String(iso || ""));
  if (!m) return null;
  const [y, mo, d] = [Number(m[1]), Number(m[2]), Number(m[3])];
  if (mo < 1 || mo > 12 || d < 1 || d > 31) return null;
  return { y, m: mo, d };
};

/**
 * Every day key in the grid, including the days either side that fill the rows.
 *
 * BUILT WITH UTC DATE ARITHMETIC, deliberately. `new Date(2026, 10, 1)` is midnight LOCAL,
 * and adding days across a daylight-saving boundary in a local-time Date can land on the
 * same calendar day twice or skip one — which in a month grid silently duplicates or
 * loses a square. Date.UTC has no such boundary.
 */
export const monthGrid = (month) => {
  const m = /^(\d{4})-(\d{2})$/.exec(String(month || ""));
  if (!m) return [];
  const year = Number(m[1]);
  const mon = Number(m[2]);
  if (mon < 1 || mon > 12) return [];

  const first = new Date(Date.UTC(year, mon - 1, 1));
  // getUTCDay is 0 for Sunday; shift so Monday is 0.
  const lead = (first.getUTCDay() + 6) % 7;
  const start = new Date(Date.UTC(year, mon - 1, 1 - lead));

  const out = [];
  for (let i = 0; i < 42; i += 1) {
    const d = new Date(start.getTime() + i * 86400000);
    out.push(`${d.getUTCFullYear()}-${pad(d.getUTCMonth() + 1)}-${pad(d.getUTCDate())}`);
  }
  // SIX ROWS ALWAYS, EXCEPT WHEN THE LAST IS DEAD. A February starting on a Monday fills
  // exactly four rows and a fifth and sixth of nothing; keeping them would put two empty
  // bands under the month. Trimmed only when the whole row is outside the month.
  while (out.length > 28) {
    const tail = out.slice(-7);
    if (tail.some((k) => k.slice(0, 7) === month)) break;
    out.length -= 7;
  }
  return out;
};

/**
 * One square, ready to draw.
 *
 * `horizon` is the last day the backend's fixture list reaches. Past it an empty square is
 * UNKNOWN rather than UPCOMING, which is the whole reason this file exists.
 */
export const squareState = (key, { month, today, horizon, fixtures = 0 } = {}) => {
  if (!key) return OUTSIDE;
  if (key.slice(0, 7) !== month) return OUTSIDE;
  if (today && key === today) return TODAY;
  if (today && key < today) return PAST;
  // A day WITH fixtures is never unknown, however far out it is: something is published.
  if (fixtures > 0) return UPCOMING;
  if (horizon && key > horizon) return UNKNOWN;
  return UPCOMING;
};

/**
 * The month as squares, each carrying its day's fixtures and the games of my teams.
 *
 * `days` comes from the endpoint already keyed by the UK calendar day — grouped there so
 * the counts and the squares cannot disagree about which day a late kick-off belongs to.
 */
export const buildMonth = (data = {}) => {
  const month = data?.month || "";
  const keys = monthGrid(month);
  if (!keys.length) return null;
  const byDay = new Map((data?.days || []).map((d) => [d.date, d]));
  const squares = keys.map((key) => {
    const day = byDay.get(key) || { date: key, fixtures: 0, leagues: 0, mine: [] };
    return {
      key,
      day: Number(key.slice(8, 10)),
      fixtures: day.fixtures || 0,
      leagues: day.leagues || 0,
      mine: day.mine || [],
      state: squareState(key, { month, today: data?.today, horizon: data?.horizon,
                                fixtures: day.fixtures || 0 }),
    };
  });
  return {
    month,
    label: monthLabel(month),
    squares,
    weeks: chunk(squares, 7),
    today: data?.today || null,
    horizon: data?.horizon || null,
    // How much of this month the fixture list does not reach. Said as a count rather than
    // left to the eye: four greyed squares at the end of a row are easy to miss.
    unknownDays: squares.filter((s) => s.state === UNKNOWN).length,
    mineCount: squares.reduce((n, s) => n + s.mine.length, 0),
    fixtureCount: squares.reduce((n, s) => n + s.fixtures, 0),
    busiest: squares.reduce((best, s) =>
      (s.state !== OUTSIDE && s.mine.length > (best?.mine.length || 0) ? s : best), null),
  };
};

const chunk = (rows, n) => {
  const out = [];
  for (let i = 0; i < rows.length; i += n) out.push(rows.slice(i, i + n));
  return out;
};

/** "November 2026" — spelled out rather than locale-formatted, as recordCard argues. */
export const monthLabel = (month) => {
  const m = /^(\d{4})-(\d{2})$/.exec(String(month || ""));
  if (!m) return "";
  const i = Number(m[2]) - 1;
  return i >= 0 && i < 12 ? `${MONTHS[i]} ${m[1]}` : "";
};

/**
 * "Sat 21 November" — the day a square stands for, for the panel under the grid.
 *
 * BUILT FROM THE KEY'S OWN DIGITS, never by parsing it into a Date and formatting that.
 * These keys are UK calendar days: the backend builds them in Europe/London so a 20:00
 * kick-off cannot land on the wrong square. `new Date("2026-11-21")` is UTC midnight, so
 * for any reader west of London it formats as the 20th — and the panel would then name a
 * different day from the square the reader just tapped.
 *
 * No year, because the heading above the grid already carries it.
 */
export const dayLabel = (key) => {
  const p = parseDay(key);
  if (!p) return "";
  // getUTCDay on a UTC-constructed date: no local zone involved either way. Sunday is 0
  // there and last here, so shift by six.
  const weekday = WEEKDAYS[(new Date(Date.UTC(p.y, p.m - 1, p.d)).getUTCDay() + 6) % 7];
  return `${weekday} ${p.d} ${MONTHS[p.m - 1]}`;
};

/**
 * What to say when the month has none of your games on it.
 *
 * TWO COMPLETELY DIFFERENT FACTS, and the page used to state the first one whatever the
 * truth was: "No teams followed yet". That is a claim about somebody's ACCOUNT, and the
 * page had not looked — it was inferred from an empty grid. Follow six sides whose games
 * are not matching and it tells you that you follow none, which sends you off to star
 * teams you already have.
 *
 * The endpoint has always sent `teams`, so the two states are there to be told apart:
 * nobody followed, versus followed and not playing. The second names them, because if
 * those sides obviously DO play this month then the fault is in the matching, and the
 * page has just said so instead of hiding it.
 */
export const emptyNote = (data = {}, label = "") => {
  const teams = (data?.teams || []).filter(Boolean);
  if (!teams.length) {
    // THE BELL, NOT THE STAR, and the distinction is the whole reason this page looked
    // broken. TeamStar's own note spells it out: "a star keeps one game, a bell or an eye
    // is about a club". Sending somebody to look for a star is sending them to the
    // control that fills a different list from the one this page reads.
    return "No teams followed yet — tap the 🔔 beside any team, or follow one below.";
  }
  const names = teams.map((t) => t?.name).filter(Boolean);
  const who = names.length === 0 ? ""
    : names.length <= 3 ? ` (${names.join(", ")})`
    : ` (${names.slice(0, 3).join(", ")} and ${names.length - 3} more)`;
  const plural = teams.length === 1 ? "" : "s";
  return `Following ${teams.length} team${plural}${who} — none of them play`
         + (label ? ` in ${label}` : "") + ".";
};

/**
 * The small print under a game on the day panel: why it is on your calendar.
 *
 * A SAVED GAME HAS NO SIDE, and that is not a missing field. A followed team puts a game
 * there from that team's point of view — "Vila Nova at home" — but a saved game was
 * starred as a FIXTURE, with no team attached. Rendering it through the team branch gave
 * a stray " away" hanging off the league name, which reads as a bug in the data.
 */
export const mineDetail = (g = {}) => {
  if (g?.list === "saved") return "saved game";
  const where = g?.side === "home" ? "at home" : g?.side === "away" ? "away" : "";
  const who = [g?.team, where].filter(Boolean).join(" ");
  return who + (g?.list === "tracking" ? `${who ? " · " : ""}tracking` : "");
};

/** The month before or after, as "YYYY-MM". */
export const shiftMonth = (month, by) => {
  const m = /^(\d{4})-(\d{2})$/.exec(String(month || ""));
  if (!m) return "";
  const total = Number(m[1]) * 12 + (Number(m[2]) - 1) + Number(by || 0);
  return `${String(Math.floor(total / 12)).padStart(4, "0")}-${pad((total % 12) + 1)}`;
};

/**
 * May the reader step to this month?
 *
 * The endpoint refuses anything outside its own window with a 400, so the arrows have to
 * know the same bounds — otherwise the page offers a step that can only produce an error.
 */
export const canShift = (month, by, { today = "", back = 2, ahead = 3 } = {}) => {
  const target = shiftMonth(month, by);
  const now = parseDay(today) || null;
  if (!target || !now) return false;
  const [ty, tm] = target.split("-").map(Number);
  const span = (ty - now.y) * 12 + (tm - now.m);
  return span >= -back && span <= ahead;
};

/** "3 games" / "1 game" / "" — what the square says under the number. */
export const mineLabel = (square = {}) => {
  const n = (square.mine || []).length;
  return n ? `${n} game${n === 1 ? "" : "s"}` : "";
};
