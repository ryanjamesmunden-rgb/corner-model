import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { Trophy, Flame, TrendingUp, Target, ArrowRight, Star } from "lucide-react";
import { api } from "@/lib/api";

const fmt = (d) => new Date(d).toLocaleDateString(undefined, { month: "short", day: "numeric" });

function BestCard({ icon: Icon, label, title, sub, chip, chipClass, onClick, accent }) {
  return (
    <button
      onClick={onClick}
      data-testid={`best-${label.toLowerCase().replace(/\s/g, "-")}`}
      className="group text-left bg-card border border-border rounded-lg p-4 hover:border-white/25 transition-colors duration-150"
      style={{ borderTop: `2px solid ${accent}` }}
    >
      <div className="flex items-center gap-2 mb-2">
        <Icon className="h-3.5 w-3.5" style={{ color: accent }} />
        <span className="text-[10px] uppercase tracking-widest text-muted-foreground">{label}</span>
        {chip && <span className={`ml-auto text-[10px] px-2 py-0.5 rounded border font-mono-data ${chipClass}`}>{chip}</span>}
      </div>
      <p className="font-head font-semibold text-base leading-tight mb-1">{title}</p>
      <div className="flex items-center justify-between">
        <p className="font-mono-data text-xs text-muted-foreground">{sub}</p>
        <ArrowRight className="h-4 w-4 text-muted-foreground opacity-0 group-hover:opacity-100 transition-opacity" />
      </div>
    </button>
  );
}

export default function HomeInsights() {
  const navigate = useNavigate();
  const [best, setBest] = useState(null);
  const [mismatches, setMismatches] = useState([]);

  useEffect(() => {
    api.bestBets().then(setBest).catch(() => {});
    api.topMismatches({ within_days: 7, limit: 10 }).then(setMismatches).catch(() => setMismatches([]));
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
          {best?.value ? (
            <BestCard
              icon={TrendingUp} label="Top Value" accent="#22D3EE"
              title={`${best.value.home_name} v ${best.value.away_name}`}
              sub={`${best.value.market_label} @ ${best.value.book_odds} · model ${best.value.fair_odds}`}
              chip={`+${best.value.ev?.toFixed(1)}%`} chipClass="bg-emerald-500/15 text-emerald-400 border-emerald-500/30"
              onClick={() => go(best.value.fixture_id)}
            />
          ) : <SkeletonCard />}
          {best?.mismatch ? (
            <BestCard
              icon={Trophy} label="Top Mismatch" accent="#10B981"
              title={`${best.mismatch.name} ${best.mismatch.next_fixture?.is_home ? "vs" : "@"} ${best.mismatch.next_fixture?.opponent}`}
              sub={`${best.mismatch.line}+ corners @ ${best.mismatch.fair_odds} · λ ${best.mismatch.lambda} (opp conc ${best.mismatch.opp_conceded})`}
              chip={best.mismatch.league_name} chipClass="bg-white/5 text-muted-foreground border-border"
              onClick={() => go(best.mismatch.next_fixture?.fixture_id)}
            />
          ) : <SkeletonCard />}
          {best?.streak ? (
            <BestCard
              icon={Flame} label="Top Streak" accent="#F59E0B"
              title={`${best.streak.name} — ${best.streak.line}+ corners`}
              sub={`hit in ${best.streak.hits}/${best.streak.window} ${best.streak.side} games · avg ${best.streak.avg}`}
              chip={`${best.streak.hits}/${best.streak.window}`} chipClass="bg-amber-500/15 text-amber-400 border-amber-500/30"
              onClick={() => go(best.streak.next_fixture?.fixture_id)}
            />
          ) : <SkeletonCard />}
        </div>
      </div>

      {/* Top mismatches this week */}
      <div className="bg-card border border-border rounded-lg">
        <div className="flex items-center gap-2 px-4 py-3 border-b border-border">
          <Target className="h-4 w-4 text-emerald-400" />
          <h2 className="font-head font-semibold text-lg">Top Mismatches This Week</h2>
          <span className="text-xs text-muted-foreground hidden sm:inline">strong corner team vs leaky defence · next 7 days · all leagues</span>
          <span className="ml-auto font-mono-data text-xs text-muted-foreground">{mismatches.length}</span>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead>
              <tr className="border-b border-border text-muted-foreground text-xs uppercase tracking-wider">
                <th className="text-left font-medium px-4 py-2.5">Team</th>
                <th className="text-left font-medium px-4 py-2.5">Fixture</th>
                <th className="text-right font-medium px-4 py-2.5">Team /g</th>
                <th className="text-right font-medium px-4 py-2.5">Opp conc</th>
                <th className="text-right font-medium px-4 py-2.5">Proj λ</th>
                <th className="text-right font-medium px-4 py-2.5">Model</th>
                <th className="px-4 py-2.5"></th>
              </tr>
            </thead>
            <tbody className="font-mono-data text-sm">
              {mismatches.length === 0 ? (
                <tr><td colSpan={7} className="px-4 py-8 text-center text-muted-foreground text-xs">No strong mismatches in the next 7 days — check the Leagues tab for the full board.</td></tr>
              ) : mismatches.map((r) => (
                <tr
                  key={r.team_id}
                  data-testid="mismatch-row"
                  onClick={() => go(r.next_fixture?.fixture_id)}
                  className="border-b border-border/50 hover:bg-white/5 cursor-pointer transition-colors duration-150"
                  style={{ borderLeft: "2px solid #10B981" }}
                >
                  <td className="px-4 py-2.5">
                    <div className="text-foreground font-sans font-medium whitespace-nowrap">{r.name}</div>
                    <div className="text-[10px] text-muted-foreground uppercase tracking-wider font-sans">{r.league_name}</div>
                  </td>
                  <td className="px-4 py-2.5 text-xs text-muted-foreground whitespace-nowrap">
                    {r.next_fixture?.is_home ? "vs" : "@"} {r.next_fixture?.opponent} · {fmt(r.next_fixture?.date)}
                    {r.next_fixture?.round && r.next_fixture.round !== "Upcoming" && (
                      <span className="ml-1.5 text-[10px] text-muted-foreground/70">· {r.next_fixture.round}</span>
                    )}
                  </td>
                  <td className="px-4 py-2.5 text-right text-emerald-400 font-semibold">{r.team_for.toFixed(1)}</td>
                  <td className="px-4 py-2.5 text-right text-emerald-400">{r.opp_conceded.toFixed(1)}</td>
                  <td className="px-4 py-2.5 text-right text-primary font-semibold">{r.lambda.toFixed(1)}</td>
                  <td className="px-4 py-2.5 text-right text-foreground whitespace-nowrap" title={`${r.prob.toFixed(0)}% to win ${r.line}+`}>{r.line}+ @ {r.fair_odds?.toFixed(2)}</td>
                  <td className="px-4 py-2.5 text-right"><ArrowRight className="h-4 w-4 text-muted-foreground inline" /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

const SkeletonCard = () => (
  <div className="bg-card border border-border rounded-lg p-4 h-[92px] animate-pulse" />
);
