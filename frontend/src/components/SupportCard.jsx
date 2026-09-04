import { useState, useEffect } from "react";
import { LifeBuoy, Mail, Send, Undo2 } from "lucide-react";
import { api } from "@/lib/api";
import { supportRoutes } from "@/lib/support";
import { useAuth } from "@/context/AuthContext";

// "How do I get my money back?" answered on the page, not in a policy.
//
// Two different things sit here on purpose. STOPPING a subscription is self-service and
// lives a few centimetres up the page — this card only points at it, so that someone
// scanning for the word "refund" is not left thinking cancelling is also a favour they
// have to ask for. GETTING A MONTH BACK under the guarantee genuinely needs a person,
// because the guarantee is measured on the channel's posted picks and no button can
// settle that.
//
// The refund route is only shown to people who have actually paid. Offering a refund to
// a free account is noise, and offering one to a comped member is a question they
// cannot answer.

export default function SupportCard({ showCancelPointer = true, className = "" }) {
  const { user, member } = useAuth();
  const [config, setConfig] = useState(null);
  useEffect(() => { api.config().then(setConfig).catch(() => setConfig({})); }, []);

  const paid = member && user?.member_source === "stripe";
  const routes = supportRoutes(config || {}, paid ? "refund" : "help", user);
  const Icon = { email: Mail, telegram: Send };

  return (
    <section className={`bg-card border border-border rounded-lg p-4 ${className}`}
      data-testid="support-card">
      <div className="flex items-center gap-2 mb-3">
        <LifeBuoy className="h-4 w-4 text-muted-foreground" />
        <h2 className="font-head font-semibold">Refunds and help</h2>
      </div>

      {showCancelPointer && (
        <p className="text-sm text-muted-foreground mb-3 flex items-start gap-2">
          <Undo2 className="h-4 w-4 shrink-0 mt-0.5" />
          <span>
            <span className="text-foreground">Just want to stop paying?</span> That's the
            Cancel button above — no message needed, and nobody will try to talk you out
            of it.
          </span>
        </p>
      )}

      <p className="text-sm text-muted-foreground mb-3">
        {paid
          ? `If the channel's picks closed a month below zero, the guarantee is real and
             the month comes back — ask within 14 days of the month ending. Same route for
             a payment that looks wrong, or anything the site has got stuck on.`
          : `Something broken, something confusing, or a question before you subscribe —
             ask. You'll get a straight answer rather than a sales pitch.`}
      </p>

      {routes.length > 0 ? (
        <div className="space-y-2">
          {routes.map((r) => {
            const I = Icon[r.kind] || Mail;
            return (
              <a key={r.kind} href={r.href}
                target={r.kind === "telegram" ? "_blank" : undefined}
                rel={r.kind === "telegram" ? "noreferrer" : undefined}
                data-testid={`support-${r.kind}`}
                className="flex items-center gap-2 text-sm px-3 py-2.5 rounded-md bg-secondary border border-border hover:bg-white/10 transition-colors"
              >
                <I className="h-4 w-4 text-muted-foreground shrink-0" />
                <span className="min-w-0">
                  <span className="block text-foreground truncate">{r.label}</span>
                  <span className="block text-[11px] text-muted-foreground">{r.hint}</span>
                </span>
              </a>
            );
          })}
        </div>
      ) : (
        // Nothing configured. Say where to go rather than printing a dead link — see the
        // note in lib/support.js.
        <p className="text-sm text-muted-foreground" data-testid="support-fallback">
          Message me in the Telegram channel and I'll pick it up there.
        </p>
      )}
    </section>
  );
}
