import { useState, useEffect, useCallback } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { ArrowLeft, ClipboardPaste, Calculator, TrendingUp } from "lucide-react";
import { api, tierMeta, confMeta } from "@/lib/api";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";

const WINDOW_LABELS = { "3": "L3", "5": "L5", "10": "L10", "0": "Season" };

export default function FixtureDetail() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [data, setData] = useState(null);
  const [odds, setOdds] = useState({});
  const [paste, setPaste] = useState("");
  const [pasteTarget, setPasteTarget] = useState("home");
  const [flash, setFlash] = useState({});

  const load = useCallback(() => {
    api.fixture(id).then((d) => {
      setData(d);
      const o = {};
      d.model.markets.forEach((m) => { if (m.book_odds) o[m.key] = String(m.book_odds); });
      setOdds(o);
    }).catch(() => toast.error("Failed to load fixture"));
  }, [id]);

  useEffect(() => { load(); }, [load]);

  const submitOdds = async (next) => {
    const payload = {};
    Object.entries(next).forEach(([k, v]) => { const n = parseFloat(v); if (n > 1) payload[k] = n; });
    try {
      const res = await api.setOdds(id, payload);
      setData((d) => ({ ...d, model: res.model }));
      const fl = {}; Object.keys(payload).forEach((k) => { fl[k] = true; });
      setFlash(fl); setTimeout(() => setFlash({}), 800);
      toast.success("EV recalculated");
    } catch { toast.error("Could not save odds"); }
  };

  const nameHit = (line, name) => {
    const toks = name.toLowerCase().split(/\s+/).filter((t) => t.length >= 4);
    return toks.some((t) => line.includes(t));
  };

  const handlePaste = () => {
    const homeName = fixture.home_name;
    const awayName = fixture.away_name;
    const lines = paste.split(/\n|;/).map((s) => s.trim()).filter(Boolean);
    const next = { ...odds };
    let matched = 0;
    lines.forEach((raw) => {
      const low = raw.toLowerCase();
      // route to a market group: explicit team name > "total" keyword > selected target
      let group = pasteTarget;
      if (nameHit(low, homeName)) group = "home";
      else if (nameHit(low, awayName)) group = "away";
      else if (/\btotal\b|\bmatch\b|\bgame\b/.test(low)) group = "total";
      const nums = raw.match(/\d+\.?\d*/g);
      if (!nums || nums.length < 2) return;
      let lineVal = parseFloat(nums[0]);
      const price = parseFloat(nums[nums.length - 1]);
      // "5+" or a whole number → N or more corners = Over (N-0.5)
      const isPlus = /\d+\s*\+/.test(raw) || Number.isInteger(lineVal);
      if (isPlus) lineVal = lineVal - 0.5;
      const key = `${group}_over_${lineVal}`;
      if (data.model.markets.some((m) => m.key === key) && price > 1) {
        next[key] = String(price); matched++;
      }
    });
    if (matched === 0) { toast.error('No matching lines. Try "Over 4.5 1.80" or "5+ 1.80"'); return; }
    setOdds(next); submitOdds(next); setPaste("");
    toast.success(`Parsed ${matched} line${matched > 1 ? "s" : ""}`);
  };

  if (!data) return <div className="py-20 text-center text-muted-foreground animate-pulse font-mono-data text-sm">Loading fixture…</div>;

  const { fixture, model, home_team, away_team } = data;
  const groups = [
    { key: "total", label: "Total Match Corners" },
    { key: "home", label: `${fixture.home_name} Corners` },
    { key: "away", label: `${fixture.away_name} Corners` },
  ];

  return (
    <div className="space-y-6" data-testid="fixture-detail-page">
      <button onClick={() => navigate(-1)} data-testid="back-btn" className="flex items-center gap-2 text-sm text-muted-foreground hover:text-foreground transition-colors duration-150">
        <ArrowLeft className="h-4 w-4" /> Back
      </button>

      {/* Header */}
      <div className="bg-card border border-border rounded-lg p-5 flex flex-col sm:flex-row sm:items-center gap-4">
        <div className="flex-1">
          <h1 className="font-head text-2xl sm:text-3xl font-bold tracking-tight">
            {fixture.home_name} <span className="text-muted-foreground font-normal">vs</span> {fixture.away_name}
          </h1>
          <p className="font-mono-data text-xs text-muted-foreground mt-1">
            {new Date(fixture.date).toLocaleString()}
            {fixture.round && fixture.round !== "Upcoming" && (
              <span data-testid="fixture-round" className="ml-2 text-primary/80">· {fixture.round}</span>
            )}
          </p>
        </div>
        <div className="flex gap-3">
          <Metric label="λ Home" value={model.lambdas.home.toFixed(2)} />
          <Metric label="λ Away" value={model.lambdas.away.toFixed(2)} />
          <Metric label="λ Total" value={model.lambdas.total.toFixed(2)} accent />
          <div className="flex flex-col items-center justify-center px-3 py-2 bg-secondary rounded-md">
            <span className="text-[10px] text-muted-foreground uppercase tracking-wider mb-1">Confidence</span>
            <span className={`text-xs px-2 py-0.5 rounded border ${confMeta[model.confidence.label]}`}>{model.confidence.label} · {model.confidence.score}</span>
          </div>
        </div>
      </div>

      {/* Quick paste */}
      <div className="bg-card border border-border rounded-lg p-4">
        <div className="flex items-center gap-2 mb-3 flex-wrap">
          <ClipboardPaste className="h-4 w-4 text-primary" />
          <h2 className="font-head font-semibold">Quick-Paste Bookmaker Odds</h2>
          <span className="text-xs text-muted-foreground">e.g. "4.5 1.80" or "5+ 1.80" — one per line</span>
        </div>
        <div className="flex items-center gap-2 mb-3">
          <span className="text-[10px] uppercase tracking-wider text-muted-foreground mr-1">Paste into</span>
          {[
            { v: "home", l: fixture.home_name },
            { v: "away", l: fixture.away_name },
            { v: "total", l: "Total" },
          ].map((o) => (
            <button
              key={o.v}
              data-testid={`paste-target-${o.v}`}
              onClick={() => setPasteTarget(o.v)}
              className={`text-xs px-2.5 py-1 rounded-md border transition-colors duration-150 max-w-[160px] truncate ${
                pasteTarget === o.v
                  ? "bg-primary/15 text-primary border-primary/40"
                  : "bg-secondary text-muted-foreground border-border hover:text-foreground"
              }`}
            >
              {o.v === "total" ? "Total match" : `${o.l} corners`}
            </button>
          ))}
        </div>
        <div className="flex flex-col sm:flex-row gap-3">
          <textarea
            data-testid="odds-paste-input"
            value={paste}
            onChange={(e) => setPaste(e.target.value)}
            placeholder={"4.5 1.80\n5.5 2.40\n6.5 3.30"}
            className="flex-1 h-24 bg-black border border-border rounded-md p-3 font-mono-data text-sm resize-none focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent"
          />
          <button
            data-testid="paste-parse-btn"
            onClick={handlePaste}
            className="sm:w-40 flex items-center justify-center gap-2 bg-primary text-black font-medium text-sm rounded-md px-4 py-2 transition-colors duration-150 hover:bg-[#33EEFF] self-start"
          >
            <Calculator className="h-4 w-4" /> Calculate EV
          </button>
        </div>
        <p className="text-[11px] text-muted-foreground mt-2 leading-relaxed">
          Tip: include a team name on a line (e.g. "{fixture.home_name} over 4.5 1.80") and it routes automatically.
          "5+" is read as 5-or-more (Over 4.5).
        </p>
      </div>

      {/* Markets */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {groups.map((g) => (
          <div key={g.key} className="bg-card border border-border rounded-lg overflow-hidden">
            <div className="px-4 py-3 border-b border-border flex items-center gap-2">
              <TrendingUp className="h-4 w-4 text-muted-foreground" />
              <h3 className="font-head font-semibold text-sm">{g.label}</h3>
            </div>
            <table className="w-full">
              <thead>
                <tr className="border-b border-border text-muted-foreground text-[10px] uppercase tracking-wider">
                  <th className="text-left font-medium px-3 py-2">Line</th>
                  <th className="text-right font-medium px-3 py-2">Prob</th>
                  <th className="text-right font-medium px-3 py-2">Fair</th>
                  <th className="text-right font-medium px-3 py-2">Book</th>
                  <th className="text-right font-medium px-3 py-2">EV</th>
                </tr>
              </thead>
              <tbody className="font-mono-data text-sm">
                {model.markets.filter((m) => m.group === g.key).map((m) => {
                  const t = m.tier ? tierMeta[m.tier] : null;
                  return (
                    <tr key={m.key} data-testid={`market-row-${m.key}`} className={`border-b border-border/50 transition-colors ${flash[m.key] ? "flash-green" : ""}`}>
                      <td className="px-3 py-2 text-foreground whitespace-nowrap">{m.label}</td>
                      <td className="px-3 py-2 text-right text-muted-foreground">{m.prob.toFixed(1)}%</td>
                      <td className="px-3 py-2 text-right text-foreground">{m.fair_odds?.toFixed(2)}</td>
                      <td className="px-3 py-2 text-right">
                        <input
                          data-testid={`odds-input-${m.key}`}
                          value={odds[m.key] || ""}
                          onChange={(e) => setOdds({ ...odds, [m.key]: e.target.value })}
                          onBlur={() => odds[m.key] && submitOdds(odds)}
                          onKeyDown={(e) => e.key === "Enter" && submitOdds(odds)}
                          placeholder="—"
                          className="w-16 bg-black border border-border rounded px-1.5 py-1 text-right text-xs focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent"
                        />
                      </td>
                      <td className={`px-3 py-2 text-right font-semibold ${t ? t.text : "text-muted-foreground"}`}>
                        {m.ev != null ? `${m.ev > 0 ? "+" : ""}${m.ev.toFixed(1)}%` : "—"}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        ))}
      </div>

      {/* Team breakdowns */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <TeamBreakdown team={home_team} title={`${fixture.home_name} — Home / Away / Overall`} highlight="home" />
        <TeamBreakdown team={away_team} title={`${fixture.away_name} — Home / Away / Overall`} highlight="away" />
      </div>
    </div>
  );
}

const GoalChip = ({ label, strong }) => (
  <span
    className={`text-[10px] px-2 py-0.5 rounded border font-mono-data ${
      strong ? "bg-emerald-500/15 text-emerald-400 border-emerald-500/30" : "bg-secondary text-muted-foreground border-border"
    }`}
  >
    {label}
  </span>
);

const Metric = ({ label, value, accent }) => (
  <div className="flex flex-col items-center justify-center px-3 py-2 bg-secondary rounded-md min-w-[64px]">
    <span className="text-[10px] text-muted-foreground uppercase tracking-wider mb-1">{label}</span>
    <span className={`font-mono-data text-base font-semibold ${accent ? "text-primary" : "text-foreground"}`}>{value}</span>
  </div>
);

function TeamBreakdown({ team, title, highlight }) {
  const [split, setSplit] = useState(highlight);
  const [count, setCount] = useState("5");
  const rows = [["3", "Last 3"], ["5", "Last 5"], ["10", "Last 10"], ["0", "Season"]];
  const recentAll = team.recent || [];
  const filtered = recentAll.filter((m) => split === "overall" || (split === "home" ? m.home : !m.home));
  const games = filtered.slice(0, parseInt(count, 10));
  const fmtDate = (d) => new Date(d).toLocaleDateString(undefined, { month: "short", day: "numeric" });
  // goal-form summary over the games currently shown; games without goal data are left out
  const withGoals = games.filter((m) => m.gf != null && m.ga != null);
  const scored = withGoals.filter((m) => m.gf >= 1).length;
  const over25 = withGoals.filter((m) => m.gf + m.ga >= 3).length;
  const avgGoals = withGoals.length ? withGoals.reduce((s, m) => s + m.gf + m.ga, 0) / withGoals.length : null;
  const fhKnown = games.filter((m) => m.fh != null);
  const fhg = fhKnown.filter((m) => m.fh).length;
  const resultTone = (m) =>
    m.gf > m.ga ? "text-emerald-400" : m.gf < m.ga ? "text-red-400" : "text-zinc-400";
  return (
    <div className="bg-card border border-border rounded-lg overflow-hidden">
      <div className="px-4 py-3 border-b border-border flex items-center gap-3">
        <h3 className="font-head font-semibold text-sm flex-1">{title}</h3>
        <span
          data-testid={`bd-samples-${highlight}`}
          className={`text-[10px] px-2 py-0.5 rounded border font-mono-data ${team.real_samples >= 5 ? "bg-emerald-500/15 text-emerald-400 border-emerald-500/30" : "bg-amber-500/15 text-amber-400 border-amber-500/30"}`}
          title="Number of real matches with corner data backing these figures"
        >
          {team.real_samples || 0} real{team.real_samples < 5 ? " · est." : ""}
        </span>
        <Tabs value={split} onValueChange={setSplit}>
          <TabsList className="bg-secondary h-8">
            {["home", "away", "overall"].map((s) => (
              <TabsTrigger key={s} value={s} data-testid={`bd-split-${highlight}-${s}`} className="text-xs px-2 h-6 capitalize">{s}</TabsTrigger>
            ))}
          </TabsList>
        </Tabs>
      </div>
      <table className="w-full">
        <thead>
          <tr className="border-b border-border text-muted-foreground text-[10px] uppercase tracking-wider">
            <th className="text-left font-medium px-4 py-2">Window</th>
            <th className="text-right font-medium px-4 py-2">Won</th>
            <th className="text-right font-medium px-4 py-2">Conceded</th>
            <th className="text-right font-medium px-4 py-2">Total /g</th>
            <th className="text-right font-medium px-4 py-2">Games</th>
          </tr>
        </thead>
        <tbody className="font-mono-data text-sm">
          {rows.map(([w, label]) => {
            const s = team.splits[split][w];
            return (
              <tr key={w} className="border-b border-border/50 hover:bg-white/5 transition-colors duration-150">
                <td className="px-4 py-2 text-foreground">{label}</td>
                <td className="px-4 py-2 text-right text-emerald-400">{s.for_avg.toFixed(2)}</td>
                <td className="px-4 py-2 text-right text-red-400">{s.against_avg.toFixed(2)}</td>
                <td className="px-4 py-2 text-right text-foreground font-semibold">{s.total_avg.toFixed(2)}</td>
                <td className="px-4 py-2 text-right text-muted-foreground">{s.played}</td>
              </tr>
            );
          })}
        </tbody>
      </table>

      {/* Per-game breakdown */}
      <div className="px-4 py-2.5 border-t border-border flex items-center gap-3">
        <span className="text-[10px] uppercase tracking-wider text-muted-foreground flex-1">Recent games ({split})</span>
        <Tabs value={count} onValueChange={setCount}>
          <TabsList className="bg-secondary h-7">
            {["5", "10"].map((c) => (
              <TabsTrigger key={c} value={c} data-testid={`bd-count-${highlight}-${c}`} className="text-xs px-2.5 h-5">Last {c}</TabsTrigger>
            ))}
          </TabsList>
        </Tabs>
      </div>
      {withGoals.length > 0 && (
        <div className="px-4 pb-2.5 flex flex-wrap gap-2" data-testid={`bd-goalform-${highlight}`}>
          <GoalChip label={`Scored in ${scored}/${withGoals.length}`} strong={scored >= withGoals.length * 0.7} />
          {fhKnown.length > 0 && <GoalChip label={`FHG in ${fhg}/${fhKnown.length}`} strong={fhg >= fhKnown.length * 0.6} />}
          <GoalChip label={`${avgGoals.toFixed(1)} goals/g`} strong={avgGoals >= 2.8} />
          <GoalChip label={`O2.5 in ${over25}/${withGoals.length}`} strong={over25 >= withGoals.length * 0.6} />
        </div>
      )}
      <table className="w-full">
        <thead>
          <tr className="border-b border-border text-muted-foreground text-[10px] uppercase tracking-wider">
            <th className="text-left font-medium px-4 py-1.5">Date</th>
            <th className="text-left font-medium px-4 py-1.5">Opponent</th>
            <th className="text-center font-medium px-2 py-1.5">V</th>
            <th className="text-center font-medium px-2 py-1.5" title="Final score (goals for-against)">Score</th>
            <th className="text-center font-medium px-2 py-1.5" title="Scored a first-half goal">FHG</th>
            <th className="text-right font-medium px-4 py-1.5">Won</th>
            <th className="text-right font-medium px-4 py-1.5">Conc</th>
            <th className="text-right font-medium px-4 py-1.5">Total</th>
          </tr>
        </thead>
        <tbody className="font-mono-data text-sm" data-testid={`bd-recent-${highlight}`}>
          {games.length === 0 ? (
            <tr><td colSpan={8} className="px-4 py-4 text-center text-muted-foreground text-xs">No real games on this split</td></tr>
          ) : games.map((m, i) => (
            <tr key={i} className="border-b border-border/50 hover:bg-white/5 transition-colors duration-150">
              <td className="px-4 py-1.5 text-muted-foreground text-xs">{fmtDate(m.date)}</td>
              <td className="px-4 py-1.5 text-foreground font-sans text-xs whitespace-nowrap truncate max-w-[140px]">{m.opponent}</td>
              <td className="px-2 py-1.5 text-center">
                <span className={`text-[9px] px-1 py-0.5 rounded ${m.home ? "bg-primary/15 text-primary" : "bg-zinc-500/15 text-zinc-400"}`}>{m.home ? "H" : "A"}</span>
              </td>
              <td className={`px-2 py-1.5 text-center text-xs font-semibold ${m.gf != null ? resultTone(m) : "text-muted-foreground"}`}>
                {m.gf != null ? `${m.gf}-${m.ga}` : "—"}
              </td>
              <td className="px-2 py-1.5 text-center text-xs">
                {m.fh == null ? <span className="text-muted-foreground">—</span>
                  : m.fh ? <span className="text-emerald-400">✓</span>
                  : <span className="text-zinc-600">·</span>}
              </td>
              <td className="px-4 py-1.5 text-right text-emerald-400 font-semibold">{m.won}</td>
              <td className="px-4 py-1.5 text-right text-red-400">{m.conceded}</td>
              <td className="px-4 py-1.5 text-right text-foreground">{m.total}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
