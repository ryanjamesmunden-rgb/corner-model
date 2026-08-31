import { useState, useEffect, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { Star, ChevronRight } from "lucide-react";
import { api } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import StarButton from "@/components/StarButton";

// The games you starred, to come back to once prices are up.
//
// The whole point of the feature: scan the week ahead when there is time, then return
// later and go straight to the handful that mattered instead of re-scanning everything.

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

  const load = useCallback(() => {
    if (!user) { setRows([]); return; }
    api.favourites()
      .then((d) => { setRows(d.favourites || []); setMissing(d.missing || 0); })
      .catch(() => setRows([]));
  }, [user]);

  useEffect(() => { if (ready) load(); }, [ready, load]);

  const drop = (fixtureId) => setRows((r) => (r || []).filter((f) => f.fixture_id !== fixtureId));

  if (!ready) return null;

  if (!user) {
    return (
      <div className="bg-card border border-border rounded-lg py-16 text-center" data-testid="saved-signed-out">
        <Star className="h-6 w-6 text-muted-foreground/50 mx-auto" />
        <h1 className="font-head font-semibold text-lg mt-3">Saved games</h1>
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
        <h1 className="font-head text-3xl font-bold tracking-tight">Your games</h1>
        <p className="text-muted-foreground text-sm mt-1">
          Starred fixtures, soonest first. Open one when the prices are up and enter what you can get.
        </p>
      </div>

      {rows === null ? (
        <div className="space-y-2">{[0, 1, 2].map((i) =>
          <div key={i} className="h-14 rounded-md bg-secondary animate-pulse" />)}</div>
      ) : !rows.length ? (
        <div className="bg-card border border-border rounded-lg py-16 text-center" data-testid="saved-empty">
          <p className="text-sm text-muted-foreground">
            Nothing saved yet. Tap the star on any fixture to keep it here.
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
                    {f.league_id}{f.round && f.round !== "Upcoming" ? ` · ${f.round}` : ""}
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
