import { useState, useEffect, useRef } from "react";
import { Link, useNavigate } from "react-router-dom";
import { CornerDownRight, Check, ExternalLink, ArrowRight, Loader2 } from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";

// The subscription page the payment link points at.
//
// A bare checkout converts badly — people want to see what they are buying.
//
// THIS PAGE PUBLISHES NO RECORD, on purpose. It used to show the /api/ledger figures, but
// that ledger holds the model's own automated Daily 2 selections — not the picks actually
// sent to the channel, which is the product being sold. Advertising one as the other
// misrepresents the service in both directions, so the section is gone until real picks
// are being logged (POST /api/picks) and there is a record here that IS the product.
//
// The rule if it returns: numbers come from settled picks, never from copy. A figure
// anyone can type is not evidence, and it is the first thing a sceptical buyer tests.
//
// SETUP: set JOIN_URL in the BACKEND environment (Render) to the Stripe payment link.
//
// It used to be REACT_APP_JOIN_URL, compiled into this bundle at build time, and that was
// the wrong place for it. Create React App inlines build-time variables, so changing the
// link needs a rebuild — and Vercel's redeploy reuses the build cache by default, which
// can hand back the previously compiled bundle. The deploy goes green, the value never
// changes, and nothing reports why. That cost an evening.
//
// The backend value wins; the build-time one is kept only as a fallback so an older
// deployment does not lose its link.
const BUILD_JOIN_URL = process.env.REACT_APP_JOIN_URL || "";
const PRICE = "£20";

// RESULTS AS RECORDED IN THE CHANNEL.
//
// Stated figures, not computed. The site cannot yet verify these: its ledger holds the
// model's automated selections, not the picks actually sent out, so there is nothing here
// to check them against. That is why the page says plainly where they come from rather
// than dressing them as site-verified — a number a buyer cannot check is worth exactly
// what its source is worth, and pretending otherwise is the fastest way to lose someone.
//
// Edit this list each month. It becomes computed — and verifiable — once real picks are
// logged through POST /api/picks and the record can be built from settled results.
const RESULTS = [
  { period: "June - July", units: 17.14 },
  { period: "August", units: 20.73 },
];

const INCLUDED = [
  "Every pick posted before kick-off, with the price taken",
  "The reasoning: projected corners, the streak or mismatch behind it, and the sample size",
  "Full access to the model site — streaks, mismatches, fixture projections, all leagues",
  "Every result settled and posted in the channel, win or lose",
];

