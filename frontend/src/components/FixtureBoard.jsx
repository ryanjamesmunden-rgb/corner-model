import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { CalendarDays, ChevronRight, Flame, Swords, Target, TrendingDown } from "lucide-react";
import { api } from "@/lib/api";
import ShareButtons from "@/components/ShareButtons";
import { withFlag } from "@/lib/countryFlag";
import { fixtureShare } from "@/lib/shareText";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import StarButton from "@/components/StarButton";
import { TONE, toneClass, toneLabel } from "@/lib/angleTone";
import { FILTERS, applyFilter } from "@/lib/fixtureFilters";

// The best upcoming games, grouped by day — a schedule you can scan, not another ranked
// list of teams. Every other board here is team-first with the fixture riding along;
// this one's unit is the match.
//
// "Per day" is a CEILING, not a quota. Every fixture clears an absolute bar first
// (sample behind both sides, an at-or-above-par projection, and at least one STRONG
// angle), so a quiet day shows fewer games — or none — rather than promoting whatever
// happened to be on. A day where nothing clears is shown as such, because an absent day
// looks like missing data.
//
// The ORDER is triage, not a measured edge: which games to open first. The bet itself
// comes from the angles on the row, which are priced. See _fixture_board in server.py.
const PER_DAY = [
  { v: "3", l: "3" },
  { v: "5", l: "5" },
  { v: "8", l: "8" },
  { v: "20", l: "All" },
];
const DAYS = [
  { v: "3", l: "3 days" },
  { v: "7", l: "Week" },
  { v: "14", l: "2 weeks" },
  { v: "30", l: "Month" },
];

