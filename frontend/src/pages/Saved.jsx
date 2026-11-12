import { useState, useEffect, useCallback, useMemo } from "react";
import { useNavigate } from "react-router-dom";
import { Star, ChevronRight, BellRing } from "lucide-react";
import { api } from "@/lib/api";
import { withFlag } from "@/lib/countryFlag";
import { useAuth } from "@/context/AuthContext";
import StarButton from "@/components/StarButton";
import TeamStar from "@/components/TeamStar";
import TeamFormChart from "@/components/TeamFormChart";
import { SAVED_SORTS, VENUES, MIN_RANK_GAMES, formView, rankTeams } from "@/lib/teamForm";

// The games you starred, to come back to once prices are up.
//
// The whole point of the feature: scan the week ahead when there is time, then return
// later and go straight to the handful that mattered instead of re-scanning everything.

// The sort survives a reload: someone who ranks by last 5 wants it that way next visit.
// Storage can throw (private mode, blocked cookies), so it is best-effort only.
const PREF_KEY = "saved-team-sort";
const readPref = () => {
  try {
    const p = JSON.parse(window.localStorage.getItem(PREF_KEY) || "null");
    const ok = p && SAVED_SORTS.some((o) => o.key === p.sort) && VENUES.some((o) => o.key === p.venue);
    return ok ? p : { sort: "next", venue: "all" };
  } catch { return { sort: "next", venue: "all" }; }
};
const writePref = (p) => {
  try { window.localStorage.setItem(PREF_KEY, JSON.stringify(p)); } catch { /* ignore */ }
};

function Chips({ options, value, onChange, testId }) {
  return (
    <div className="flex rounded-md bg-secondary p-0.5" data-testid={testId}>
      {options.map((o) => (
        <button key={o.key} type="button" onClick={() => onChange(o.key)}
          data-testid={`${testId}-${o.key}`} aria-pressed={value === o.key}
          className={`text-[11px] px-2 py-1 rounded transition-colors whitespace-nowrap ${
            value === o.key ? "bg-primary text-primary-foreground font-medium" : "text-muted-foreground"}`}>
          {o.label}
        </button>
      ))}
    </div>
  );
}

const kickoff = (iso) => {
  const d = new Date(iso);
  return {
    day: d.toLocaleDateString(undefined, { weekday: "short", day: "numeric", month: "short" }),
    time: d.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" }),
  };
};

