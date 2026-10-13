import { useQuery } from "@tanstack/react-query";
import { Loader2, ShieldCheck, AlertTriangle, HelpCircle } from "lucide-react";
import { api } from "@/lib/api";
import ErrorBoundary from "@/components/ErrorBoundary";
import { verdictTone, hasEnough, bandRows, caveats, headline }
  from "@/lib/calibrationView";

/**
 * The evidence page: when this model says 65%, does it happen 65% of the time?
 *
 * PUBLIC, WHERE /results IS NOT, and the difference is what each one contains. The record
 * lists the picks, and the picks are the product — so it sits behind a free account. This
 * lists no pick and names no team: it is a table of how often the model's own stated
 * percentages come true. That is evidence about the MODEL, nothing anybody could act on,
 * and it is for the one visitor the rest of the site cannot reach — the stranger who
 * wants to know why they should believe a single number here before giving an email away.
 *
 * WHAT MAKES IT WORTH READING is that it cannot flatter itself. Every probability comes
 * from a snapshot frozen before kick-off, taken over every fixture in the window with no
 * quality bar and both ends of the board. So there is no selection to explain away, and
 * nothing recomputed with the benefit of the result.
 *
 * THE CAVEATS ARE NOT A FOOTNOTE AND ARE NOT OPTIONAL. A table of percentages under a
 * green tick is the most persuasive thing this site can put in front of a stranger and
 * therefore the easiest to overclaim with. Three facts qualify it, all computed from the
 * payload rather than typed here so they stop appearing when they stop being true: the
 * lines on one fixture rise and fall together so the real sample is the fixture count; a
 * probability may have been derived afterwards from a frozen forecast rather than stored
 * at the time; and a band under the floor cannot be read at all. See lib/calibrationView.
 *
 * NO SHARE BUTTON, DELIBERATELY. Every other board here has one. A calibration table
 * cropped to its best row is precisely the misuse this page exists to argue against, and
 * the page's own address carries the whole of it.
 */

// THE AMBER IS RESERVED FOR THE ONE THAT COSTS MONEY. A model running HIGH inflates every
// EV figure built on it, so that is the warning. Running LOW means the stated percentages
// are pessimistic — the opposite of a problem for anyone betting off them — and colouring
// it as a fault would be the page crying wolf about its own model.
const TONE = {
  holding: { icon: ShieldCheck, cls: "text-tone-strong-fg", label: "Holding up" },
  high: { icon: AlertTriangle, cls: "text-amber-400", label: "Running high" },
  low: { icon: ShieldCheck, cls: "text-primary", label: "Running low" },
  mixed: { icon: AlertTriangle, cls: "text-muted-foreground", label: "Off at the edges" },
  unknown: { icon: HelpCircle, cls: "text-muted-foreground", label: "Not enough yet" },
};

// ONE DECIMAL, ALWAYS. Left to the raw number, 72.0 renders as "72" beside 77.4 and the
// column stops lining up — in a table whose entire argument is that two numbers should be
// compared with each other.
const pct = (v) => (v === null || v === undefined ? "—" : `${Number(v).toFixed(1)}%`);

/** The gap, signed and coloured — but only where the band can carry one. */
const Miss = ({ row }) => {
  if (!row.readable || row.miss === null) {
    return <span className="text-muted-foreground">—</span>;
  }
  const good = Math.abs(row.miss) < 3;
  return (
    <span className={good ? "text-tone-strong-fg"
                          : row.miss < 0 ? "text-amber-400" : "text-primary"}>
      {row.miss > 0 ? "+" : ""}{row.miss}
    </span>
  );
};

