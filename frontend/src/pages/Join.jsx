import { useState, useEffect } from "react";
import { Link } from "react-router-dom";
import { CornerDownRight, Check, ExternalLink, ArrowRight } from "lucide-react";
import { api } from "@/lib/api";
import { publishableRecord, signed, MIN_SAMPLE } from "@/lib/record";

// The subscription page the payment link points at.
//
// A bare checkout converts badly — people want to see what they are buying. But a sales
// page for a betting service is the one place in this app where the temptation to state
// something flattering is strongest, so the numbers here are NOT copy. They are read live
// from /api/ledger, the same settled record the Picks page shows, and they are withheld
// when the sample cannot support them (see lib/record.js). Nothing on this page can be
// improved by editing it — only by the picks doing better.
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

const INCLUDED = [
  "Every pick posted before kick-off, with the price taken",
  "The reasoning: projected corners, the streak or mismatch behind it, and the sample size",
  "Full access to the model site — streaks, mismatches, fixture projections, all leagues",
  "The settled record, updated automatically, win or lose",
];

export default function Join() {
  const [summary, setSummary] = useState(undefined);   // undefined = loading, null = failed
  const [joinUrl, setJoinUrl] = useState(BUILD_JOIN_URL);
  const [configReached, setConfigReached] = useState(null);   // null = still asking

  useEffect(() => {
    api.ledger()
      .then((d) => setSummary(d?.summary || null))
      .catch(() => setSummary(null));
    // Runtime config wins over anything compiled into this bundle.
    api.config()
      .then((c) => { setConfigReached(true); if (c?.join_url) setJoinUrl(c.join_url); })
      .catch(() => setConfigReached(false));
  }, []);

  const rec = summary === undefined ? undefined : publishableRecord(summary);

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

        <Record rec={rec} />

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
          {joinUrl ? (
            <a href={joinUrl} target="_blank" rel="noopener noreferrer"
              data-testid="join-button"
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
          <p className="mt-3 text-xs text-muted-foreground">
            Checkout asks for your Telegram username — that's how you get added. Access is manual,
            so allow a few hours.
          </p>
        </section>

        <section className="border border-border rounded-lg p-5" data-testid="join-guarantee">
          <h2 className="font-head font-semibold text-lg">Money back on a losing month</h2>
          <p className="mt-2 text-sm text-muted-foreground leading-relaxed">
            Measured on the published picks only, flat 1 point per pick, at the odds shown when the
            pick was posted. If the published record for a calendar month closes below 0 points,
            that month's {PRICE} is refunded on request within 14 days of month end — just ask.
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

function Record({ rec }) {
  if (rec === undefined) {
    return <div className="h-28 rounded-lg bg-secondary animate-pulse" data-testid="join-record-loading" />;
  }
  // A sales page that cannot reach its own ledger says so. Silently dropping the section
  // would leave the claims above with nothing behind them and no sign anything is missing.
  if (rec === null) {
    return (
      <section className="border border-border rounded-lg p-5" data-testid="join-record-error">
        <h2 className="font-head font-semibold text-lg">The record</h2>
        <p className="mt-2 text-sm text-muted-foreground">
          The results can't be loaded right now. They're on the{" "}
          <Link to="/picks" className="underline hover:text-foreground">Picks page</Link> — please
          check there before subscribing.
        </p>
      </section>
    );
  }
  if (rec.empty) {
    return (
      <section className="border border-border rounded-lg p-5" data-testid="join-record-thin">
        <h2 className="font-head font-semibold text-lg">The record</h2>
        <p className="mt-2 text-sm text-muted-foreground leading-relaxed">
          Not enough settled picks yet to publish a strike rate or a return — there are{" "}
          <span className="font-mono-data text-foreground">{rec.settled}</span>, and anything below{" "}
          {MIN_SAMPLE} says more about luck than about the model. Every pick is logged and settled
          publicly on the{" "}
          <Link to="/picks" className="underline hover:text-foreground">Picks page</Link> as it
          happens, so you can watch the record build rather than take a number on trust.
        </p>
      </section>
    );
  }
  return (
    <section className="border border-border rounded-lg p-5" data-testid="join-record">
      <div className="flex items-baseline gap-2 flex-wrap">
        <h2 className="font-head font-semibold text-lg">The record</h2>
        <Link to="/picks" className="text-xs text-muted-foreground underline hover:text-foreground">
          every pick, settled
        </Link>
      </div>
      <div className="mt-4 grid grid-cols-2 sm:grid-cols-4 gap-4">
        <Stat label="Settled" value={rec.settled} sub={rec.pending ? `${rec.pending} pending` : null} />
        {rec.showWinRate && <Stat label="Strike rate" value={`${rec.winRate}%`} sub={`of ${rec.settled}`} />}
        {rec.showReturn && (
          <>
            <Stat label="P&L" value={`${signed(rec.profit, 2)} pts`} sub="flat 1pt stakes"
              tone={rec.profit > 0 ? "up" : rec.profit < 0 ? "down" : null} />
            <Stat label="ROI" value={`${signed(rec.roi)}%`} sub={`over ${rec.staked} priced`}
              tone={rec.roi > 0 ? "up" : rec.roi < 0 ? "down" : null} />
          </>
        )}
      </div>
      {/* The caveat belongs BESIDE the number, not in a footnote nobody reaches. Returns are
          computed only over picks with a recorded price, so when that is a subset of the
          settled picks the headline describes part of the record and has to admit it. */}
      {rec.showReturn && rec.coverage < 100 && (
        <p className="mt-3 text-xs text-muted-foreground" data-testid="join-coverage">
          P&L and ROI cover the {rec.staked} of {rec.settled} settled picks with a recorded price
          ({rec.coverage}%). The other {rec.unpriced} are in the strike rate but not the return.
        </p>
      )}
      {!rec.showReturn && rec.showWinRate && (
        <p className="mt-3 text-xs text-muted-foreground" data-testid="join-no-return">
          Not enough picks with a recorded price to publish a return yet — a strike rate without
          prices doesn't tell you whether it made money.
        </p>
      )}
    </section>
  );
}

function Stat({ label, value, sub, tone }) {
  const colour = tone === "up" ? "text-emerald-400" : tone === "down" ? "text-red-400" : "text-foreground";
  return (
    <div data-testid="join-stat">
      <div className="text-[10px] uppercase tracking-wider text-muted-foreground">{label}</div>
      <div className={`font-mono-data text-2xl mt-0.5 ${colour}`}>{value}</div>
      {sub && <div className="text-[10px] text-muted-foreground/70 mt-0.5">{sub}</div>}
    </div>
  );
}
