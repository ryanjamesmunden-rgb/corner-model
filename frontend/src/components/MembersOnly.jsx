import { useState } from "react";
import { Lock, ArrowRight } from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";

// Wraps a screen that is part of the paid product.
//
// Two different walls, and they must not look the same: signed out you need an account,
// signed in without a membership you need to subscribe. Collapsing those into one
// message sends people to the wrong place — which is why the API answers 401 and 402
// separately rather than a single 403.
//
// It says what is behind the wall rather than just refusing. "Members only" tells you
// nothing about whether it is worth £20; naming what is in there does.
export default function MembersOnly({ title, blurb, children }) {
  const { user, ready, member, setMember } = useAuth();
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState(false);

  if (!ready) return null;
  if (user && member) return children;

  const redeem = async (e) => {
    e.preventDefault();
    if (!code.trim() || busy) return;
    setBusy(true);
    try {
      await api.redeemCode(code.trim());
      setMember(true);
      toast.success("Unlocked — welcome in");
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Could not check that code");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="bg-card border border-border rounded-lg p-6 sm:p-10 text-center"
      data-testid="members-only">
      <div className="h-10 w-10 rounded-full bg-secondary border border-border grid place-items-center mx-auto">
        <Lock className="h-4 w-4 text-muted-foreground" />
      </div>
      <h2 className="font-head font-semibold text-xl mt-4">{title}</h2>
      <p className="text-sm text-muted-foreground mt-2 max-w-md mx-auto leading-relaxed">{blurb}</p>

      {!user ? (
        <p className="mt-5 text-sm text-muted-foreground" data-testid="members-signin">
          Sign in with the button at the top right to get started.
        </p>
      ) : (
        <form onSubmit={redeem} className="mt-6 max-w-sm mx-auto" data-testid="members-redeem">
          <label className="block text-xs uppercase tracking-wider text-muted-foreground mb-2">
            Member code
          </label>
          <div className="flex gap-2">
            <input
              value={code} onChange={(e) => setCode(e.target.value)}
              placeholder="From the VIP channel" data-testid="members-code"
              className="flex-1 bg-[#121212] border border-border rounded-md px-3 py-2 font-mono-data text-sm
                         focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent" />
            <button type="submit" disabled={busy || !code.trim()} data-testid="members-unlock"
              className="px-4 py-2 rounded-md bg-primary text-black font-medium text-sm disabled:opacity-50">
              {busy ? "…" : "Unlock"}
            </button>
          </div>
          <p className="text-[11px] text-muted-foreground/70 mt-2">
            Posted in the VIP channel. Enter it once and this browser stays unlocked.
          </p>
        </form>
      )}

      <a href="/join" className="mt-6 inline-flex items-center gap-1.5 text-sm text-primary hover:underline"
        data-testid="members-join">
        Not a member yet — see what's included <ArrowRight className="h-3.5 w-3.5" />
      </a>
    </div>
  );
}
