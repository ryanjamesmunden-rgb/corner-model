import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { Radar, TrendingUp, Filter, ArrowRight } from "lucide-react";
import { api, tierMeta, confMeta } from "@/lib/api";
import { useLeague } from "@/context/LeagueContext";
import HomeInsights from "@/components/HomeInsights";
import IntroBanner from "@/components/IntroBanner";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";

const MARKETS = [
  { v: "all", l: "All Markets" },
  { v: "total", l: "Total Corners" },
  { v: "home", l: "Home Team" },
  { v: "away", l: "Away Team" },
];
const EDGES = [
  { v: "-100", l: "All bets" },
  { v: "0", l: "Positive EV only" },
  { v: "5", l: "Strong value (5%+)" },
];

const fmtDate = (d) => {
  if (!d) return null;
  return new Date(d).toLocaleDateString(undefined, { weekday: "short", month: "short", day: "numeric" });
};

export default function Scanner() {
  const { leagueId, leagues } = useLeague();
  const navigate = useNavigate();
  const [scope, setScope] = useState("all");
  const [market, setMarket] = useState("all");
  const [minEdge, setMinEdge] = useState("0");
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    api.scanner({ league_id: scope === "current" ? leagueId : "all", market, min_edge: minEdge })
      .then(setRows).catch(() => setRows([])).finally(() => setLoading(false));
  }, [scope, leagueId, market, minEdge]);

  const strong = rows.filter((r) => r.tier === "strong").length;
  const small = rows.filter((r) => r.tier === "small").length;

  return (
    <div className="space-y-6" data-testid="scanner-page">
      <div className="flex flex-col sm:flex-row sm:items-end justify-between gap-4">
        <div>
          <div className="flex items-center gap-2 text-primary mb-1">
            <Radar className="h-4 w-4" />
            <span className="font-mono-data text-xs tracking-widest uppercase">Daily Value Scanner</span>
          </div>
          <h1 className="font-head text-3xl sm:text-4xl font-bold tracking-tight">Ranked Value Bets</h1>
          <p className="text-muted-foreground text-sm mt-1">
            Model-priced edges across upcoming fixtures. Paste odds in a fixture to add more.
          </p>
        </div>
        <div className="flex gap-3">
          <StatChip label="Strong" value={strong} className="text-emerald-400" dot="bg-emerald-500" />
          <StatChip label="Small edge" value={small} className="text-amber-400" dot="bg-amber-500" />
          <StatChip label="Total" value={rows.length} className="text-foreground" dot="bg-primary" />
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
        <FilterSelect testid="filter-market" value={market} onChange={setMarket} options={MARKETS} />
        <FilterSelect testid="filter-edge" value={minEdge} onChange={setMinEdge} options={EDGES} />
      </div>

      <div className="bg-card border border-border rounded-lg overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead>
              <tr className="border-b border-border text-muted-foreground text-xs uppercase tracking-wider">
                <th className="text-left font-medium px-4 py-3">Tier</th>
                <th className="text-left font-medium px-4 py-3">Fixture</th>
                <th className="text-left font-medium px-4 py-3">Market</th>
                <th className="text-right font-medium px-4 py-3">Book</th>
                <th className="text-right font-medium px-4 py-3">Model</th>
                <th className="text-right font-medium px-4 py-3">Prob</th>
                <th className="text-right font-medium px-4 py-3">EV</th>
                <th className="text-left font-medium px-4 py-3">Conf</th>
                <th className="px-4 py-3"></th>
              </tr>
            </thead>
            <tbody className="font-mono-data text-sm">
              {loading ? (
                <tr><td colSpan={9} className="px-4 py-16 text-center text-muted-foreground animate-pulse">Scanning fixtures…</td></tr>
              ) : rows.length === 0 ? (
                <tr><td colSpan={9} className="px-4 py-16 text-center text-muted-foreground">No value bets match these filters. Paste odds in a fixture to feed the scanner.</td></tr>
              ) : rows.map((r, i) => {
                const t = tierMeta[r.tier];
                return (
                  <tr
                    key={`${r.fixture_id}-${r.market_label}-${i}`}
                    data-testid="scanner-row"
                    onClick={() => navigate(`/fixture/${r.fixture_id}`)}
                    className="border-b border-border/50 hover:bg-white/5 cursor-pointer transition-colors duration-150"
                    style={{ borderLeft: r.tier === "strong" ? "2px solid #10B981" : "2px solid transparent" }}
                  >
                    <td className="px-4 py-3">
                      <span className={`inline-flex items-center gap-1.5 text-xs px-2 py-1 rounded border ${t.chip}`}>
                        <span className={`h-1.5 w-1.5 rounded-full ${t.dot}`} /> {t.label}
                      </span>
                    </td>
                    <td className="px-4 py-3">
                      <div className="text-foreground whitespace-nowrap">{r.home_name} <span className="text-muted-foreground">v</span> {r.away_name}</div>
                      <div className="flex items-center gap-1.5 text-[10px] text-muted-foreground uppercase tracking-wider font-sans">
                        <span>{r.league_name}</span>
                        {fmtDate(r.date) && <><span className="opacity-40">·</span><span data-testid="scanner-row-date" className="text-primary/80 normal-case tracking-normal">{fmtDate(r.date)}</span></>}
                        {r.round && r.round !== "Upcoming" && <><span className="opacity-40">·</span><span data-testid="scanner-row-round" className="normal-case tracking-normal">{r.round}</span></>}
                      </div>
                    </td>
                    <td className="px-4 py-3 text-foreground whitespace-nowrap">{r.market_label}</td>
                    <td className="px-4 py-3 text-right text-foreground">{r.book_odds?.toFixed(2)}</td>
                    <td className="px-4 py-3 text-right text-muted-foreground">{r.fair_odds?.toFixed(2)}</td>
                    <td className="px-4 py-3 text-right text-muted-foreground">{r.prob?.toFixed(1)}%</td>
                    <td className={`px-4 py-3 text-right font-semibold ${t.text}`}>
                      {r.ev > 0 ? "+" : ""}{r.ev?.toFixed(1)}%
                    </td>
                    <td className="px-4 py-3">
                      <span className={`text-[10px] px-2 py-0.5 rounded border ${confMeta[r.confidence.label]}`}>{r.confidence.label}</span>
                    </td>
                    <td className="px-4 py-3 text-right"><ArrowRight className="h-4 w-4 text-muted-foreground inline" /></td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

const StatChip = ({ label, value, className, dot }) => (
  <div className="flex items-center gap-2 px-3 py-2 bg-card border border-border rounded-md">
    <span className={`h-2 w-2 rounded-full ${dot}`} />
    <span className={`font-mono-data text-lg font-semibold ${className}`}>{value}</span>
    <span className="text-xs text-muted-foreground">{label}</span>
  </div>
);

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
