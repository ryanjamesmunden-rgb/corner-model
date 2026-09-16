import { useState, useEffect } from "react";
import { Send, X, Loader2 } from "lucide-react";
import { api } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { promptCopy, promptLevel } from "@/lib/channelPrompt";

// A member who has paid and never arrived in the channel, told so on every page.
//
// WHY IT FOLLOWS THEM RATHER THAN LIVING ON /account. The invite was on the account page
// and nowhere else, so the only people who saw it were the people who went looking. A
// subscriber closed the tab after Stripe and never came back to that page — he had bought
// the channel and been handed nothing, and the product had no idea.
//
// THE BOT CANNOT DELIVER THE FIRST LINK. We learn somebody's Telegram identity at exactly
// one moment: when they walk through an invite we issued. So the only people the bot could
// DM are the ones already in. The first link has to reach them where they already are.
//
// IT DISMISSES, AND THE DISMISSAL DOES NOT STICK FOREVER. Session storage, not local: a
// banner about the thing you are paying for and have not received should come back
// tomorrow. What it must not do is reappear three times in one sitting.

const KEY = "cm2_channel_prompt_dismissed";

export default function ChannelBanner() {
  const { user } = useAuth();
  const [hidden, setHidden] = useState(() => {
    try { return sessionStorage.getItem(KEY) === "1"; } catch { return false; }
  });
  const [link, setLink] = useState(null);
  const [busy, setBusy] = useState(false);

  const level = promptLevel(user);

  useEffect(() => {
    if (level !== "loud" || hidden || link || busy) return;
    setBusy(true);
    api.vipInvite()
      .then((r) => setLink(r.invite_link))
      // SILENT. A member who did not ask for this should not be shown an error about it;
      // the account page has the button that explains what went wrong when pressed.
      .catch(() => {})
      .finally(() => setBusy(false));
  }, [level, hidden, link, busy]);

  if (level !== "loud" || hidden) return null;
  const copy = promptCopy(user);

  const dismiss = () => {
    setHidden(true);
    try { sessionStorage.setItem(KEY, "1"); } catch { /* private mode */ }
  };

  return (
    <div className="border-b border-primary/30 bg-primary/10" data-testid="channel-banner">
      <div className="max-w-5xl mx-auto px-4 py-2.5 flex items-center gap-3">
        <Send className="h-4 w-4 text-primary shrink-0" />
        <div className="min-w-0 flex-1">
          <p className="text-sm font-medium leading-tight">{copy.title}</p>
          <p className="text-xs text-muted-foreground leading-snug mt-0.5">{copy.body}</p>
        </div>
        {/* THE LINK ITSELF, not a route to a page with the link on it. Every extra hop is
            somewhere else to lose them, and losing them here costs the subscription. */}
        {link ? (
          <a href={link} target="_blank" rel="noreferrer" data-testid="channel-banner-link"
            className="shrink-0 inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md
                       bg-primary text-black text-xs font-semibold hover:opacity-90">
            {copy.cta}
          </a>
        ) : (
          <span className="shrink-0 text-xs text-muted-foreground inline-flex items-center gap-1.5">
            {busy && <Loader2 className="h-3 w-3 animate-spin" />}
            <a href="/account" className="underline">Your account</a>
          </span>
        )}
        <button onClick={dismiss} data-testid="channel-banner-dismiss"
          aria-label="Dismiss" className="shrink-0 text-muted-foreground hover:text-foreground">
          <X className="h-4 w-4" />
        </button>
      </div>
    </div>
  );
}
