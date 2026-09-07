import { Lock, ArrowRight } from "lucide-react";
import { Link } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";

// The strip under a preview board that says what is being held back.
//
// It replaces a hard wall, and the difference is the whole point. A wall asks for £20 on
// the strength of an assertion that something good is behind it. A few real rows with
// "and 44 more" underneath makes the same case with evidence: the visitor can see the
// teams, check the records against their own knowledge of the league, and decide whether
// the rest is worth having. The rows do the selling; this only does the asking.
//
// THE COUNT IS THE PERSUASION, so it is only claimed when the server actually said so.
// `total` comes from a response header; when that is missing the copy drops to "the full
// board" rather than inventing a number, because a made-up count on a sales prompt is
// the one number a sceptical buyer would think to check.
//
// Two audiences, two asks — the same split MembersOnly makes. Signed out you need an
// account before you can buy anything; signed in and unpaid you need the subscription.
// Sending the second group to a "create an account" message is how a ready buyer bounces.
export default function PreviewWall({ total, shown, noun = "rows", className = "" }) {
  const { user } = useAuth();
  const hidden = Number.isFinite(total) && Number.isFinite(shown) ? total - shown : null;

  return (
    <div className={`border-t border-border bg-secondary/30 px-4 py-4 text-center ${className}`}
      data-testid="preview-wall">
      <div className="flex items-center justify-center gap-2 text-muted-foreground">
        <Lock className="h-3.5 w-3.5" />
        <span className="text-sm">
          {hidden && hidden > 0
            ? <>Showing {shown} of {total}. <span className="text-foreground">{hidden} more {noun}</span> for members.</>
            : <>You're seeing a sample. <span className="text-foreground">The full board</span> is for members.</>}
        </span>
      </div>

      <p className="mt-1.5 text-xs text-muted-foreground max-w-md mx-auto leading-relaxed">
        {user
          ? "Your account is set up — subscribing unlocks every board on the site, and you can cancel from your account page any time."
          : "Sign in with Google at the top right to create a free account, then subscribe to see the lot."}
      </p>

      <Link to="/join" data-testid="preview-wall-join"
        className="mt-3 inline-flex items-center gap-1.5 text-sm font-semibold px-4 py-2 rounded-md bg-primary text-black hover:opacity-90 transition-opacity">
        See what's included <ArrowRight className="h-3.5 w-3.5" />
      </Link>
    </div>
  );
}