function EvidenceBoard() {
  const { data, isLoading, error } = useQuery({
    queryKey: ["calibration"],
    queryFn: () => api.calibration({ days: 180 }),
  });

  const tone = verdictTone(data);
  const Tone = TONE[tone];
  const rows = bandRows(data);
  const notes = caveats(data);
  const o = data?.overall || {};

  return (
    <div className="space-y-5" data-testid="evidence-page">
      <div>
        <div className="flex items-center gap-2 text-primary mb-1">
          <ShieldCheck className="h-4 w-4" />
          <span className="font-mono-data text-xs tracking-widest uppercase">Evidence</span>
        </div>
        <h1 className="font-head text-3xl sm:text-4xl font-bold tracking-tight">
          Does 65% mean 65%?
        </h1>
        <p className="text-sm text-muted-foreground mt-2 max-w-2xl">
          Every night this site freezes the expected corners for every upcoming fixture,
          before kick-off, with no filter on which games. Afterwards each one is graded
          against what the match actually produced. This page is the result: how often the
          percentages the model prints come true.
        </p>
        <p className="text-sm text-muted-foreground mt-2 max-w-2xl">
          A single game proves nothing about a percentage. Hundreds can. If the model says
          about 65% and the answer comes back near 65%, the number is honest and so is any
          price built on it. If it comes back at 52%, the number is not honest and every
          edge computed from it is overstated by the difference.
        </p>
      </div>

      {isLoading && !data ? (
        <div className="flex items-center gap-2 text-muted-foreground text-sm py-8">
          <Loader2 className="h-4 w-4 animate-spin" /> Loading the record…
        </div>
      ) : error ? (
        <p className="text-sm text-muted-foreground py-8">
          Could not load the calibration record. Try again in a moment.
        </p>
      ) : (
        <>
          <section className="bg-card border border-border rounded-lg p-4 space-y-2"
                   data-testid="evidence-verdict">
            <div className={`flex items-center gap-2 ${Tone.cls}`}>
              <Tone.icon className="h-4 w-4" />
              <span className="font-head font-semibold text-sm">{Tone.label}</span>
            </div>
            <p className="text-sm">{headline(data)}</p>
            {data?.shape_note && (
              /* WHICH KIND of miscalibration, where the table can see one — a level error
                 and a dispersion error need different work, and the table is the only
                 thing that can tell them apart. */
              <p className="text-[11px] text-muted-foreground">{data.shape_note}</p>
            )}
          </section>

          <section className="bg-card border border-border rounded-lg overflow-hidden">
            <div className="px-4 py-3 border-b border-border">
              <h2 className="font-head font-semibold text-sm">
                What the model said, and what happened
              </h2>
              <p className="text-[11px] text-muted-foreground mt-0.5 font-mono-data">
                {o.fixtures ? `${o.fixtures.toLocaleString()} graded fixtures · `
                            : ""}
                {data?.fixtures_frozen
                  ? `${data.fixtures_frozen.toLocaleString()} frozen` : ""}
              </p>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-xs" data-testid="evidence-table">
                <thead>
                  <tr className="text-muted-foreground border-b border-border">
                    <th className="text-left font-normal px-3 py-2">Model said</th>
                    {/* LINES AND THE INTERVAL STAND DOWN ON A PHONE, not Games. At
                        390px all seven columns pushed Gap off the edge — the one column
                        a first-time reader is actually here for — and a table you have
                        to discover is scrollable is a table whose point is missed.
                        Games is the honest denominator of the two (lines on one fixture
                        rise and fall together), so it is the one that stays. */}
                    <th className="text-right font-normal px-3 py-2 hidden sm:table-cell">
                      Lines
                    </th>
                    <th className="text-right font-normal px-3 py-2">Games</th>
                    <th className="text-right font-normal px-3 py-2">Promised</th>
                    <th className="text-right font-normal px-3 py-2">Happened</th>
                    <th className="text-right font-normal px-3 py-2">Gap</th>
                    <th className="text-right font-normal px-3 py-2 whitespace-nowrap
                                   hidden sm:table-cell">
                      95% range
                    </th>
                  </tr>
                </thead>
                <tbody className="font-mono-data">
                  {rows.map((r) => (
                    <tr key={r.band}
                        data-testid={`evidence-band-${r.band}`}
                        className={`border-b border-border/50 ${
                          r.readable ? "" : "text-muted-foreground/60"}`}>
                      <td className="px-3 py-2 whitespace-nowrap">
                        {r.band}
                        {/* A THIN BAND IS SHOWN AND LABELLED, never dropped — and never
                            left looking like a readable one. */}
                        {!!r.claims && !r.readable && (
                          <span className="ml-1.5 text-[10px] normal-case">too few</span>
                        )}
                      </td>
                      <td className="px-3 py-2 text-right hidden sm:table-cell">
                        {r.claims ? r.claims.toLocaleString() : "—"}
                      </td>
                      <td className="px-3 py-2 text-right">
                        {r.fixtures ? r.fixtures.toLocaleString() : "—"}
                      </td>
                      <td className="px-3 py-2 text-right">{pct(r.promised)}</td>
                      <td className="px-3 py-2 text-right">{pct(r.actual)}</td>
                      <td className="px-3 py-2 text-right"><Miss row={r} /></td>
                      <td className="px-3 py-2 text-right whitespace-nowrap
                                     hidden sm:table-cell">
                        {r.readable ? `${r.lo}–${r.hi}%` : "—"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p className="px-4 py-3 text-[11px] text-muted-foreground">
              A band is honest when its promise sits inside the 95% range beside it. The
              gap is what happened minus what was promised: negative means the model
              claimed more than it delivered.
            </p>
          </section>

          {hasEnough(data) && !!(data?.team_lines || []).length && (
            <section className="bg-card border border-border rounded-lg overflow-hidden">
              <div className="px-4 py-3 border-b border-border">
                <h2 className="font-head font-semibold text-sm">By corner line</h2>
                <p className="text-[11px] text-muted-foreground mt-0.5">
                  A model can be honest at 4+ and wrong at 7+, and the table above would
                  show neither. One side's own corners.
                </p>
              </div>
              <div className="overflow-x-auto">
                <table className="w-full text-xs">
                  <thead>
                    <tr className="text-muted-foreground border-b border-border">
                      <th className="text-left font-normal px-3 py-2">Line</th>
                      <th className="text-right font-normal px-3 py-2 hidden sm:table-cell">
                        Lines
                      </th>
                      <th className="text-right font-normal px-3 py-2">Promised</th>
                      <th className="text-right font-normal px-3 py-2">Happened</th>
                      <th className="text-right font-normal px-3 py-2">Gap</th>
                    </tr>
                  </thead>
                  <tbody className="font-mono-data">
                    {(data.team_lines || []).map((r) => (
                      <tr key={r.line} className="border-b border-border/50">
                        <td className="px-3 py-2">{r.line}+</td>
                        <td className="px-3 py-2 text-right hidden sm:table-cell">
                          {r.claims.toLocaleString()}
                        </td>
                        <td className="px-3 py-2 text-right">{pct(r.promised)}</td>
                        <td className="px-3 py-2 text-right">{pct(r.actual)}</td>
                        <td className="px-3 py-2 text-right">
                          <Miss row={{ readable: !r.thin, miss: r.residual }} />
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>
          )}

          {!!notes.length && (
            <section className="bg-card border border-border rounded-lg p-4"
                     data-testid="evidence-caveats">
              <h2 className="font-head font-semibold text-sm mb-2">
                What this does not prove
              </h2>
              <ul className="space-y-1.5">
                {notes.map((n) => (
                  <li key={n} className="text-[11px] text-muted-foreground flex gap-2">
                    <span className="text-muted-foreground/50">·</span>
                    <span>{n}</span>
                  </li>
                ))}
              </ul>
            </section>
          )}

          <p className="text-[11px] text-muted-foreground max-w-2xl">
            Nothing on this page is a selection or a tip. It measures one thing — whether a
            stated percentage comes true that often — and the only conclusions it supports
            are about the model, not about any bet.
          </p>
        </>
      )}
    </div>
  );
}

export default function Evidence() {
  return <ErrorBoundary><EvidenceBoard /></ErrorBoundary>;
}