export default function Saved() {
  const navigate = useNavigate();
  const { user, ready } = useAuth();
  const [rows, setRows] = useState(null);
  const [missing, setMissing] = useState(0);
  // Followed teams and their upcoming games. Loaded separately from starred fixtures so
  // a failure in one leaves the other on screen.
  const [teams, setTeams] = useState([]);
  const [pref, setPref] = useState(readPref);
  const setSort = (sort) => { const p = { ...pref, sort }; setPref(p); writePref(p); };
  const setVenue = (venue) => { const p = { ...pref, venue }; setPref(p); writePref(p); };
  const ranked = useMemo(() => rankTeams(teams, { sort: pref.sort, venue: pref.venue }),
    [teams, pref]);

  const load = useCallback(() => {
    if (!user) { setRows([]); return; }
    api.favourites()
      .then((d) => { setRows(d.favourites || []); setMissing(d.missing || 0); })
      .catch(() => setRows([]));
    api.favouriteTeams()
      .then((d) => setTeams(d.teams || []))
      .catch(() => setTeams([]));
  }, [user]);

  useEffect(() => { if (ready) load(); }, [ready, load]);

  const drop = (fixtureId) => setRows((r) => (r || []).filter((f) => f.fixture_id !== fixtureId));

  if (!ready) return null;

  if (!user) {
    return (
      <div className="bg-card border border-border rounded-lg py-16 text-center" data-testid="saved-signed-out">
        <Star className="h-6 w-6 text-muted-foreground/50 mx-auto" />
        <h1 className="font-head font-semibold text-lg mt-3">Saved games and teams</h1>
        <p className="text-sm text-muted-foreground mt-1 max-w-sm mx-auto">
          Sign in to star fixtures while you scan the week, then come back to just those
          once the prices are up. Sign-in is in the top right.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-2.5 sm:space-y-4" data-testid="saved-page">
      <div>
        <div className="flex items-center gap-2 text-amber-400 mb-1">
          <Star className="h-4 w-4" fill="currentColor" />
          <span className="font-mono-data text-xs tracking-widest uppercase">Saved</span>
        </div>
        <h1 className="font-head text-3xl font-bold tracking-tight">Saved</h1>
        <p className="text-muted-foreground text-sm mt-1">
          Starred fixtures, soonest first. Open one when the prices are up and enter what you can get.
        </p>
      </div>

      {/* FOLLOWED TEAMS, above the starred games. Someone following a club wants the run
          of fixtures coming up, not one game — that is the whole difference between
          following a team and starring a fixture, and showing only the next match would
          make the two features the same thing with different icons. */}
      {teams.length > 0 && (
        <section className="space-y-2" data-testid="saved-teams">
          <div className="flex items-center gap-2">
            <BellRing className="h-4 w-4 text-primary" />
            <h2 className="font-head font-semibold text-lg">Teams you follow</h2>
            <span className="font-mono-data text-[10px] text-muted-foreground">{teams.length}</span>
          </div>
          {/* Rank by recent corners won. Kick-off is the default because following a
              side is first about what they have coming up. */}
          <div className="flex flex-wrap items-center gap-2" data-testid="saved-team-sort">
            <span className="text-[11px] text-muted-foreground">Sort</span>
            <Chips options={SAVED_SORTS} value={pref.sort} onChange={setSort} testId="saved-sort" />
            {pref.sort !== "next" && (
              <Chips options={VENUES} value={pref.venue} onChange={setVenue} testId="saved-venue" />
            )}
          </div>
          {ranked.map((t, i) => {
            const v = pref.sort === "next" ? null
              : formView(t.form, { venue: pref.venue, window: pref.sort, metric: "won" });
            return (
            <div key={t.team_id} className="bg-card border border-border rounded-lg p-3"
              data-testid="saved-team">
              <div className="flex items-center gap-2">
                <span className="font-sans font-medium text-foreground">{t.name}</span>
                <span className="text-[10px] text-muted-foreground uppercase tracking-wider truncate">
                  {withFlag(t.league_id, t.league_name)}
                </span>
                <TeamStar teamId={t.team_id} teamName={t.name} className="ml-auto" />
              </div>
              {v && (
                <p className="mt-1 font-mono-data text-[11px]" data-testid="saved-team-score">
                  <span className="text-muted-foreground">#{i + 1} · </span>
                  {v.avg == null ? (
                    <span className="text-muted-foreground">no {pref.venue !== "all" ? `${pref.venue} ` : ""}games on file</span>
                  ) : (
                    <>
                      <span className="text-primary font-semibold">{v.avg.toFixed(1)}</span>
                      <span className="text-muted-foreground"> corners won a game · last {v.n}
                        {pref.venue !== "all" ? ` ${pref.venue}` : ""}
                        {v.n < MIN_RANK_GAMES ? " (too few to rank)" : ""}</span>
                    </>
                  )}
                </p>
              )}
              {/* THE FIXTURES COME FIRST, and that is a correction rather than a preference.
                  Following a side has always answered "what have they got coming up" —
                  the favourites endpoint returns the next few games precisely because
                  one game would just be a slower fixture star — and putting a
                  twenty-game chart above that list replaced the answer with the
                  evidence for it. The form is still here, one tap down. */}
              {t.fixtures.length === 0 ? (
                <p className="mt-3 text-xs text-muted-foreground">
                  Nothing scheduled in the next 30 days.
                </p>
              ) : (
                <div className="mt-3 pt-1 border-t border-border/50 divide-y divide-border/50">
                  {t.fixtures.slice(0, 5).map((f) => {
                    const k = kickoff(f.date);
                    return (
                      <button key={f.fixture_id}
                        onClick={() => navigate(`/fixture/${f.fixture_id}`)}
                        data-testid="saved-team-fixture"
                        className="w-full flex items-center gap-2 py-1.5 px-1 text-left rounded hover:bg-white/5 transition-colors"
                      >
                        <span className="text-xs text-muted-foreground w-8 shrink-0">
                          {f.is_home ? "vs" : "@"}
                        </span>
                        <span className="text-sm text-foreground truncate">{f.opponent}</span>
                        <span className="ml-auto text-[11px] text-muted-foreground whitespace-nowrap">
                          {k.day} · {k.time}
                        </span>
                        <ChevronRight className="h-3.5 w-3.5 text-muted-foreground shrink-0" />
                      </button>
                    );
                  })}
                </div>
              )}
              <details className="mt-3 group">
                <summary className="text-[11px] text-muted-foreground cursor-pointer
                  list-none flex items-center gap-1 hover:text-foreground transition-colors">
                  <ChevronRight className="h-3 w-3 transition-transform group-open:rotate-90" />
                  Corner form — last 20 games
                </summary>
                <TeamFormChart form={t.form} teamName={t.name} />
              </details>
            </div>
            );
          })}
        </section>
      )}

      {rows === null ? (
        <div className="space-y-2">{[0, 1, 2].map((i) =>
          <div key={i} className="h-14 rounded-md bg-secondary animate-pulse" />)}</div>
      ) : !rows.length ? (
        <div className="bg-card border border-border rounded-lg py-16 text-center" data-testid="saved-empty">
          <p className="text-sm text-muted-foreground">
            Nothing saved yet. Tap the star on a fixture to keep it here, or the bell on
            a team to follow their fixtures.
          </p>
        </div>
      ) : (
        <div className="bg-card border border-border rounded-lg divide-y divide-border">
          {rows.map((f) => {
            const k = kickoff(f.date);
            return (
              <div key={f.fixture_id} data-testid="saved-row" role="button" tabIndex={0}
                onClick={() => navigate(`/fixture/${f.fixture_id}`)}
                onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && navigate(`/fixture/${f.fixture_id}`)}
                className="w-full cursor-pointer text-left px-3 py-2.5 sm:px-4 sm:py-3 hover:bg-white/5 transition-colors flex items-center gap-2 sm:gap-3">
                <StarButton fixtureId={f.fixture_id} onChange={drop} />
                <div className="font-mono-data text-[11px] text-muted-foreground w-20 shrink-0 leading-tight">
                  {k.day}<br />{k.time}
                </div>
                <div className="min-w-0 flex-1">
                  <p className="font-sans font-medium text-sm truncate">
                    {f.home_name} <span className="text-muted-foreground font-normal">v</span> {f.away_name}
                  </p>
                  <p className="text-[10px] text-muted-foreground uppercase tracking-wider mt-0.5">
                    {withFlag(f.league_id, f.league_id)}{f.round && f.round !== "Upcoming" ? ` · ${f.round}` : ""}
                  </p>
                </div>
                <ChevronRight className="h-4 w-4 text-muted-foreground shrink-0" />
              </div>
            );
          })}
        </div>
      )}

      {/* A star can outlive its fixture: the sync rebuilds db.fixtures every run, so a
          played game leaves the star pointing at nothing. Said out loud, because a star
          that quietly disappeared looks like it was never saved. */}
      {missing > 0 && (
        <p className="text-xs text-muted-foreground" data-testid="saved-missing">
          {missing} saved {missing === 1 ? "game is" : "games are"} no longer in the fixture list —
          they have most likely been played.
        </p>
      )}
    </div>
  );
}
