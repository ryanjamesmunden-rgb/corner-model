import { UserPlus } from "lucide-react";
import { useAuth } from "@/context/AuthContext";

// Wraps a screen that needs an ACCOUNT but not a subscription.
//
// WHY THIS IS NOT MembersOnly. That component asks for £20, and asking for money is the
// wrong next step when the actual next step is free. Someone who has never signed in and
// is shown a price has been told the door is locked; someone shown "sign in, it's free"
// has been told where the handle is. The two states already answer with different HTTP
// codes — 401 here, 402 there — and the screens have to match, or the code is doing work
// the interface throws away.
//
// It says what is behind it rather than only refusing. "Sign in to continue" tells you
// nothing about whether it is worth the thirty seconds; naming what is in there does.
export default function SignedInOnly({ title, blurb, children }) {
  const { user, ready } = useAuth();

  // Until the session resolves everyone looks signed out, and flashing a wall at someone
  // who is already signed in is a worse first impression than showing it a beat late.
  if (!ready) return null;
  if (user) return children;

  return (
    <div className="bg-card border border-border rounded-lg p-6 sm:p-10 text-center"
      data-testid="signed-in-only">
      <div className="h-10 w-10 rounded-full bg-secondary border border-border grid place-items-center mx-auto">
        <UserPlus className="h-4 w-4 text-muted-foreground" />
      </div>
      <h2 className="font-head font-semibold text-xl mt-4">{title}</h2>
      <p className="text-sm text-muted-foreground mt-2 max-w-md mx-auto leading-relaxed">{blurb}</p>
      <p className="mt-5 text-sm text-muted-foreground">
        <span className="text-foreground">It's free.</span> Sign in with the Google button
        at the top right — a few seconds, no card, and it's the same account you'd use if
        you subscribe later.
      </p>
    </div>
  );
}
