import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { Flame, ArrowRight, Target, TrendingDown, History } from "lucide-react";
import { api } from "@/lib/api";
import ShareButtons from "@/components/ShareButtons";
import { flagBullet, withFlag } from "@/lib/countryFlag";
import { kickoffLabel, timesFooter } from "@/lib/kickoff";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";

const SIDES = [{ v: "home", l: "Home" }, { v: "away", l: "Away" }, { v: "overall", l: "Overall" }];
// One model, two directions: overs clear the line, unders stay below it (exact line = void).
const DIRECTIONS = [{ v: "over", l: "Over" }, { v: "under", l: "Under" }];
const SUBJECTS = [{ v: "team", l: "Team corners" }, { v: "match", l: "Match total" }];
// Ordered loosest-first: the looser presets surface more teams (good for a wide
// screenshot), the longer windows demand more history and return fewer but
// better-evidenced runs. A team needs at least `window` real games to appear at all.
const PRESETS = [
  { v: "4-5", l: "4 / 5", window: 5, min_hits: 4 },
  { v: "5-5", l: "5 / 5", window: 5, min_hits: 5 },
  { v: "7-10", l: "7 / 10", window: 10, min_hits: 7 },
  { v: "8-10", l: "8 / 10", window: 10, min_hits: 8 },
  { v: "9-10", l: "9 / 10", window: 10, min_hits: 9 },
  { v: "10-10", l: "10 / 10", window: 10, min_hits: 10 },
  { v: "11-15", l: "11 / 15", window: 15, min_hits: 11 },
  { v: "15-20", l: "15 / 20", window: 20, min_hits: 15 },
];
const TIMEFRAMES = [
  { v: "all", l: "Any upcoming" },
  { v: "3", l: "Next 3 days" },
  { v: "7", l: "Next 7 days" },
  { v: "14", l: "Next 14 days" },
  { v: "21", l: "Next 21 days" },
  { v: "30", l: "Next 30 days" },
];
// Laddered lines per direction/subject — team corners run far lower than match totals.
const LADDERS = {
  "over-team": [3, 4, 5, 6, 7],
  "over-match": [8, 9, 10, 11, 12, 13],
  "under-team": [3, 4, 5, 6, 7, 8],
  "under-match": [8, 9, 10, 11, 12],
};
const MIN_LINE = { team: 3, match: 7 };

const lineLabel = (line, direction) => (direction === "under" ? `U ${line}` : `${line}+`);
const fmtDate = (d) => (d ? new Date(d).toLocaleDateString(undefined, { month: "short", day: "numeric" }) : "");

