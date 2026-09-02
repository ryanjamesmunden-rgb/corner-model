import { useState, useEffect, useRef } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { CreditCard, LogOut, ShieldCheck, Loader2, ExternalLink, CheckCircle2 } from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";

// Where a subscriber manages their subscription — and, above all, where they cancel it.
//
// This page exists because there was nowhere to do that. Payment was a bare Stripe link,
// membership was a code from the Telegram, and the two were never connected: the site
// could not tell you whether you were subscribed, let alone stop it. Someone who wanted
// to cancel had to email and hope, which is how a legitimate subscription gets reported
// as a scam.
//
// CANCELLING HAPPENS ON STRIPE, not here. The button opens Stripe's billing portal,
// which owns the confirmation flow, the proration rules and the card details. Building
// our own would mean owning all of that to arrive somewhere worse and less trusted.
//
// The page is honest about which kind of member you are. A comped account has no Stripe
// subscription, so it is told that plainly rather than shown a cancel button that would
// 404 — a dead button on a billing page reads as a site that has lost your money.

const fmtDate = (iso) => (iso
  ? new Date(iso).toLocaleDateString(undefined, { day: "numeric", month: "long", year: "numeric" })
  : "");

function Row({ label, children }) {
  return (
    <div className="flex items-baseline justify-between gap-4 py-3 border-b border-border/60 last:border-0">
      <span className="text-xs uppercase tracking-wider text-muted-foreground">{label}</span>
      <span className="text-sm text-foreground text-right">{children}</span>
    </div>
  );
}

export default function Account() {
  const navigate = useNavigate();
  const { user, ready, member, signOut, renderButton, clientId } = useAuth();
  const [params] = useSearchParams();
  const [busy, setBusy] = useState(false);
  // renderButton DRAWS INTO a node rather than returning one — same pattern as SignIn.
  const signInSlot = useRef(null);
  useEffect(() => { if (!user) renderButton(signInSlot.current); }, [user, renderButton, clientId]);

  // Stripe sends people back here after checkout. The webhook is what actually grants
  // membership, and it can land a beat after the redirect, so this refreshes rather than
  // asserting success — telling someone they are subscribed before the webhook has been
  // processed produces a page that says "member" over a locked screen.
  const justPaid = params.get("checkout") === "success";
  useEffect(() => {
    if (!justPaid) return;
    const t = setTimeout(() => window.location.reload(), 2500);
    return () => clearTimeout(t);
  }, [justPaid]);

  if (!ready) return null;

  if (!user) {
    return (
      <div className="max-w-lg mx-auto py-16 text-center" data-testid="account-signed-out">
        <h1 className="font-head text-2xl font-bold mb-2">Your account</h1>
        <p className="text-muted-foreground text-sm mb-6">
          Sign in to see your membership and manage your subscription.
        </p>
        <div className="flex justify-center" ref={signInSlot} />
      </div>
    );
  }

  const source = user.member_source;
  const isStripe = source === "stripe";
  const isComp = source === "code";
  const ending = user.cancel_at_period_end;

  const openPortal = async () => {
    if (busy) return;
    setBusy(true);
    try {
      const { url } = await api.billingPortal();
      window.location.href = url;
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Couldn't open the billing portal");
      setBusy(false);
    }
  };

  const subscribe = async () => {
    if (busy) return;
    setBusy(true);
    try {
      const { url } = await api.billingCheckout();
      window.location.href = url;
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Couldn't start checkout");
      setBusy(false);
    }
  };

  return (
    <div className="max-w-lg mx-auto py-8 space-y-6" data-testid="account-page">
      <div>
        <h1 className="font-head text-2xl font-bold">Your account</h1>
        <p className="text-muted-foreground text-sm mt-1">{user.email}</p>
      </div>

      {justPaid && (
        <div className="flex items-center gap-2 text-sm bg-emerald-500/10 border border-emerald-500/30 text-emerald-400 rounded-lg px-4 py-3">
          <CheckCircle2 className="h-4 w-4 shrink-0" />
          Payment received — setting up your membership…
        </div>
      )}

      <section className="bg-card border border-border rounded-lg p-4">
        <div className="flex items-center gap-2 mb-2">
          <ShieldCheck className={`h-4 w-4 ${member ? "text-emerald-400" : "text-muted-foreground"}`} />
          <h2 className="font-head font-semibold">Membership</h2>
        </div>

        <Row label="Status">
          {member
            ? <span className="text-emerald-400 font-medium">Active</span>
            : <span className="text-muted-foreground">Not subscribed</span>}
        </Row>
        {member && (
          <Row label="Type">
            {isStripe ? "Paid subscription" : isComp ? "Complimentary" : "Member"}
          </Row>
        )}
        {user.member_since && <Row label="Member since">{fmtDate(user.member_since)}</Row>}
        {isStripe && user.subscription_ends_at && (
          <Row label={ending ? "Access ends" : "Renews"}>{fmtDate(user.subscription_ends_at)}</Row>
        )}
      </section>

      {/* The cancellation route, and the reason this page exists. */}
      <section className="bg-card border border-border rounded-lg p-4">
        <div className="flex items-center gap-2 mb-3">
          <CreditCard className="h-4 w-4 text-muted-foreground" />
          <h2 className="font-head font-semibold">Billing</h2>
        </div>

        {isStripe || user.has_billing ? (
          <>
            <p className="text-sm text-muted-foreground mb-3">
              {ending
                ? "Your subscription is set to end — you keep access until the date above. You can restart it from the same place."
                : "Update your card, download invoices, or cancel your subscription. Cancelling takes effect at the end of the period you've paid for."}
            </p>
            <button
              onClick={openPortal}
              disabled={busy}
              data-testid="manage-subscription"
              className="w-full flex items-center justify-center gap-2 text-sm font-medium px-4 py-2.5 rounded-md bg-secondary border border-border hover:bg-white/10 transition-colors disabled:opacity-50"
            >
              {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <ExternalLink className="h-4 w-4" />}
              Manage or cancel subscription
            </button>
          </>
        ) : isComp ? (
          // No Stripe customer, so no portal. Say so rather than showing a dead button.
          <p className="text-sm text-muted-foreground">
            Your access was granted directly rather than bought, so there's no subscription
            to cancel and nothing to pay. Get in touch if you'd like it removed.
          </p>
        ) : member ? (
          <p className="text-sm text-muted-foreground">
            Your membership predates online billing, so there's nothing here to cancel.
            Get in touch if you'd like it removed.
          </p>
        ) : (
          <>
            <p className="text-sm text-muted-foreground mb-3">
              Subscribe to unlock the streaks, mismatches and the full board. Cancel any
              time from this page.
            </p>
            <button
              onClick={subscribe}
              disabled={busy}
              data-testid="account-subscribe"
              className="w-full flex items-center justify-center gap-2 text-sm font-semibold px-4 py-2.5 rounded-md bg-primary text-primary-foreground hover:opacity-90 transition-opacity disabled:opacity-50"
            >
              {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
              Subscribe
            </button>
          </>
        )}
      </section>

      <button
        onClick={() => { signOut(); navigate("/scanner"); }}
        data-testid="account-signout"
        className="flex items-center gap-2 text-sm text-muted-foreground hover:text-foreground transition-colors"
      >
        <LogOut className="h-4 w-4" /> Sign out
      </button>
    </div>
  );
}
