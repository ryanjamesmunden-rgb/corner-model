import { Link } from "react-router-dom";
import { CornerDownRight } from "lucide-react";

// The bottom of every page, and the standing answer to "where do I stop paying?".
//
// Until now /account was reachable from exactly one place: the avatar in the header,
// only once signed in, and only if you guessed it was a link. That is fine for someone
// looking for their teams and hopeless for someone looking for the exit — and a
// subscription whose cancel route has to be guessed is one that gets cancelled through
// a bank instead, which costs the fee twice and counts against the Stripe account.
//
// So the links are plain words in a fixed place: questions, account, cancel. Named
// bluntly rather than softened into "manage preferences", because the person reading
// this row already knows what they came for.
export default function SiteFooter({ className = "" }) {
  return (
    <footer className={`border-t border-border mt-10 ${className}`} data-testid="site-footer">
      <div className="max-w-[1600px] mx-auto px-3 sm:px-6 py-6 flex flex-wrap items-center gap-x-5 gap-y-2 text-xs text-muted-foreground">
        <span className="flex items-center gap-1.5 text-foreground/80">
          <CornerDownRight className="h-3.5 w-3.5 text-primary" />
          Corner Model
        </span>
        <Link to="/faq" className="hover:text-foreground transition-colors" data-testid="footer-faq">
          Questions
        </Link>
        <Link to="/account" className="hover:text-foreground transition-colors" data-testid="footer-account">
          Your account
        </Link>
        <Link to="/account" className="hover:text-foreground transition-colors" data-testid="footer-cancel">
          Cancel or refund
        </Link>
        <span className="ml-auto text-muted-foreground/70">
          18+ ·{" "}
          <a href="https://www.begambleaware.org" target="_blank" rel="noopener noreferrer"
            className="underline hover:text-foreground">BeGambleAware.org</a>
        </span>
      </div>
    </footer>
  );
}
