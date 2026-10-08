import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { useSearchParams } from "react-router-dom";
import { Loader2, ChevronRight, Flame, TrendingUp, TrendingDown, Globe } from "lucide-react";
import { api } from "@/lib/api";
import { kickoffLabel } from "@/lib/kickoff";
import { flagFor } from "@/lib/countryFlag";
import ErrorBoundary from "@/components/ErrorBoundary";

/**
 * The front door: what is on, and where.
 *
 * EVERY OTHER BOARD ANSWERS "WHAT SHOULD I BET", which assumes the reader has already
 * decided to be shown a selection. The site opened on one of those, and a visitor who
 * simply wanted to look up a game had to work out which of five screens was the index.
 * This is the index, in the shape football is organised in: country, competition, games.
 *
 * IT EXPANDS IN PLACE RATHER THAN NAVIGATING. Comparing England with Norway means having
 * both open at once, which a page per league cannot do — and the back button is not a
 * browsing tool. Everything is in one payload, so opening a row costs nothing.
 *
 * THE FILTER REMOVES GAMES, it does not restyle them. "Streaks" and "Trends" are shorter
 * lists, and the counts beside every country and league follow the filter — a league
 * reading "12" that opens to two is worse than one reading two, because the count is what
 * a reader decides to open on.
 */

const DAYS = [3, 7, 14, 28];

/**
 * The flag for a country row.
 *
 * DERIVED FROM A LEAGUE ID, NOT THE COUNTRY NAME, because that is what countryFlag.js is
 * keyed on and its note says why: ids carry a stable three-letter country prefix, while
 * names collide across borders. A second lookup keyed on the name would be a second map
 * to keep in step, and the one it disagreed with would be the one nobody tested.
 *
 * The backend sorts cups last, so leagues[0] is a domestic competition wherever one
 * exists — and where none does, the group IS the European competitions and the trophy
 * countryFlag returns for them is the right badge anyway.
 */
const countryFlag = (country) => flagFor(country?.leagues?.[0]?.league_id || "");

/** "Sat 11 Oct", and "Today" / "Tomorrow" where that is friendlier to scan. */
const dayChipLabel = (iso) => {
  const d = new Date(`${iso}T12:00:00`);
  const today = new Date();
  const diff = Math.round((d - new Date(today.getFullYear(), today.getMonth(), today.getDate(), 12))
                          / 86400000);
  if (diff === 0) return "Today";
  if (diff === 1) return "Tomorrow";
  return d.toLocaleDateString(undefined, { weekday: "short", day: "numeric", month: "short" });
};

const SHOWS = [
  { v: "all", label: "All games",
    blurb: "Every fixture in the window." },
  { v: "streaks", label: "Streaks",
    blurb: "Only games with a live run going in, at a line above what the division does." },
  { v: "trends", label: "Trends",
    blurb: "Only games where a side's corner rate has moved from its own norm." },
];

const TrendMark = ({ direction }) =>
  direction === "up"
    ? <TrendingUp className="h-3.5 w-3.5 text-tone-strong-fg" />
    : <TrendingDown className="h-3.5 w-3.5 text-amber-400" />;

function Game({ game, onOpen }) {
  return (
    <button
      onClick={onOpen}
      data-testid={`browse-game-${game.fixture_id}`}
      className="w-full text-left px-3 py-2.5 rounded-md hover:bg-secondary/60
                 transition-colors border border-transparent hover:border-border"
    >
      <div className="flex items-baseline gap-2 flex-wrap">
        <span className="text-sm font-medium">{game.home}</span>
        <span className="text-[11px] text-muted-foreground">v</span>
        <span className="text-sm font-medium">{game.away}</span>
        <span className="ml-auto text-[11px] text-muted-foreground font-mono-data">
          {kickoffLabel(game.date)}
        </span>
      </div>
      {/* WHY THIS ROW IS ON A FILTERED LIST. Surviving a filter is not a reason; the run
          or the direction of travel is, and it is the thing worth opening the game for. */}
      {(game.streak || (game.trends || []).length > 0) && (
        <div className="flex items-center gap-3 flex-wrap mt-1">
          {game.streak && (
            <span className="flex items-center gap-1 text-[11px] text-tone-streak-fg">
              <Flame className="h-3 w-3" />
              {game.streak.team} {game.streak.line_label} · {game.streak.run} in a row
            </span>
          )}
          {(game.trends || []).map((t) => (
            <span key={t.team} className="flex items-center gap-1 text-[11px] text-muted-foreground">
              <TrendMark direction={t.direction} />
              {t.team} corners {t.direction}
            </span>
          ))}
        </div>
      )}
    </button>
  );
}

