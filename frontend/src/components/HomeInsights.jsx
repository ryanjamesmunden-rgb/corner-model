import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { Trophy, Flame, TrendingUp, ArrowRight, Star } from "lucide-react";
import { api } from "@/lib/api";

// COLOUR MEANS QUALITY, NOT SIGNAL TYPE — matching the fixture board. These were cyan,
// green and amber by which signal produced them, which looks deliberate and says nothing:
// a 2-of-5 chase spot got the same confident cyan as a 5-of-5 one. Green now means the
// card's own evidence clears the bar; muted means it is the best of a weak lot.
const GOOD = "#10B981";
const MUTED = "#3F3F46";

function BestCard({ icon: Icon, label, title, sub, chip, onClick, strong, why }) {
  const accent = strong ? GOOD : MUTED;
  return (
    <button
      onClick={onClick}
      data-testid={`best-${label.toLowerCase().replace(/\s/g, "-")}`}
      title={why}
      className="group text-left bg-card border border-border rounded-lg p-4 hover:border-white/25 transition-colors duration-150"
      style={{ borderTop: `2px solid ${accent}` }}
    >
      <div className="flex items-center gap-2 mb-2">
        <Icon className="h-3.5 w-3.5" style={{ color: accent }} />
        <span className="text-[10px] uppercase tracking-widest text-muted-foreground">{label}</span>
        {chip && (
          <span className={`ml-auto text-[10px] px-2 py-0.5 rounded border font-mono-data ${
            strong ? "bg-emerald-500/15 text-emerald-400 border-emerald-500/30"
                   : "border-border/60 text-muted-foreground/60"}`}>{chip}</span>
        )}
      </div>
      <p className={`font-head font-semibold text-base leading-tight mb-1 ${strong ? "" : "text-foreground/70"}`}>{title}</p>
      <div className="flex items-center justify-between">
        <p className="font-mono-data text-xs text-muted-foreground">{sub}</p>
        <ArrowRight className="h-4 w-4 text-muted-foreground opacity-0 group-hover:opacity-100 transition-opacity" />
      </div>
    </button>
  );
}

// What "solid" means per card, stated rather than implied. Each is the same bar the
// board itself uses, so the colours cannot disagree with the rest of the site.
const rate = (n, of) => (of ? n / of : 0);

export default function HomeInsights() {
  const navigate = useNavigate();
  const [best, setBest] = useState(null);

  useEffect(() => {
    api.bestBets().then(setBest).catch(() => {});
  }, []);

  const go = (fixtureId) => fixtureId && navigate(`/fixture/${fixtureId}`);

  return (
    <div className="space-y-4" data-testid="home-insights">
      {/* Best Bets strip */}
      <div>
        <div className="flex items-center gap-2 mb-2">
          <Star className="h-4 w-4 text-primary" />
          <h2 className="font-head font-semibold text-lg">Best Bets Today</h2>
          <span className="text-xs text-muted-foreground">the standout pick from each signal</span>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
          {best?.chase ? (
            <BestCard
              icon={TrendingUp} label="Top Chase"
              strong={rate(best.chase.consistency, best.chase.consistency_of) >= 0.8}
              why={`Solid when the team has hit this line in 4 of its last 5 on this venue. This one: ${best.chase.consistency}/${best.chase.consistency_of}.`}
              title={`${best.chase.name} ${best.chase.next_fixture?.is_home ? "vs" : "@"} ${best.chase.next_fixture?.opponent}`}
              sub={`${best.chase.line}+ corners @ ${best.chase.fair_odds} · λ ${best.chase.lambda} · opp scores FH ${best.chase.opp_fh_rate}%`}
              chip={`${best.chase.consistency}/${best.chase.consistency_of}`}
              onClick={() => go(best.chase.next_fixture?.fixture_id)}
            />
          ) : <SkeletonCard />}
          {best?.mismatch ? (
            <BestCard
              icon={Trophy} label="Top Mismatch"
              strong={(best.mismatch.real_samples || 0) >= 6}
              why={`A mismatch is a lambda comparison with no hit-rate behind it, so what makes it solid is SAMPLE: 6+ real games. This one has ${best.mismatch.real_samples || 0}.`}
              title={`${best.mismatch.name} ${best.mismatch.next_fixture?.is_home ? "vs" : "@"} ${best.mismatch.next_fixture?.opponent}`}
              sub={`${best.mismatch.line}+ corners @ ${best.mismatch.fair_odds} · λ ${best.mismatch.lambda} (opp conc ${best.mismatch.opp_conceded})`}
              chip={best.mismatch.league_name}
              onClick={() => go(best.mismatch.next_fixture?.fixture_id)}
            />
          ) : <SkeletonCard />}
          {best?.streak ? (
            <BestCard
              icon={Flame} label="Top Streak"
              strong={rate(best.streak.hits, best.streak.window) >= 0.8}
              why={`Solid when the line landed in at least 4 of every 5 games in the window. This one: ${best.streak.hits}/${best.streak.window}.`}
              title={`${best.streak.name} — ${best.streak.line}+ corners`}
              sub={`hit in ${best.streak.hits}/${best.streak.window} ${best.streak.side} games · avg ${best.streak.avg}`}
              chip={`${best.streak.hits}/${best.streak.window}`}
              onClick={() => go(best.streak.next_fixture?.fixture_id)}
            />
          ) : <SkeletonCard />}
        </div>
      </div>
    </div>
  );
}

const SkeletonCard = () => (
  <div className="bg-card border border-border rounded-lg p-4 h-[92px] animate-pulse" />
);
