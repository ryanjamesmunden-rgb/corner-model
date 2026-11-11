import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { Bell, Eye, ChevronRight, ChevronDown, Flame, Snowflake, Minus } from "lucide-react";
import { api } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { withFlag } from "@/lib/countryFlag";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import {
  SORTS, SOURCES, VIEWS, formTone, scheduleTone, betSummary, evTone,
  idleTeams, missingTeams, filterSummary,
} from "@/lib/myTeams";

const kickoff = (iso) => {
  if (!iso) return { day: "", time: "" };
  const d = new Date(iso);
  return {
    day: d.toLocaleDateString(undefined, { weekday: "short", day: "numeric", month: "short" }),
    time: d.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" }),
  };
};

const TONE_CLASS = {
  hot: "text-emerald-400",
  cold: "text-red-400",
  steady: "text-muted-foreground",
  unknown: "text-muted-foreground/60",
};
const ToneIcon = ({ tone, className = "h-3 w-3" }) =>
  tone === "hot" ? <Flame className={className} />
    : tone === "cold" ? <Snowflake className={className} />
      : <Minus className={className} />;

const ListBadge = ({ list }) => (
  <span className="inline-flex items-center gap-1 text-[10px] uppercase tracking-wider
    text-muted-foreground shrink-0">
    {list === "tracking" ? <Eye className="h-3 w-3" /> : <Bell className="h-3 w-3" />}
    {list === "tracking" ? "Tracking" : "Favourite"}
  </span>
);

/** The model's side of a fixture, and the edge only where a real price backs it. */
function BetReadout({ game }) {
  const s = betSummary(game);
  if (s.kind === "none") {
    return <span className="text-[11px] text-muted-foreground/60">{s.note}</span>;
  }
  return (
    <span className="flex flex-wrap items-baseline gap-x-2 gap-y-0.5 font-mono-data text-[11px]">
      <span className="text-foreground">{s.line}+ {s.prob.toFixed(0)}%</span>
      <span className="text-muted-foreground">fair {s.fair?.toFixed(2)}</span>
      {s.kind === "priced" ? (
        <>
          <span className="text-muted-foreground">book {s.book.toFixed(2)}</span>
          <span className={TONE_CLASS[evTone(s.ev)]}>
            {s.ev >= 0 ? "+" : ""}{s.ev.toFixed(1)}%
          </span>
        </>
      ) : (
        // NOT "no edge". Nobody has priced this game, which is a different statement.
        <span className="text-muted-foreground/60">{s.note}</span>
      )}
    </span>
  );
}

