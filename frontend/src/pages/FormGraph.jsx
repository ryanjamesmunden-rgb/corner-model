import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { Activity, BellRing, ChevronLeft, ChevronRight, Eye, Loader2 } from "lucide-react";
import {
  CartesianGrid, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { useLeague } from "@/context/LeagueContext";
import { withFlag } from "@/lib/countryFlag";
import { METRICS, VENUES, WINDOWS } from "@/lib/teamForm";
import { SERIES_COLOURS, chartRows, pages, teamSummary, PAGE_SIZE } from "@/lib/formLines";
import TrackingAdvice, { FLAGS, NextFixtures } from "@/components/TrackingAdvice";

// FORM — every team you care about on one line chart, ten at a time.
//
// Three lists: FAVOURITES (the bell), TRACKING (the eye — a trial list, for sides you are
// watching before you trust them) and any LEAGUE. Lines are aligned on each team's latest
// game, so the right edge is "now" for everyone. Switch to "vs avg" and each line is drawn
// against that team's own average: above zero they over-performed, below they under-did,
// and the tooltip says who against.
//
// Ten lines per page is the cap: past that they knot together. Tap a team's chip (or its
// line) to bring it forward and see its best and worst games; tap again to let go.

const SOURCES = [
  { key: "favourites", label: "Favourites", icon: BellRing },
  { key: "tracking", label: "Tracking", icon: Eye },
  { key: "league", label: "League", icon: Activity },
];
const MODES = [{ key: "raw", label: "Corners" }, { key: "diff", label: "vs avg" }];

const shortDate = (iso) => {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? "" : d.toLocaleDateString(undefined, { day: "numeric", month: "short" });
};
const signed = (x) => (x > 0 ? `+${x}` : `${x}`);

function Seg({ options, value, onChange, testId }) {
  return (
    <div className="flex rounded-md bg-secondary p-0.5" data-testid={testId}>
      {options.map((o) => {
        const Icon = o.icon;
        return (
          <button key={o.key} type="button" onClick={() => onChange(o.key)}
            data-testid={`${testId}-${o.key}`} aria-pressed={value === o.key}
            className={`flex items-center gap-1 text-[11px] px-2 py-1 rounded transition-colors ${
              value === o.key ? "bg-primary text-primary-foreground font-medium" : "text-muted-foreground"}`}>
            {Icon && <Icon className="h-3 w-3" />}{o.label}
          </button>
        );
      })}
    </div>
  );
}

// The hover readout, drawn UNDER the chart rather than floating over it: ten rows of a
// floating box cover a phone-width chart entirely. Focused team only, when one is focused.
function Readout({ row, onPage, colourOf, mode, metric, focus }) {
  if (!row) {
    return (
      <p className="text-[11px] text-muted-foreground mt-2 min-h-[2rem]">
        Hover or tap along the chart to see each team's game — who against and how many.
      </p>
    );
  }
  const items = onPage
    .map((t, i) => ({ t, i, value: row[t.team_id], g: row[`${t.team_id}__g`] }))
    .filter((x) => x.value != null && (!focus || x.t.team_id === focus))
    .sort((a, b) => b.value - a.value);
  return (
    <div className="mt-2 text-[11px] min-h-[2rem]" data-testid="fg-readout">
      <p className="text-muted-foreground mb-1">
        {row.ago === 1 ? "Most recent game" : `${row.ago - 1} game${row.ago === 2 ? "" : "s"} before the latest`}
      </p>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-x-4">
        {items.map(({ t, i, value, g }) => (
          <div key={t.team_id} className="flex items-center gap-1.5 py-0.5 min-w-0">
            <span className="h-2 w-2 rounded-full shrink-0" style={{ background: colourOf(i) }} />
            <span className="text-foreground truncate">{t.name}</span>
            <span className="text-muted-foreground truncate">
              {g ? `${g.home ? "v" : "@"} ${g.opponent}` : ""}
            </span>
            <span className="ml-auto font-mono-data text-foreground pl-2 whitespace-nowrap">
              {mode === "diff" ? `${signed(value)} (${g?.[metric]})` : value}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

export default function FormGraph() {
  const { user, ready, setStarredTeam, setTrackedTeam } = useAuth();
  const { leagueId: defaultLeague, leagues } = useLeague();
  const [source, setSource] = useState("favourites");
  const [leagueId, setLeagueId] = useState(defaultLeague);
  const [data, setData] = useState(null);
  const [venue, setVenue] = useState("all");
  const [win, setWin] = useState(10);
  const [metric, setMetric] = useState("won");
  const [mode, setMode] = useState("raw");
  const [page, setPage] = useState(0);
  const [focus, setFocus] = useState(null);
  const [reload, setReload] = useState(0);
  const [hoverAgo, setHoverAgo] = useState(null);
  const [advice, setAdvice] = useState(null);
  const [pendingFocus, setPendingFocus] = useState(null);

  // Start / stop tracking prompts. Loaded once per change to the lists, not per toggle.
  useEffect(() => {
    if (!ready) return;
    let alive = true;
    api.trackingSuggestions().then((d) => alive && setAdvice(d)).catch(() => alive && setAdvice(null));
    return () => { alive = false; };
  }, [ready, user, reload]);

  // Signed out, the personal lists are empty, so start them on a league instead.
  useEffect(() => { if (ready && !user) setSource("league"); }, [ready, user]);
  useEffect(() => { if (!leagueId && defaultLeague) setLeagueId(defaultLeague); }, [defaultLeague, leagueId]);

  useEffect(() => {
    if (!ready) return;
    let alive = true;
    setData(null); setPage(0); setFocus(null); setHoverAgo(null);
    api.teamForm(source, source === "league" ? leagueId : undefined)
      .then((d) => alive && setData(d))
      .catch(() => alive && setData({ teams: [], error: true }));
    return () => { alive = false; };
  }, [ready, source, leagueId, reload]);

  const teams = useMemo(() => data?.teams || [], [data]);

  // A "heads up" row was tapped: once its list has loaded, page to the team and focus it.
  useEffect(() => {
    if (!pendingFocus || !teams.length) return;
    const i = teams.findIndex((t) => t.team_id === pendingFocus);
    if (i >= 0) { setPage(Math.floor(i / PAGE_SIZE)); setFocus(pendingFocus); }
    setPendingFocus(null);
  }, [pendingFocus, teams]);
  const focusFromAdvice = (o) => {
    if (o.list && o.list !== source) setSource(o.list);
    setPendingFocus(o.team_id);
  };
  const outlookOf = (tid) => advice?.watched?.[tid] || (advice?.suggestions || []).find((o) => o.team_id === tid);
  const pageList = useMemo(() => pages(teams), [teams]);
  const onPage = useMemo(() => pageList[page] || [], [pageList, page]);
  const opts = useMemo(() => ({ venue, window: win, metric, mode }), [venue, win, metric, mode]);
  const rows = useMemo(() => chartRows(onPage, opts), [onPage, opts]);
  const colourOf = (i) => SERIES_COLOURS[i % SERIES_COLOURS.length];
  const focused = onPage.find((t) => t.team_id === focus);
  const summary = focused ? teamSummary(focused, opts) : null;

  // Where tracking started, for the focused team: the first slot on or after the date.
  const trackedSlot = useMemo(() => {
    if (!focused?.tracked_at) return null;
    const cut = String(focused.tracked_at).slice(0, 10);
    const row = rows.find((r) => r[`${focused.team_id}__g`]
      && String(r[`${focused.team_id}__g`].date).slice(0, 10) >= cut);
    return row ? row.ago : null;
  }, [focused, rows]);

  const promote = async (t) => {
    try {
      await api.promoteTrackedTeam(t.team_id);
      setStarredTeam(t.team_id, true);
      setTrackedTeam(t.team_id, false);
      toast.success(`${t.name} moved to favourites`);
      setReload((n) => n + 1);
    } catch { toast.error("Couldn't move that team"); }
  };
  const untrack = async (t) => {
    try {
      await api.removeTrackedTeam(t.team_id);
      setTrackedTeam(t.team_id, false);
      setReload((n) => n + 1);
    } catch { toast.error("Couldn't stop tracking that team"); }
  };

  if (!ready) return null;
  const personal = source !== "league";
  const metricWord = metric === "won" ? "won" : metric === "conceded" ? "conceded" : "in the match";

  return (
    <div className="space-y-3 sm:space-y-4" data-testid="form-page">
      <div>
        <div className="flex items-center gap-2 text-primary mb-1">
          <Activity className="h-4 w-4" />
          <span className="font-mono-data text-xs tracking-widest uppercase">Form</span>
        </div>
        <h1 className="font-head text-3xl font-bold tracking-tight">Corner form</h1>
        <p className="text-muted-foreground text-sm mt-1">
          Each line is a team's last games, newest on the right. Switch to <b>vs avg</b> to see
          when they over- and under-performed their own average — hover or tap for who against.
        </p>
      </div>

      {/* Filters, one row above the chart. */}
      <div className="flex flex-wrap items-center gap-1.5">
        <Seg testId="fg-source" options={SOURCES} value={source} onChange={setSource} />
        {source === "league" && (
          <select value={leagueId || ""} onChange={(e) => setLeagueId(e.target.value)}
            data-testid="fg-league"
            className="bg-secondary border border-border rounded-md text-[11px] px-2 py-1.5 text-foreground max-w-[200px]">
            {leagues.map((l) => (
              <option key={l.league_id} value={l.league_id}>{withFlag(l.league_id, l.name)}</option>
            ))}
          </select>
        )}
      </div>
      <div className="flex flex-wrap items-center gap-1.5">
        <Seg testId="fg-venue" options={VENUES} value={venue} onChange={setVenue} />
        <Seg testId="fg-window" options={WINDOWS.map((n) => ({ key: n, label: `L${n}` }))}
          value={win} onChange={setWin} />
        <Seg testId="fg-metric" options={METRICS} value={metric} onChange={setMetric} />
        <Seg testId="fg-mode" options={MODES} value={mode} onChange={setMode} />
      </div>

      <section className="bg-card border border-border rounded-lg p-3 sm:p-4" data-testid="fg-chart">
        {data === null ? (
          <div className="h-64 flex items-center justify-center text-xs text-muted-foreground gap-2">
            <Loader2 className="h-4 w-4 animate-spin" /> Loading form…
          </div>
        ) : personal && !data.signed_in ? (
          <p className="py-16 text-center text-sm text-muted-foreground" data-testid="fg-signed-out">
            Sign in to see your {source}. Signing in is free and in the top right.
          </p>
        ) : teams.length === 0 ? (
          <div className="py-14 text-center text-sm text-muted-foreground max-w-sm mx-auto" data-testid="fg-empty">
            {source === "tracking" ? (
              <>Nobody tracked yet. Tap the <Eye className="inline h-3.5 w-3.5 text-amber-400" /> next
                to any team to keep an eye on them here before making them a favourite.</>
            ) : source === "favourites" ? (
              <>No favourites yet. Tap the <BellRing className="inline h-3.5 w-3.5 text-primary" /> next
                to a team, or track them first with the <Eye className="inline h-3.5 w-3.5" />.</>
            ) : data.error ? "Couldn't load that league." : "No played games on file for that league yet."}
            {" "}<Link to="/" className="text-primary hover:underline">Find teams</Link>
          </div>
        ) : (
          <>
            {/* Legend chips: tap to bring a team forward. Always present, so identity never
                rests on colour alone. */}
            <div className="flex flex-wrap gap-1.5 mb-3" data-testid="fg-legend">
              {onPage.map((t, i) => (
                <button key={t.team_id} type="button" onClick={() => setFocus(focus === t.team_id ? null : t.team_id)}
                  data-testid="fg-chip" aria-pressed={focus === t.team_id}
                  className={`flex items-center gap-1.5 text-[11px] px-2 py-1 rounded-full border transition-opacity ${
                    focus === t.team_id ? "border-foreground/50 bg-white/5" : "border-border"} ${
                    focus && focus !== t.team_id ? "opacity-40" : ""}`}>
                  <span className="h-2.5 w-2.5 rounded-full" style={{ background: colourOf(i) }} />
                  <span className="text-foreground">{t.name}</span>
                  {t.tracked_at && <Eye className="h-3 w-3 text-amber-400" />}
                  {(() => {
                    const f = FLAGS[advice?.watched?.[t.team_id]?.flag];
                    if (!f) return null;
                    const I = f.icon;
                    return <I className={`h-3 w-3 ${f.tone}`} aria-label={f.text} />;
                  })()}
                </button>
              ))}
            </div>

            <div className="h-72 sm:h-80 -ml-2" role="img"
              aria-label={`Corners ${metricWord} for ${onPage.length} teams over their last ${win} games`}>
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={rows} margin={{ top: 8, right: 12, bottom: 4, left: 0 }}
                  onMouseMove={(st) => {
                    const r = st?.activeLabel != null ? st.activeLabel
                      : (st?.activeTooltipIndex != null ? rows[st.activeTooltipIndex]?.ago : null);
                    if (r != null) setHoverAgo(Number(r));
                  }}
                  onClick={(st) => {
                    const r = st?.activeLabel ?? rows[st?.activeTooltipIndex]?.ago;
                    if (r != null) setHoverAgo(Number(r));
                  }}>
                  <CartesianGrid stroke="currentColor" className="text-border" strokeOpacity={0.5} vertical={false} />
                  <XAxis dataKey="ago" reversed={false} tick={{ fontSize: 10, fill: "#8b95a5" }}
                    tickLine={false} axisLine={false}
                    tickFormatter={(a) => (a === 1 ? "Latest" : `-${a - 1}`)} interval="preserveStartEnd" />
                  <YAxis width={28} tick={{ fontSize: 10, fill: "#8b95a5" }} tickLine={false} axisLine={false}
                    allowDecimals={mode === "diff"} />
                  {mode === "diff" && <ReferenceLine y={0} stroke="#8b95a5" strokeDasharray="4 3" />}
                  {trackedSlot != null && (
                    <ReferenceLine x={trackedSlot} stroke="#f59e0b" strokeDasharray="3 3"
                      label={{ value: "tracked", fill: "#f59e0b", fontSize: 10, position: "insideTopRight" }} />
                  )}
                  {/* No floating box — the readout under the chart says what is here. */}
                  <Tooltip content={() => null} cursor={{ stroke: "#8b95a5", strokeOpacity: 0.5 }} />
                  {onPage.map((t, i) => {
                    const dim = focus && focus !== t.team_id;
                    return (
                      <Line key={t.team_id} type="linear" dataKey={t.team_id} name={t.name}
                        stroke={colourOf(i)} strokeWidth={focus === t.team_id ? 3 : 2}
                        strokeOpacity={dim ? 0.12 : 1} connectNulls={false} isAnimationActive={false}
                        dot={false} activeDot={dim ? false : { r: 4, strokeWidth: 2, stroke: "#11161d" }}
                        onClick={() => setFocus(focus === t.team_id ? null : t.team_id)} />
                    );
                  })}
                </LineChart>
              </ResponsiveContainer>
            </div>
            <Readout row={rows.find((r) => r.ago === hoverAgo)} onPage={onPage} colourOf={colourOf}
              mode={mode} metric={metric} focus={focus} />
            <p className="text-[10px] text-muted-foreground mt-2">
              {mode === "diff"
                ? `Corners ${metricWord} minus each team's own average over the games shown. 0 = their normal.`
                : `Corners ${metricWord} per game.`}
              {" "}Games ago, latest on the right. Tap a team to focus it.
            </p>

            {pageList.length > 1 && (
              <div className="flex items-center justify-center gap-3 mt-3" data-testid="fg-pages">
                <button type="button" disabled={page === 0} onClick={() => { setPage(page - 1); setFocus(null); setHoverAgo(null); }}
                  className="p-1.5 rounded border border-border disabled:opacity-30" aria-label="Previous ten">
                  <ChevronLeft className="h-4 w-4" />
                </button>
                <span className="text-xs text-muted-foreground font-mono-data">
                  {page * 10 + 1}–{page * 10 + onPage.length} of {teams.length}
                </span>
                <button type="button" disabled={page >= pageList.length - 1}
                  onClick={() => { setPage(page + 1); setFocus(null); setHoverAgo(null); }}
                  className="p-1.5 rounded border border-border disabled:opacity-30" aria-label="Next ten">
                  <ChevronRight className="h-4 w-4" />
                </button>
              </div>
            )}
          </>
        )}
      </section>

      {summary && focused && (
        <section className="bg-card border border-border rounded-lg p-3 sm:p-4" data-testid="fg-focus">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="h-3 w-3 rounded-full"
              style={{ background: colourOf(onPage.indexOf(focused)) }} />
            <h2 className="font-head font-semibold">{focused.name}</h2>
            <span className="text-[10px] text-muted-foreground uppercase tracking-wider">
              {withFlag(focused.league_id, focused.league_name)}
            </span>
            {source === "tracking" && (
              <span className="ml-auto flex gap-1.5">
                <button type="button" onClick={() => promote(focused)} data-testid="fg-promote"
                  className="flex items-center gap-1 text-[11px] px-2 py-1 rounded bg-primary text-primary-foreground">
                  <BellRing className="h-3 w-3" /> Move to favourites
                </button>
                <button type="button" onClick={() => untrack(focused)} data-testid="fg-untrack"
                  className="text-[11px] px-2 py-1 rounded border border-border text-muted-foreground">
                  Stop tracking
                </button>
              </span>
            )}
          </div>

          <div className="grid grid-cols-3 gap-3 mt-3">
            <div>
              <p className="font-mono-data text-xl text-foreground">{summary.avg?.toFixed(2)}</p>
              <p className="text-[10px] text-muted-foreground">avg {metricWord} · last {summary.n}</p>
            </div>
            <div>
              <p className="font-mono-data text-xl text-foreground">{summary.over} / {summary.under}</p>
              <p className="text-[10px] text-muted-foreground">games above / below avg</p>
            </div>
            {summary.since ? (
              <div data-testid="fg-since">
                <p className="font-mono-data text-xl text-foreground">
                  {summary.since.avg != null ? summary.since.avg.toFixed(2) : "–"}
                </p>
                <p className="text-[10px] text-muted-foreground">
                  since tracking ({summary.since.games} game{summary.since.games === 1 ? "" : "s"})
                  {summary.since.before_avg != null ? ` · ${summary.since.before_avg.toFixed(2)} before` : ""}
                </p>
              </div>
            ) : <div />}
          </div>

          {(() => {
            const o = outlookOf(focused.team_id);
            if (!o) return null;
            const f = FLAGS[o.flag];
            return (
              <div className="mt-3" data-testid="fg-outlook">
                {f && (
                  <p className={`text-[12px] mb-1 ${f.tone}`}>
                    <b>{f.text}.</b> <span className="text-muted-foreground">{f.say}</span>
                  </p>
                )}
                <p className="text-[10px] text-muted-foreground uppercase tracking-wider mb-0.5">Next fixtures</p>
                <NextFixtures games={o.next} />
              </div>
            );
          })()}

          <div className="mt-3 space-y-1 text-[12px]">
            {summary.best && (
              <p>
                <span className="text-muted-foreground">Best:</span>{" "}
                <span className="font-mono-data">{summary.best.value}</span>{" "}
                ({signed(summary.best.diff)}) {summary.best.home ? "v" : "@"} {summary.best.opponent}
                <span className="text-muted-foreground"> · {shortDate(summary.best.date)}</span>
              </p>
            )}
            {summary.worst && (
              <p>
                <span className="text-muted-foreground">Worst:</span>{" "}
                <span className="font-mono-data">{summary.worst.value}</span>{" "}
                ({signed(summary.worst.diff)}) {summary.worst.home ? "v" : "@"} {summary.worst.opponent}
                <span className="text-muted-foreground"> · {shortDate(summary.worst.date)}</span>
              </p>
            )}
          </div>
        </section>
      )}
      <TrackingAdvice data={advice} onFocus={focusFromAdvice} />
    </div>
  );
}
