import { useState } from "react";
import { Trophy, Flame, TrendingUp, Target } from "lucide-react";
import { useLeague } from "@/context/LeagueContext";
import HomeInsights from "@/components/HomeInsights";
import FixtureBoard from "@/components/FixtureBoard";
import IntroBanner from "@/components/IntroBanner";
import BestTeams from "@/components/BestTeams";
import TrendFinder from "@/components/TrendFinder";
import StreakFinder from "@/components/StreakFinder";
import ChaseBoard from "@/components/ChaseBoard";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";

const TABS = [
  { v: "best", l: "Best Teams", icon: Trophy },
  { v: "form", l: "Hot Form", icon: TrendingUp },
  { v: "streaks", l: "Streaks", icon: Flame },
  { v: "chase", l: "Chase Board", icon: Target },
];

export default function Scanner() {
  const { leagueId } = useLeague();
  const [view, setView] = useState("best");

  return (
    <div className="space-y-3 sm:space-y-6" data-testid="scanner-page">
      <div>
        <div className="flex items-center gap-2 text-primary mb-1">
          <Trophy className="h-4 w-4" />
          <span className="font-mono-data text-xs tracking-widest uppercase">Corner Value Finder</span>
        </div>
        <h1 className="font-head text-3xl sm:text-4xl font-bold tracking-tight">Best Corner Teams & Streaks</h1>
        <p className="text-muted-foreground text-sm mt-1">
          Highest corner averages, hottest recent form and the most consistent home/away streaks — over or under, team corners or match totals, across every league.
        </p>
      </div>

      <IntroBanner />

      <HomeInsights />

      {/* The board comes BEFORE the fixture list. The page is titled "Best Corner Teams
          & Streaks" and opens on the Best Teams tab, so the thing it is named after was
          arriving below a full fixture board — a scroll away from the headline that
          promised it. Fixtures are still there, one scroll down, which is where someone
          looking for a specific game goes anyway. */}
      <Tabs value={view} onValueChange={setView}>
        <TabsList className="bg-secondary h-10 flex-wrap">
          {TABS.map((t) => (
            <TabsTrigger key={t.v} value={t.v} data-testid={`vf-tab-${t.v}`} className="text-sm px-4 h-8 gap-2">
              <t.icon className="h-4 w-4" /> {t.l}
            </TabsTrigger>
          ))}
        </TabsList>
      </Tabs>

      {view === "best" && <BestTeams leagueId={leagueId} />}
      {view === "form" && <TrendFinder />}
      {view === "streaks" && <StreakFinder leagueId={leagueId} />}
      {view === "chase" && <ChaseBoard leagueId="all" withinDays={7} limit={25} />}

      <FixtureBoard leagueId="all" />
    </div>
  );
}
