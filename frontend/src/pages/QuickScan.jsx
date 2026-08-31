import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { Zap, ArrowRight, Swords, TrendingUp, ShieldAlert, Sparkles, Loader2 } from "lucide-react";
import { api } from "@/lib/api";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import MembersOnly from "@/components/MembersOnly";

const WINDOWS = [
  { v: "3", l: "Next 3 days" },
  { v: "7", l: "Next 7 days" },
  { v: "14", l: "Next 14 days" },
  { v: "0", l: "All upcoming" },
];

const fmt = (d) => (d ? new Date(d).toLocaleDateString(undefined, { weekday: "short", month: "short", day: "numeric" }) : "");

export default function QuickScan() {
  const navigate = useNavigate();
  const [within, setWithin] = useState("7");
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    const params = { limit: 30 };
    if (within !== "0") params.within_days = Number(within);
    api.topMismatches(params).then(setRows).catch(() => setRows([])).finally(() => setLoading(false));
  }, [within]);

  return (
    <MembersOnly title="Corner mismatches" blurb="Strong corner-winning sides drawn against defences that concede them, ranked by projected total, with the sample behind both halves.">
      <div className="space-y-3 sm:space-y-6" data-testid="quickscan-page">
        <div className="flex flex-col sm:flex-row sm:items-end justify-between gap-4">
          <div>
            <div className="flex items-center gap-2 text-primary mb-1">
              <Zap className="h-4 w-4" />
              <span className="font-mono-data text-xs tracking-widest uppercase">Quick Value Scan</span>
            </div>
            <h1 className="font-head text-3xl sm:text-4xl font-bold tracking-tight">Corner Mismatches</h1>
            <p className="text-muted-foreground text-sm mt-1">
              Strong corner-winning teams drawn against defences that concede a lot — ranked by projected total corners.
            </p>
          </div>
          <Tabs value={within} onValueChange={setWithin}>
            <TabsList className="bg-secondary h-9">
              {WINDOWS.map((w) => (
                <TabsTrigger key={w.v} value={w.v} data-testid={`quickscan-window-${w.v}`} className="text-xs px-2.5 h-7">{w.l}</TabsTrigger>
              ))}
            </TabsList>
          </Tabs>
        </div>

        {loading ? (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {Array.from({ length: 6 }).map((_, i) => <div key={i} className="h-[184px] bg-card border border-border rounded-lg animate-pulse" />)}
          </div>
        ) : rows.length === 0 ? (
          <div className="bg-card border border-border rounded-lg py-20 text-center text-muted-foreground text-sm" data-testid="quickscan-empty">
            No strong mismatches in this window. Try widening the timeframe.
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 items-start">
            {rows.map((r) => (
              <PairCard key={r.team_id} r={r} onClick={() => r.next_fixture?.fixture_id && navigate(`/fixture/${r.next_fixture.fixture_id}`)} />
            ))}
          </div>
        )}
      </div>
    </MembersOnly>
  );
}

function PairCard({ r, onClick }) {
  const nf = r.next_fixture || {};
  const [explanation, setExplanation] = useState(null);
  const [loadingExp, setLoadingExp] = useState(false);

  const explain = async (e) => {
    e.stopPropagation();
    if (explanation || loadingExp) return;
    setLoadingExp(true);
    try {
      const res = await api.explain({
        key: `${nf.fixture_id}-${r.line}`,
        team: r.name, opponent: nf.opponent, league: r.league_name,
        is_home: !!nf.is_home, line: r.line,
        team_for: r.team_for, opp_conceded: r.opp_conceded,
        lam: r.lambda, prob: r.prob, fair_odds: r.fair_odds,
      });
      setExplanation(res.explanation);
    } catch {
      setExplanation("Couldn't generate an explanation right now.");
    } finally {
      setLoadingExp(false);
    }
  };

  return (
    <div
      onClick={onClick}
      data-testid="quickscan-card"
      className="group cursor-pointer bg-card border border-border rounded-lg p-4 hover:border-emerald-500/40 transition-colors duration-150 flex flex-col gap-3"
      style={{ borderTop: "2px solid #10B981" }}
    >
      <div className="flex items-center gap-2 text-[10px] uppercase tracking-widest text-muted-foreground">
        <span>{r.league_name}</span>
        <span className="opacity-40">·</span>
        <span className="text-primary/80 normal-case tracking-normal">{fmt(nf.date)}</span>
        {nf.round && nf.round !== "Upcoming" && <><span className="opacity-40">·</span><span className="normal-case tracking-normal">{nf.round}</span></>}
      </div>

      <div className="flex items-center gap-3">
        {/* attacker */}
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-1.5 text-emerald-400 text-[10px] uppercase tracking-wider mb-0.5">
            <TrendingUp className="h-3 w-3" /> Wins corners
          </div>
          <p className="font-head font-semibold text-sm leading-tight truncate">{r.name}</p>
          <p className="font-mono-data text-xs text-emerald-400 mt-0.5">{r.team_for?.toFixed(1)} /g</p>
        </div>

        <Swords className="h-4 w-4 text-muted-foreground shrink-0" />

        {/* defence */}
        <div className="flex-1 min-w-0 text-right">
          <div className="flex items-center justify-end gap-1.5 text-amber-400 text-[10px] uppercase tracking-wider mb-0.5">
            Concedes <ShieldAlert className="h-3 w-3" />
          </div>
          <p className="font-head font-semibold text-sm leading-tight truncate">
            <span className="text-muted-foreground font-normal text-xs mr-1">{nf.is_home ? "vs" : "@"}</span>{nf.opponent}
          </p>
          <p className="font-mono-data text-xs text-amber-400 mt-0.5">{r.opp_conceded?.toFixed(1)} /g</p>
        </div>
      </div>

      <div className="flex items-center justify-between pt-2 border-t border-border/60">
        <div className="flex items-center gap-3 font-mono-data text-xs">
          <span className="text-muted-foreground">Proj λ <span className="text-primary font-semibold">{r.lambda?.toFixed(1)}</span></span>
          <span className="text-muted-foreground" title={`${r.prob?.toFixed(0)}% to hit`}>Model <span className="text-foreground font-semibold">{r.line}+ @ {r.fair_odds?.toFixed(2)}</span></span>
        </div>
        <ArrowRight className="h-4 w-4 text-muted-foreground opacity-0 group-hover:opacity-100 transition-opacity" />
      </div>

      {/* Claude explainer */}
      {explanation ? (
        <div data-testid="quickscan-explanation" className="rounded-md bg-primary/5 border border-primary/20 p-2.5">
          <div className="flex gap-2">
            <Sparkles className="h-3.5 w-3.5 text-primary shrink-0 mt-0.5" />
            <p className="text-xs text-foreground/90 leading-relaxed">{explanation}</p>
          </div>
          <button
            data-testid="quickscan-hide-btn"
            onClick={(e) => { e.stopPropagation(); setExplanation(null); }}
            className="mt-1.5 ml-5 text-[10px] text-muted-foreground hover:text-foreground transition-colors"
          >
            Hide
          </button>
        </div>
      ) : (
        <button
          data-testid="quickscan-explain-btn"
          onClick={explain}
          disabled={loadingExp}
          className="self-start inline-flex items-center gap-1.5 text-[11px] text-primary hover:text-primary/80 transition-colors disabled:opacity-60"
        >
          {loadingExp ? <Loader2 className="h-3 w-3 animate-spin" /> : <Sparkles className="h-3 w-3" />}
          {loadingExp ? "Thinking…" : "Why this angle?"}
        </button>
      )}
    </div>
  );
}
