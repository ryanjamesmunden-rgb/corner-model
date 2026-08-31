import { useState } from "react";
import { Star } from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";

// Star a fixture now, come back to it when the prices are up.
//
// Signed out the star is still SHOWN, not hidden. Hiding it would leave a signed-out
// visitor with no idea the feature exists; showing it and explaining on tap is how
// somebody finds out there is a reason to sign in.
//
// Optimistic: the star fills immediately and reverts if the request fails. A star that
// waits on a round trip feels broken, and this is a bookmark — the cost of being briefly
// wrong is nil.
export default function StarButton({ fixtureId, onChange, size = "sm" }) {
  const { user, starred, setStarred } = useAuth();
  const [busy, setBusy] = useState(false);
  const on = starred.has(fixtureId);

  const toggle = async (e) => {
    e.stopPropagation();          // the whole row is a link to the fixture
    e.preventDefault();
    if (!user) {
      toast.message("Sign in to save games", {
        description: "Starred games are kept to your account so you can come back to them.",
      });
      return;
    }
    if (busy) return;
    const next = !on;
    setStarred(fixtureId, next);        // optimistic — see the note above
    setBusy(true);
    try {
      await (next ? api.addFavourite(fixtureId) : api.removeFavourite(fixtureId));
      onChange?.(fixtureId, next);
    } catch {
      setStarred(fixtureId, !next);   // put it back — the server does not agree
      toast.error("Could not save that — try again");
    } finally {
      setBusy(false);
    }
  };

  const px = size === "lg" ? "h-5 w-5" : "h-4 w-4";
  return (
    <button onClick={toggle} data-testid="star" data-starred={on ? "1" : "0"}
      aria-label={on ? "Remove from saved games" : "Save this game"}
      title={user ? (on ? "Saved — tap to remove" : "Save this game")
                  : "Sign in to save games"}
      className={`shrink-0 rounded p-1.5 -m-0.5 transition-colors ${
        on ? "text-amber-400 hover:text-amber-300"
           : "text-muted-foreground hover:text-amber-400"}`}>
      <Star className={px} fill={on ? "currentColor" : "none"} />
    </button>
  );
}
