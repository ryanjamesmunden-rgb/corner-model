import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { ChevronLeft, ChevronRight, CalendarDays } from "lucide-react";
import { api } from "@/lib/api";
import { withFlag } from "@/lib/countryFlag";
import { kickoffTime } from "@/lib/kickoff";
import TeamStar from "@/components/TeamStar";
import { useAuth } from "@/context/AuthContext";
import {
  WEEKDAYS, PAST, TODAY, UNKNOWN, OUTSIDE,
  buildMonth, monthLabel, shiftMonth, canShift, mineLabel, dayLabel, emptyNote,
  mineDetail,
} from "@/lib/calendarMonth";

/**
 * The month ahead, with the games your teams are in picked out.
 *
 * WHY A MONTH AND NOT ANOTHER BOARD. Every other screen here looks forward in days and
 * answers "what is worth backing soon". None of them answers "when do my teams actually
 * play", which is a question about a month and about six particular sides — and it is the
 * question somebody asks when deciding which evenings to keep free.
 *
 * THE GREY SQUARES ARE THE POINT. A day with no fixtures means one of two completely
 * different things: nobody is playing, or the provider has not published that far ahead.
 * Drawn the same way, an empty Saturday three weeks out reads as a free weekend. The
 * endpoint reports where its fixture list actually stops and everything past it is drawn
 * as unknown and counted in a line under the grid.
 */
const TONE = {
  [PAST]: "bg-card/40 border-border/40 text-muted-foreground/60",
  [TODAY]: "bg-card border-primary text-foreground",
  [UNKNOWN]: "bg-transparent border-dashed border-border/40 text-muted-foreground/40",
  [OUTSIDE]: "bg-transparent border-transparent text-muted-foreground/25",
};
const UPCOMING_TONE = "bg-card border-border text-foreground";