const KIND = {
  chase: Target,
  mismatch: Swords,
  over_team: Flame,
  under_team: TrendingDown,
  over_match: Flame,
  under_match: TrendingDown,
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
  const [perDay, setPerDay] = useState("5");
  const [days, setDays] = useState("3");
  // CLIENT-SIDE, because every angle the filter tests is already on the rows the board
  // returned. A round trip would re-ask the server a question it has already answered,
  // and toggling between "home streak" and "both teams" would cost a spinner each time.
  const [filter, setFilter] = useState("all");

  useEffect(() => {
    setLoading(true);
    api
      .fixtureBoard({ days: Number(days), per_day: Number(perDay), league_id: leagueId })
      .then(setBoard)
      .catch(() => setBoard(null))
      .finally(() => setLoading(false));
  }, [leagueId, perDay, days]);

  // Filtered FIRST, so everything downstream — the count, the share text, the day groups
  // — describes what is actually on screen. A share button that posts games the reader
  // cannot see is worse than no share button.
  const shown = applyFilter(board, filter);
  const allFixtures = (shown?.days || []).flatMap((d) => d.fixtures || []);
  const fixtureCount = allFixtures.length;
  const hidden = (shown?.before_filter || 0) - fixtureCount;
  // Shared with the scheduled post — see lib/shareText.
  const SHARE_ROWS = 8;
  const buildShare = fixtureShare({ fixtures: allFixtures, days });

  return (
    <section className="bg-card border border-border rounded-lg" data-testid="fixture-board">
      <div className="flex flex-col sm:flex-row sm:items-center gap-3 px-4 py-3 border-b border-border">
        <div className="flex items-center gap-2 min-w-0">
          <CalendarDays className="h-4 w-4 text-primary shrink-0" />
          <h2 className="font-head font-semibold text-lg">Best Upcoming Games</h2>
          <span className="text-xs text-muted-foreground hidden md:inline truncate">
            only games that clear the bar — a quiet day shows fewer, not worse
          </span>
          {fixtureCount > 0 && (
            <span className="font-mono-data text-[10px] text-muted-foreground shrink-0">{fixtureCount} games</span>
          )}
        </div>
        {fixtureCount > 0 && (
          <ShareButtons text={buildShare(SHARE_ROWS)} buildX={buildShare} className="shrink-0" />
        )}
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

      {/* The key. It was in the footer at 10px and went unread — colour is only useful
          if its meaning is where you meet the colour, not 300px below it. */}
      {/* THE FILTER ROW. The board answers "what is worth opening tonight" and returns
          every kind of angle at once, which is right as a default and wrong to scan when
          you have a specific idea — "which of these has the HOME side on a run". */}
      {!loading && board?.days?.length > 0 && (
        <div className="px-4 py-2 border-b border-border flex items-center gap-1.5 flex-wrap"
          data-testid="fb-filters">
          <span className="text-[10px] uppercase tracking-wider text-muted-foreground mr-1">
            Show
          </span>
          {FILTERS.map((f) => (
            <button key={f.key} onClick={() => setFilter(f.key)} title={f.hint}
              data-testid={`fb-filter-${f.key}`}
              className={`text-[11px] px-2 py-1 rounded border transition-colors ${
                filter === f.key
                  ? "bg-primary text-primary-foreground border-primary font-semibold"
                  : "bg-secondary/40 text-muted-foreground border-border hover:text-foreground"}`}>
              {f.label}
            </button>
          ))}
          {filter !== "all" && (
            <span className="text-[10px] text-muted-foreground w-full mt-1">
              {FILTERS.find((f) => f.key === filter)?.hint}
              {hidden > 0 && (
                <>
                  {" "}Hiding {hidden} of {shown.before_filter} that cleared the bar.
                  {/* The per-day CEILING is applied server-side, before this filter ever
                      sees a row. So "no games" here can mean "none exist" or "the ones
                      that do were trimmed before they arrived" — two different facts, and
                      only one of them is about football. */}
                  {fixtureCount === 0 && " Try a longer window, or raise the per-day count —"
                    + " this filters what the board already trimmed."}
                </>
              )}
            </span>
          )}
        </div>
      )}

      {!loading && board?.days?.length > 0 && (
        <div className="px-4 py-2 border-b border-border flex items-center gap-2 flex-wrap"
          data-testid="fb-legend">
          <span className="text-[10px] uppercase tracking-wider text-muted-foreground">Key</span>
          {[
            { t: TONE.strong.on, Icon: Flame, l: "solid", d: "a run long enough to back" },
            { t: TONE.streak.on, Icon: Flame, l: "streak", d: "live, still short" },
            { t: TONE.under.on, Icon: TrendingDown, l: "under", d: "betting it does NOT happen" },
            { t: TONE.edge.on, Icon: Swords, l: "mismatch", d: "the opponent is the reason" },
          ].map(({ t, Icon, l, d }) => (
            <span key={l} className="inline-flex items-center gap-1.5">
              <span className={`inline-flex items-center gap-1 text-[10px] px-1.5 py-0.5 rounded border font-mono-data ${t}`}>
                <Icon className="h-2.5 w-2.5" /> {l}
              </span>
              <span className="text-[10px] text-muted-foreground">{d}</span>
            </span>
          ))}
          <span className="text-[10px] text-muted-foreground/70 w-full">
            Filled means the evidence is there; outlined means it is building. Each colour means
            one thing and always carries its own icon, so the shape tells you as much as the
            colour does.
          </span>
        </div>
      )}

      {loading ? (
        <div className="p-4 space-y-2">
          {[0, 1, 2].map((i) => <div key={i} className="h-16 rounded-md bg-secondary animate-pulse" />)}
        </div>
      ) : !board?.days?.length ? (
        <p className="px-4 py-6 text-sm text-muted-foreground" data-testid="fb-empty">
          No upcoming fixtures in this window. Try the full week, or refresh the data if a
          round is due.
        </p>
      ) : (
        <div className="divide-y divide-border">
          {shown.days.map((d) => (
            <div key={d.day} data-testid="fb-day">
              <div className="flex items-center gap-2 px-4 py-2 bg-secondary/40">
                <span className="text-xs font-head font-semibold text-foreground">{dayLabel(d.day)}</span>
                <span className="ml-auto text-[10px] text-muted-foreground font-mono-data"
                  title="Shown out of every fixture kicking off that day">
                  {d.fixtures.length} of {d.scanned ?? d.considered}
                </span>
              </div>
              {d.fixtures.length ? d.fixtures.map((f) => (
                <FixtureRow key={f.fixture_id} f={f}
                  onClick={() => navigate(`/fixture/${f.fixture_id}`)} />
              )) : (
                // Saying so beats hiding the day: a missing date reads as broken data,
                // and "nothing qualified" is itself the answer to "what's on tonight".
                <p className="px-4 py-3 text-xs text-muted-foreground" data-testid="fb-day-empty">
                  {filter !== "all" && d.before_filter > 0
                    ? `${d.before_filter} game${d.before_filter === 1 ? "" : "s"} cleared the bar, none matching this filter.`
                    : <>Nothing cleared the bar
                  {d.scanned ? ` — ${d.scanned} fixture${d.scanned === 1 ? "" : "s"} on, none with enough behind ${d.scanned === 1 ? "it" : "them"}` : ""}.</>}
                </p>
              )}
            </div>
          ))}
        </div>
      )}
      {board?.days?.length > 0 && (
        <p className="px-4 py-2.5 border-t border-border text-[10px] text-muted-foreground">
          A fixture qualifies on evidence, not on the day being quiet: {board.min_games}+ games
          behind each side, a projection at or above that league's average, and at least one
          angle that is actually strong — a live streak of {board.min_run}+, a chase spot hitting
          4 of 5, or a mismatch with 6+ games behind both averages. The line under each fixture
          says which of those put it there. Order is triage — take the bet from the angle.
          {/* A projection three weeks out is not the same claim as one for tomorrow, and the
              board should not present them identically. Both sides will play several more
              times first, and the form driving these numbers is today's. */}
          {Number(days) > 14 && (
            <span className="block mt-1.5 text-amber-400/80">
              Beyond a fortnight these are built on today's form — both sides play several more
              games before kick-off, so the numbers will move. Use this as a research list to
              work through, not a card to bet.
            </span>
          )}
        </p>
      )}
    </section>
  );
}

