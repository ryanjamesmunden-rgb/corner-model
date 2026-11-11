import { useState } from "react";
import { Bell, BellRing, Eye } from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";

// Two team buttons, side by side: TRACK (eye) and FOLLOW (bell).
//
// Tracking is a trial list — keep an eye on a side without committing to it. Following is
// the favourites list. The eye only shows while a team is NOT followed: once it has proven
// itself and been promoted, watching it on trial as well would mean nothing.
//
// Tapping the bell on a tracked team PROMOTES it — follows it and takes it off the trial
// list in one step — so a side can never sit on both lists.
//
// Both are deliberately different icons from the fixture star: a star keeps one game, a
// bell or an eye is about a club. Shown when signed out so the feature is discoverable,
// and optimistic because a bookmark that waits on a round trip feels broken.
export default function TeamStar({ teamId, teamName, className = "" }) {
  const { user, starredTeams, setStarredTeam, trackedTeams, setTrackedTeam } = useAuth();
  const [busy, setBusy] = useState(false);
  const on = starredTeams.has(teamId);
  const tracked = trackedTeams.has(teamId);
  const name = teamName || "this team";

  const needUser = (what) => {
    toast.message(`Sign in to ${what} teams`, {
      description: "Tracked and followed teams get their own corner form graph on the Form page.",
    });
  };

  const toggleFollow = async (e) => {
    e.stopPropagation();          // rows are usually links
    e.preventDefault();
    if (!user) return needUser("follow");
    if (busy) return;
    setBusy(true);
    const next = !on;
    const wasTracked = tracked;
    setStarredTeam(teamId, next);   // optimistic
    if (next && wasTracked) setTrackedTeam(teamId, false);
    try {
      if (next && wasTracked) {
        await api.promoteTrackedTeam(teamId);
        toast.success(`${teamName || "Team"} moved to favourites`);
      } else if (next) await api.addFavouriteTeam(teamId);
      else await api.removeFavouriteTeam(teamId);
    } catch {
      setStarredTeam(teamId, !next);  // put it back
      if (next && wasTracked) setTrackedTeam(teamId, true);
      toast.error(next ? "Couldn't follow that team" : "Couldn't unfollow that team");
    } finally {
      setBusy(false);
    }
  };

  const toggleTrack = async (e) => {
    e.stopPropagation();
    e.preventDefault();
    if (!user) return needUser("track");
    if (busy) return;
    setBusy(true);
    const next = !tracked;
    setTrackedTeam(teamId, next);
    try {
      if (next) {
        await api.addTrackedTeam(teamId);
        toast.success(`Tracking ${teamName || "team"}`, {
          description: "Watch their form on the Form page. Tap the bell once they've proven themselves.",
        });
      } else await api.removeTrackedTeam(teamId);
    } catch {
      setTrackedTeam(teamId, !next);
      toast.error(next ? "Couldn't track that team" : "Couldn't stop tracking that team");
    } finally {
      setBusy(false);
    }
  };

  const BellIcon = on ? BellRing : Bell;
  return (
    <span className={`shrink-0 inline-flex items-center ${className}`}>
      {!on && (
        <button
          onClick={toggleTrack}
          disabled={busy}
          data-testid="team-track"
          aria-pressed={tracked}
          aria-label={tracked ? `Stop tracking ${name}` : `Track ${name}`}
          title={tracked ? `Tracking ${name} — tap to stop`
                         : `Track ${name}: keep an eye on them before making them a favourite`}
          className={`p-1 rounded transition-colors duration-150 ${
            tracked ? "text-amber-400" : "text-muted-foreground/40 hover:text-muted-foreground"}`}
        >
          <Eye className="h-3.5 w-3.5" />
        </button>
      )}
      <button
        onClick={toggleFollow}
        disabled={busy}
        data-testid="team-star"
        aria-pressed={on}
        aria-label={on ? `Unfollow ${name}` : tracked ? `Move ${name} to favourites` : `Follow ${name}`}
        title={on ? `Favourite — tap to stop following ${name}`
                  : tracked ? `Proven? Tap to move ${name} from tracking to favourites`
                            : `Follow ${name} as a favourite`}
        className={`p-1 rounded transition-colors duration-150 ${
          on ? "text-primary" : "text-muted-foreground/40 hover:text-muted-foreground"}`}
      >
        <BellIcon className="h-3.5 w-3.5" />
      </button>
    </span>
  );
}