export default function Calendar() {
  const navigate = useNavigate();
  const [month, setMonth] = useState("");
  const [source, setSource] = useState("all");
  const [data, setData] = useState(null);
  const [err, setErr] = useState("");
  const [loading, setLoading] = useState(true);
  const [picked, setPicked] = useState(null);
  const [find, setFind] = useState("");
  const { starredTeams, trackedTeams } = useAuth();

  // FOLLOWING A TEAM HAS TO REDRAW THE MONTH. The bell below the grid is the whole point
  // of this page's empty state, and a star that leaves the grid exactly as it was reads
  // as a control that did nothing. Keyed on the ids rather than on the Set, which is
  // mutated in place, and not on size, which is unchanged by a follow-then-unfollow.
  const mineKey = [...starredTeams, "|", ...trackedTeams].sort().join(",");

  useEffect(() => {
    let live = true;
    setLoading(true);
    setErr("");
    const qs = new URLSearchParams({ source });
    if (month) qs.set("month", month);
    api(`/calendar?${qs}`)
      .then((d) => { if (live) { setData(d); setMonth(d.month); } })
      .catch((e) => { if (live) setErr(e?.message || "Could not load the calendar"); })
      .finally(() => { if (live) setLoading(false); });
    return () => { live = false; };
  }, [month, source, mineKey]);

  const built = useMemo(() => buildMonth(data || {}), [data]);
  const day = useMemo(
    () => (built && picked ? built.squares.find((s) => s.key === picked) : null),
    [built, picked]);

  const step = (by) => {
    if (!data || !canShift(data.month, by, {
      today: data.today, back: data.months_back, ahead: data.months_ahead,
    })) return;
    setPicked(null);
    setMonth(shiftMonth(data.month, by));
  };

  const canBack = data && canShift(data.month, -1, {
    today: data.today, back: data.months_back, ahead: data.months_ahead });
  const canFwd = data && canShift(data.month, 1, {
    today: data.today, back: data.months_back, ahead: data.months_ahead });

  return (
    <div className="mx-auto max-w-4xl px-4 py-6 sm:px-6">
      <div className="mb-4 flex items-center gap-2">
        <CalendarDays className="h-5 w-5 text-primary" />
        <h1 className="text-xl font-semibold">Calendar</h1>
      </div>

      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <button type="button" onClick={() => step(-1)} disabled={!canBack}
            data-testid="cal-prev" aria-label="Previous month"
            className="rounded-lg border border-border p-1.5 disabled:opacity-30">
            <ChevronLeft className="h-4 w-4" />
          </button>
          <span className="min-w-[10rem] text-center text-base font-semibold"
            data-testid="cal-month">
            {built?.label || monthLabel(month) || "—"}
          </span>
          <button type="button" onClick={() => step(1)} disabled={!canFwd}
            data-testid="cal-next" aria-label="Next month"
            className="rounded-lg border border-border p-1.5 disabled:opacity-30">
            <ChevronRight className="h-4 w-4" />
          </button>
        </div>
        <div className="flex gap-1 text-xs">
          {[["all", "All mine"], ["favourites", "Favourites"], ["tracking", "Tracking"],
            ["saved", "Saved games"]]
            .map(([v, l]) => (
              <button key={v} type="button" onClick={() => setSource(v)}
                className={`rounded-full px-3 py-1 border transition-colors ${
                  source === v ? "border-primary text-primary"
                    : "border-border text-muted-foreground hover:text-foreground"}`}>
                {l}
              </button>
            ))}
        </div>
      </div>

      {err && <p className="mb-3 text-sm text-rose-400">{err}</p>}
      {loading && !built && <p className="text-sm text-muted-foreground">Loading…</p>}

      {built && (
        <>
          <div className="grid grid-cols-7 gap-1 text-center text-[10px]
            uppercase tracking-wider text-muted-foreground">
            {WEEKDAYS.map((d) => <span key={d} className="py-1">{d}</span>)}
          </div>
          <div className="grid grid-cols-7 gap-1" data-testid="cal-grid">
            {built.squares.map((s) => (
              <button key={s.key} type="button"
                data-testid="cal-day" data-state={s.state}
                disabled={s.state === OUTSIDE}
                onClick={() => setPicked(s.key === picked ? null : s.key)}
                className={`min-h-[4.25rem] rounded-lg border p-1 text-left
                  transition-colors sm:min-h-[5.5rem]
                  ${TONE[s.state] || UPCOMING_TONE}
                  ${picked === s.key ? "ring-1 ring-primary" : ""}`}>
                <span className="block text-xs font-semibold">{s.day}</span>
                {s.mine.length > 0 && (
                  <span className="mt-0.5 block truncate rounded bg-primary/15 px-1
                    text-[10px] font-semibold text-primary">
                    {mineLabel(s)}
                  </span>
                )}
                {/* The whole card's size, small, so a quiet day is visible as quiet
                    rather than as a day nothing was loaded for. */}
                {s.fixtures > 0 && (
                  <span className="mt-0.5 block text-[10px] text-muted-foreground/70">
                    {s.fixtures}
                  </span>
                )}
              </button>
            ))}
          </div>

          <p className="mt-3 text-xs text-muted-foreground">
            {built.mineCount} game{built.mineCount === 1 ? "" : "s"} for your teams
            {" · "}{built.fixtureCount} fixtures this month
            {/* SAID AS A NUMBER. Greyed squares at the end of a row are easy to miss, and
                the difference between "no games" and "not published yet" is the one thing
                this page must not blur. */}
            {built.unknownDays > 0 && (
              <span className="text-amber-400/90">
                {" · "}{built.unknownDays} day{built.unknownDays === 1 ? "" : "s"} not
                published yet{built.horizon ? ` (fixtures reach ${built.horizon})` : ""}
              </span>
            )}
          </p>

          {day && (
            <div className="mt-4 rounded-xl border border-border bg-card p-3"
              data-testid="cal-detail">
              <p className="mb-2 text-sm font-semibold">{dayLabel(day.key)}</p>
              {day.mine.length === 0 && (
                <p className="text-xs text-muted-foreground">
                  {day.state === UNKNOWN
                    ? "Nothing published for this day yet."
                    : `None of your teams play. ${day.fixtures} fixture${
                      day.fixtures === 1 ? "" : "s"} on the card.`}
                </p>
              )}
              {day.mine.map((g) => (
                <button key={`${g.fixture_id}-${g.team_id}`} type="button"
                  onClick={() => navigate(`/fixture/${g.fixture_id}`)}
                  className="flex w-full items-baseline justify-between gap-3
                    rounded-lg px-1 py-1.5 text-left hover:bg-white/5">
                  <span className="min-w-0">
                    <span className="block truncate text-sm">
                      {g.home_name} v {g.away_name}
                    </span>
                    <span className="block truncate text-[11px] text-muted-foreground">
                      {[withFlag(g.league_id, g.league_name), mineDetail(g)]
                        .filter(Boolean).join("  ·  ")}
                    </span>
                  </span>
                  <span className="shrink-0 text-xs text-muted-foreground">
                    {kickoffTime(g.kickoff)}
                  </span>
                </button>
              ))}
            </div>
          )}

          {built.mineCount === 0 && (
            <p className="mt-4 text-xs text-muted-foreground" data-testid="cal-empty">
              {emptyNote(data, built.label)}
            </p>
          )}

          {/* THE PAGE FIXES ITS OWN EMPTY STATE. Before this, an empty calendar's only
              advice was to go and find a bell somewhere else on the site — and the one
              place it is NOT is the page telling you to look for it. These are the sides
              playing this month, so following one changes the grid you are looking at. */}
          {built.mineCount === 0 && (data?.playing?.length || 0) > 0 && (
            <div className="mt-3 rounded-xl border border-border bg-card p-3"
              data-testid="cal-follow">
              <div className="mb-2 flex flex-wrap items-baseline justify-between gap-2">
                <p className="text-xs font-semibold">Follow a team playing this month</p>
                <input value={find} onChange={(e) => setFind(e.target.value)}
                  placeholder="Find a team…" aria-label="Find a team"
                  className="min-w-0 flex-1 rounded-lg border border-border bg-transparent
                    px-2 py-1 text-xs sm:max-w-[14rem]" />
              </div>
              <div className="flex flex-col gap-0.5">
                {data.playing
                  .filter((t) => t.name.toLowerCase().includes(find.trim().toLowerCase()))
                  .slice(0, 12)
                  .map((t) => (
                    <div key={t.team_id}
                      className="flex items-baseline justify-between gap-3 py-0.5">
                      <span className="min-w-0">
                        <span className="truncate text-sm">{t.name}</span>
                        <span className="ml-2 text-[11px] text-muted-foreground">
                          {withFlag(t.league_id, t.league_name)}
                          {"  ·  "}{t.games} game{t.games === 1 ? "" : "s"}
                        </span>
                      </span>
                      <TeamStar teamId={t.team_id} teamName={t.name} />
                    </div>
                  ))}
              </div>
              {/* Twelve at a time: the list is the month's whole card and scrolling it is
                  not the job — typing is. Said plainly so a missing side looks like a
                  filter to use rather than a team the site does not have. */}
              <p className="mt-2 text-[11px] text-muted-foreground">
                Showing up to 12 — type to find any side playing this month.
              </p>
            </div>
          )}
        </>
      )}
    </div>
  );
}
