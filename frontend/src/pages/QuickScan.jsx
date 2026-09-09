import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { Zap, ArrowRight, Swords, TrendingUp, ShieldAlert, Sparkles, Loader2, ChevronDown, AlertTriangle } from "lucide-react";
import { api } from "@/lib/api";
import PreviewWall from "@/components/PreviewWall";
import { withFlag } from "@/lib/countryFlag";
import StoryButton from "@/components/StoryButton";
import { mismatchStoryDays, renderAngleStory } from "@/lib/storyImage";
import { kickoffLabel } from "@/lib/kickoff";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";

const WINDOWS = [
  { v: "3", l: "Next 3 days" },
  { v: "7", l: "Next 7 days" },
  { v: "14", l: "Next 14 days" },
  { v: "0", l: "All upcoming" },
];

const fmt = (d) => (d ? new Date(d).toLocaleDateString(undefined, { weekday: "short", month: "short", day: "numeric" }) : "");

export default function QuickScan() {
  const navigate = useNavigate();
  const [within, setWithin] = useState("7");
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);
  // Set by the API when the server trimmed this board for a non-member.
  const [preview, setPreview] = useState(null);

  useEffect(() => {
    setLoading(true);
    const params = { limit: 30 };
    if (within !== "0") params.within_days = Number(within);
    api.topMismatches(params)
      .then((d) => { setRows(d); setPreview(d?.preview ? { total: d.total } : null); })
      .catch(() => { setRows([]); setPreview(null); })
      .finally(() => setLoading(false));
  }, [within]);

  // One story per matchday; the weekend is capped at a top 3 because Saturday's full
  // card is unreadable at story size. Numbers stay hidden on every row.
  const storyDays = mismatchStoryDays(rows);

  return (
    <div className="space-y-3 sm:space-y-6" data-testid="quickscan-page">
      <div className="flex flex-col sm:flex-row sm:items-end justify-between gap-4">
        <div>
          <div className="flex items-center gap-2 text-primary mb-1">
            <Zap className="h-4 w-4" />
            <span className="font-mono-data text-xs tracking-widest uppercase">Quick Value Scan</span>
          </div>
          <h1 className="font-head text-3xl sm:text-4xl font-bold tracking-tight">Corner Mismatches</h1>
          <p className="text-muted-foreground text-sm mt-1">
            Strong corner-winning teams drawn against defences that concede a lot — ranked by projected total corners.
          </p>
        </div>
        <div className="flex items-center gap-2">
          {/* One story per matchday, numbers blurred — see lib/storyImage. */}
          <StoryButton days={storyDays} className="h-9 px-3" />
          <Tabs value={within} onValueChange={setWithin}>
            <TabsList className="bg-secondary h-9">
              {WINDOWS.map((w) => (
                <TabsTrigger key={w.v} value={w.v} data-testid={`quickscan-window-${w.v}`} className="text-xs px-2.5 h-7">{w.l}</TabsTrigger>
              ))}
            </TabsList>
          </Tabs>
        </div>
      </div>

      {loading ? (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {Array.from({ length: 6 }).map((_, i) => <div key={i} className="h-[184px] bg-card border border-border rounded-lg animate-pulse" />)}
        </div>
      ) : rows.length === 0 ? (
        <div className="bg-card border border-border rounded-lg py-20 text-center text-muted-foreground text-sm" data-testid="quickscan-empty">
          No strong mismatches in this window. Try widening the timeframe.
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 items-start">
          {rows.map((r) => (
            <PairCard key={r.team_id} r={r} onClick={() => r.next_fixture?.fixture_id && navigate(`/fixture/${r.next_fixture.fixture_id}`)} />
          ))}
        </div>
      )}

      {preview && (
        <PreviewWall total={preview.total} shown={rows.length} noun="mismatches"
          className="rounded-lg border border-border" />
      )}
    </div>
  );
}

