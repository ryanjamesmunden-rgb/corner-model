import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { Flame, ArrowRight, Target } from "lucide-react";
import { api } from "@/lib/api";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";

const SIDES = [{ v: "home", l: "Home" }, { v: "away", l: "Away" }, { v: "overall", l: "Overall" }];
const PRESETS = [
  { v: "5-5", l: "5 / 5", window: 5, min_hits: 5 },
  { v: "8-10", l: "8 / 10", window: 10, min_hits: 8 },
  { v: "9-10", l: "9 / 10", window: 10, min_hits: 9 },
  { v: "10-10", l: "10 / 10", window: 10, min_hits: 10 },
];
const THRESHOLDS = [
  { v: "auto", l: "Best line (auto)" },
  { v: "3", l: "3+ corners" },
  { v: "4", l: "4+ corners" },
  { v: "5", l: "5+ corners" },
  { v: "6", l: "6+ corners" },
  { v: "7", l: "7+ corners" },
];
const TIMEFRAMES = [
  { v: "all", l: "Any upcoming" },
  { v: "3", l: "Next 3 days" },
  { v: "7", l: "Next 7 days" },
  { v: "14", l: "Next 14 days" },
];

// Global cross-league corner consistency finder for the home page.
export default function StreakFinder({ leagueId }) {
  const navigate = useNavigate();
  const [scope, setScope] = useState("all");
  const [side, setSide] = useState("home");
  const [preset, setPreset] = useState("5-5");
  const [threshold, setThreshold] = useState("auto");
  const [days, setDays] = useState("all");
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const p = PRESETS.find((x) => x.v === preset);
    const params = { league_id: scope === "current" ? leagueId : "all", side, window: p.window, min_hits: p.min_hits, min_line: 3 };
    if (threshold !== "auto") params.threshold = threshold;
    if (days !== "all") params.within_days = days;
    setLoading(true);
    api.streaks(params).then(setRows).catch(() => setRows([])).finally(() => setLoading(false));
  }, [scope, side, preset, threshold, days, leagueId]);

  const fmt = (d) => new Date(d).toLocaleDateString(undefined, { month: "short", day: "numeric" });

  return (
    <section className="bg-card border border-border rounded-lg" data-testid="streak-finder">
      <div className="flex flex-col lg:flex-row lg:items-center gap-3 px-4 py-3 border-b border-border">
        <div className="flex items-center gap-2">
          <Flame className="h-4 w-4 text-primary" />
          <h2 className="font-head font-semibold text-lg">Corner Streak Finder</h2>
          <span className="text-xs text-muted-foreground hidden sm:inline">consistent corner-winners (real games only)</span>
        </div>
        <div className="lg:ml-auto flex flex-wrap items-center gap-2">
          <Tabs value={side} onValueChange={setSide}>
            <TabsList className="bg-secondary h-8">
              {SIDES.map((s) => <TabsTrigger key={s.v} value={s.v} data-testid={`streak-side-${s.v}`} className="text-xs px-2.5 h-6">{s.l}</TabsTrigger>)}
            </TabsList>
          </Tabs>
          <Tabs value={preset} onValueChange={setPreset}>
            <TabsList className="bg-secondary h-8">
              {PRESETS.map((p) => <TabsTrigger key={p.v} value={p.v} data-testid={`streak-preset-${p.v}`} className="text-xs px-2 h-6 font-mono-data">{p.l}</TabsTrigger>)}
            </TabsList>
          </Tabs>
          <Select value={threshold} onValueChange={setThreshold}>
            <SelectTrigger data-testid="streak-threshold" className="w-[150px] bg-[#121212] border-border text-xs h-8"><SelectValue /></SelectTrigger>
            <SelectContent className="bg-[#121212] border-border">
              {THRESHOLDS.map((o) => <SelectItem key={o.v} value={o.v} className="text-xs">{o.l}</SelectItem>)}
            </SelectContent>
          </Select>
          <Select value={days} onValueChange={setDays}>
            <SelectTrigger data-testid="streak-timeframe" className="w-[140px] bg-[#121212] border-border text-xs h-8"><SelectValue /></SelectTrigger>
            <SelectContent className="bg-[#121212] border-border">
              {TIMEFRAMES.map((o) => <SelectItem key={o.v} value={o.v} className="text-xs">{o.l}</SelectItem>)}
            </SelectContent>
          </Select>
          <Select value={scope} onValueChange={setScope}>
            <SelectTrigger data-testid="streak-scope" className="w-[130px] bg-[#121212] border-border text-xs h-8"><SelectValue /></SelectTrigger>
            <SelectContent className="bg-[#121212] border-border">
              <SelectItem value="all" className="text-xs">All Leagues</SelectItem>
              <SelectItem value="current" className="text-xs">This League</SelectItem>
            </SelectContent>
          </Select>
        </div>
      </div>

      <div className="overflow-x-auto max-h-[420px] overflow-y-auto">
        <table className="w-full">
          <thead className="sticky top-0 bg-card z-10">
            <tr className="border-b border-border text-muted-foreground text-xs uppercase tracking-wider">
              <th className="text-left font-medium px-4 py-2.5">Team</th>
              <th className="text-left font-medium px-4 py-2.5">Line</th>
              <th className="text-left font-medium px-4 py-2.5">Hit rate</th>
              <th className="text-right font-medium px-4 py-2.5">Avg</th>
              <th className="text-left font-medium px-4 py-2.5 hidden md:table-cell">Recent ({side})</th>
              <th className="text-left font-medium px-4 py-2.5">Next</th>
              <th className="text-right font-medium px-4 py-2.5">Opp conc</th>
              <th className="text-right font-medium px-4 py-2.5">Model odds</th>
              <th className="text-right font-medium px-4 py-2.5">Edge</th>
              <th className="px-4 py-2.5"></th>
            </tr>
          </thead>
          <tbody className="font-mono-data text-sm">
            {loading ? (
              <tr><td colSpan={10} className="px-4 py-12 text-center text-muted-foreground animate-pulse">Scanning corner streaks…</td></tr>
            ) : rows.length === 0 ? (
              <tr><td colSpan={10} className="px-4 py-12 text-center text-muted-foreground">No teams match this streak. Try a lower threshold or a wider window.</td></tr>
            ) : rows.map((r) => (
              <tr
                key={r.team_id}
                data-testid="streak-row"
                onClick={() => r.next_fixture && navigate(`/fixture/${r.next_fixture.fixture_id}`)}
                className={`border-b border-border/50 transition-colors duration-150 ${r.next_fixture ? "hover:bg-white/5 cursor-pointer" : ""}`}
                style={{ borderLeft: "2px solid #10B981" }}
              >
                <td className="px-4 py-2.5">
                  <div className="text-foreground font-sans font-medium whitespace-nowrap">{r.name}</div>
                  <div className="text-[10px] text-muted-foreground uppercase tracking-wider font-sans">{r.league_name}</div>
                </td>
                <td className="px-4 py-2.5">
                  <span className="inline-flex items-center gap-1 text-xs px-2 py-1 rounded border bg-emerald-500/15 text-emerald-400 border-emerald-500/30">
                    <Target className="h-3 w-3" /> {r.line}+
                  </span>
                </td>
                <td className="px-4 py-2.5 text-emerald-400 font-semibold whitespace-nowrap">{r.hits}/{r.window}</td>
                <td className="px-4 py-2.5 text-right text-foreground">{r.avg.toFixed(1)}</td>
                <td className="px-4 py-2.5 hidden md:table-cell">
                  <div className="flex gap-1">
                    {r.recent.map((m, i) => (
                      <span key={i} title={`${m.corners} vs ${m.opponent}`}
                        className={`inline-flex h-5 min-w-5 px-1 items-center justify-center rounded text-[10px] ${m.corners >= r.line ? "bg-emerald-500/20 text-emerald-400" : "bg-red-500/15 text-red-400"}`}>
                        {m.corners}
                      </span>
                    ))}
                  </div>
                </td>
                <td className="px-4 py-2.5 text-xs text-muted-foreground whitespace-nowrap">
                  {r.next_fixture ? `${r.next_fixture.is_home ? "vs" : "@"} ${r.next_fixture.opponent} · ${fmt(r.next_fixture.date)}` : "—"}
                </td>
                <td className="px-4 py-2.5 text-right">
                  {r.projection ? (
                    <span className={r.projection.opp_conceded >= r.line ? "text-emerald-400" : "text-muted-foreground"}>
                      {r.projection.opp_conceded.toFixed(1)}
                    </span>
                  ) : <span className="text-muted-foreground">—</span>}
                </td>
                <td className="px-4 py-2.5 text-right whitespace-nowrap">
                  {r.projection ? (
                    <span className="text-foreground font-semibold" title={`Model: ${r.projection.prob.toFixed(1)}% to win ${r.line}+ corners (λ ${r.projection.lambda})`}>
                      {r.projection.fair_odds?.toFixed(2)}
                    </span>
                  ) : <span className="text-muted-foreground">—</span>}
                </td>
                <td className="px-4 py-2.5 text-right whitespace-nowrap">
                  {r.projection && r.projection.ev != null ? (
                    <span className={`font-semibold ${r.projection.ev >= 5 ? "text-emerald-400" : r.projection.ev >= 0 ? "text-amber-400" : "text-red-400"}`}
                      title={`Book ${r.projection.book_odds} vs model ${r.projection.fair_odds}`}>
                      {r.projection.ev > 0 ? "+" : ""}{r.projection.ev.toFixed(1)}%
                    </span>
                  ) : <span className="text-muted-foreground" title="Paste this team's corner odds on the fixture page">—</span>}
                </td>
                <td className="px-4 py-2.5 text-right">{r.next_fixture && <ArrowRight className="h-4 w-4 text-muted-foreground inline" />}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
