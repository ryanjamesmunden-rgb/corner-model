import { useState, useEffect, useRef } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { CreditCard, LogOut, ShieldCheck, Loader2, ExternalLink, CheckCircle2, XCircle, RotateCcw } from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import WelcomeVideo from "@/components/WelcomeVideo";
import AccountTeams from "@/components/AccountTeams";
import SupportCard from "@/components/SupportCard";
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

// Greeting rather than a header. This page is otherwise a wall of status rows and a
// cancel button, and the one place a subscriber lands after paying should sound like it
// is run by the person whose picks they just bought — not like a billing portal. Time of
// day rather than a fixed hello, because it costs nothing and reads as a site that is
// awake.
const greet = (name, now = new Date()) => {
  const first = String(name || "").trim().split(/\s+/)[0];
  const h = now.getHours();
  const when = h < 12 ? "Morning" : h < 18 ? "Afternoon" : "Evening";
  return first ? `${when}, ${first}` : "Your account";
};

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
  const { user, ready, member, signOut, renderButton, clientId, setMember } = useAuth();
  const [params] = useSearchParams();
  const [busy, setBusy] = useState(false);
  // Cancelling is two steps, not one. A single click that ends a paid subscription is
  // too easy to hit by accident on a phone, and an accidental cancellation costs the
  // same support conversation the whole page exists to avoid.
  const [confirming, setConfirming] = useState(false);
  // Held locally so the page updates the moment Stripe confirms, rather than waiting for
  // the next reload to reflect what the user just did.
  const [ends, setEnds] = useState(null);
  // Runtime config, so the video can be swapped without a frontend rebuild.
  const [tutorialUrl, setTutorialUrl] = useState("");
  useEffect(() => { api.config().then((c) => setTutorialUrl(c?.tutorial_url || "")).catch(() => {}); }, []);
  // renderButton DRAWS INTO a node rather than returning one — same pattern as SignIn.
  const signInSlot = useRef(null);
  useEffect(() => { if (!user) renderButton(signInSlot.current); }, [user, renderButton, clientId]);

  // Stripe sends people back here after checkout. The webhook is what actually grants
  // membership and it can land a beat after the redirect, so this waits for it rather
  // than asserting success — telling someone they are subscribed before the webhook has
  // been processed produces a page that says "member" over a locked screen.
  //
  // POLLED, NOT RELOADED. This used to call window.location.reload(), which was fine
  // until the same view started showing a welcome video: a reload two seconds in kills
  // playback and restarts the video under someone who had just pressed play. Asking the
  // API instead updates the same state without touching the page.
  const justPaid = params.get("checkout") === "success";
  useEffect(() => {
    if (!justPaid || member) return;
    let alive = true;
    let tries = 0;
    const tick = async () => {
      if (!alive || tries >= 10) return;      // ~30s, then give up quietly
      tries += 1;
      try {
        const res = await api.me();
        if (alive && res?.user?.member) { setMember(true); return; }
      } catch { /* transient; try again */ }
      if (alive) setTimeout(tick, 3000);
    };
    const t = setTimeout(tick, 1500);
    return () => { alive = false; clearTimeout(t); };
  }, [justPaid, member, setMember]);

  if (!ready) return null;

  if (!user) {
    return (
      <div className="max-w-lg mx-auto py-16 text-center" data-testid="account-signed-out">
        <h1 className="font-head text-2xl font-bold mb-2">Your account</h1>
        <p className="text-muted-foreground text-sm mb-6">
          Sign in to follow your teams, keep your starred games, and manage or cancel
          your subscription. Free, and about ten seconds.
        </p>
        <div className="flex justify-center" ref={signInSlot} />
      </div>
    );
  }

  const source = user.member_source;
  const isStripe = source === "stripe";
  const isComp = source === "code";
  // Access that predates billing. It is permanent — no Stripe event can end it — so the
  // page says so outright rather than leaving someone wondering what happens next.
  const isGrandfathered = user.grandfathered;
  const ending = ends === null ? user.cancel_at_period_end : ends;

  // One line that tells you where you stand, in the voice of the channel rather than of
  // a payments processor. It is the first thing under the greeting because "am I still
  // a member?" is the question that brought most people to this page.
  const blurb = !member
    ? `You're signed in, so your starred games and followed teams stick around. The
       members' screens — streaks, mismatches, the full board — are still locked.`
    : ending
      ? `Winding down, but you're still in until the date below. Nothing else to do, and
         you can put it back any time.`
      : isStripe
        ? `You're in — streaks, mismatches and the full board, all unlocked. Follow a few
           teams below and the site starts working for you rather than the other way round.`
        : `You've got the run of the place, on the house. Nothing to pay and nothing to
           cancel.`;

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

  const setCancelled = async (cancel) => {
    if (busy) return;
    setBusy(true);
    try {
      const res = await api.billingCancel(cancel);
      setEnds(res.cancel_at_period_end);
      setConfirming(false);
      toast.success(cancel
        ? "Cancelled — you keep access until the end of the period you've paid for"
        : "Subscription resumed");
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Couldn't update the subscription");
    } finally {
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
        <div className="flex items-center gap-3">
          {user.picture ? (
            <img src={user.picture} alt="" referrerPolicy="no-referrer"
              className="h-11 w-11 rounded-full border border-border shrink-0" />
          ) : null}
          <div className="min-w-0">
            <h1 className="font-head text-2xl font-bold truncate">{greet(user.name)}</h1>
            <p className="text-muted-foreground text-xs truncate">{user.email}</p>
          </div>
        </div>
        <p className="text-sm text-muted-foreground mt-3">{blurb}</p>
      </div>

      {justPaid && (
        <div className="flex items-center gap-2 text-sm bg-emerald-500/10 border border-emerald-500/30 text-emerald-400 rounded-lg px-4 py-3">
          <CheckCircle2 className="h-4 w-4 shrink-0" />
          Payment received — setting up your membership…
        </div>
      )}

      {/* Straight after checkout this is the first thing on the page, above the
          membership box: someone who has just paid wants to know what to do next, not
          to be told what they already know about their own status. */}
      {justPaid && (
        <WelcomeVideo
          url={tutorialUrl}
          prominent
          title="Start here — how to use the site"
          subtitle="Five minutes on where the value is, how to read a streak, and what the projections mean."
        />
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
            {isGrandfathered && !isStripe ? "Founding member"
              : isStripe ? "Paid subscription"
              : isComp ? "Complimentary" : "Member"}
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
                ? (isGrandfathered
                    ? "Your subscription is set to end. Your original access predates subscriptions and stays either way."
                    : "Your subscription is set to end — you keep access until the date above, and you won't be charged again.")
                : "Cancel any time. Cancelling takes effect at the end of the period you've already paid for, so you keep what you bought."}
            </p>
            {/* CANCELLING FIRST, and on this page rather than behind a redirect. The
                portal below is for cards and invoices; sending someone off-site to stop
                paying is where they give up and email you, or call their bank. */}
            {ending ? (
              <button
                onClick={() => setCancelled(false)}
                disabled={busy}
                data-testid="resume-subscription"
                className="w-full flex items-center justify-center gap-2 text-sm font-medium px-4 py-2.5 rounded-md bg-secondary border border-border hover:bg-white/10 transition-colors disabled:opacity-50"
              >
                {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <RotateCcw className="h-4 w-4" />}
                Resume subscription
              </button>
            ) : confirming ? (
              <div className="rounded-md border border-border bg-secondary/50 p-3" data-testid="cancel-confirm">
                <p className="text-sm text-foreground mb-1">Cancel your subscription?</p>
                <p className="text-xs text-muted-foreground mb-3">
                  You'll keep access until {fmtDate(user.subscription_ends_at) || "the end of the current period"},
                  and you won't be charged again. You can restart any time.
                </p>
                <div className="flex gap-2">
                  <button
                    onClick={() => setCancelled(true)}
                    disabled={busy}
                    data-testid="cancel-confirm-yes"
                    className="flex-1 flex items-center justify-center gap-2 text-sm font-medium px-3 py-2 rounded-md border border-red-500/40 text-red-400 hover:bg-red-500/10 transition-colors disabled:opacity-50"
                  >
                    {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
                    Yes, cancel
                  </button>
                  <button
                    onClick={() => setConfirming(false)}
                    disabled={busy}
                    data-testid="cancel-confirm-no"
                    className="flex-1 text-sm font-medium px-3 py-2 rounded-md bg-secondary border border-border hover:bg-white/10 transition-colors"
                  >
                    Keep it
                  </button>
                </div>
              </div>
            ) : (
              <button
                onClick={() => setConfirming(true)}
                disabled={busy}
                data-testid="cancel-subscription"
                className="w-full flex items-center justify-center gap-2 text-sm font-medium px-4 py-2.5 rounded-md border border-border text-muted-foreground hover:text-foreground hover:bg-white/10 transition-colors disabled:opacity-50"
              >
                <XCircle className="h-4 w-4" />
                Cancel subscription
              </button>
            )}

            <button
              onClick={openPortal}
              disabled={busy}
              data-testid="manage-subscription"
              className="mt-2 w-full flex items-center justify-center gap-2 text-xs text-muted-foreground hover:text-foreground transition-colors disabled:opacity-50"
            >
              <ExternalLink className="h-3.5 w-3.5" />
              Update card or view invoices
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
            You had access before subscriptions existed here, and you keep it — there's
            nothing to pay and nothing to cancel. Get in touch if you'd like it removed.
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

      {/* Teams before the video: someone who has been here a week has watched it, and the
          thing they came back to change is what the site follows for them. */}
      <AccountTeams />

      {member && !justPaid && (
        <WelcomeVideo
          url={tutorialUrl}
          title="How to use the site"
          subtitle="Where the value is, how to read a streak, and what the projections mean."
        />
      )}

      {/* Below billing on purpose. Cancelling is self-service and comes first; this is
          for the things a button cannot settle — refunds above all. */}
      <SupportCard showCancelPointer={member && (isStripe || user.has_billing)} />

      <a href="/faq" className="block text-sm text-primary hover:underline" data-testid="account-faq">
        Questions about your subscription
      </a>

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
