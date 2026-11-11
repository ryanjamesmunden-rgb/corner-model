import { useMemo, useState } from "react";
import { METRICS, VENUES, WINDOWS, defaultLine, formView } from "@/lib/teamForm";

// A followed team's corner form, one bar per game, oldest on the left.
//
// Flick between All / Home / Away, last 5 / 10 / 20, and corners Won / Conceded / Match
// total. Bars that cleared the chosen line are cyan, misses are slate — the same "in the
// bet / out of it" split the probability chart uses — and the split is also written out
// as "7 of 10 at 5+", so it never rests on colour alone.
//
// All slicing happens here from the twenty games the endpoint already sent, so the
// toggles are instant and cost no request.

const short = (iso) => {
  const d = new Date(iso);
  return Number.isNaN(d.getTime())
    ? ""
    : d.toLocaleDateString(undefined, { day: "numeric", month: "short" });
};

function Seg({ options, value, onChange, testId }) {
  return (
    <div className="flex rounded-md bg-secondary p-0.5" data-testid={testId}>
      {options.map((o) => (
        <button key={o.key} type="button" onClick={() => onChange(o.key)}
          data-testid={`${testId}-${o.key}`} aria-pressed={value === o.key}
          className={`text-[11px] px-2 py-1 rounded transition-colors ${
            value === o.key ? "bg-primary text-primary-foreground font-medium" : "text-muted-foreground"}`}>
          {o.label}
        </button>
      ))}
    </div>
  );
}

