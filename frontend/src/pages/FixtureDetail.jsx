import { useState, useEffect, useCallback } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { ArrowLeft, TrendingUp, ClipboardPaste } from "lucide-react";
import StarButton from "@/components/StarButton";
import { api, tierMeta, confMeta } from "@/lib/api";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";

// Bands, not a gradient: a rate either reads as reliable, playable, thin or unlikely.
// Shared by the match-total table and the team-corner tables so the two cannot show the
// same number in different colours — the team tables previously had NO colour at all,
// which made a 78% line and a 22% line look equally worth reading.
const band = (pct) =>
  pct >= 70 ? { text: "text-emerald-400", bar: "bg-emerald-500", chip: "bg-emerald-500/15 border-emerald-500/30", label: "reliable" }
  : pct >= 50 ? { text: "text-primary", bar: "bg-primary", chip: "bg-primary/15 border-primary/30", label: "playable" }
  : pct >= 30 ? { text: "text-amber-400", bar: "bg-amber-500", chip: "bg-amber-500/15 border-amber-500/30", label: "thin" }
  : { text: "text-muted-foreground/60", bar: "bg-zinc-600", chip: "border-border/60", label: "unlikely" };

const WINDOW_LABELS = { "3": "L3", "5": "L5", "10": "L10", "0": "Season" };

