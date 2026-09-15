import { useQuery } from "@tanstack/react-query";
import { Loader2 } from "lucide-react";
import { api } from "@/lib/api";

// HOW THE BOARD ABOVE HAS ACTUALLY DONE.
//
// The board says a game will have 10.4 corners. Nothing anywhere said whether games it
// called 10.4 went on to produce ten, or eight, or thirteen — so the number could be read
// as confident or as decoration and there was no way to tell which. This is the half that
// makes the other half checkable.
//
// LED BY THE LINE, NOT BY THE ERROR. "Mean absolute error 1.8" is a modelling number and
// settles nothing; "when it called under 9.5 the game went under 9.5 seven times in ten"
// is the same data pointed at the decision somebody is about to make. The error is here
// too, underneath, because it is the thing that tells you whether a run of seven in ten
// was skill or a small sample.
//
// BIAS IS SHOWN BESIDE IT AND THAT IS DELIBERATE. A model wrong by two corners in both
// directions is noisy and usable. A model wrong by one corner in the SAME direction every
// time poisons every over bet placed off it while reading as twice as accurate.

const pct = (v) => (v == null ? "—" : `${v}%`);
const num = (v) => (v == null ? "—" : v.toFixed ? v.toFixed(2) : v);

// A rate over a handful of games is not a rate, and printing one at the same weight as a
// rate over two hundred invites a decision the data cannot support. Thin rows are shown —
// hiding them would be its own dishonesty — and marked.
const THIN = 20;

function Rate({ rate, of }) {
  if (rate == null) return <span className="text-muted-foreground">—</span>;
  return (
    <span className={of < THIN ? "text-muted-foreground" : "font-semibold"}>
      {pct(rate)}<span className="text-muted-foreground font-normal"> ({of})</span>
    </span>
  );
}

export default function ProjectionRecord({ days = 30 }) {
  const { data, isLoading, error } = useQuery({
    queryKey: ["projection-record", days],
    queryFn: () => api.projectionRecord({ days }),
  });

  if (isLoading) {
    return (
      <div className="flex items-center gap-2 text-xs text-muted-foreground p-4">
        <Loader2 className="h-3 w-3 animate-spin" /> Loading the record…
      </div>
    );
  }
  // A record that cannot be loaded says so. Rendering an empty table instead would read as
  // "nothing has ever landed", which is the one wrong answer that looks like a real one.
  if (error) {
    return (
      <p className="text-xs text-muted-foreground p-4">
        Couldn't load the record just now.
      </p>
    );
  }

  const settled = data?.settled || 0;

  return (
    <section className="space-y-3" data-testid="projection-record">
      <div>
        <h2 className="font-head text-sm font-semibold">How these projections have done</h2>
        <p className="text-xs text-muted-foreground mt-1 leading-relaxed max-w-2xl">
          Every game frozen on this board before kick-off, graded on what it actually
          produced. {settled} settled
          {data?.pending ? `, ${data.pending} still to play` : ""} over the last {days} days.
        </p>
      </div>

      {settled === 0 ? (
        // THE HONEST EMPTY STATE. The record starts the day the first snapshot is taken,
        // and saying so beats an empty table that reads as a model which has never been
        // right. Nothing here can be backfilled: a projection recomputed after the game
        // would have been made with the benefit of the result.
        <p className="text-xs text-muted-foreground border border-border rounded p-3">
          Nothing has settled yet. The record starts from the first snapshot — projections
          can't be graded retrospectively, because recomputing one after the game would
          use everything that has happened since.
        </p>
      ) : (
        <>
          <div className="flex flex-wrap gap-4 text-xs border border-border rounded p-3">
            <div>
              <div className="text-muted-foreground">Bias</div>
              <div className="font-mono-data font-semibold">
                {data.bias == null ? "—" : `${data.bias > 0 ? "+" : ""}${num(data.bias)}`}
              </div>
              <div className="text-[10px] text-muted-foreground mt-0.5">
                {data.bias == null ? "" : data.bias > 0
                  ? "games run busier than projected"
                  : data.bias < 0 ? "games run quieter than projected" : "no lean"}
              </div>
            </div>
            <div>
              <div className="text-muted-foreground">Typical miss</div>
              <div className="font-mono-data font-semibold">{num(data.mean_abs_error)}</div>
              <div className="text-[10px] text-muted-foreground mt-0.5">corners either way</div>
            </div>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full text-xs border-collapse">
              <thead>
                <tr className="text-muted-foreground text-left">
                  <th className="py-1.5 pr-3 font-normal">Line</th>
                  <th className="py-1.5 pr-3 font-normal">Called over</th>
                  <th className="py-1.5 pr-3 font-normal">Called under</th>
                  <th className="py-1.5 font-normal">Overall</th>
                </tr>
              </thead>
              <tbody className="font-mono-data">
                {(data.lines || []).map((l) => (
                  <tr key={l.line} className="border-t border-border">
                    <td className="py-1.5 pr-3">{l.line}</td>
                    <td className="py-1.5 pr-3"><Rate rate={l.over.rate} of={l.over.called} /></td>
                    <td className="py-1.5 pr-3"><Rate rate={l.under.rate} of={l.under.called} /></td>
                    <td className="py-1.5"><Rate rate={l.rate} of={l.settled} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
            <p className="text-[10px] text-muted-foreground mt-1">
              How often the side the projection pointed at was the winning side. Counts in
              brackets; anything under {THIN} games is greyed because it isn't a rate yet.
            </p>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full text-xs border-collapse">
              <thead>
                <tr className="text-muted-foreground text-left">
                  <th className="py-1.5 pr-3 font-normal">Projected</th>
                  <th className="py-1.5 pr-3 font-normal">Games</th>
                  <th className="py-1.5 pr-3 font-normal">Avg said</th>
                  <th className="py-1.5 pr-3 font-normal">Avg got</th>
                  <th className="py-1.5 pr-3 font-normal">Under 9.5</th>
                  <th className="py-1.5 font-normal">Over 10.5</th>
                </tr>
              </thead>
              <tbody className="font-mono-data">
                {(data.bands || []).map((b) => (
                  <tr key={b.band} className="border-t border-border">
                    <td className="py-1.5 pr-3 font-sans">{b.band}</td>
                    <td className="py-1.5 pr-3">{b.settled}</td>
                    <td className="py-1.5 pr-3">{num(b.avg_projected)}</td>
                    <td className="py-1.5 pr-3">{num(b.avg_actual)}</td>
                    <td className="py-1.5 pr-3"><Rate rate={b.under_9_5} of={b.settled} /></td>
                    <td className="py-1.5"><Rate rate={b.over_10_5} of={b.settled} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
            <p className="text-[10px] text-muted-foreground mt-1">
              Grouped by what the model SAID beforehand, not by what happened — the band you
              can find a game in before kick-off is the only one worth reading.
            </p>
          </div>
        </>
      )}
    </section>
  );
}
