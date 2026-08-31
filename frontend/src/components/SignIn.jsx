import { useEffect, useRef } from "react";
import { LogOut } from "lucide-react";
import { useAuth } from "@/context/AuthContext";

// Sign-in for the header. Renders nothing at all until the client id has arrived, so a
// site with sign-in unconfigured looks finished rather than broken — the button simply
// is not there, instead of being there and failing when tapped.
export default function SignIn({ compact = false }) {
  const { user, ready, clientId, signOut, renderButton } = useAuth();
  const slot = useRef(null);

  useEffect(() => { if (!user) renderButton(slot.current); }, [user, renderButton, clientId]);

  if (!ready) return null;

  if (user) {
    return (
      <div className="flex items-center gap-2" data-testid="signed-in">
        {user.picture ? (
          <img src={user.picture} alt="" referrerPolicy="no-referrer"
            className="h-6 w-6 rounded-full border border-border" />
        ) : (
          <span className="h-6 w-6 rounded-full bg-secondary border border-border grid place-items-center text-[10px]">
            {(user.name || "?").slice(0, 1).toUpperCase()}
          </span>
        )}
        {!compact && (
          <span className="text-xs text-muted-foreground max-w-[110px] truncate">{user.name}</span>
        )}
        <button onClick={signOut} title="Sign out" data-testid="sign-out"
          className="text-muted-foreground hover:text-foreground">
          <LogOut className="h-3.5 w-3.5" />
        </button>
      </div>
    );
  }

  // Google draws its own button into this node — it will not accept a styled one of ours.
  return <div ref={slot} data-testid="sign-in" className="min-h-[32px]" />;
}