// Global cross-league corner streak finder: overs and unders, team corners or match totals.
export default function StreakFinder({ leagueId }) {
  const navigate = useNavigate();
  const [scope, setScope] = useState("all");
  const [side, setSide] = useState("home");
  const [direction, setDirection] = useState("over");
  const [subject, setSubject] = useState("team");
  const [preset, setPreset] = useState("5-5");
  const [threshold, setThreshold] = useState("auto");
  const [days, setDays] = useState("all");
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);

  const ladder = LADDERS[`${direction}-${subject}`] || [];
  const isUnder = direction === "under";

  // a line from the previous ladder is meaningless on the new one
  const switchTo = (setter) => (v) => { setter(v); setThreshold("auto"); };

  useEffect(() => {
    const p = PRESETS.find((x) => x.v === preset);
    const params = {
      league_id: scope === "current" ? leagueId : "all",
      side, window: p.window, min_hits: p.min_hits, direction, subject,
    };
    if (!isUnder) params.min_line = MIN_LINE[subject];
    if (threshold !== "auto") params.threshold = threshold;
    if (days !== "all") params.within_days = days;
    setLoading(true);
    api.streaks(params).then(setRows).catch(() => setRows([])).finally(() => setLoading(false));
  }, [scope, side, direction, subject, preset, threshold, days, leagueId, isUnder]);

  // COLOUR MEANS QUALITY, NOT DIRECTION — matching the fixture board and Best Bets.
  // Every row used to be the same colour whether it was 5/5 or 5/10, because the colour
  // encoded over-vs-under, which the toggle and the icon already tell you. Green now
  // means the record is solid; muted means it is thin and scrolled past.
  const SOLID = "bg-emerald-500/15 text-emerald-400 border-emerald-500/30";
  const THIN = "border-border/60 text-muted-foreground/70";
  // Solid = landed in at least 4 of every 5 SETTLED games (voids are stake-back, so they
  // are excluded from the denominator rather than counted as either).
  const isSolid = (r) => {
    const settled = r.settled ?? r.window;
    return settled > 0 && r.hits / settled >= 0.8;
  };
  const resultChip = {
    win: "bg-emerald-500/20 text-emerald-400",
    void: "bg-zinc-500/20 text-zinc-400",
    loss: "bg-red-500/15 text-red-400",
  };

  // A postable summary of what's on screen: the headline filter plus the top few runs.
  const presetMeta = PRESETS.find((x) => x.v === preset);
  const shareText = (() => {
    if (!rows.length) return "";
    const what = subject === "match" ? "match total corners" : "team corners";
    const head = `${isUnder ? "Under" : "Over"} ${what} — hit in ${presetMeta?.l || ""} `
      + `${side === "overall" ? "" : side + " "}games:`;
    const shown = rows.slice(0, 6);
    const lines = shown.map((r) => {
      const fx = r.next_fixture;
      const vs = fx ? ` ${fx.is_home ? "vs" : "@"} ${fx.opponent}` : "";
      // The kick-off closes the line rather than interrupting it: the bet is what the
      // reader is deciding about, the time is what they act on once they've decided.
      const when = kickoffLabel(fx?.date);
      // The flag replaces the bullet rather than joining it — see flagBullet.
      return `${flagBullet(r.league_id)} ${r.name} ${isUnder ? "U" : ""}${r.line}${isUnder ? "" : "+"}${vs}`
        + ` (${r.hits}/${r.window})${when ? ` · ${when}` : ""}`;
    });
    const more = rows.length > 6 ? `\n+${rows.length - 6} more on the site` : "";
    // The zone is named ONCE, not on every line — six repeats of "BST" is a third of a
    // tweet. See timesFooter for when it is dropped entirely.
    const times = timesFooter(shown.map((r) => r.next_fixture?.date));
    return `${head}\n${lines.join("\n")}${more}${times}`;
  })();

  return (
    <section className="bg-card border border-border rounded-lg" data-testid="streak-finder">
      <div className="flex flex-col lg:flex-row lg:items-center gap-3 px-2 py-2 sm:px-4 sm:py-3 border-b border-border">
        <div className="flex items-center gap-2">
          <Flame className="h-4 w-4 text-primary" />
          <h2 className="font-head font-semibold text-lg">Corner Streak Finder</h2>
          <span className="text-xs text-muted-foreground hidden sm:inline">
            {isUnder
              ? "teams staying under the line (exact line = void, streak survives)"
              : "consistent corner-winners (real games only)"}
          </span>
          {rows.length > 0 && (
            <span className="font-mono-data text-[10px] text-muted-foreground ml-1" data-testid="streak-count">
              {rows.length} shown
            </span>
          )}
        </div>
        {rows.length > 0 && <ShareButtons text={shareText} className="lg:ml-2" />}
        <div className="lg:ml-auto flex flex-wrap items-center gap-2">
          <Tabs value={direction} onValueChange={switchTo(setDirection)}>
            <TabsList className="bg-secondary h-8">
              {DIRECTIONS.map((d) => (
                <TabsTrigger key={d.v} value={d.v} data-testid={`streak-direction-${d.v}`} className="text-xs px-2.5 h-6">{d.l}</TabsTrigger>
              ))}
            </TabsList>
          </Tabs>
          <Select value={subject} onValueChange={switchTo(setSubject)}>
            <SelectTrigger data-testid="streak-subject" className="w-[140px] bg-[#121212] border-border text-xs h-8"><SelectValue /></SelectTrigger>
            <SelectContent className="bg-[#121212] border-border">
              {SUBJECTS.map((o) => <SelectItem key={o.v} value={o.v} className="text-xs">{o.l}</SelectItem>)}
            </SelectContent>
          </Select>
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
              <SelectItem value="auto" className="text-xs">Best line (auto)</SelectItem>
              {ladder.map((l) => (
                <SelectItem key={l} value={String(l)} className="text-xs">
                  {isUnder ? `Under ${l} corners` : `${l}+ corners`}
                </SelectItem>
              ))}
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

      <div className="overflow-x-auto sm:max-h-[420px] sm:overflow-y-auto">
        <table className="w-full">
          <thead className="sticky top-0 bg-card z-10">
            <tr className="border-b border-border text-muted-foreground text-xs uppercase tracking-wider">
              <th className="text-left font-medium px-2 py-1.5 sm:px-4 sm:py-2.5 sticky left-0 bg-card z-20">Team</th>
              <th className="text-left font-medium px-2 py-1.5 sm:px-4 sm:py-2.5">Line</th>
              <th className="text-left font-medium px-2 py-1.5 sm:px-4 sm:py-2.5">Hit rate</th>
              <th className="text-left font-medium px-2 py-1.5 sm:px-4 sm:py-2.5">Streak</th>
              <th className="text-left font-medium px-2 py-1.5 sm:px-4 sm:py-2.5">Longest</th>
              <th className="text-right font-medium px-2 py-1.5 sm:px-4 sm:py-2.5">Avg</th>
              <th className="text-left font-medium px-2 py-1.5 sm:px-4 sm:py-2.5 hidden md:table-cell">Recent ({side})</th>
              <th className="text-left font-medium px-2 py-1.5 sm:px-4 sm:py-2.5">Next</th>
              <th className="text-right font-medium px-2 py-1.5 sm:px-4 sm:py-2.5">{subject === "match" ? "Proj λ" : "Opp conc"}</th>
              <th className="text-right font-medium px-2 py-1.5 sm:px-4 sm:py-2.5">Model odds</th>
              <th className="text-right font-medium px-2 py-1.5 sm:px-4 sm:py-2.5">Edge</th>
              <th className="px-2 py-1.5 sm:px-4 sm:py-2.5"></th>
            </tr>
          </thead>
          <tbody className="font-mono-data text-sm">
            {loading ? (
              <tr><td colSpan={12} className="px-4 py-12 text-center text-muted-foreground animate-pulse">Scanning corner streaks…</td></tr>
            ) : rows.length === 0 ? (
              <tr><td colSpan={12} className="px-4 py-12 text-center text-muted-foreground">
                No teams match this streak. Try {isUnder ? "a higher" : "a lower"} line or a wider window.
              </td></tr>
            ) : rows.map((r) => (
              <tr
                key={r.team_id}
                data-testid="streak-row"
                onClick={() => r.next_fixture && navigate(`/fixture/${r.next_fixture.fixture_id}`)}
                className={`border-b border-border/50 transition-colors duration-150 ${r.next_fixture ? "hover:bg-white/5 cursor-pointer" : ""}`}
                style={{ borderLeft: `2px solid ${isSolid(r) ? "#10B981" : "#3F3F46"}` }}
              >
                <td className="px-2 py-1.5 sm:px-4 sm:py-2.5 sticky left-0 bg-card z-10">
                  <div className="text-foreground font-sans font-medium whitespace-nowrap">{r.name}</div>
                  <div className="text-[10px] text-muted-foreground uppercase tracking-wider font-sans">{withFlag(r.league_id, r.league_name)}</div>
                </td>
                <td className="px-2 py-1.5 sm:px-4 sm:py-2.5">
                  <span className={`inline-flex items-center gap-1 text-xs px-2 py-1 rounded border ${isSolid(r) ? SOLID : THIN}`}
                    title={`${subject === "match" ? "Match total corners" : "Team corners"} — ${
                      isSolid(r) ? "solid: landed in 4 of every 5 settled games"
                                 : "thin: under 4 in 5, so treat it as a lead rather than a signal"}`}>
                    {isUnder ? <TrendingDown className="h-3 w-3" /> : <Target className="h-3 w-3" />} {lineLabel(r.line, r.direction)}
                  </span>
                </td>
                <td className="px-2 py-1.5 sm:px-4 sm:py-2.5 whitespace-nowrap">
                  <span className={isSolid(r) ? "text-emerald-400 font-semibold" : "text-muted-foreground/70 font-semibold"}>
                    {r.hits}/{r.settled ?? r.window}
                  </span>
                  {r.voids > 0 && (
                    <span className="ml-1 text-[10px] text-zinc-400" title="Landed exactly on the line — void, streak intact">
                      +{r.voids} void
                    </span>
                  )}
                </td>
                <td className="px-2 py-1.5 sm:px-4 sm:py-2.5 whitespace-nowrap">
                  {r.streak && r.streak.length > 0 ? (
                    <>
                      <span className="text-foreground font-semibold">{r.streak.length}</span>
                      <span className="ml-1 text-[10px] text-muted-foreground font-sans">
                        since {fmtDate(r.streak.start_date)}
                      </span>
                    </>
                  ) : (
                    <span className="text-muted-foreground" title="Broken — the latest game missed this line">0</span>
                  )}
                </td>
                <td className="px-2 py-1.5 sm:px-4 sm:py-2.5 whitespace-nowrap">
                  {r.longest ? (
                    <span className={r.longest.is_current ? "text-foreground" : "text-muted-foreground"}
                      title={r.longest.is_current
                        ? "This run is the team's longest on record"
                        : `Best run: ${fmtDate(r.longest.start_date)} – ${fmtDate(r.longest.end_date)}`}>
                      <History className="h-3 w-3 inline mr-1 opacity-60" />{r.longest.length}
                      {r.longest.is_current && <span className="ml-1 text-[10px] text-amber-400 font-sans">best ever</span>}
                    </span>
                  ) : <span className="text-muted-foreground">—</span>}
                </td>
                <td className="px-2 py-1.5 sm:px-4 sm:py-2.5 text-right text-foreground">{r.avg.toFixed(1)}</td>
                <td className="px-2 py-1.5 sm:px-4 sm:py-2.5 hidden md:table-cell">
                  <div className="flex gap-1">
                    {r.recent.map((m, i) => (
                      <span key={i} title={`${m.corners} vs ${m.opponent}${m.result === "void" ? " — void (exact line)" : ""}`}
                        className={`inline-flex h-5 min-w-5 px-1 items-center justify-center rounded text-[10px] ${resultChip[m.result] || resultChip.loss}`}>
                        {m.corners}
                      </span>
                    ))}
                  </div>
                </td>
                <td className="px-2 py-1.5 sm:px-4 sm:py-2.5 text-xs text-muted-foreground whitespace-nowrap">
                  {r.next_fixture ? (
                    <>
                      <div>{r.next_fixture.is_home ? "vs" : "@"} {r.next_fixture.opponent}</div>
                      {/* The kick-off, not just the date: at 6pm "tonight" and "started an
                          hour ago" are the same date and opposite decisions. */}
                      <div className="text-[10px] text-primary/80">{kickoffLabel(r.next_fixture.date)}</div>
                    </>
                  ) : "—"}
                </td>
                <td className="px-2 py-1.5 sm:px-4 sm:py-2.5 text-right">
                  {r.projection ? (
                    subject === "match" ? (
                      <span className="text-foreground" title="Projected match total corners">{r.projection.lambda.toFixed(1)}</span>
                    ) : (
                      <span className={isUnder
                        ? (r.projection.opp_conceded <= r.line ? "text-sky-400" : "text-muted-foreground")
                        : (r.projection.opp_conceded >= r.line ? "text-emerald-400" : "text-muted-foreground")}>
                        {r.projection.opp_conceded.toFixed(1)}
                      </span>
                    )
                  ) : <span className="text-muted-foreground">—</span>}
                </td>
                <td className="px-2 py-1.5 sm:px-4 sm:py-2.5 text-right whitespace-nowrap">
                  {r.projection && r.projection.fair_odds ? (
                    <span className="text-foreground font-semibold"
                      title={`Model: ${r.projection.prob.toFixed(1)}% to land ${lineLabel(r.line, r.direction)} (λ ${r.projection.lambda})`
                        + (r.projection.void_prob ? ` · ${r.projection.void_prob.toFixed(1)}% void` : "")}>
                      {r.projection.fair_odds.toFixed(2)}
                    </span>
                  ) : <span className="text-muted-foreground">—</span>}
                </td>
                <td className="px-2 py-1.5 sm:px-4 sm:py-2.5 text-right whitespace-nowrap">
                  {r.projection && r.projection.ev != null ? (
                    <span className={`font-semibold ${r.projection.ev >= 5 ? "text-emerald-400" : r.projection.ev >= 0 ? "text-amber-400" : "text-red-400"}`}
                      title={`Book ${r.projection.book_odds} vs model ${r.projection.fair_odds}`}>
                      {r.projection.ev > 0 ? "+" : ""}{r.projection.ev.toFixed(1)}%
                    </span>
                  ) : <span className="text-muted-foreground" title={`Paste ${r.projection?.market_key || "this"} odds on the fixture page`}>—</span>}
                </td>
                <td className="px-2 py-1.5 sm:px-4 sm:py-2.5 text-right">{r.next_fixture && <ArrowRight className="h-4 w-4 text-muted-foreground inline" />}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
