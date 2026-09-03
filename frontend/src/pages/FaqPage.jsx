import { useState, useEffect } from "react";
import { Link } from "react-router-dom";
import { CornerDownRight, ArrowRight } from "lucide-react";
import { api } from "@/lib/api";
import Faq from "@/components/Faq";

const PRICE = "£20";

// A standalone /faq, so the answers can be linked to directly — from the Telegram
// channels, from a reply to someone asking, from anywhere. An FAQ that only exists
// halfway down a sales page cannot be sent to somebody.
//
// Outside the app chrome for the same reason /join is: whoever is reading this may not
// have paid yet, and a league switcher above a "how do I cancel" answer is noise.
export default function FaqPage() {
  const [instant, setInstant] = useState(true);

  useEffect(() => {
    // Whether checkout grants access immediately depends on which one is live. Assume
    // the modern flow if the backend cannot be reached — it is what a new visitor will
    // get, and the alternative reads as "expect a delay" to someone who won't have one.
    api.config().then((c) => setInstant(!!c?.stripe_ready)).catch(() => {});
  }, []);

  return (
    <div className="min-h-screen bg-background text-foreground">
      <header className="border-b border-border">
        <div className="max-w-3xl mx-auto px-5 py-4 flex items-center gap-2">
          <CornerDownRight className="h-4 w-4 text-primary" />
          <Link to="/scanner" className="font-head font-bold">Corner Model</Link>
        </div>
      </header>

      <main className="max-w-3xl mx-auto px-5 py-10 space-y-8">
        <div>
          <h1 className="font-head text-3xl font-bold tracking-tight">Questions</h1>
          <p className="text-muted-foreground text-sm mt-1">
            How it works, what you get, and how to stop paying for it.
          </p>
        </div>

        <Faq price={PRICE} instant={instant} />

        <div className="flex flex-wrap gap-3 pt-2">
          <Link to="/join"
            className="inline-flex items-center gap-1.5 text-sm font-semibold px-4 py-2.5 rounded-md bg-primary text-black hover:opacity-90 transition-opacity">
            See what's included <ArrowRight className="h-4 w-4" />
          </Link>
          <Link to="/account"
            className="inline-flex items-center gap-1.5 text-sm px-4 py-2.5 rounded-md bg-secondary border border-border hover:bg-white/10 transition-colors">
            Your account
          </Link>
        </div>

        <p className="text-xs text-muted-foreground/70 pt-4 border-t border-border">
          18+. Please gamble responsibly —{" "}
          <a href="https://www.begambleaware.org" target="_blank" rel="noopener noreferrer"
            className="underline hover:text-foreground">BeGambleAware.org</a>
        </p>
      </main>
    </div>
  );
}