export default function MyTeams() {
  const navigate = useNavigate();
  const { user } = useAuth();
  const [view, setView] = useState("teams");
  const [source, setSource] = useState("all");
  const [sort, setSort] = useState("form");
  const [showFilters, setShowFilters] = useState(false);
  const [data, setData] = useState(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    if (!user) return;
    setFailed(false);
    api.myTeams({ sort, source })
      .then(setData)
      .catch(() => setFailed(true));
  }, [sort, source, user]);

  if (!user) {
    return (
      <div className="space-y-3" data-testid="my-teams-page">
        <h1 className="font-head text-3xl font-bold tracking-tight">My Teams</h1>
        <p className="text-muted-foreground text-sm max-w-prose">
          Sign in and follow a few sides, then this ranks them by the shape they are in and
          lists every game they have coming up.
        </p>
      </div>
    );
  }

  const teams = (data?.teams || []).filter((t) => !t.missing);
  const fixtures = data?.fixtures || [];
  const idle = idleTeams(data?.teams);
  const gone = missingTeams(data?.teams);
  const sortHint = SORTS.find((s) => s.v === sort)?.hint;

  return (
    <div className="space-y-3 sm:space-y-5" data-testid="my-teams-page">
      <div>
        <div className="flex items-center gap-2 text-primary mb-1">
          <Bell className="h-4 w-4" />
          <span className="font-mono-data text-xs tracking-widest uppercase">
            Favourites &amp; tracking
          </span>
        </div>
        <h1 className="font-head text-3xl sm:text-4xl font-bold tracking-tight">My Teams</h1>
        <p className="text-muted-foreground text-sm mt-1 max-w-prose">
          Both lists together, ranked by the shape each side is in. Switch to Fixtures for
          every game they have coming up, with the model&apos;s line and the price where one
          is stored.
        </p>
      </div>

      {/* Below sm the controls fold away, with what is applied on the button itself. */}
      <button type="button" onClick={() => setShowFilters((v) => !v)}
        data-testid="my-teams-filter-toggle"
        className="sm:hidden w-full flex items-center gap-2 text-xs text-muted-foreground
          bg-card border border-border rounded-lg px-3 py-2">
        <span className="truncate">{filterSummary({ view, source, sort })}</span>
        <ChevronDown className={`h-3.5 w-3.5 ml-auto shrink-0 transition-transform
          ${showFilters ? "rotate-180" : ""}`} />
      </button>

      <div className={`${showFilters ? "flex" : "hidden"} sm:flex flex-wrap items-center gap-2`}>
        <Tabs value={view} onValueChange={setView}>
          <TabsList className="bg-secondary h-8">
            {VIEWS.map((v) => (
              <TabsTrigger key={v.v} value={v.v} data-testid={`my-teams-view-${v.v}`}
                className="text-xs px-3 h-6">{v.l}</TabsTrigger>
            ))}
          </TabsList>
        </Tabs>
        <Tabs value={source} onValueChange={setSource}>
          <TabsList className="bg-secondary h-8">
            {SOURCES.map((s) => (
              <TabsTrigger key={s.v} value={s.v} data-testid={`my-teams-source-${s.v}`}
                className="text-xs px-3 h-6">
                {s.l}
                {s.v === "favourites" && data ? ` ${data.counts.favourites}` : ""}
                {s.v === "tracking" && data ? ` ${data.counts.tracking}` : ""}
              </TabsTrigger>
            ))}
          </TabsList>
        </Tabs>
        <Select value={sort} onValueChange={setSort}>
          <SelectTrigger data-testid="my-teams-sort"
            className="w-full sm:w-[170px] bg-[#121212] border-border text-xs h-8">
            <SelectValue />
          </SelectTrigger>
          <SelectContent className="bg-[#121212] border-border">
            {SORTS.map((s) => (
              <SelectItem key={s.v} value={s.v} className="text-xs">{s.l}</SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>
      {sortHint ? (
        <p className="text-[11px] text-muted-foreground -mt-1">{sortHint}</p>
      ) : null}

      {failed ? (
        <p className="text-sm text-muted-foreground">
          Could not load your teams just now. Reload and it should come back.
        </p>
      ) : data === null ? (
        <div className="space-y-2">
          {[0, 1, 2].map((i) => (
            <div key={i} className="h-20 bg-card border border-border rounded-lg animate-pulse" />
          ))}
        </div>
      ) : teams.length === 0 ? (
        <p className="text-sm text-muted-foreground max-w-prose">
          Nothing on either list yet. Follow a side with the bell, or start a trial with the
          eye, and they will both show up here.
        </p>
      ) : view === "teams" ? (
        <section className="space-y-2" data-testid="my-teams-teams">
          {teams.map((t) => {
            const f = formTone(t.form_delta);
            const sc = scheduleTone(t.schedule_label);
            return (
              <div key={t.team_id} className="bg-card border border-border rounded-lg p-3"
                data-testid="my-teams-row">
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="font-sans font-medium text-foreground">{t.name}</span>
                  <span className="text-[10px] text-muted-foreground uppercase tracking-wider truncate">
                    {withFlag(t.league_id, t.league_name)}
                  </span>
                  <ListBadge list={t.list} />
                </div>
                <div className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1
                  font-mono-data text-[11px]">
                  <span className={`inline-flex items-center gap-1 ${TONE_CLASS[f.tone]}`}>
                    <ToneIcon tone={f.tone} /> {f.l}
                  </span>
                  <span className="text-muted-foreground">
                    L5 {t.l5 ?? "–"} · L20 {t.l20 ?? "–"}
                  </span>
                  {t.run ? (
                    <span className="text-foreground">{t.run} in a row at {t.line}+</span>
                  ) : null}
                  <span className={`inline-flex items-center gap-1 ${TONE_CLASS[sc.tone]}`}>
                    <ToneIcon tone={sc.tone} /> {sc.l}
                  </span>
                  <span className="text-muted-foreground/60">{t.games_on_file} on file</span>
                </div>
                {(t.next || []).length === 0 ? (
                  <p className="mt-2 text-xs text-muted-foreground">
                    Nothing scheduled in the next {data.within_days} days.
                  </p>
                ) : (
                  <div className="mt-2 pt-1 border-t border-border/50 divide-y divide-border/50">
                    {t.next.map((g) => {
                      const k = kickoff(g.date);
                      return (
                        <button key={g.fixture_id}
                          onClick={() => navigate(`/fixture/${g.fixture_id}`)}
                          data-testid="my-teams-fixture"
                          className="w-full text-left py-1.5 px-1 rounded hover:bg-white/5
                            transition-colors">
                          <span className="flex items-center gap-2">
                            <span className="text-xs text-muted-foreground w-7 shrink-0">
                              {g.is_home ? "vs" : "@"}
                            </span>
                            <span className="text-sm text-foreground truncate">{g.opponent}</span>
                            <span className={`text-[10px] shrink-0
                              ${TONE_CLASS[scheduleTone(g.label).tone]}`}>
                              {g.ratio ? `${g.ratio}×` : ""}
                            </span>
                            <span className="ml-auto text-[11px] text-muted-foreground
                              whitespace-nowrap">{k.day} · {k.time}</span>
                            <ChevronRight className="h-3.5 w-3.5 text-muted-foreground shrink-0" />
                          </span>
                          <span className="flex mt-0.5 pl-9"><BetReadout game={g} /></span>
                        </button>
                      );
                    })}
                  </div>
                )}
              </div>
            );
          })}
        </section>
      ) : fixtures.length === 0 ? (
        <p className="text-sm text-muted-foreground">
          None of your teams have a game in the next {data.within_days} days.
        </p>
      ) : (
        // THE BET SCREEN. One row per game in kick-off order, across every team on both
        // lists — which is the order a weekend is actually planned in, and the thing the
        // per-team view cannot show.
        <section className="bg-card border border-border rounded-lg divide-y divide-border/50"
          data-testid="my-teams-fixtures">
          {fixtures.map((g) => {
            const k = kickoff(g.date);
            const f = formTone(g.form_delta);
            return (
              <button key={`${g.team_id}-${g.fixture_id}`}
                onClick={() => navigate(`/fixture/${g.fixture_id}`)}
                data-testid="my-teams-fixture-row"
                className="w-full text-left p-3 hover:bg-white/5 transition-colors">
                <span className="flex items-center gap-2 flex-wrap">
                  <span className="text-sm font-medium text-foreground">{g.team}</span>
                  <span className="text-xs text-muted-foreground">
                    {g.is_home ? "vs" : "@"} {g.opponent}
                  </span>
                  <ListBadge list={g.list} />
                  <span className="ml-auto text-[11px] text-muted-foreground whitespace-nowrap">
                    {k.day} · {k.time}
                  </span>
                  <ChevronRight className="h-3.5 w-3.5 text-muted-foreground shrink-0" />
                </span>
                <span className="flex flex-wrap items-center gap-x-3 gap-y-1 mt-1">
                  <BetReadout game={g} />
                  <span className={`font-mono-data text-[11px] inline-flex items-center gap-1
                    ${TONE_CLASS[f.tone]}`}>
                    <ToneIcon tone={f.tone} /> {f.l}
                  </span>
                  {g.run ? (
                    <span className="font-mono-data text-[11px] text-foreground">
                      {g.run} in a row
                    </span>
                  ) : null}
                </span>
              </button>
            );
          })}
        </section>
      )}

      {idle.length && view === "teams" ? (
        <p className="text-[11px] text-muted-foreground">
          {idle.length} team{idle.length === 1 ? "" : "s"} with nothing scheduled inside{" "}
          {data.within_days} days.
        </p>
      ) : null}
      {gone.length ? (
        // A follow outliving its team is a maintenance note, not a ranking — see the
        // favourites endpoint, which returns these rather than dropping them so a list
        // that has gone quiet is visible instead of looking empty.
        <p className="text-[11px] text-muted-foreground">
          {gone.length} follow{gone.length === 1 ? "" : "s"} point at a team that is no
          longer syncing.
        </p>
      ) : null}
    </div>
  );
}
