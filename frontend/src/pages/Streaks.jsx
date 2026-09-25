import { useState } from "react";
import { Flame, TrendingUp, Target } from "lucide-react";
import { useLeague } from "@/context/LeagueContext";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import TrendFinder from "@/components/TrendFinder";
import StreakFinder from "@/components/StreakFinder";
import ErrorBoundary from "@/components/ErrorBoundary";
import { DEFAULT_STREAK_VIEW, streakViewLabel } from "@/lib/streakViews";

// CONSISTENCY LEADS, HOT FORM SITS BEHIND IT. The order and the landing tab live in
// lib/streakViews, with the reasoning and the tests — jest here cannot resolve
// react-router, so nothing asserted about this page can live in this file.
export default function Streaks() {
  const { leagueId } = useLeague();
  const [view, setView] = useState(DEFAULT_STREAK_VIEW);

  return (
    <div className="space-y-3 sm:space-y-6" data-testid="streaks-page">
      <div>
        <div className="flex items-center gap-2 text-primary mb-1">
          <Flame className="h-4 w-4" />
          <span className="font-mono-data text-xs tracking-widest uppercase">Corner Streaks & Form</span>
        </div>
        <h1 className="font-head text-3xl sm:text-4xl font-bold tracking-tight">Streaks</h1>
        <p className="text-muted-foreground text-sm mt-1">
          Teams landing the same side of a corner line — over or under — game after game.
          Hot form, behind, is the earlier signal: sides averaging more corners lately than
          they do across the season.
        </p>
      </div>

      <Tabs value={view} onValueChange={setView}>
        <TabsList className="bg-secondary h-10">
          <TabsTrigger value="consistency" data-testid="streaks-view-consistency" className="text-sm px-4 h-8 gap-2"><Target className="h-4 w-4" /> Consistency</TabsTrigger>
          <TabsTrigger value="form" data-testid="streaks-view-form" className="text-sm px-4 h-8 gap-2"><TrendingUp className="h-4 w-4" /> Hot Form</TabsTrigger>
        </TabsList>
      </Tabs>

      <ErrorBoundary label={streakViewLabel(view)}
        resetKey={`${view}-${leagueId}`}>
        {view === "form" ? <TrendFinder /> : <StreakFinder leagueId={leagueId} />}
      </ErrorBoundary>
    </div>
  );
}
