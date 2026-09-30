import { createContext, useContext } from "react";

// `leagueId` is a BROWSING PREFERENCE — which league the boards filter to — and it persists
// across visits.
//
// `viewedLeague` is something else, and the difference is the whole reason it exists. On a
// fixture page the league is a FACT ABOUT THE FIXTURE, not a filter: the page shows Benfica
// v Vitória whatever the header says, so a dropdown there changes nothing you can see and
// quietly rewrites your saved preference for every other screen. A reader who opened a
// Portuguese game from a Telegram link came back to find their Value Finder had moved to
// Portugal.
//
// So a page that IS a single league reports it here, the header shows that instead of the
// selector, and the stored preference is left alone. Cleared on unmount, so going back to a
// board restores the control and the league it was on.
export const LeagueContext = createContext({
  leagueId: "ned-ed",
  changeLeague: () => {},
  leagues: [],
  viewedLeague: null,
  setViewedLeague: () => {},
});
export const useLeague = () => useContext(LeagueContext);
