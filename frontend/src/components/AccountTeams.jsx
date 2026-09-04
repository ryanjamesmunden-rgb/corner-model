import { useState, useEffect, useCallback } from "react";
import { Link } from "react-router-dom";
import { BellRing, Plus, Loader2, ChevronRight } from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { flagBullet } from "@/lib/countryFlag";
import { useAuth } from "@/context/AuthContext";
import TeamStar from "@/components/TeamStar";

// "Pick a team" — asked on the account page, and answerable in one tap.
//
// Following teams already existed and almost nobody was doing it, for the ordinary
// reason: the bell only appears next to a team you have already gone looking for, so
// discovering it requires having already found the thing it would have helped you find.
// An account page is where someone looks for the switches, so the ask belongs here.
//
// It ASKS WITH A LIST, not with a sentence. "You can follow teams" sends people off to
// hunt; a row of the best corner sides in the database with their averages on them is
// both the invitation and the answer, and it doubles as a taste of what the site is for.
// The suggestions are the same top-corner-teams ranking the homepage leads with, so the
// first tap follows something worth following rather than whatever is alphabetically
// first.

const HOW_MANY = 8;

const kickoff = (iso) => {
  const d = new Date(iso);
  return `${d.toLocaleDateString(undefined, { weekday: "short", day: "numeric", month: "short" })} · `
    + d.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" });
};

export default function AccountTeams() {
  const { starredTeams, setStarredTeam } = useAuth();
  const [teams, setTeams] = useState(null);
  const [picks, setPicks] = useState(null);
  const [adding, setAdding] = useState(false);
  const [busyId, setBusyId] = useState("");

  const load = useCallback(() => {
    api.favouriteTeams(7).then((d) => setTeams(d.teams || [])).catch(() => setTeams([]));
  }, []);
  useEffect(load, [load]);

  // Suggestions are fetched only once they are wanted — an empty follow list on first
  // load, or the explicit "Follow another". A signed-in member opening their account to
  // cancel should not pay for a team scan on the way.
  const wantPicks = adding || (teams !== null && teams.length === 0);
  useEffect(() => {
    if (!wantPicks || picks !== null) return;
    api.topCornerTeams({ limit: 24 })
      .then((rows) => setPicks(Array.isArray(rows) ? rows : []))
      .catch(() => setPicks([]));
  }, [wantPicks, picks]);

  const follow = async (t) => {
    if (busyId) return;
    setBusyId(t.team_id);
    setStarredTeam(t.team_id, true);        // optimistic, as everywhere else
    try {
      await api.addFavouriteTeam(t.team_id);
      toast.success(`Following ${t.name}`, {
        description: "Their next games show up on Saved.",
      });
      load();
      setAdding(false);
    } catch {
      setStarredTeam(t.team_id, false);
      toast.error("Couldn't follow that team");
    } finally {
      setBusyId("");
    }
  };

  const suggestions = (picks || [])
    .filter((t) => !starredTeams.has(t.team_id))
    .slice(0, HOW_MANY);

  return (
    <section className="bg-card border border-border rounded-lg p-4" data-testid="account-teams">
      <div className="flex items-center gap-2 mb-1">
        <BellRing className="h-4 w-4 text-primary" />
        <h2 className="font-head font-semibold">Your teams</h2>
        {teams?.length > 0 && (
          <span className="font-mono-data text-[10px] text-muted-foreground">{teams.length}</span>
        )}
      </div>

      {teams === null ? (
        <div className="h-10 rounded-md bg-secondary animate-pulse mt-2" />
      ) : teams.length === 0 ? (
        <p className="text-sm text-muted-foreground mb-3">
          Pick a team or two and their fixtures come to you — every game they've got
          coming up, waiting on your Saved page, instead of you scrolling the board to
          find them. Here are some worth watching for corners:
        </p>
      ) : (
        <>
          <p className="text-sm text-muted-foreground mb-3">
            Their next games are on <Link to="/saved" className="text-primary hover:underline">Saved</Link>.
            Tap the bell to stop following.
          </p>
          <div className="divide-y divide-border/50 mb-3">
            {teams.map((t) => (
              <div key={t.team_id} className="flex items-center gap-2 py-2"
                data-testid="account-team">
                <span className="shrink-0">{flagBullet(t.league_id)}</span>
                <span className="text-sm text-foreground truncate">{t.name}</span>
                <span className="ml-auto text-[11px] text-muted-foreground whitespace-nowrap">
                  {t.fixtures?.length
                    ? kickoff(t.fixtures[0].date)
                    : "nothing this week"}
                </span>
                <TeamStar teamId={t.team_id} teamName={t.name} />
              </div>
            ))}
          </div>
        </>
      )}

      {teams !== null && (wantPicks ? (
        picks === null ? (
          <div className="flex items-center gap-2 text-xs text-muted-foreground">
            <Loader2 className="h-3.5 w-3.5 animate-spin" /> Finding teams…
          </div>
        ) : suggestions.length ? (
          <div className="flex flex-wrap gap-2">
            {suggestions.map((t) => (
              <button key={t.team_id} onClick={() => follow(t)} disabled={!!busyId}
                data-testid="account-team-suggestion"
                className="flex items-center gap-1.5 text-xs px-2.5 py-1.5 rounded-full bg-secondary border border-border hover:bg-white/10 transition-colors disabled:opacity-50"
              >
                {busyId === t.team_id
                  ? <Loader2 className="h-3 w-3 animate-spin" />
                  : <Plus className="h-3 w-3 text-muted-foreground" />}
                <span>{flagBullet(t.league_id)} {t.name}</span>
                <span className="font-mono-data text-muted-foreground">
                  {Number(t.won_avg).toFixed(2)}
                </span>
              </button>
            ))}
          </div>
        ) : (
          <p className="text-xs text-muted-foreground">
            Nothing left to suggest — find any side from the{" "}
            <Link to="/scanner" className="text-primary hover:underline">board</Link> and tap its bell.
          </p>
        )
      ) : (
        <button onClick={() => setAdding(true)} data-testid="account-team-add"
          className="flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground transition-colors">
          <Plus className="h-3.5 w-3.5" /> Follow another
          <ChevronRight className="h-3 w-3" />
        </button>
      ))}
    </section>
  );
}