function League({ league, open, onToggle }) {
  const navigate = useNavigate();
  return (
    <div className="border-t border-border/60">
      <button
        onClick={onToggle}
        data-testid={`browse-league-${league.league_id}`}
        className="w-full flex items-center gap-2 px-3 py-2.5 hover:bg-secondary/40
                   transition-colors text-left"
      >
        <ChevronRight className={`h-3.5 w-3.5 text-muted-foreground transition-transform
                                  ${open ? "rotate-90" : ""}`} />
        <span className="text-sm">{league.name}</span>
        {league.tier > 1 && (
          <span className="text-[10px] text-muted-foreground font-mono-data">T{league.tier}</span>
        )}
        {league.is_cup && (
          <span className="text-[10px] px-1.5 py-0.5 rounded border border-border
                           text-muted-foreground">cup</span>
        )}
        <span className="ml-auto font-mono-data text-xs text-muted-foreground">
          {league.count}
        </span>
      </button>
      {open && (
        <div className="px-2 pb-2 space-y-0.5">
          {/* AN EMPTY LEAGUE IS KEPT AND SAYS SO. Dropping it would reshuffle the list
              every time the filter changed, moving the row you were about to tap. */}
          {league.count === 0
            ? <p className="px-3 py-2 text-[11px] text-muted-foreground">
                Nothing matches this filter here.
              </p>
            : league.games.map((g) => (
                <Game key={g.fixture_id} game={g}
                      onOpen={() => navigate(`/fixture/${g.fixture_id}`)} />
              ))}
        </div>
      )}
    </div>
  );
}

function Country({ country, open, onToggle, openLeagues, toggleLeague }) {
  return (
    <section className="bg-card border border-border rounded-lg overflow-hidden"
             data-testid={`browse-country-${country.country}`}>
      <button
        onClick={onToggle}
        className="w-full flex items-center gap-2.5 px-4 py-3 hover:bg-secondary/40
                   transition-colors text-left"
      >
        <ChevronRight className={`h-4 w-4 text-muted-foreground transition-transform
                                  ${open ? "rotate-90" : ""}`} />
        <span className="text-base leading-none" aria-hidden="true">{countryFlag(country)}</span>
        <span className="font-head font-semibold text-sm">{country.country}</span>
        <span className="text-[11px] text-muted-foreground">
          {country.leagues.length} competition{country.leagues.length === 1 ? "" : "s"}
        </span>
        <span className="ml-auto font-mono-data text-sm text-primary">{country.count}</span>
      </button>
      {open && country.leagues.map((l) => (
        <League key={l.league_id} league={l}
                open={!!openLeagues[l.league_id]}
                onToggle={() => toggleLeague(l.league_id)} />
      ))}
    </section>
  );
}

