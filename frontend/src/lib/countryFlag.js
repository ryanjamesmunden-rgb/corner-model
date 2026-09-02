// Country flags for shared board text.
//
// The share buttons put a board on Telegram or X as plain text, where the league name is
// the first thing that gets cut for length and the last thing a skimming reader takes in.
// A flag survives both: it sits at the head of the line, costs one character, and says
// which country's football the row is about before the team name is even read.
//
// The flag is derived from the LEAGUE ID, not the league name. Ids carry a stable
// three-letter country prefix (`nor-el`, `nor-d1`), while names collide across borders —
// "Bundesliga" is Germany and Austria, "Super League" is Switzerland and Greece — so a
// name lookup would silently mis-flag rows. Keep this in step with LEAGUE_META in
// backend/leagues_meta.py; test_share_flags.py fails if a league is added without one.
//
// A note on rendering: regional-indicator flags show as letter pairs on Windows, which
// has no flag glyphs. That is the platform, not this map — the text still reads fine,
// and everywhere the audience actually is (phones, Telegram, X on mobile) draws them.

// League-id prefix -> ISO 3166-1 alpha-2, or a subdivision code for the home nations,
// which have their own flags rather than a country code.
const CODES = {
  eng: "gb-eng",
  sco: "gb-sct",
  wal: "gb-wls",
  aus: "AU",
  nor: "NO",
  ned: "NL",
  bra: "BR",
  ita: "IT",
  fra: "FR",
  esp: "ES",
  ger: "DE",
  por: "PT",
  bel: "BE",
  tur: "TR",
  usa: "US",
  den: "DK",
  sui: "CH",
  aut: "AT",
  gre: "GR",
  jpn: "JP",
  arg: "AR",
  // Seeded demo leagues — real for anyone running without a provider key.
  fin: "FI",
  swe: "SE",
};

// Two letters -> the pair of regional indicator symbols the platform draws as a flag.
const regional = (iso) =>
  [...iso.toUpperCase()].map((c) => String.fromCodePoint(0x1f1e6 + c.charCodeAt(0) - 65)).join("");

// England and Scotland are subdivisions, not countries: a black flag followed by the
// subdivision code in tag characters, terminated by the cancel tag.
const subdivision = (code) =>
  "\u{1F3F4}"
  + [...code.replace(/-/g, "").toLowerCase()].map((c) => String.fromCodePoint(0xe0000 + c.charCodeAt(0))).join("")
  + "\u{E007F}";

/** The flag for a league id, or "" when the league isn't one we know. */
export const flagFor = (leagueId) => {
  const code = CODES[String(leagueId || "").slice(0, 3).toLowerCase()];
  if (!code) return "";
  return code.includes("-") ? subdivision(code) : regional(code);
};

/**
 * What to open a shared line with: the country's flag, or the plain bullet when there
 * isn't one. Never both — a line that reads "• 🇳🇴" wastes the width the flag bought.
 */
export const flagBullet = (leagueId, fallback = "•") => flagFor(leagueId) || fallback;

/** Prefix a label with its flag, leaving the label alone when the league is unknown. */
export const withFlag = (leagueId, text) => {
  const flag = flagFor(leagueId);
  return flag ? `${flag} ${text}` : text;
};