export default function Join() {
  const [joinUrl, setJoinUrl] = useState(BUILD_JOIN_URL);
  const [configReached, setConfigReached] = useState(null);   // null = still asking
  const [stripeReady, setStripeReady] = useState(false);
  const [busy, setBusy] = useState(false);
  const navigate = useNavigate();
  const { user, member, renderButton, clientId } = useAuth();
  const signInSlot = useRef(null);

  useEffect(() => {
    // Runtime config wins over anything compiled into this bundle.
    api.config()
      .then((c) => {
        setConfigReached(true);
        if (c?.join_url) setJoinUrl(c.join_url);
        setStripeReady(!!c?.stripe_ready);
      })
      .catch(() => setConfigReached(false));
  }, []);

  // Google's button draws into a node rather than returning one — same as SignIn.
  useEffect(() => { if (!user) renderButton(signInSlot.current); }, [user, renderButton, clientId]);

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
    <div className="min-h-screen bg-background text-foreground">
      <header className="border-b border-border">
        <div className="max-w-3xl mx-auto px-5 py-4 flex items-center gap-2">
          <div className="h-8 w-8 rounded-md bg-primary flex items-center justify-center">
            <CornerDownRight className="h-4 w-4 text-black" strokeWidth={2.5} />
          </div>
          <span className="font-head font-semibold">The Corner Model</span>
          <Link to="/scanner"
            className="ml-auto text-xs text-muted-foreground hover:text-foreground flex items-center gap-1">
            Browse the model <ArrowRight className="h-3 w-3" />
          </Link>
        </div>
      </header>

      <main className="max-w-3xl mx-auto px-5 py-10 space-y-10">
        <section>
          <h1 className="font-head font-bold text-3xl sm:text-4xl leading-tight">
            Corner betting, priced by a model
          </h1>
          <p className="mt-3 text-muted-foreground leading-relaxed">
            A negative-binomial model projects corner counts for every fixture across 28 leagues,
            using each team's own home and away form rather than a season average. Picks go out on
            Telegram before kick-off with the price taken and the reasoning attached. Every one is
            settled and published, win or lose.
          </p>
        </section>

        <section data-testid="join-results">
          <div className="flex items-baseline gap-2 flex-wrap">
            <h2 className="font-head font-semibold text-lg">Results</h2>
            <span className="text-xs text-muted-foreground">flat 1 point per pick</span>
          </div>
          <div className="mt-3 border border-border rounded-lg divide-y divide-border">
            {RESULTS.map((r) => (
              <div key={r.period} className="flex items-baseline gap-3 px-4 py-2.5">
                <span className="text-sm text-muted-foreground">{r.period}</span>
                <span className={`ml-auto font-mono-data text-lg ${
                  r.units > 0 ? "text-emerald-400" : r.units < 0 ? "text-red-400" : "text-foreground"}`}>
                  {r.units > 0 ? "+" : ""}{r.units.toFixed(2)}
                </span>
                <span className="text-xs text-muted-foreground w-8">pts</span>
              </div>
            ))}
            <div className="flex items-baseline gap-3 px-4 py-2.5 bg-secondary/40">
              <span className="text-sm font-medium">Since June</span>
              <span className="ml-auto font-mono-data text-lg text-emerald-400">
                +{RESULTS.reduce((a, r) => a + r.units, 0).toFixed(2)}
              </span>
              <span className="text-xs text-muted-foreground w-8">pts</span>
            </div>
          </div>
          {/* Where they come from, stated rather than implied. */}
          <p className="mt-2 text-xs text-muted-foreground/70 leading-relaxed">
            Settled results recorded in the channel, at flat 1-point stakes. Picks are posted
            before kick-off and settled publicly, win or lose, so members can check every one
            against what was sent. Your own return depends on your stakes and the prices you get.
          </p>
        </section>

        <section>
          <h2 className="font-head font-semibold text-lg mb-3">What you get</h2>
          <ul className="space-y-2">
            {INCLUDED.map((line) => (
              <li key={line} className="flex gap-2.5 text-sm text-muted-foreground">
                <Check className="h-4 w-4 text-emerald-400 shrink-0 mt-0.5" />
                <span>{line}</span>
              </li>
            ))}
          </ul>
        </section>

        <section className="bg-card border border-border rounded-lg p-5" data-testid="join-cta">
          <div className="flex flex-wrap items-baseline gap-x-2">
            <span className="font-head font-bold text-3xl">{PRICE}</span>
            <span className="text-muted-foreground">per month</span>
            <span className="ml-auto text-xs text-muted-foreground">cancel any time</span>
          </div>
          {/* SIGN IN FIRST, then pay. The old flow was a bare payment link anyone could
              open, so the money arrived with no way to tell whose it was — which is why
              the site could never show you your subscription or let you cancel it.
              Checkout now starts from an account, and that account is what the cancel
              button on /account hangs off. */}
          {!user ? (
            <div className="mt-4" data-testid="join-signin">
              <p className="text-sm text-muted-foreground mb-3">
                Create your account first — it's how you'll manage or cancel your
                subscription later.
              </p>
              <div className="flex justify-center" ref={signInSlot} />
            </div>
          ) : member ? (
            <button
              onClick={() => navigate("/account")}
              data-testid="join-already-member"
              className="mt-4 w-full inline-flex items-center justify-center gap-2 px-4 py-3 rounded-md bg-secondary border border-border font-semibold hover:bg-white/10 transition-colors">
              You're already a member — go to your account
            </button>
          ) : stripeReady ? (
            <button
              onClick={subscribe}
              disabled={busy}
              data-testid="join-button"
              className="mt-4 w-full inline-flex items-center justify-center gap-2 px-4 py-3 rounded-md bg-primary text-black font-semibold hover:opacity-90 transition-opacity disabled:opacity-50">
              {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
              Subscribe <ExternalLink className="h-4 w-4" />
            </button>
          ) : joinUrl ? (
            // Fallback to the old payment link while Stripe keys are not configured, so
            // the page can still take money during the switchover. Anyone arriving this
            // way has no linked subscription and redeems a code as before.
            <a href={joinUrl} target="_blank" rel="noopener noreferrer"
              data-testid="join-button-legacy"
              className="mt-4 w-full inline-flex items-center justify-center gap-2 px-4 py-3 rounded-md bg-primary text-black font-semibold hover:opacity-90 transition-opacity">
              Subscribe <ExternalLink className="h-4 w-4" />
            </a>
          ) : (
            // Deliberately not a disabled button: a greyed-out CTA reads as "sold out" to a
            // visitor and as "working" to whoever deployed it. This says which it is.
            <div className="mt-4 rounded-md border border-amber-500/30 bg-amber-500/10 px-3 py-2.5 text-xs text-amber-300"
              data-testid="join-unconfigured">
              Subscriptions aren't open yet — no payment link is configured.
              <span className="block mt-1 text-amber-300/70">
                Set JOIN_URL in the backend environment (Render) to the Stripe payment link.
              </span>
              {/* What the page ACTUALLY received. Without this the only way to tell a
                  missing backend value from an unreachable backend was to guess. */}
              <span className="block mt-2 font-mono-data text-[10px] text-amber-300/60"
                data-testid="join-diagnostic">
                backend /api/config:{" "}
                {configReached === null ? "asking…"
                  : configReached ? "reached, join_url empty" : "UNREACHABLE"}
                {" · "}build-time value: {BUILD_JOIN_URL ? "present" : "absent"}
              </span>
            </div>
          )}
          {/* This has to track which checkout is actually live. The Stripe flow unlocks
              the site the moment the webhook lands; the old payment-link fallback is
              still manual. Saying "allow a few hours" under an instant checkout would
              have people waiting for access they already have — and emailing to ask. */}
          <p className="mt-3 text-xs text-muted-foreground">
            {stripeReady
              ? "Access unlocks as soon as payment goes through. Manage or cancel any time from your account."
              : "Checkout asks for your Telegram username — that's how you get added. Access is manual, so allow a few hours."}
          </p>
        </section>

        <section className="border border-border rounded-lg p-5" data-testid="join-guarantee">
          <h2 className="font-head font-semibold text-lg">Money back on a losing month</h2>
          <p className="mt-2 text-sm text-muted-foreground leading-relaxed">
            Measured on the picks posted in the channel, flat 1 point per pick, at the odds shown
            when the pick went out. If that month's picks close below 0 points, that month's {PRICE} is
            refunded on request within 14 days of month end — just ask.
          </p>
          <p className="mt-2 text-xs text-muted-foreground/70 leading-relaxed">
            Your own returns depend on your stakes, the prices you get and which picks you take, so
            they can differ from the published record and don't form part of this. The refund covers
            the subscription fee, never betting losses.
          </p>
        </section>

        <section className="text-xs text-muted-foreground/70 leading-relaxed space-y-2">
          <p>
            This is an information service. Nothing here is a guarantee of profit, and past results
            do not predict future ones. Only stake what you can afford to lose.
          </p>
          <p>
            18+. Help and advice at{" "}
            <a href="https://www.begambleaware.org" target="_blank" rel="noopener noreferrer"
              className="underline hover:text-foreground">BeGambleAware.org</a>{" "}
            or the National Gambling Helpline on 0808 8020 133.
          </p>
        </section>
      </main>
    </div>
  );
}