export default function TeamFormChart({ form, teamName }) {
  const [venue, setVenue] = useState("all");
  const [win, setWin] = useState(20);
  const [metric, setMetric] = useState("won");
  const [line, setLine] = useState(null);
  const [picked, setPicked] = useState(null);

  // The line follows the metric until someone picks one: 5+ makes sense for corners won,
  // nonsense for a match total.
  const base = useMemo(() => formView(form, { venue, window: win, metric }),
    [form, venue, win, metric]);
  const active = line ?? defaultLine(base.avg);
  const v = useMemo(() => formView(form, { venue, window: win, metric, line: active }),
    [form, venue, win, metric, active]);

  if (!Array.isArray(form) || form.length === 0) {
    return (
      <p className="mt-2 text-xs text-muted-foreground" data-testid="team-form-empty">
        No played games on file yet for {teamName || "this team"}.
      </p>
    );
  }

  const scaleTop = Math.max(v.peak, active || 0, 1);
  const lineOptions = [];
  if (active != null) {
    for (let l = Math.max(1, active - 2); l <= active + 2; l += 1) lineOptions.push(l);
  }
  const shown = picked != null ? v.games[picked] : null;
  const metricWord = metric === "won" ? "won" : metric === "conceded" ? "conceded" : "in the match";

  return (
    <div className="mt-3" data-testid="team-form">
      <div className="flex flex-wrap items-center gap-1.5">
        <Seg testId="tf-venue" options={VENUES} value={venue}
          onChange={(k) => { setVenue(k); setPicked(null); }} />
        <Seg testId="tf-window" options={WINDOWS.map((n) => ({ key: n, label: `L${n}` }))}
          value={win} onChange={(k) => { setWin(k); setPicked(null); }} />
        <Seg testId="tf-metric" options={METRICS} value={metric}
          onChange={(k) => { setMetric(k); setLine(null); setPicked(null); }} />
      </div>

      {v.n === 0 ? (
        <p className="mt-3 text-xs text-muted-foreground">
          No {venue} games in the last twenty on file.
        </p>
      ) : (
        <>
          {/* Headline: the average and the hit count, in words. */}
          <div className="flex items-end gap-4 flex-wrap mt-3">
            <div>
              <p className="font-mono-data text-2xl font-bold text-primary leading-none"
                data-testid="tf-avg">{v.avg?.toFixed(2)}</p>
              <p className="text-[10px] text-muted-foreground mt-1">
                avg corners {metricWord} · last {v.n}{venue !== "all" ? ` ${venue}` : ""}
              </p>
            </div>
            {active != null && (
              <div>
                <p className="font-mono-data text-lg text-foreground leading-none" data-testid="tf-hits">
                  {v.hits}/{v.n}
                </p>
                <p className="text-[10px] text-muted-foreground mt-1">
                  at {active}+{v.run > 0 ? ` · last ${v.run} in a row` : ""}
                </p>
              </div>
            )}
            <div className="ml-auto text-right">
              <p className="font-mono-data text-sm text-foreground leading-none">{v.low}–{v.high}</p>
              <p className="text-[10px] text-muted-foreground mt-1">range</p>
            </div>
          </div>

          {/* The bars. Height is the corner count; the dashed rule is the average. */}
          <div className="relative mt-3" role="img"
            aria-label={`${teamName || "Team"} corners ${metricWord}, last ${v.n} games, average ${v.avg}. ${v.hits} of ${v.n} at ${active} or more.`}>
            {v.avg != null && (
              <div className="absolute left-0 right-0 border-t border-dashed border-foreground/40 pointer-events-none"
                style={{ bottom: `${(v.avg / scaleTop) * 100}%` }} />
            )}
            <div className="relative flex items-end gap-[3px] h-28" data-testid="tf-bars">
              {v.games.map((g, i) => {
                const val = g[metric];
                const has = typeof val === "number";
                const hit = has && active != null && val >= active;
                return (
                  <button key={`${g.date}-${i}`} type="button" data-testid="tf-bar"
                    data-hit={hit ? "1" : "0"}
                    onClick={() => setPicked(picked === i ? null : i)}
                    title={`${short(g.date)} ${g.home ? "vs" : "@"} ${g.opponent} — ${has ? val : "?"}`}
                    aria-label={`${short(g.date)} ${g.home ? "home to" : "away at"} ${g.opponent}, ${has ? val : "unknown"} corners`}
                    className="flex-1 min-w-0 flex flex-col justify-end items-center h-full cursor-pointer">
                    <span className="font-mono-data text-[9px] text-muted-foreground leading-none mb-0.5">
                      {has ? val : "–"}
                    </span>
                    <span className={`w-full rounded-t transition-colors ${
                      hit ? "bg-primary" : "bg-slate-600/70"} ${picked === i ? "ring-2 ring-foreground/50" : ""}`}
                      style={{ height: `${has ? Math.max(3, (val / scaleTop) * 100) : 3}%` }} />
                  </button>
                );
              })}
            </div>
            {/* H / A under each bar so the venue mix is readable at a glance on "All". */}
            <div className="flex gap-[3px] mt-1">
              {v.games.map((g, i) => (
                <span key={i} className={`flex-1 min-w-0 text-center font-mono-data text-[9px] ${
                  g.home ? "text-foreground/70" : "text-muted-foreground/60"}`}>
                  {g.home ? "H" : "A"}
                </span>
              ))}
            </div>
          </div>

          {shown ? (
            <p className="mt-2 text-[11px] text-foreground" data-testid="tf-picked">
              {short(shown.date)} · {shown.home ? "vs" : "@"} {shown.opponent}
              {shown.gf != null && shown.ga != null ? ` · ${shown.gf}-${shown.ga}` : ""}
              {" · "}corners {shown.won}{shown.conceded != null ? `–${shown.conceded}` : ""}
            </p>
          ) : (
            <p className="mt-2 text-[11px] text-muted-foreground">
              Oldest left, newest right. Dashed line is the average. Tap a bar for the game.
            </p>
          )}

          {lineOptions.length > 0 && (
            <div className="flex flex-wrap items-center gap-1 mt-2" data-testid="tf-lines">
              <span className="text-[10px] text-muted-foreground mr-1">Line</span>
              {lineOptions.map((l) => (
                <button key={l} type="button" data-testid={`tf-line-${l}`} onClick={() => setLine(l)}
                  className={`font-mono-data text-[11px] px-2 py-0.5 rounded border transition-colors ${
                    l === active
                      ? "border-primary/60 bg-primary/15 text-primary"
                      : "border-border text-muted-foreground hover:text-foreground"}`}>
                  {l}+
                </button>
              ))}
            </div>
          )}
        </>
      )}
    </div>
  );
}
