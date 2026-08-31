import { useState } from "react";
import { Flame, TrendingUp, Target } from "lucide-react";
import { useLeague } from "@/context/LeagueContext";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import TrendFinder from "@/components/TrendFinder";
import StreakFinder from "@/components/StreakFinder";
import MembersOnly from "@/components/MembersOnly";

export default function Streaks() {
  const { leagueId } = useLeague();
  const [view, setView] = useState("form");

  return (
    <MembersOnly title="Streaks & form" blurb="Every team on a live run — overs and unders, team corners and match totals — with the hit rate, the length of the run and the model's price beside each one.">
      <div className="space-y-3 sm:space-y-6" data-testid="streaks-page">
        <div>
          <div className="flex items-center gap-2 text-primary mb-1">
            <Flame className="h-4 w-4" />
            <span className="font-mono-data text-xs tracking-widest uppercase">Corner Streaks & Form</span>
          </div>
          <h1 className="font-head text-3xl sm:text-4xl font-bold tracking-tight">Streaks</h1>
          <p className="text-muted-foreground text-sm mt-1">
            Teams heating up (averaging more than usual) and teams landing the same side of a corner line —
            over or under — game after game.
          </p>
        </div>

        <Tabs value={view} onValueChange={setView}>
          <TabsList className="bg-secondary h-10">
            <TabsTrigger value="form" data-testid="streaks-view-form" className="text-sm px-4 h-8 gap-2"><TrendingUp className="h-4 w-4" /> Hot Form</TabsTrigger>
            <TabsTrigger value="consistency" data-testid="streaks-view-consistency" className="text-sm px-4 h-8 gap-2"><Target className="h-4 w-4" /> Consistency</TabsTrigger>
          </TabsList>
        </Tabs>

        {view === "form" ? <TrendFinder /> : <StreakFinder leagueId={leagueId} />}
      </div>
    </MembersOnly>
  );
}