function PairCard({ r, onClick }) {
  const nf = r.next_fixture || {};
  const [explanation, setExplanation] = useState(null);
  const [loadingExp, setLoadingExp] = useState(false);
  // Second level of the same answer. The blurb says what the angle is; this says what
  // it is made of, and the numbers behind it ship with the row so opening it costs
  // nothing and works even when the explainer itself is down.
  const [expanded, setExpanded] = useState(false);

  const explain = async (e) => {
    e.stopPropagation();
    if (explanation || loadingExp) return;
    setLoadingExp(true);
    try {
      const res = await api.explain({
        key: `${nf.fixture_id}-${r.line}`,
        team: r.name, opponent: nf.opponent, league: r.league_name,
        is_home: !!nf.is_home, line: r.line,
        team_for: r.team_for, opp_conceded: r.opp_conceded,
        lam: r.lambda, prob: r.prob, fair_odds: r.fair_odds,
      });
      setExplanation(res.explanation);
    } catch {
      // Still opens the panel, because the NUMBERS do not depend on the explainer —
      // they came down with the row. A failed model call should cost you the prose, not
      // the evidence.
      setExplanation("Couldn't write an explanation right now — the numbers behind this angle are still below.");
    } finally {
      setLoadingExp(false);
    }
  };

  return (
    <div
      onClick={onClick}
      data-testid="quickscan-card"
      className="group cursor-pointer bg-card border border-border rounded-lg p-4 hover:border-emerald-500/40 transition-colors duration-150 flex flex-col gap-3"
      style={{ borderTop: "2px solid #10B981" }}
    >
      <div className="flex items-center gap-2 text-[10px] uppercase tracking-widest text-muted-foreground">
        <span>{withFlag(r.league_id, r.league_name)}</span>
        <span className="opacity-40">·</span>
        <span className="text-primary/80 normal-case tracking-normal">{fmt(nf.date)}</span>
        {nf.round && nf.round !== "Upcoming" && <><span className="opacity-40">·</span><span className="normal-case tracking-normal">{nf.round}</span></>}
      </div>

      <div className="flex items-center gap-3">
        {/* attacker */}
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-1.5 text-emerald-400 text-[10px] uppercase tracking-wider mb-0.5">
            <TrendingUp className="h-3 w-3" /> Wins corners
          </div>
          <p className="font-head font-semibold text-sm leading-tight truncate">{r.name}</p>
          <p className="font-mono-data text-xs text-emerald-400 mt-0.5">{r.team_for?.toFixed(1)} /g</p>
        </div>

        <Swords className="h-4 w-4 text-muted-foreground shrink-0" />

        {/* defence */}
        <div className="flex-1 min-w-0 text-right">
          <div className="flex items-center justify-end gap-1.5 text-amber-400 text-[10px] uppercase tracking-wider mb-0.5">
            Concedes <ShieldAlert className="h-3 w-3" />
          </div>
          <p className="font-head font-semibold text-sm leading-tight truncate">
            <span className="text-muted-foreground font-normal text-xs mr-1">{nf.is_home ? "vs" : "@"}</span>{nf.opponent}
          </p>
          <p className="font-mono-data text-xs text-amber-400 mt-0.5">{r.opp_conceded?.toFixed(1)} /g</p>
        </div>
      </div>

      <div className="flex items-center justify-between pt-2 border-t border-border/60">
        <div className="flex items-center gap-3 font-mono-data text-xs">
          <span className="text-muted-foreground">Proj λ <span className="text-primary font-semibold">{r.lambda?.toFixed(1)}</span></span>
          <span className="text-muted-foreground" title={`${r.prob?.toFixed(0)}% to hit`}>Model <span className="text-foreground font-semibold">{r.line}+ @ {r.fair_odds?.toFixed(2)}</span></span>
        </div>
        <ArrowRight className="h-4 w-4 text-muted-foreground opacity-0 group-hover:opacity-100 transition-opacity" />
      </div>

      {/* Claude explainer */}
      {explanation ? (
        // ABSORBS ITS OWN CLICKS. The whole card is a link to the fixture, so without
        // this the panel could not be opened, read or selected without being navigated
        // away from mid-sentence.
        <div data-testid="quickscan-explanation"
          onClick={(e) => e.stopPropagation()}
          className="rounded-md bg-primary/5 border border-primary/20 p-2.5">
          <div className="flex gap-2">
            <Sparkles className="h-3.5 w-3.5 text-primary shrink-0 mt-0.5" />
            <p className="text-xs text-foreground/90 leading-relaxed">{explanation}</p>
          </div>

          <div className="mt-1.5 ml-5 flex items-center gap-3">
            <button
              data-testid="quickscan-expand-btn"
              onClick={() => setExpanded((v) => !v)}
              aria-expanded={expanded}
              className="inline-flex items-center gap-1 text-[10px] text-primary hover:text-primary/80 transition-colors"
            >
              <ChevronDown className={`h-3 w-3 transition-transform duration-150 ${expanded ? "rotate-180" : ""}`} />
              {expanded ? "Hide the numbers" : "Show the numbers"}
            </button>
            {/* SHARE THE ARGUMENT, NOT THE PRICE. The image is built from the row's own
                numbers rather than from the prose above it: the explainer is handed the
                line, the probability and the fair odds and told to reference them, so its
                text routinely contains the price this story is supposed to withhold. */}
            <StoryButton
              days={[{ key: `angle-${nf.fixture_id}-${r.line}` }]}
              testId="quickscan-angle-story"
              label="Share"
              title="A Story image arguing this angle — line and price blurred"
              className="!px-1.5 !py-0.5 !text-[10px] !border-0 !bg-transparent !text-primary hover:!bg-primary/10"
              render={(canvas) => renderAngleStory(canvas, {
                row: r, fixture: nf, kickoff: kickoffLabel(nf.date),
              })}
            />
            <button
              data-testid="quickscan-hide-btn"
              onClick={() => { setExplanation(null); setExpanded(false); }}
              className="text-[10px] text-muted-foreground hover:text-foreground transition-colors"
            >
              Hide
            </button>
          </div>

          {expanded && <Evidence r={r} nf={nf} />}
        </div>
      ) : (
        <button
          data-testid="quickscan-explain-btn"
          onClick={explain}
          disabled={loadingExp}
          className="self-start inline-flex items-center gap-1.5 text-[11px] text-primary hover:text-primary/80 transition-colors disabled:opacity-60"
        >
          {loadingExp ? <Loader2 className="h-3 w-3 animate-spin" /> : <Sparkles className="h-3 w-3" />}
          {loadingExp ? "Thinking…" : "Why this angle?"}
        </button>
      )}
    </div>
  );
}


