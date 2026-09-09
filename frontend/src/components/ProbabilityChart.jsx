import { useMemo, useState } from "react";
import { Dices, Video } from "lucide-react";
import StoryButton from "@/components/StoryButton";
import { fixtureStoryMarkets, renderFixtureStory } from "@/lib/storyImage";
import { canRecord, extFor, recordStoryVideo } from "@/lib/storyVideo";
import { kickoffLabel } from "@/lib/kickoff";

// THE SHAPE BEHIND THE NUMBER.
//
// "54%" is the model's answer but not its confidence: 54% off a tight distribution and 54%
// off a flat one are different bets, and the bare percentage hides which one you have. This
// draws the curve the price came from — one bar per possible corner count, with the counts
// that WIN the bet filled in.
//
// The bars come from the backend (`model.distribution`), which builds them with the same
// pmf that prices the market — NB for team lines, Poisson for match totals. Recomputing
// them here in JavaScript would eventually drift, and a chart that disagrees with the
// number printed beside it is worse than no chart at all.
//
// Colour is the brand cyan for the winning region and muted slate for the rest, NOT the
// status palette: this is "in the bet / out of it", which is not one of the four meanings.
// The split is stated in words under the chart as well, so it never rests on colour.

const fmtPct = (p) => `${(p * 100).toFixed(1)}%`;

