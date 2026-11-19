import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { Layers, Zap, Flame, Target, AlertTriangle } from "lucide-react";
import { api } from "@/lib/api";
import PreviewWall from "@/components/PreviewWall";
import { withFlag } from "@/lib/countryFlag";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";

// QUICK SCAN, STREAKS AND PERFECT GAMES ON ONE PAGE. One row per team and fixture, kept
// only when two or more of the three boards agree, and priced at the two lines actually
// bet: 5+ and 6+ team corners. The merge is server-side (backend/combined.py) so the page
// and the weekly rebuild read the same rows.
const BOARDS = {
  quick_scan: { label: "Quick Scan", icon: Zap },
  streaks: { label: "Streak", icon: Flame },
  perfect_games: { label: "Perfect", icon: Target },
};

const FILTERS = [
  { v: "value", l: "Value only" },
  { v: "all", l: "All agreed" },
];

const fmt = (d) =>
  d ? new Date(d).toLocaleString(undefined, { weekday: "short", day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" }) : "";

export default function Combined() {
  const navigate = useNavigate();
  const [filter, setFilter] = useState("value");
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [preview, setPreview] = useState(null);

  useEffect(() => {
    setLoading(true);
    api.combined({ value_only: filter === "value" })
      .then((d) => { setRows(Array.isArray(d) ? d : []); setPreview(d?.preview ? { total: d.total } : null); })
      .catch(() => { setRows([]); setPreview(null); })
      .finally(() => setLoading(false));
  }, [filter]);

  return (
    <div className="space-y-3 sm:space-y-6" data-testid="combined-page">
      <div className="flex flex-col sm:flex-row sm:items-end justify-between gap-4">
        <div>
          <div className="flex items-center gap-2 text-primary mb-1">
            <Layers className="h-4 w-4" />
            <span className="font-mono-data text-xs tracking-widest uppercase">This week</span>
          </div>
          <h1 className="font-head text-3xl sm:text-4xl font-bold tracking-tight">Combined Board</h1>
          <p className="text-muted-foreground text-sm mt-1 max-w-2xl">
            Teams on two or more of Quick Scan, Streaks and Perfect Games for the same game, priced at 5+ and 6+ team
            corners. 15+ games only. The floor is the fewest corners in the run — the "whatever the score" test.
          </p>
        </div>
        <Tabs value={filter} onValueChange={setFilter}>
          <TabsList className="bg-secondary h-9">
            {FILTERS.map((f) => (
              <TabsTrigger key={f.v} value={f.v} data-testid={`combined-filter-${f.v}`} className="text-xs px-2.5 h-7">{f.l}</TabsTrigger>
            ))}
          </TabsList>
        </Tabs>
      </div>

      {loading ? (
        <div className="space-y-2">
          {Array.from({ length: 6 }).map((_, i) => <div key={i} className="h-24 bg-card border border-border rounded-lg animate-pulse" />)}
        </div>
      ) : rows.length === 0 ? (
        <div className="bg-card border border-border rounded-lg py-16 text-center text-muted-foreground text-sm" data-testid="combined-empty">
          {filter === "value" ? "Nothing priced above the model this week yet — prices fill in as books open their corner markets." : "No team is on two boards this week."}
        </div>
      ) : (
        <div className="space-y-2">
          {rows.map((r) => (
            <Row key={`${r.team_id}-${r.next_fixture?.fixture_id}`} r={r}
              onClick={() => r.next_fixture?.fixture_id && navigate(`/fixture/${r.next_fixture.fixture_id}`)} />
          ))}
        </div>
      )}

      {preview && <PreviewWall total={preview.total} shown={rows.length} noun="angles" className="rounded-lg border border-border" />}
    </div>
  );
}

function Row({ r, onClick }) {
  const nf = r.next_fixture || {};
  const s = r.streak;
  return (
    <div onClick={onClick} data-testid="combined-row"
      className={`cursor-pointer bg-card border rounded-lg p-3 sm:p-4 hover:border-primary/40 transition-colors ${r.value ? "border-emerald-500/40" : "border-border"} ${r.blurred ? "blur-[2px]" : ""}`}>
      <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-[10px] uppercase tracking-widest text-muted-foreground">
        <span>{withFlag(r.league_id, r.league_name)}</span>
        <span className="opacity-40">·</span>
        <span className="normal-case tracking-normal text-primary/80">{fmt(nf.date)}</span>
        <span className="ml-auto flex gap-1">
          {r.boards.map((b) => {
            const B = BOARDS[b];
            const Icon = B.icon;
            return (
              <span key={b} className="inline-flex items-center gap-1 rounded border border-border px-1.5 py-0.5 normal-case tracking-normal">
                <Icon className="h-3 w-3" />{B.label}
              </span>
            );
          })}
        </span>
      </div>

      <div className="mt-2 flex flex-col sm:flex-row sm:items-center gap-2 sm:gap-4">
        <div className="flex-1 min-w-0">
          <p className="font-head font-semibold text-sm truncate">
            {r.name} <span className="text-muted-foreground font-normal text-xs">{nf.is_home ? "vs" : "@"}</span> {nf.opponent}
          </p>
          <p className="font-mono-data text-[11px] text-muted-foreground mt-0.5">
            {r.samples} games
            {r.quick_scan && <> · wins {r.quick_scan.team_for?.toFixed(1)} / opp concedes {r.quick_scan.opp_conceded?.toFixed(1)}</>}
            {s && <> · {s.line_label} in {s.hits}/{s.settled} {s.side} · floor {s.floor}</>}
          </p>
        </div>

        <div className="flex gap-2 font-mono-data text-xs">
          {(r.angles || []).map((a) => {
            const best = r.best && r.best.line === a.line;
            return (
              <div key={a.line} className={`rounded-md border px-2 py-1 text-center min-w-[88px] ${best && r.value ? "border-emerald-500/50 bg-emerald-500/10" : "border-border"}`}>
                <div className="text-muted-foreground text-[10px]">{a.label} corners</div>
                <div>
                  <span className="text-foreground font-semibold">{a.book_odds ? a.book_odds.toFixed(2) : "—"}</span>
                  <span className="text-muted-foreground"> / fair {a.fair_odds?.toFixed(2) ?? "?"}</span>
                </div>
                {a.ev != null && (
                  <div className={a.ev > 0 ? "text-emerald-400" : "text-muted-foreground"}>{a.ev > 0 ? "+" : ""}{a.ev}%</div>
                )}
              </div>
            );
          })}
        </div>
      </div>

      {r.warnings?.length > 0 && (
        <p className="mt-2 flex items-center gap-1 text-[11px] text-amber-400">
          <AlertTriangle className="h-3 w-3 shrink-0" />{r.warnings.join(" · ")}
        </p>
      )}
    </div>
  );
}
