import { useState } from "react";
import { Target, Filter } from "lucide-react";
import { useLeague } from "@/context/LeagueContext";
import HomeInsights from "@/components/HomeInsights";
import IntroBanner from "@/components/IntroBanner";
import ChaseBoard from "@/components/ChaseBoard";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";

const WINDOWS = [
  { v: "7", l: "Next 7 days" },
  { v: "14", l: "Next 14 days" },
  { v: "3", l: "Next 3 days" },
];
const LIMITS = [
  { v: "25", l: "Top 25" },
  { v: "50", l: "Top 50" },
  { v: "15", l: "Top 15" },
];

export default function Scanner() {
  const { leagueId, leagues } = useLeague();
  const [scope, setScope] = useState("all");
  const [withinDays, setWithinDays] = useState("7");
  const [limit, setLimit] = useState("25");

  return (
    <div className="space-y-6" data-testid="scanner-page">
      <div className="flex flex-col sm:flex-row sm:items-end justify-between gap-4">
        <div>
          <div className="flex items-center gap-2 text-primary mb-1">
            <Target className="h-4 w-4" />
            <span className="font-mono-data text-xs tracking-widest uppercase">Weekly Chase Board</span>
          </div>
          <h1 className="font-head text-3xl sm:text-4xl font-bold tracking-tight">This Week's Best Corner Spots</h1>
          <p className="text-muted-foreground text-sm mt-1">
            The whole market trimmed to the strongest team-corner chase spots — ranked, not 600 rows.
          </p>
        </div>
      </div>

      <IntroBanner />

      <HomeInsights />

      <div className="flex flex-wrap items-center gap-3 p-4 bg-card border border-border rounded-lg">
        <div className="flex items-center gap-2 text-muted-foreground text-xs font-medium mr-1">
          <Filter className="h-3.5 w-3.5" /> Filters
        </div>
        <FilterSelect testid="filter-scope" value={scope} onChange={setScope} options={[
          { v: "all", l: "All Leagues" },
          { v: "current", l: leagues.find((l) => l.league_id === leagueId)?.name || "Current League" },
        ]} />
        <FilterSelect testid="filter-window" value={withinDays} onChange={setWithinDays} options={WINDOWS} />
        <FilterSelect testid="filter-limit" value={limit} onChange={setLimit} options={LIMITS} />
      </div>

      <ChaseBoard
        leagueId={scope === "current" ? leagueId : "all"}
        withinDays={parseInt(withinDays, 10)}
        limit={parseInt(limit, 10)}
      />

      <p className="text-[11px] text-muted-foreground leading-relaxed max-w-3xl">
        Ranked by a composite of corner dominance (team corners won + opponent corners conceded),
        a chase catalyst (how often the opponent scores a first-half goal, putting our team behind),
        and consistency (last-5 same-venue hit rate). Open any spot to paste the real bookmaker odds
        and see your true edge.
      </p>
    </div>
  );
}

const FilterSelect = ({ testid, value, onChange, options }) => (
  <Select value={value} onValueChange={onChange}>
    <SelectTrigger data-testid={testid} className="w-[180px] bg-[#121212] border-border text-xs h-9">
      <SelectValue />
    </SelectTrigger>
    <SelectContent className="bg-[#121212] border-border">
      {options.map((o) => (
        <SelectItem key={o.v} value={o.v} className="text-xs">{o.l}</SelectItem>
      ))}
    </SelectContent>
  </Select>
);
