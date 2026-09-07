import { useState } from "react";
import { Trophy, Flame, TrendingUp, Target, Crosshair, BadgePercent, Lock } from "lucide-react";
import { useLeague } from "@/context/LeagueContext";
import { useAuth } from "@/context/AuthContext";
import HomeInsights from "@/components/HomeInsights";
import FixtureBoard from "@/components/FixtureBoard";
import IntroBanner from "@/components/IntroBanner";
import BestTeams from "@/components/BestTeams";
import TrendFinder from "@/components/TrendFinder";
import StreakFinder from "@/components/StreakFinder";
import ChaseBoard from "@/components/ChaseBoard";
import PerfectGames from "@/components/PerfectGames";
import ValueBoard from "@/components/ValueBoard";
import MembersOnly from "@/components/MembersOnly";
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

// EVERY TAB HERE EXCEPT "best" IS THE PAID PRODUCT. /streaks the page knew that and
// wrapped itself in MembersOnly; these tabs are a second route to the same components
// and never did, so a signed-out visitor got the component, the component got a 402, and
// the 402 was caught and rendered as an empty table reading "No teams match this
// streak". The site told people its product was empty — the single worst outcome for
// anyone arriving from the free channel.
//
// The wall says what is behind it, which is the whole reason MembersOnly takes a blurb:
// "members only" tells you nothing about whether it is worth £20; naming what is in
// there does. Best Teams stays open on purpose — it is the tab the page opens on, so a
// visitor lands on real football rather than a paywall, and it is the teaser that makes
// the rest worth paying for.
const GATED = {
  form: {
    title: "Hot form",
    blurb: "Teams whose corner numbers have jumped above their own season average — who is heating up, by how much, and over which window.",
  },
  streaks: {
    title: "Corner streaks",
    blurb: "Every team on a live run — overs and unders, team corners and match totals — with the hit rate, how long the run is, how much room it had, and the model's price on the next game.",
  },
  perfect: {
    title: "Perfect games",
    blurb: "Fixtures where a corner streak and a favourable matchup land on the same team: the run, the opponent's concession rate, and the projection in one row.",
  },
  chase: {
    title: "The chase board",
    blurb: "The week's best team-corner chase spots, ranked on projection, opponent leakage and how often the line has actually landed.",
  },
  value: {
    title: "Your value board",
    blurb: "Enter the prices you can get on any fixture and this collects the best positive-EV line on every game you have priced, ranked, with how old each price is.",
  },
};

export default function Scanner() {
  const { leagueId } = useLeague();
  const { member } = useAuth();
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
              {/* Shown BEFORE the click rather than after. A tab that looks free and
                  then refuses you reads as a bait; a padlock reads as a price list. */}
              {!member && GATED[t.v] && (
                <Lock className="h-3 w-3 shrink-0 opacity-50" aria-label="Members only" />
              )}
            </TabsTrigger>
          ))}
        </TabsList>
      </Tabs>

      {view === "best" && <BestTeams leagueId={leagueId} />}

      {/* MembersOnly returns the wall INSTEAD of its children, so a non-member never
          mounts these and never fires the request that would 402. */}
      {GATED[view] && (
        <MembersOnly title={GATED[view].title} blurb={GATED[view].blurb}>
          {view === "form" && <TrendFinder />}
          {view === "streaks" && <StreakFinder leagueId={leagueId} />}
          {view === "perfect" && <PerfectGames />}
          {view === "chase" && <ChaseBoard leagueId="all" withinDays={7} limit={25} />}
          {view === "value" && <ValueBoard />}
        </MembersOnly>
      )}

      <FixtureBoard leagueId="all" />
    </div>
  );
}
