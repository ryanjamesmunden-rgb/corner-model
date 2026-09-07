import { useState } from "react";
import { Trophy, Flame, TrendingUp, Target, Crosshair, BadgePercent } from "lucide-react";
import { useLeague } from "@/context/LeagueContext";
import HomeInsights from "@/components/HomeInsights";
import FixtureBoard from "@/components/FixtureBoard";
import IntroBanner from "@/components/IntroBanner";
import BestTeams from "@/components/BestTeams";
import TrendFinder from "@/components/TrendFinder";
import StreakFinder from "@/components/StreakFinder";
import ChaseBoard from "@/components/ChaseBoard";
import PerfectGames from "@/components/PerfectGames";
import ValueBoard from "@/components/ValueBoard";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";

// `short` is what a phone gets. Six full labels wrap to three rows on a 390px screen,
// which is most of the viewport spent on navigation before any football appears — and
// with a fixed-height list it was worse than that, see the note on TabsList below.
const TABS = [
  { v: "best", l: "Best Teams", short: "Teams", icon: Trophy },
  { v: "form", l: "Hot Form", short: "Form", icon: TrendingUp },
  { v: "streaks", l: "Streaks", short: "Streaks", icon: Flame },
  // Next to Streaks on purpose: it is the same runs, narrowed to the ones whose fixture
  // agrees, so the tab someone reaches for after scanning streaks is the one beside it.
  { v: "perfect", l: "Perfect Games", short: "Perfect", icon: Crosshair },
  // Last, because it is the only tab that is empty until you have done something:
  // it shows what YOUR entered prices found, not what the model found unprompted.
  { v: "chase", l: "Chase Board", short: "Chase", icon: Target },
  { v: "value", l: "Your Value Board", short: "Value", icon: BadgePercent },
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
      {/* h-auto, NOT the h-10 this used to carry. TabsList sets a fixed height, and a
          fixed height with flex-wrap is a trap: the tabs wrapped onto three rows on a
          phone while the box stayed one row tall, so rows two and three rendered
          OUTSIDE it and landed on top of the panel below. The tabs looked like they had
          been printed over the content. Height now follows the rows, and the shorter
          mobile labels keep it to two of them. */}
      <Tabs value={view} onValueChange={setView}>
        <TabsList className="bg-secondary h-auto flex-wrap justify-start gap-1 p-1">
          {TABS.map((t) => (
            <TabsTrigger key={t.v} value={t.v} data-testid={`vf-tab-${t.v}`}
              className="text-xs sm:text-sm px-2.5 sm:px-4 h-8 gap-1.5 sm:gap-2">
              <t.icon className="h-4 w-4 shrink-0" />
              <span className="sm:hidden">{t.short}</span>
              <span className="hidden sm:inline">{t.l}</span>
            </TabsTrigger>
          ))}
        </TabsList>
      </Tabs>

      {view === "best" && <BestTeams leagueId={leagueId} />}
      {view === "form" && <TrendFinder />}
      {view === "streaks" && <StreakFinder leagueId={leagueId} />}
      {view === "perfect" && <PerfectGames />}
      {view === "chase" && <ChaseBoard leagueId="all" withinDays={7} limit={25} />}
      {view === "value" && <ValueBoard />}

      <FixtureBoard leagueId="all" />
    </div>
  );
}