export default function FixtureDetail() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [data, setData] = useState(null);
  const [odds, setOdds] = useState({});
  const [paste, setPaste] = useState("");
  // Defaults to totals: it is the market at the top of the page and the one most
  // people are pricing. An unrecognised line lands here rather than nowhere.
  const [pasteTarget, setPasteTarget] = useState("total");
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
  // Every market — totals included — now carries fair odds, your price and the EV
  // between them. See TotalCorners for why totals were the exception and no longer are.
  const groups = [
    { key: "home", label: `${fixture.home_name} Corners`, team: home_team, venue: true },
    { key: "away", label: `${fixture.away_name} Corners`, team: away_team, venue: false },
  ];

  return (
    <div className="space-y-3 sm:space-y-6" data-testid="fixture-detail-page">
      <button onClick={() => navigate(-1)} data-testid="back-btn" className="flex items-center gap-2 text-sm text-muted-foreground hover:text-foreground transition-colors duration-150">
        <ArrowLeft className="h-4 w-4" /> Back
      </button>

      {/* Header */}
      <div className="bg-card border border-border rounded-lg p-5 flex flex-col sm:flex-row sm:items-center gap-4">
        <div className="flex-1">
          {/* The most natural place to save a game is the game's own page — this was the
              one surface the star was missing from, which is most of why it could not
              be found. */}
          <div className="flex items-start gap-2">
            <StarButton fixtureId={fixture.fixture_id} size="lg" />
            <h1 className="font-head text-2xl sm:text-3xl font-bold tracking-tight">
              {fixture.home_name} <span className="text-muted-foreground font-normal">vs</span> {fixture.away_name}
            </h1>
          </div>
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

      {/* TOTAL CORNERS FIRST, and across the full width. It is the market with the most
          liquidity and the one most people are actually pricing, and it now carries a
          full ladder — landed, model, fair, your price, gap, EV — which does not fit in
          a third of a row. The team tables get half each below instead of a third, which
          they needed anyway. */}
      {/* THE BULK ENTRY BOX. This parser was written, complete, and never rendered —
          `handlePaste` had no caller, so filling a ladder meant eight separate inputs
          and eight round trips. Prices arrive from a bookmaker as a block of text, so
          this takes them as a block: it reads a team name or the word "total" to route
          each line, understands both "Over 9.5 1.85" and "10+ 1.85", and prices every
          market on the page in one go. */}
      <PastePrices
        value={paste}
        onChange={setPaste}
        target={pasteTarget}
        onTarget={setPasteTarget}
        onSubmit={handlePaste}
        homeName={fixture.home_name}
        awayName={fixture.away_name}
      />

      <TotalCorners
        markets={model.markets}
        home={home_team}
        away={away_team}
        homeName={fixture.home_name}
        awayName={fixture.away_name}
        odds={odds}
        setOdds={setOdds}
        submitOdds={submitOdds}
        flash={flash}
      />

      {/* Markets */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {groups.map((g) => (
          <div key={g.key} className="bg-card border border-border rounded-lg overflow-hidden">
            <div className="px-4 py-3 border-b border-border flex items-center gap-2">
              <TrendingUp className="h-4 w-4 text-muted-foreground" />
              <h3 className="font-head font-semibold text-sm">{g.label}</h3>
            </div>
            {/* Wide on a phone: the card clips, so the table needs its own scroller. */}
            <div className="overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr className="border-b border-border text-muted-foreground text-[10px] uppercase tracking-wider">
                  <th className="text-left font-medium px-3 py-2">Line</th>
                  <th className="text-left font-medium px-3 py-2"
                    title="How often this team ACTUALLY hit the line, in its games on this venue">Landed</th>
                  <th className="text-right font-medium px-3 py-2">Prob</th>
                  <th className="text-right font-medium px-3 py-2">Fair</th>
                  <th className="text-right font-medium px-3 py-2">Book</th>
                  <th className="text-right font-medium px-3 py-2">EV</th>
                </tr>
              </thead>
              <tbody className="font-mono-data text-sm">
                {model.markets.filter((m) => m.group === g.key).map((m) => {
                  const t = m.tier ? tierMeta[m.tier] : null;
                  // Colour by what actually happened, not by the model's own probability —
                  // the same evidence the match-total table uses, on the same bands.
                  // Venue-filtered, because the market is for this team at this venue and
                  // the model prices it that way too.
                  const played = (g.team?.recent || []).filter((x) => x.home === g.venue);
                  const plus = Math.ceil(m.line ?? parseFloat(String(m.key).split("_").pop()));
                  const hit = played.filter((x) => (x.won ?? -1) >= plus).length;
                  const pct = played.length ? Math.round((hit / played.length) * 100) : null;
                  const c = band(pct ?? 0);
                  const dim = pct != null && pct < 30;
                  return (
                    <tr key={m.key} data-testid={`market-row-${m.key}`}
                      className={`border-b border-border/50 transition-colors ${flash[m.key] ? "flash-green" : ""} ${dim ? "opacity-60" : ""}`}>
                      <td className="px-3 py-2 whitespace-nowrap">
                        <span className={`text-xs px-1.5 py-0.5 rounded border ${c.chip} ${c.text}`}
                          title={pct == null ? "no games on this venue yet" : `${c.label} — landed ${hit}/${played.length} on this venue`}>
                          {m.label}
                        </span>
                      </td>
                      <td className="px-3 py-2">
                        {pct == null ? <span className="text-muted-foreground text-xs">—</span> : (
                          <div className="flex items-center gap-2">
                            <span className={`${c.text} text-xs font-semibold w-9 shrink-0`}>{hit}/{played.length}</span>
                            <div className="h-1.5 rounded-full bg-white/5 overflow-hidden flex-1 min-w-[28px]">
                              <div className={`h-full rounded-full ${c.bar}`} style={{ width: `${pct}%` }} />
                            </div>
                            <span className={`${c.text} text-xs w-8 text-right`}>{pct}%</span>
                          </div>
                        )}
                      </td>
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
            <BandKey note="Landed = how often this team hit the line in its own games on this venue. Colour follows that, not the model's probability." />
          </div>
        ))}
      </div>

      {/* Team breakdowns */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <TeamBreakdown team={home_team} title={fixture.home_name} highlight="home" />
        <TeamBreakdown team={away_team} title={fixture.away_name} highlight="away" />
      </div>
    </div>
  );
}

// Prices in bulk, because that is how they arrive: copied off a bookmaker's coupon as
// a block of lines. Typing eight totals into eight boxes is eight chances to fat-finger
// a price into the wrong row, and the parser behind this already handled the block —
// it just had nothing to type into.
function PastePrices({ value, onChange, target, onTarget, onSubmit, homeName, awayName }) {
  const targets = [
    { key: "total", label: "Total" },
    { key: "home", label: homeName },
    { key: "away", label: awayName },
  ];
  return (
    <details className="bg-card border border-border rounded-lg" data-testid="paste-prices">
      <summary className="px-4 py-3 cursor-pointer list-none flex items-center gap-2 text-sm
                          font-head font-semibold hover:text-primary transition-colors
                          [&::-webkit-details-marker]:hidden">
        <ClipboardPaste className="h-4 w-4 text-muted-foreground" />
        Paste prices
        <span className="font-sans font-normal text-xs text-muted-foreground ml-1">
          — fill every line at once
        </span>
      </summary>
      <div className="px-4 pb-4 space-y-2">
        <textarea
          data-testid="paste-input"
          value={value}
          onChange={(e) => onChange(e.target.value)}
          rows={4}
          placeholder={"Over 9.5  1.85\nOver 10.5  2.30\n11+  3.10"}
          className="w-full bg-black border border-border rounded px-2 py-1.5 font-mono-data
                     text-xs focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent"
        />
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-[10px] uppercase tracking-wider text-muted-foreground">
            Lines without a name go to
          </span>
          {targets.map((t) => (
            <button key={t.key} onClick={() => onTarget(t.key)}
              data-testid={`paste-target-${t.key}`}
              className={`text-xs px-2 py-1 rounded border transition-colors max-w-[10rem] truncate ${
                target === t.key
                  ? "bg-primary/15 border-primary/40 text-primary"
                  : "bg-secondary border-border text-muted-foreground hover:text-foreground"}`}>
              {t.label}
            </button>
          ))}
          <button onClick={onSubmit} disabled={!value.trim()}
            data-testid="paste-submit"
            className="ml-auto text-xs font-semibold px-3 py-1.5 rounded-md bg-primary
                       text-black hover:opacity-90 transition-opacity disabled:opacity-40">
            Price them
          </button>
        </div>
        <p className="text-[10px] text-muted-foreground leading-relaxed">
          One line each: a line and a price. Both <span className="text-foreground">Over 9.5 1.85</span>{" "}
          and <span className="text-foreground">10+ 1.85</span> work, and they mean the same
          thing. Name a team in the line and it routes itself.
        </p>
      </div>
    </details>
  );
}

// TOTAL CORNERS: what the model makes it, what you can get, and the gap between them.
//
// This table used to show hit rates ONLY, with the fair-odds and EV columns stripped out.
// That was right at the time and is not any more, and the difference is where the book
// price comes from. Back then the odds collection was filled by `seed_data`, which
// invented a price by jittering the model's own fair odds — so "EV" was the model
// marking its own homework and every green number was noise. `seed_data` is dead code
// now: the only writer to that collection is POST /fixtures/{id}/odds, which is you
// typing in what the shop is offering. A gap against a real price is worth showing.
//
// LANDED STAYS, next to the model column and ahead of both prices. The fair odds come
// off a Poisson fitted to the two teams' scoring rates, and the hit rate is what those
// fixtures actually did; when the two disagree, that is information, and burying it
// under a green EV badge is how a model gets believed past its evidence.
//
// The GAP column is deliberately separate from EV. The gap is what you eyeball at the
// shop — model says 2.10, you can get 2.35, that is a quarter of a point in hand. EV is
// the same fact as a percentage of stake, which is the one that adds up over a season.
// Showing both means the quick check and the arithmetic agree in front of you.

function TotalCorners({ markets, home, away, homeName, awayName,
                        odds, setOdds, submitOdds, flash }) {
  // Straight off the model's own total ladder, so the prices and the hit rates cannot
  // drift onto different lines. Over 9.5 is displayed as "10+", which is how it is said.
  const rows = (markets || [])
    .filter((m) => m.group === "total")
    .map((m) => ({ ...m, plus: Math.ceil(m.line ?? parseFloat(String(m.key).split("_").pop())) }))
    .filter((r) => Number.isFinite(r.plus));

  const totals = (team) => (team?.recent || []).map((g) => g.total).filter((t) => t != null);
  const homeTotals = totals(home);
  const awayTotals = totals(away);
  const sample = homeTotals.length + awayTotals.length;

  if (!rows.length) return null;

  const hits = (arr, plus) => arr.filter((t) => t >= plus).length;

  return (
    <div className="bg-card border border-border rounded-lg overflow-hidden"
      data-testid="total-corners-landed">
      <div className="px-4 py-3 border-b border-border flex items-center gap-2">
        <TrendingUp className="h-4 w-4 text-muted-foreground" />
        <h3 className="font-head font-semibold text-sm">Total Match Corners</h3>
        <span className="ml-auto font-mono-data text-[10px] text-muted-foreground"
          title={`${homeTotals.length} ${homeName} games + ${awayTotals.length} ${awayName} games`}>
          {sample} games
        </span>
      </div>
      {/* Wide on a phone: the card clips, so the table needs its own scroller. */}
      <div className="overflow-x-auto">
      <table className="w-full">
        <thead>
          <tr className="border-b border-border text-muted-foreground text-[10px] uppercase tracking-wider">
            <th className="text-left font-medium px-3 py-2">Line</th>
            <th className="text-right font-medium px-3 py-2" title={homeName}>Home</th>
            <th className="text-right font-medium px-3 py-2" title={awayName}>Away</th>
            <th className="text-left font-medium px-3 py-2">Landed in</th>
            <th className="text-right font-medium px-3 py-2"
              title="The model's probability this line clears">Model</th>
            <th className="text-right font-medium px-3 py-2"
              title="The price that probability is worth — no margin, no juice">Fair</th>
            <th className="text-right font-medium px-3 py-2"
              title="What you can actually get. Type it in and the gap and EV fill themselves">Your price</th>
            <th className="text-right font-medium px-3 py-2"
              title="Your price minus the fair price. Positive means you are being paid over the odds">Gap</th>
            <th className="text-right font-medium px-3 py-2"
              title="The gap as a share of your stake, over the long run">EV</th>
          </tr>
        </thead>
        <tbody className="font-mono-data text-sm">
          {rows.map((m) => {
            const h = hits(homeTotals, m.plus);
            const a = hits(awayTotals, m.plus);
            const pct = sample ? Math.round(((h + a) / sample) * 100) : null;
            const c = band(pct ?? 0);
            const t = m.tier ? tierMeta[m.tier] : null;
            // The gap is only meaningful once BOTH prices exist. A "gap" computed
            // against a blank input would read as the model calling every line value.
            const gap = (m.book_odds && m.fair_odds) ? m.book_odds - m.fair_odds : null;
            return (
              <tr key={m.key} data-testid={`total-landed-${m.plus}`}
                className={`border-b border-border/50 transition-colors ${flash?.[m.key] ? "flash-green" : ""}`}>
                <td className="px-3 py-2 whitespace-nowrap">
                  <span className={`text-xs px-1.5 py-0.5 rounded border ${c.chip} ${c.text}`}>{m.plus}+</span>
                </td>
                <td className="px-3 py-2 text-right text-muted-foreground text-xs">
                  {homeTotals.length ? `${h}/${homeTotals.length}` : "—"}
                </td>
                <td className="px-3 py-2 text-right text-muted-foreground text-xs">
                  {awayTotals.length ? `${a}/${awayTotals.length}` : "—"}
                </td>
                <td className="px-3 py-2">
                  {pct == null ? <span className="text-muted-foreground text-xs">—</span> : (
                    <div className="flex items-center gap-2">
                      <span className={`${c.text} font-semibold w-14 shrink-0`}>{h + a}/{sample}</span>
                      <div className="h-1.5 rounded-full bg-white/5 overflow-hidden flex-1 min-w-[40px]">
                        <div className={`h-full rounded-full ${c.bar}`} style={{ width: `${pct}%` }} />
                      </div>
                      <span className={`${c.text} text-xs w-9 text-right`}>{pct}%</span>
                    </div>
                  )}
                </td>
                <td className="px-3 py-2 text-right text-muted-foreground text-xs">
                  {m.prob != null ? `${Math.round(m.prob)}%` : "—"}
                </td>
                <td className="px-3 py-2 text-right text-foreground">
                  {m.fair_odds?.toFixed(2) ?? "—"}
                </td>
                <td className="px-3 py-2 text-right">
                  <input
                    data-testid={`odds-input-${m.key}`}
                    inputMode="decimal"
                    value={odds?.[m.key] || ""}
                    onChange={(e) => setOdds({ ...odds, [m.key]: e.target.value })}
                    onBlur={() => odds?.[m.key] && submitOdds(odds)}
                    onKeyDown={(e) => e.key === "Enter" && submitOdds(odds)}
                    placeholder="—"
                    className="w-16 bg-black border border-border rounded px-1.5 py-1 text-right text-xs focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent"
                  />
                </td>
                <td className={`px-3 py-2 text-right text-xs ${
                  gap == null ? "text-muted-foreground"
                    : gap > 0 ? "text-emerald-400" : "text-red-400"}`}
                  title={gap == null ? "Type a price to see the gap"
                    : `Model ${m.fair_odds?.toFixed(2)} · yours ${m.book_odds?.toFixed(2)}`}>
                  {gap == null ? "—" : `${gap > 0 ? "+" : ""}${gap.toFixed(2)}`}
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
      <BandKey note="Landed in = how often both teams' recent games cleared this total. Colour follows that, not the model." />
      <div className="px-3 py-2 text-[10px] text-muted-foreground leading-relaxed border-t border-border space-y-1">
        <p>
          <span className="text-foreground">Reading a row:</span> the model prices the line
          at <span className="text-foreground">Fair</span>. Type what the shop is
          offering into <span className="text-foreground">Your price</span> and the gap
          and EV fill in. +5% EV means that for every £10 staked, the model reckons you
          are getting £10.50 of value — over one bet that is nothing, over a season it is
          the whole game.
        </p>
        <p>
          <span className="text-foreground">Check it against Landed.</span> The model
          prices totals off a Poisson fitted to both sides' corner rates, which assumes
          less variation between games than corners really show — so it can be short on
          the extreme lines at either end. Where the model and the hit rate disagree
          sharply, trust neither and look at the fixture.
        </p>
        <p>
          Landed counts both sides' recent games equally and takes no account of who they
          played. It is a form guide, not a forecast.
        </p>
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
      <div className="overflow-x-auto">
      <table className="w-full">
        <thead>
          <tr className="border-b border-border text-muted-foreground text-[10px] uppercase tracking-wider">
            <th className="text-left font-medium px-2 py-2 sm:px-4">Window</th>
            <th className="text-right font-medium px-2 py-2 sm:px-4">Won</th>
            <th className="text-right font-medium px-2 py-2 sm:px-4">Conceded</th>
            <th className="text-right font-medium px-2 py-2 sm:px-4">Total /g</th>
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
      </div>

      <ShotBlock feats={team.features?.[split]} intent={team.intent?.[split]}
        highlight={highlight} split={split} />

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
      <div className="overflow-x-auto">
      <table className="w-full">
        <thead>
          <tr className="border-b border-border text-muted-foreground text-[10px] uppercase tracking-wider">
            <th className="text-left font-medium px-2 py-1.5 sm:px-4">Date</th>
            <th className="text-left font-medium px-2 py-1.5 sm:px-4">Opponent</th>
            <th className="text-center font-medium px-2 py-1.5">V</th>
            <th className="text-right font-medium px-2 py-1.5 sm:px-4" title="Corners won">Won</th>
            <th className="text-right font-medium px-2 py-1.5 sm:px-4" title="Corners conceded">Conc</th>
            <th className="text-right font-medium px-2 py-1.5 sm:px-4">Total</th>
            <th className="text-center font-medium px-2 py-1.5" title="Final score (goals for-against)">Score</th>
            <th className="text-center font-medium px-2 py-1.5 hidden sm:table-cell" title="Scored a first-half goal">FHG</th>
            <th className="text-center font-medium px-2 py-1.5 hidden sm:table-cell"
              title="Shots taken by this team vs shots faced. A high corner count against a side that concedes a lot of shots is a different signal from one earned against a solid defence.">Shots F–A</th>
            <th className="text-center font-medium px-2 py-1.5 hidden sm:table-cell"
              title="Shots on target, taken vs faced. Reported for only about half of fixtures, so a dash here means the provider didn't cover it — not that nothing was on target.">SoT F–A</th>
          </tr>
        </thead>
        <tbody className="font-mono-data text-sm" data-testid={`bd-recent-${highlight}`}>
          {games.length === 0 ? (
            <tr><td colSpan={10} className="px-4 py-4 text-center text-muted-foreground text-xs">No real games on this split</td></tr>
          ) : games.map((m, i) => (
            <tr key={i} className="border-b border-border/50 hover:bg-white/5 transition-colors duration-150">
              <td className="px-2 py-1.5 sm:px-4 text-muted-foreground text-xs whitespace-nowrap">{fmtDate(m.date)}</td>
              <td className="px-2 py-1.5 sm:px-4 text-foreground font-sans text-xs whitespace-nowrap truncate max-w-[88px] sm:max-w-[140px]">{m.opponent}</td>
              <td className="px-2 py-1.5 text-center">
                <span className={`text-[9px] px-1 py-0.5 rounded ${m.home ? "bg-primary/15 text-primary" : "bg-zinc-500/15 text-zinc-400"}`}>{m.home ? "H" : "A"}</span>
              </td>
              <td className="px-2 py-1.5 sm:px-4 text-right text-emerald-400 font-semibold">{m.won}</td>
              <td className="px-2 py-1.5 sm:px-4 text-right text-red-400">{m.conceded}</td>
              <td className="px-2 py-1.5 sm:px-4 text-right text-foreground">{m.total}</td>
              <td className={`px-2 py-1.5 text-center text-xs font-semibold ${m.gf != null ? resultTone(m) : "text-muted-foreground"}`}
                title={scorerNote(m)}>
                {m.gf != null ? `${m.gf}-${m.ga}` : "—"}
                {m.minutes_trailing > 0 && (
                  <span className="ml-1 text-[9px] text-amber-400 font-normal"
                    title={`Spent ${m.minutes_trailing} minutes behind`}>{m.minutes_trailing}'</span>
                )}
              </td>
              <td className="px-2 py-1.5 text-center text-xs hidden sm:table-cell">
                {m.fh == null ? <span className="text-muted-foreground">—</span>
                  : m.fh ? <span className="text-emerald-400">✓</span>
                  : <span className="text-zinc-600">·</span>}
              </td>
              <td className="px-2 py-1.5 text-center text-xs hidden sm:table-cell">
                {m.shots_for == null && m.shots_against == null ? (
                  <span className="text-muted-foreground">—</span>
                ) : (
                  <span title={m.blocked_shots_for != null
                    ? `${m.blocked_shots_for} blocked`
                    : "blocked-shot detail not reported for this fixture"}>
                    <span className="text-foreground">{m.shots_for ?? "?"}</span>
                    <span className="text-muted-foreground">–</span>
                    <span className="text-muted-foreground">{m.shots_against ?? "?"}</span>
                  </span>
                )}
              </td>
              <td className="px-2 py-1.5 text-center text-xs hidden sm:table-cell">
                {m.shots_on_target_for == null && m.shots_on_target_against == null ? (
                  <span className="text-muted-foreground" title="not reported for this fixture">—</span>
                ) : (
                  <span>
                    <span className="text-foreground">{m.shots_on_target_for ?? "?"}</span>
                    <span className="text-muted-foreground">–</span>
                    <span className="text-muted-foreground">{m.shots_on_target_against ?? "?"}</span>
                  </span>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      </div>
      <GoalDetail profile={team.goal_profile?.[split]} highlight={highlight} split={split} />
    </div>
  );
}

// Shot volume, and the intent term the LIVE model derives from it. The backend builds
// `intent` with the same call pricing makes, so this panel cannot describe one thing
// while the price does another — including which branch fired (v3 blocked shots, or the
// v2 shots fallback for a team without enough blocked history).
const SHOT_COLS = [
  ["shots", "Shots"],
  ["shots_on_target", "On target"],
  ["blocked_shots", "Blocked"],
  // dangerous_attacks is deliberately absent: the provider returns it empty for these
  // leagues (0/40 on the coverage check), so a column for it would only ever read "—"
];

function ShotBlock({ feats, intent, highlight, split }) {
  if (!feats) return null;
  const covered = feats.covered?.shots ?? 0;
  if (!covered) {
    return (
      <div className="px-4 py-2.5 border-t border-border text-[11px] text-muted-foreground"
        data-testid={`bd-shots-empty-${highlight}`}>
        No shot data on this split yet — run the shots backfill in Tools.
      </div>
    );
  }
  const pct = intent ? (intent.multiplier * intent.form - 1) * 100 : 0;
  const dir = pct >= 0.05 ? "lifts" : pct <= -0.05 ? "cuts" : "leaves";
  const tone = pct >= 0.05 ? "text-emerald-400" : pct <= -0.05 ? "text-red-400" : "text-muted-foreground";
  return (
    <div className="px-4 py-3 border-t border-border space-y-2.5" data-testid={`bd-shots-${highlight}`}>
      <div className="flex items-center gap-2">
        <span className="text-[10px] uppercase tracking-wider text-muted-foreground flex-1">
          Shot volume ({split})
        </span>
        <span className="text-[10px] text-muted-foreground font-mono-data"
          title="Games on this split that actually carry the stat">
          {covered}/{feats.played} covered
        </span>
      </div>

      <div className="flex flex-wrap gap-2">
        {SHOT_COLS.map(([key, label]) => (
          <Metric key={key} label={label}
            value={feats[`${key}_for`] != null ? feats[`${key}_for`].toFixed(1) : "—"}
            accent={key === "blocked_shots" && intent?.source === "blocked"} />
        ))}
      </div>

      {intent && (
        <div className="rounded-md border border-border bg-secondary/50 px-3 py-2"
          data-testid={`bd-intent-${highlight}`}>
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-[10px] uppercase tracking-wider text-muted-foreground">
              {intent.source === "blocked" ? "v3 intent · blocked shots"
                : intent.source === "shots" ? "v2 fallback · shots"
                : "no intent applied"}
            </span>
            <span className={`ml-auto font-mono-data text-sm font-semibold ${tone}`}>
              ×{(intent.multiplier * intent.form).toFixed(3)}
            </span>
          </div>
          <p className="text-[11px] text-muted-foreground mt-1">
            {intent.source === "none" ? (
              <>Not enough history to move this team's λ — it prices at the raw corner average.</>
            ) : (
              <>
                <span className="font-mono-data text-foreground">{intent.value?.toFixed(2)}</span>
                {" vs league "}
                <span className="font-mono-data text-foreground">{intent.league_avg?.toFixed(2)}</span>
                {" at weight "}
                <span className="font-mono-data">{intent.weight}</span>
                {" — "}
                {dir === "leaves" ? "leaves λ where it is" : (
                  <>{dir} λ by <span className={`font-mono-data ${tone}`}>{Math.abs(pct).toFixed(1)}%</span></>
                )}
              </>
            )}
          </p>
          {intent.reason && (
            <p className="text-[10px] text-amber-400/80 mt-1">Why not v3: {intent.reason}</p>
          )}
        </div>
      )}
    </div>
  );
}

// Scorers and minutes come from /fixtures/events, which the goal backfill fills in.
// Matches it hasn't reached carry no goal keys at all — those read as "not covered"
// rather than as zero, because "never trailed" and "we don't know" are not the same claim.
function scorerNote(m) {
  if (!m.scorers?.length) return undefined;
  return m.scorers.map((g) => `${g.minute}' ${g.player || "?"}${g.kind === "Own Goal" ? " (og)" : ""}`).join(", ");
}

function GoalDetail({ profile, highlight, split }) {
  if (!profile || !profile.games) {
    return (
      <div className="px-4 py-2.5 border-t border-border text-[11px] text-muted-foreground"
        data-testid={`bd-goals-empty-${highlight}`}>
        No goal detail on this split yet — run the goal backfill in Tools to fill scorers and minutes.
      </div>
    );
  }
  const { minutes, first_goal: fg, windows, scorers, games, played } = profile;
  const peak = Math.max(1, ...Object.values(windows));
  return (
    <div className="px-4 py-3 border-t border-border space-y-3" data-testid={`bd-goals-${highlight}`}>
      <div className="flex items-center gap-2">
        <span className="text-[10px] uppercase tracking-wider text-muted-foreground flex-1">
          Goal detail ({split})
        </span>
        <span className="text-[10px] text-muted-foreground font-mono-data"
          title="Matches the goal backfill has reached, out of matches played on this split">
          {games}/{played} covered
        </span>
      </div>

      <div className="flex flex-wrap gap-2">
        <GoalChip label={`${minutes.trailing}′ behind/g`} strong={minutes.trailing >= 30} />
        <GoalChip label={`${minutes.leading}′ ahead/g`} strong={minutes.leading >= 30} />
        {fg.scored_first_pct != null && (
          <GoalChip label={`Scored first ${fg.scored_first_pct}%`} strong={fg.scored_first_pct >= 60} />
        )}
        {fg.avg_first_scored_min != null && (
          <GoalChip label={`1st goal ${fg.avg_first_scored_min}′`} strong={fg.avg_first_scored_min <= 30} />
        )}
        {fg.avg_first_conceded_min != null && (
          <GoalChip label={`1st conceded ${fg.avg_first_conceded_min}′`} strong={fg.avg_first_conceded_min >= 55} />
        )}
      </div>

      <div>
        <p className="text-[10px] uppercase tracking-wider text-muted-foreground mb-1">When they score</p>
        <div className="flex items-end gap-1 h-12">
          {Object.entries(windows).map(([label, n]) => (
            <div key={label} className="flex-1 flex flex-col items-center gap-0.5" title={`${n} goals, ${label} min`}>
              <div className="w-full rounded-t bg-primary/60" style={{ height: `${(n / peak) * 100}%` }} />
              <span className="text-[8px] text-muted-foreground whitespace-nowrap">{label}</span>
            </div>
          ))}
        </div>
      </div>

      {scorers.length > 0 && (
        <div>
          <p className="text-[10px] uppercase tracking-wider text-muted-foreground mb-1">Scorers</p>
          <div className="flex flex-wrap gap-1.5">
            {scorers.map((s) => (
              <span key={s.player} title={`${s.minutes.filter((x) => x != null).join("′, ")}′`}
                className="text-[11px] px-2 py-0.5 rounded border border-border bg-secondary font-sans">
                {s.player} <span className="font-mono-data text-primary">{s.goals}</span>
              </span>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
