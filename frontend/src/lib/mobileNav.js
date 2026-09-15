// Which destinations reach the phone's tab bar, and which go behind More.
//
// PURE AND ON ITS OWN, because it is the only decision in the mobile nav worth testing
// without a browser — and because the component it serves imports react-router, which
// this project's test runner cannot load.
//
// The header carried every destination as a 16px icon in a row: nine of them at 390px,
// beside Join, an account chip, a truncated league selector and an export button. It fit,
// in the sense that nothing overlapped. Nobody could hit any of it.
//
// FOUR PLUS MORE, because five is the most a 390px row holds at a 44px target, and the
// fifth slot buys access to everything rather than one more destination. Which four is
// stated rather than derived from list order: PRIMARY names them, and the bar tops up
// from whatever else is in the nav when one of them is missing — Projected and Results
// are not in the nav signed out, and a bar with a hole in it looks broken rather than
// personalised.
//
// THE SHEET IS NOT A MENU OF EVERYTHING. It holds the destinations that did not make the
// bar, and nothing else: no settings, no account, no sign-out. Those live on the avatar
// and in the footer, where they already were.
const PRIMARY = ["/scanner", "/quick-scan", "/streaks", "/projections"];

export function splitNav(nav, slots = 4) {
  // Primary first, in PRIMARY's order rather than nav's, then topped up from the rest so
  // the bar is always full. Pure, and exported, because "which four" is the one decision
  // here worth being able to test without a browser.
  const byPath = new Map(nav.map((n) => [n.to, n]));
  const bar = PRIMARY.map((p) => byPath.get(p)).filter(Boolean);
  const rest = nav.filter((n) => !bar.includes(n));
  while (bar.length < slots && rest.length) bar.push(rest.shift());
  return { bar: bar.slice(0, slots), rest: [...rest, ...bar.slice(slots)] };
}