export default function ProbabilityChart({ distribution, lambdas, markets, homeName, awayName,
                                          leagueId, kickoff }) {
  const groups = useMemo(() => [
    { key: "total", label: "Match total" },
    { key: "home", label: homeName },
    { key: "away", label: awayName },
  ], [homeName, awayName]);

  const [group, setGroup] = useState("total");
  // Memoised because the `|| []` fallback mints a NEW array on every render when the
  // group is missing, which would make every memo below it recompute each time.
  const dist = useMemo(() => distribution?.[group] || [], [distribution, group]);
  const lam = lambdas?.[group];

  // Lines worth offering: a window around the projection, not every count the chart draws.
  // The full range is eighteen buttons on a match total, which is a wall rather than a
  // choice — and nobody is pricing 3+ corners in a game projected for ten. Bars outside the
  // window stay tappable, so the range is still reachable, just not shouted.
  const LINE_SPREAD = 3;
  const lines = useMemo(() => {
    if (!dist.length) return [];
    const lo = Math.max(dist[0].k + 1, Math.round(lam || 0) - LINE_SPREAD);
    const hi = Math.min(dist[dist.length - 1].k, Math.round(lam || 0) + LINE_SPREAD);
    return Array.from({ length: Math.max(0, hi - lo + 1) }, (_, i) => lo + i);
  }, [dist, lam]);

  // Any drawn count can be the line — the buttons are a shortcut, not the whole range.
  const [line, setLine] = useState(null);
  const inRange = (k) => dist.length > 0 && k > dist[0].k && k <= dist[dist.length - 1].k;
  const active = line != null && inRange(line)
    ? line
    : (lines.length ? lines[Math.floor(lines.length / 2)] : null);

  const [hover, setHover] = useState(null);

  // The markets the story draws. Built from the model's own rows so the picture cannot
  // claim a probability the page does not show, and overridden for the group in view so
  // the image matches the line the reader just moved.
  const storyMarkets = useMemo(() => {
    const rows = fixtureStoryMarkets(markets, lambdas, { homeName, awayName });
    if (active == null || !dist.length) return rows;
    // Re-derived from the SAME bars the chart draws rather than looked up in `markets`,
    // because a reader can move the line to a count the market ladder has no row for.
    const p = dist.reduce((s, r) => s + (r.k >= active ? r.p : 0), 0);
    return rows.map((m) => (m.group === group && m.line !== active
      ? { ...m, line: active, prob: p * 100, price: p > 0 ? (1 / p).toFixed(2) : null }
      : m));
  }, [markets, lambdas, homeName, awayName, group, active, dist]);

  if (!dist.length || active == null) return null;

  // One description of the picture, used by both the still and the video, so the two
  // cannot show different games.
  const storyArgs = { homeName, awayName, leagueId, kickoff: kickoffLabel(kickoff),
                      dist, group, markets: storyMarkets };

  const pWin = dist.reduce((s, r) => s + (r.k >= active ? r.p : 0), 0);
  const peak = Math.max(...dist.map((r) => r.p)) || 1;
  const fair = pWin > 0 ? (1 / pWin) : null;
  const shown = hover != null ? dist.find((r) => r.k === hover) : null;

  return (
    <section className="bg-card border border-border rounded-lg overflow-hidden"
      data-testid="prob-chart">
      <div className="px-4 py-3 border-b border-border flex items-center gap-2 flex-wrap">
        <Dices className="h-4 w-4 text-primary" />
        <h3 className="font-head font-semibold text-sm">How likely is it?</h3>
        {/* SHARE THE CHANCE, NOT THE PRICE. The percentage is the claim worth posting;
            the model's price is the reason to open the site, so it goes out blurred. */}
        {storyMarkets.length > 0 && (
          <StoryButton
            days={[{ key: `fixture-${active}` }]}
            testId="story-image"
            label="Share"
            title="Instagram Story — the probability, with the model price blurred out"
            render={(canvas) => renderFixtureStory(canvas, { ...storyArgs })}
          />
        )}
        {/* The same story, animated and recorded. Hidden entirely where the browser has no
            encoder — a button that fails when tapped is worse than one that is not there. */}
        {storyMarkets.length > 0 && canRecord() && (
          <StoryButton
            days={[{ key: `fixture-${active}` }]}
            testId="story-video"
            icon={Video}
            label="Video"
            title="A 5-second Story video — the bars draw in and the number counts up"
            makeFile={async (day) => {
              const canvas = document.createElement("canvas");
              const { blob, mime, type, ext } = await recordStoryVideo(canvas, (progress) =>
                renderFixtureStory(canvas, { ...storyArgs, progress }));
              // `type`, not `mime`: the plain container. A file typed
              // "video/mp4;codecs=avc1.42E01E,…" is refused by the Android share sheet.
              const container = extFor(mime);
              return new File([blob], `corner-model-${day.key}.${ext || container}`,
                              { type: type || `video/${container}` });
            }}
          />
        )}
        <div className="ml-auto flex rounded-md bg-secondary p-0.5">
          {groups.map((g) => (
            <button key={g.key} data-testid={`pc-group-${g.key}`} onClick={() => { setGroup(g.key); setLine(null); }}
              className={`text-[11px] px-2 py-1 rounded transition-colors max-w-[92px] truncate ${
                group === g.key ? "bg-primary text-primary-foreground font-medium" : "text-muted-foreground"}`}>
              {g.label}
            </button>
          ))}
        </div>
      </div>

      <div className="px-4 pt-4 pb-3">
        {/* The headline. A big number with its line spelled out, because this is the one
            thing most visitors will read. */}
        <div className="flex items-end gap-3 flex-wrap mb-4">
          <div>
            <p className="font-mono-data text-4xl font-bold text-primary leading-none"
              data-testid="pc-headline">{Math.round(pWin * 100)}%</p>
            <p className="text-xs text-muted-foreground mt-1.5">
              chance of <span className="text-foreground font-medium">{active}+ corners</span>
              {group !== "total" && <> for {group === "home" ? homeName : awayName}</>}
            </p>
          </div>
          {fair && (
            <div className="ml-auto text-right">
              <p className="font-mono-data text-xl text-foreground leading-none">{fair.toFixed(2)}</p>
              <p className="text-[10px] text-muted-foreground mt-1">break-even odds</p>
            </div>
          )}
        </div>

        {/* The distribution. One bar per corner count; height is how often that exact count
            happens. `role=img` with a spoken summary, because the bars themselves are not
            readable by a screen reader and the table below is the long form. */}
        <div className="relative" role="img"
          aria-label={`Distribution of corner counts. ${Math.round(pWin * 100)} percent chance of ${active} or more.`}>
          {shown && (
            <div className="absolute -top-1 left-0 right-0 text-center pointer-events-none z-10">
              <span className="inline-block bg-secondary border border-border rounded px-2 py-1 text-[11px] font-mono-data">
                exactly {shown.k} · {fmtPct(shown.p)}
              </span>
            </div>
          )}
          <div className="flex items-end gap-[2px] h-32" data-testid="pc-bars">
            {dist.map((r) => {
              const inBet = r.k >= active;
              return (
                <button key={r.k} type="button" data-testid={`pc-bar-${r.k}`}
                  data-in-bet={inBet ? "1" : "0"}
                  onMouseEnter={() => setHover(r.k)} onMouseLeave={() => setHover(null)}
                  onFocus={() => setHover(r.k)} onBlur={() => setHover(null)}
                  onClick={() => inRange(r.k) && setLine(r.k)}
                  title={`exactly ${r.k} corners — ${fmtPct(r.p)}`}
                  aria-label={`${r.k} corners, ${fmtPct(r.p)}`}
                  className="flex-1 min-w-0 flex flex-col justify-end h-full group cursor-pointer">
                  <span
                    className={`w-full rounded-t transition-colors ${
                      inBet ? "bg-primary group-hover:bg-primary/80" : "bg-slate-600/70 group-hover:bg-slate-500"
                    } ${hover === r.k ? "ring-2 ring-foreground/40" : ""}`}
                    style={{ height: `${Math.max(2, (r.p / peak) * 100)}%` }} />
                </button>
              );
            })}
          </div>
          <div className="flex gap-[2px] mt-1.5">
            {dist.map((r) => (
              <span key={r.k} className="flex-1 min-w-0 text-center font-mono-data text-[9px] text-muted-foreground">
                {dist.length > 16 && r.k % 2 ? "" : r.k}
              </span>
            ))}
          </div>
        </div>

        {/* The legend, in words. Two regions, both named — never colour on its own. */}
        <p className="text-[11px] text-muted-foreground mt-3 leading-relaxed">
          <span className="inline-block h-2 w-2 rounded-sm bg-primary align-middle mr-1" />
          <span className="text-foreground">{active} or more</span> wins the bet ({Math.round(pWin * 100)}%)
          <span className="mx-2 text-muted-foreground/40">·</span>
          <span className="inline-block h-2 w-2 rounded-sm bg-slate-600/70 align-middle mr-1" />
          under {active} loses it ({Math.round((1 - pWin) * 100)}%).
          {" "}Tap a bar to move the line.
        </p>

        {/* The line picker. Duplicated from tapping a bar because a row of labelled buttons
            is discoverable and a bar is not. */}
        <div className="flex flex-wrap gap-1 mt-2.5" data-testid="pc-lines">
          {lines.map((l) => (
            <button key={l} data-testid={`pc-line-${l}`} onClick={() => setLine(l)}
              className={`font-mono-data text-[11px] px-2 py-1 rounded border transition-colors ${
                l === active
                  ? "border-primary/60 bg-primary/15 text-primary"
                  : "border-border text-muted-foreground hover:text-foreground hover:border-foreground/30"}`}>
              {l}+
            </button>
          ))}
        </div>
      </div>
    </section>
  );
}
