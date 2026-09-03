import { useState } from "react";
import { Bell, BellRing } from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";

// Follow a TEAM, as distinct from starring a fixture.
//
// Deliberately a different icon from the fixture star. They sit on the same screens and
// often on the same row, and two identical stars meaning "save this game" and "follow
// this club forever" is the kind of ambiguity someone only resolves by tapping one and
// finding out. A bell says notify-me-about-them; a star says keep-this-one.
//
// Same behaviour as StarButton otherwise, for the same reasons: shown when signed out so
// the feature is discoverable, and optimistic because a bookmark that waits on a round
// trip feels broken.
export default function TeamStar({ teamId, teamName, className = "" }) {
  const { user, starredTeams, setStarredTeam } = useAuth();
  const [busy, setBusy] = useState(false);
  const on = starredTeams.has(teamId);

  const toggle = async (e) => {
    e.stopPropagation();          // rows are usually links
    e.preventDefault();
    if (!user) {
      toast.message("Sign in to follow teams", {
        description: "Followed teams show their upcoming fixtures on your Saved page.",
      });
      return;
    }
    if (busy) return;
    setBusy(true);
    const next = !on;
    setStarredTeam(teamId, next);   // optimistic
    try {
      if (next) await api.addFavouriteTeam(teamId);
      else await api.removeFavouriteTeam(teamId);
    } catch {
      setStarredTeam(teamId, !next);  // put it back
      toast.error(next ? "Couldn't follow that team" : "Couldn't unfollow that team");
    } finally {
      setBusy(false);
    }
  };

  const Icon = on ? BellRing : Bell;
  return (
    <button
      onClick={toggle}
      disabled={busy}
      data-testid="team-star"
      aria-pressed={on}
      aria-label={on ? `Unfollow ${teamName || "team"}` : `Follow ${teamName || "team"}`}
      title={on ? `Following ${teamName || "this team"} — tap to stop`
                : `Follow ${teamName || "this team"} to see their fixtures on Saved`}
      className={`shrink-0 p-1 rounded transition-colors duration-150 ${
        on ? "text-primary" : "text-muted-foreground/40 hover:text-muted-foreground"
      } ${className}`}
    >
      <Icon className="h-3.5 w-3.5" />
    </button>
  );
}
