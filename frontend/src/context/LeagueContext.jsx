import { createContext, useContext } from "react";

export const LeagueContext = createContext({ leagueId: "ned-ed", changeLeague: () => {}, leagues: [] });
export const useLeague = () => useContext(LeagueContext);