// The second level: what the two headline averages are actually made of.
//
// The blurb above it is prose from the model. This is the arithmetic under the prose —
// the sample behind each number and the recent games themselves — so someone who wants
// to check the claim rather than take it can, without leaving the card.
//
// IT REPORTS THE VENUE FALLBACK. `_real_avg` drops a venue split when the pool is
// thinner than three games and averages everything instead. That is the right call for
// a projection and a lie in an evidence panel: a card headed "at home" listing eleven
// games, most of them away, is worse than one that admits the split was not applied. So
// where the fallback fired, it is said in words.

const VENUE_WORD = { home: "home", away: "away" };

function Side({ label, name, value, unit, data, accent }) {
  const asked = VENUE_WORD[data?.venue_asked];
  const fellBack = data && data.venue_used === "all" && asked;
  return (
    <div className="py-1.5">
      <div className="flex items-baseline gap-2">
        <span className="text-[10px] uppercase tracking-wider text-muted-foreground">{label}</span>
        <span className="text-xs text-foreground truncate">{name}</span>
        <span className={`ml-auto font-mono-data text-xs font-semibold ${accent}`}>
          {value?.toFixed(1)} {unit}
        </span>
      </div>
      {data && (
        <div className="mt-1 flex items-center gap-1.5 flex-wrap">
          <span className="text-[10px] text-muted-foreground">
            {data.games} {fellBack ? "" : asked ? `${asked} ` : ""}game{data.games === 1 ? "" : "s"}
          </span>
          {data.recent?.length > 0 && (
            <span className="flex gap-1" title="Most recent first">
              {data.recent.map((v, i) => (
                <span key={i}
                  className="inline-flex h-4 min-w-4 px-1 items-center justify-center rounded bg-white/5 text-[10px] font-mono-data text-foreground/80">
                  {v}
                </span>
              ))}
            </span>
          )}
        </div>
      )}
      {fellBack && (
        <p className="mt-1 flex items-start gap-1 text-[10px] text-amber-400/90 leading-snug">
          <AlertTriangle className="h-3 w-3 shrink-0 mt-px" />
          Fewer than 3 {asked} games, so this is all {data.games} games — not an {asked}-only figure.
        </p>
      )}
    </div>
  );
}

function Evidence({ r, nf }) {
  const ev = r.evidence;
  return (
    <div data-testid="quickscan-evidence" className="mt-2 ml-5 border-t border-primary/15 pt-2">
      {ev ? (
        <div className="divide-y divide-border/40">
          <Side label="Wins" name={r.name} value={r.team_for} unit="/g"
            data={ev.team} accent="text-emerald-400" />
          <Side label="Concedes" name={nf.opponent} value={r.opp_conceded} unit="/g"
            data={ev.opponent} accent="text-amber-400" />
        </div>
      ) : (
        // An older cached row from before the evidence shipped. Say so rather than
        // rendering an empty panel that looks like the numbers are missing.
        <p className="text-[10px] text-muted-foreground">
          Sample detail isn't available for this row yet — it arrives with the next sync.
        </p>
      )}

      <div className="mt-2 pt-2 border-t border-border/40 grid grid-cols-2 gap-x-3 gap-y-1 font-mono-data text-[10px]">
        <span className="text-muted-foreground">Projected λ</span>
        <span className="text-right text-foreground">{r.lambda?.toFixed(2)}</span>
        <span className="text-muted-foreground">Line</span>
        <span className="text-right text-foreground">{r.line}+ corners</span>
        <span className="text-muted-foreground">Model probability</span>
        <span className="text-right text-foreground">{r.prob?.toFixed(1)}%</span>
        <span className="text-muted-foreground">Fair price</span>
        <span className="text-right text-foreground">{r.fair_odds?.toFixed(2)}</span>
      </div>

      <p className="mt-2 text-[10px] text-muted-foreground leading-relaxed">
        The projection is built from both averages, not just the first — a side that wins
        a lot of corners against a defence that concedes few is not the same spot as one
        drawn against a defence that leaks.
      </p>
    </div>
  );
}
