import { Send, Link2, Check } from "lucide-react";
import { fitToPost, X_SHARE_ROWS } from "@/lib/xLimit";
import { useState } from "react";
import { toast } from "sonner";

// X's own logo isn't in lucide, so draw the glyph directly.
const XLogo = (props) => (
  <svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true" {...props}>
    <path d="M18.244 2.25h3.308l-7.227 8.26 8.502 11.24H16.17l-5.214-6.817L4.99 21.75H1.68l7.73-8.835L1.254 2.25H8.08l4.713 6.231zm-1.161 17.52h1.833L7.084 4.126H5.117z" />
  </svg>
);

// Re-exported so the boards and their tests keep importing it from here.
export { X_SHARE_ROWS };

/**
 * Share intents for a view the user is looking at. These open the platform's own
 * compose window with text prefilled — nothing is ever posted automatically, the
 * user still has to hit send on X or Telegram.
 *
 * `xRows` is the ceiling to start from, defaulting to X_SHARE_ROWS. A board with short
 * rows passes its own, higher, number: fitToPost still drops whatever will not fit, so
 * the ceiling only decides where the trying starts. Best Corner Teams fits all eight
 * rows in a post; capping it at four would throw away half a board that fits.
 *
 * `buildX(rows)` builds the same board at a given row count, for X alone. It is a
 * FUNCTION rather than a second string because fitting a post means rebuilding at fewer
 * rows, not cutting one short: the "+N more on the site" tail has to keep matching the
 * list above it, and only the board knows what N is. Boards that don't pass it share
 * their full text everywhere, as before.
 */
export default function ShareButtons({ text, buildX, xRows = X_SHARE_ROWS, url, className = "" }) {
  const [copied, setCopied] = useState(false);
  const shareUrl = url || (typeof window !== "undefined" ? window.location.href : "");
  const body = text || "";
  const xBody = buildX ? fitToPost(buildX, xRows) : body;

  const open = (href) => window.open(href, "_blank", "noopener,noreferrer");

  const shareX = () =>
    open(`https://x.com/intent/tweet?text=${encodeURIComponent(xBody)}&url=${encodeURIComponent(shareUrl)}`);

  const shareTelegram = () =>
    open(`https://t.me/share/url?url=${encodeURIComponent(shareUrl)}&text=${encodeURIComponent(body)}`);

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(`${body}\n\n${shareUrl}`);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      toast.error("Couldn't copy — your browser blocked clipboard access");
    }
  };

  const btn = "flex items-center gap-1.5 text-xs px-2.5 py-1.5 rounded-md border border-border " +
    "bg-secondary text-muted-foreground hover:text-foreground hover:bg-white/10 transition-colors duration-150";

  return (
    <div className={`flex items-center gap-2 ${className}`} data-testid="share-buttons">
      <button onClick={shareX} className={btn} data-testid="share-x" title={`Share on X — up to ${xRows} rows, trimmed to fit one post`}>
        <XLogo className="h-3.5 w-3.5" /> <span className="hidden sm:inline">Share</span>
      </button>
      <button onClick={shareTelegram} className={btn} data-testid="share-telegram" title="Share on Telegram">
        <Send className="h-3.5 w-3.5" /> <span className="hidden sm:inline">Telegram</span>
      </button>
      <button onClick={copy} className={btn} data-testid="share-copy" title="Copy text and link">
        {copied ? <Check className="h-3.5 w-3.5 text-emerald-400" /> : <Link2 className="h-3.5 w-3.5" />}
        <span className="hidden sm:inline">{copied ? "Copied" : "Copy"}</span>
      </button>
    </div>
  );
}