function BrowseBoard() {
  const [params, setParams] = useSearchParams();
  const show = SHOWS.some((s) => s.v === params.get("show")) ? params.get("show") : "all";
  const days = DAYS.includes(Number(params.get("days"))) ? Number(params.get("days")) : 7;
  // One date inside the window, as YYYY-MM-DD in London. Empty means the whole window.
  const day = /^\d{4}-\d{2}-\d{2}$/.test(params.get("day") || "") ? params.get("day") : "";
  // Open rows live in component state rather than the URL: which countries you have
  // expanded is a reading position, not a thing to share or to restore a week later.
  const [openCountries, setOpenCountries] = useState({});
  const [openLeagues, setOpenLeagues] = useState({});

  const setBoth = (patch) => {
    const next = new URLSearchParams(params);
    Object.entries(patch).forEach(([k, v]) => {
      if (v === "" || v === null || v === undefined) next.delete(k);
      else next.set(k, String(v));
    });
    setParams(next, { replace: true });
  };
  const set = (k, v) => setBoth({ [k]: v });

  const { data, isLoading, error } = useQuery({
    queryKey: ["browse", days, show, day],
    queryFn: () => api.browse({ days, show, ...(day ? { day } : {}) }),
    keepPreviousData: true,
  });

  const blurb = SHOWS.find((s) => s.v === show)?.blurb;

  return (
    <div className="space-y-4" data-testid="browse-page">
      <div>
        <div className="flex items-center gap-2 text-primary mb-1">
          <Globe className="h-4 w-4" />
          <span className="font-mono-data text-xs tracking-widest uppercase">What's on</span>
        </div>
        <h1 className="font-head text-3xl sm:text-4xl font-bold tracking-tight">Fixtures</h1>
        <p className="text-sm text-muted-foreground mt-1 max-w-2xl">
          Every competition the model carries, by country. Open one to see what is coming up.
        </p>
      </div>

      <div className="flex items-center gap-2 flex-wrap">
        <div className="flex rounded-md bg-secondary p-0.5">
          {SHOWS.map((s) => (
            <button key={s.v} onClick={() => set("show", s.v)}
              data-testid={`browse-show-${s.v}`}
              className={`text-xs px-3 py-1.5 rounded transition-colors ${
                show === s.v ? "bg-primary text-primary-foreground font-medium"
                             : "text-muted-foreground"}`}>
              {s.label}
            </button>
          ))}
        </div>
        <div className="flex rounded-md bg-secondary p-0.5">
          {DAYS.map((d) => (
            <button key={d} onClick={() => setBoth({ days: d, day: "" })}
              data-testid={`browse-days-${d}`}
              className={`text-xs px-2.5 py-1.5 rounded transition-colors ${
                days === d ? "bg-primary text-primary-foreground font-medium"
                           : "text-muted-foreground"}`}>
              {d}d
            </button>
          ))}
        </div>
        {data && (
          <span className="text-[11px] text-muted-foreground ml-auto font-mono-data">
            {data.total} game{data.total === 1 ? "" : "s"}
          </span>
        )}
      </div>
      {/* ONE DAY, OR THE WHOLE WINDOW. The chips are built from the window BEFORE the day
          filter is applied, so picking Saturday still shows that Sunday has eleven on —
          a filter that hides what else exists makes you clear it to find out. */}
      {(data?.calendar || []).length > 1 && (
        <div className="flex gap-1.5 overflow-x-auto pb-1 -mx-1 px-1">
          <button onClick={() => set("day", "")} data-testid="browse-day-all"
            className={`shrink-0 text-xs px-3 py-1.5 rounded-md transition-colors ${
              !day ? "bg-primary text-primary-foreground font-medium"
                   : "bg-secondary text-muted-foreground"}`}>
            All {days}d
          </button>
          {data.calendar.map((c) => (
            <button key={c.day} onClick={() => set("day", c.day)}
              data-testid={`browse-day-${c.day}`}
              className={`shrink-0 text-xs px-3 py-1.5 rounded-md transition-colors
                          flex items-center gap-1.5 ${
                day === c.day ? "bg-primary text-primary-foreground font-medium"
                              : "bg-secondary text-muted-foreground"}`}>
              {dayChipLabel(c.day)}
              <span className="font-mono-data opacity-70">{c.count}</span>
            </button>
          ))}
        </div>
      )}
      {blurb && <p className="text-[11px] text-muted-foreground">{blurb}</p>}

      {isLoading && !data ? (
        <div className="flex items-center gap-2 text-muted-foreground text-sm py-8">
          <Loader2 className="h-4 w-4 animate-spin" /> Loading fixtures…
        </div>
      ) : error ? (
        <p className="text-sm text-muted-foreground py-8">
          Could not load the fixture list. Try again in a moment.
        </p>
      ) : !data?.countries?.length ? (
        <p className="text-sm text-muted-foreground py-8" data-testid="browse-empty">
          Nothing {day ? `on ${dayChipLabel(day)}` : `in the next ${days} days`} matches this filter.
        </p>
      ) : (
        <div className="space-y-2">
          {data.countries.map((c) => (
            <Country key={c.country} country={c}
              open={!!openCountries[c.country]}
              onToggle={() => setOpenCountries((o) => ({ ...o, [c.country]: !o[c.country] }))}
              openLeagues={openLeagues}
              toggleLeague={(id) => setOpenLeagues((o) => ({ ...o, [id]: !o[id] }))} />
          ))}
        </div>
      )}
    </div>
  );
}

export default function Browse() {
  return <ErrorBoundary><BrowseBoard /></ErrorBoundary>;
}