function FixtureRow({ f, onClick }) {
  // corner_edge is the projected match total over what this league actually averages
  const edgePct = Math.round((f.corner_edge - 1) * 100);
  const hot = edgePct >= 8;
  return (
    <div onClick={onClick} role="button" tabIndex={0} data-testid="fb-fixture"
      onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && onClick()}
      className="w-full cursor-pointer text-left px-4 py-3 hover:bg-white/5 transition-colors duration-150 flex gap-3 items-start">
      <StarButton fixtureId={f.fixture_id} />
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
          {withFlag(f.league_id, f.league_name)}
          <span className="ml-2 normal-case tracking-normal font-mono-data"
            title="Real matches behind each side's numbers">
            {Math.min(f.home_games ?? 0, f.away_games ?? 0)}+ games each
          </span>
        </div>
        {/* WHY THIS GAME IS HERE, in words. Every fixture cleared the evidence hurdle, so
            one of its angles is always the reason — before this the reader had to infer
            it from up to six chips, which is exactly the confusion the colours caused. */}
        {f.reason && (
          <p className="text-[11px] text-foreground/70 mt-1 leading-snug" data-testid="fb-reason">
            {f.reason}
          </p>
        )}
        <div className="flex flex-wrap gap-1.5 mt-1.5">
          {f.angles.map((a, i) => {
            const Icon = KIND[a.kind] || Target;
            const cls = toneClass(a.kind, a.strong, a.streak_len);
            return (
              <span key={i} data-testid="fb-angle" data-strong={a.strong ? "1" : "0"}
                title={`${toneLabel(a.kind, a.strong, a.streak_len)} — ${a.team} · ${a.detail}`}
                className={`inline-flex items-center gap-1 text-[10px] px-1.5 py-0.5 rounded border font-mono-data ${cls}`}>
                <Icon className="h-2.5 w-2.5" />
                <span className="font-sans">{a.team}</span> {a.label}
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
    </div>
  );
}
