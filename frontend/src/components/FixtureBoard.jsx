import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { CalendarDays, ChevronRight, Flame, Target, TrendingDown } from "lucide-react";
import { api } from "@/lib/api";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";

// The best upcoming games, grouped by day and capped — a schedule you can scan, not
// another ranked list of teams. Every other board here is team-first with the fixture
// riding along; this one's unit is the match.
//
// The order is TRIAGE, not a measured edge: which games to open first. The actual bet
// comes from the angles listed on the row, which are priced. See _fixture_board in
// server.py for exactly what "best" means.
const PER_DAY = [
  { v: "2", l: "2 / day" },
  { v: "3", l: "3 / day" },
];
const DAYS = [
  { v: "3", l: "3 days" },
  { v: "7", l: "Week" },
];

const KIND = {
  chase: { Icon: Target, cls: "text-cyan-400 border-cyan-500/30 bg-cyan-500/10" },
  over_team: { Icon: Flame, cls: "text-emerald-400 border-emerald-500/30 bg-emerald-500/10" },
  under_team: { Icon: TrendingDown, cls: "text-sky-400 border-sky-500/30 bg-sky-500/10" },
  over_match: { Icon: Flame, cls: "text-amber-400 border-amber-500/30 bg-amber-500/10" },
  under_match: { Icon: TrendingDown, cls: "text-indigo-400 border-indigo-500/30 bg-indigo-500/10" },
};

const dayLabel = (iso) => {
  const d = new Date(`${iso}T12:00:00Z`);
  const today = new Date();
  const diff = Math.round((d - new Date(today.toDateString())) / 86400000);
  const rel = diff === 0 ? "Today" : diff === 1 ? "Tomorrow" : null;
  const full = d.toLocaleDateString(undefined, { weekday: "long", day: "numeric", month: "short" });
  return rel ? `${rel} · ${full}` : full;
};
const kickoff = (iso) =>
  new Date(iso).toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" });

export default function FixtureBoard({ leagueId = "all" }) {
  const navigate = useNavigate();
  const [board, setBoard] = useState(null);
  const [loading, setLoading] = useState(true);
  const [perDay, setPerDay] = useState("3");
  const [days, setDays] = useState("3");

  useEffect(() => {
    setLoading(true);
    api
      .fixtureBoard({ days: Number(days), per_day: Number(perDay), league_id: leagueId })
      .then(setBoard)
      .catch(() => setBoard(null))
      .finally(() => setLoading(false));
  }, [leagueId, perDay, days]);

  return (
    <section className="bg-card border border-border rounded-lg" data-testid="fixture-board">
      <div className="flex flex-col sm:flex-row sm:items-center gap-3 px-4 py-3 border-b border-border">
        <div className="flex items-center gap-2 min-w-0">
          <CalendarDays className="h-4 w-4 text-primary shrink-0" />
          <h2 className="font-head font-semibold text-lg">Best Upcoming Games</h2>
          <span className="text-xs text-muted-foreground hidden md:inline truncate">
            the games worth opening, day by day
          </span>
        </div>
        <div className="sm:ml-auto flex gap-2">
          <Tabs value={days} onValueChange={setDays}>
            <TabsList className="bg-secondary h-8">
              {DAYS.map((d) => (
                <TabsTrigger key={d.v} value={d.v} data-testid={`fb-days-${d.v}`}
                  className="text-xs px-2.5 h-6">{d.l}</TabsTrigger>
              ))}
            </TabsList>
          </Tabs>
          <Tabs value={perDay} onValueChange={setPerDay}>
            <TabsList className="bg-secondary h-8">
              {PER_DAY.map((p) => (
                <TabsTrigger key={p.v} value={p.v} data-testid={`fb-per-${p.v}`}
                  className="text-xs px-2.5 h-6">{p.l}</TabsTrigger>
              ))}
            </TabsList>
          </Tabs>
        </div>
      </div>

      {loading ? (
        <div className="p-4 space-y-2">
          {[0, 1, 2].map((i) => <div key={i} className="h-16 rounded-md bg-secondary animate-pulse" />)}
        </div>
      ) : !board?.days?.length ? (
        <p className="px-4 py-6 text-sm text-muted-foreground" data-testid="fb-empty">
          No upcoming fixtures carry a live angle in this window. Try the full week, or
          refresh the data if a round is due.
        </p>
      ) : (
        <div className="divide-y divide-border">
          {board.days.map((d) => (
            <div key={d.day} data-testid="fb-day">
              <div className="flex items-center gap-2 px-4 py-2 bg-secondary/40">
                <span className="text-xs font-head font-semibold text-foreground">{dayLabel(d.day)}</span>
                <span className="ml-auto text-[10px] text-muted-foreground font-mono-data"
                  title="Shown out of the fixtures that day carrying at least one angle">
                  {d.fixtures.length} of {d.considered}
                </span>
              </div>
              {d.fixtures.map((f) => (
                <FixtureRow key={f.fixture_id} f={f}
                  onClick={() => navigate(`/fixture/${f.fixture_id}`)} />
              ))}
            </div>
          ))}
        </div>
      )}
    </section>
  );
}

function FixtureRow({ f, onClick }) {
  // corner_edge is the projected match total over what this league actually averages
  const edgePct = Math.round((f.corner_edge - 1) * 100);
  const hot = edgePct >= 8;
  return (
    <button onClick={onClick} data-testid="fb-fixture"
      className="w-full text-left px-4 py-3 hover:bg-white/5 transition-colors duration-150 flex gap-3 items-start">
      <div className="font-mono-data text-xs text-muted-foreground pt-0.5 w-11 shrink-0">
        {kickoff(f.date)}
      </div>
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2 flex-wrap">
          <span className="font-sans font-medium text-foreground text-sm truncate">
            {f.home} <span className="text-muted-foreground font-normal">v</span> {f.away}
          </span>
          <span className={`text-[10px] px-1.5 py-0.5 rounded border font-mono-data ${
            hot ? "bg-emerald-500/15 text-emerald-400 border-emerald-500/30"
                : "bg-secondary text-muted-foreground border-border"}`}
            title={`Model projects ${f.lambda_total} corners; this league averages ${f.league_avg_total}`}>
            λ {f.lambda_total} · {edgePct >= 0 ? "+" : ""}{edgePct}%
          </span>
        </div>
        <div className="text-[10px] text-muted-foreground uppercase tracking-wider mt-0.5">
          {f.league_name}
        </div>
        <div className="flex flex-wrap gap-1.5 mt-1.5">
          {f.angles.map((a, i) => {
            const meta = KIND[a.kind] || KIND.chase;
            const { Icon } = meta;
            return (
              <span key={i} title={`${a.team} — ${a.detail}`}
                className={`inline-flex items-center gap-1 text-[10px] px-1.5 py-0.5 rounded border font-mono-data ${meta.cls}`}>
                <Icon className="h-2.5 w-2.5" />
                <span className="font-sans text-foreground/90">{a.team}</span> {a.label}
              </span>
            );
          })}
          {f.angle_count > f.angles.length && (
            <span className="text-[10px] text-muted-foreground font-mono-data px-1 py-0.5">
              +{f.angle_count - f.angles.length} more
            </span>
          )}
        </div>
      </div>
      <ChevronRight className="h-4 w-4 text-muted-foreground shrink-0 mt-0.5" />
    </button>
  );
}
