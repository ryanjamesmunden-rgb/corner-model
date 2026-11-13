import { useEffect, useId, useRef, useState } from "react";
import { AlertTriangle } from "lucide-react";
import {
  hasQuotes, quoteList, isOutlier, quoteSummary, quoteWarning,
} from "@/lib/bookQuotes";

/**
 * The price slot: best odds showing, every other book underneath.
 *
 * WHY IT IS NOT HOVER-ONLY. A hover disclosure does not exist on a phone, and this board
 * is read on one more than anywhere else — so the panel opens on CLICK for everybody, and
 * additionally on hover where the pointer is fine. Both paths set the same state, so
 * there is no behaviour that only desktop has.
 *
 * WHY IT IS A BUTTON. It is the price, so it looks like text; it opens something, so it
 * has to be reachable by keyboard and announce that it expands. A div with an onClick is
 * neither, and this sits inside a row that is itself clickable — every handler here stops
 * propagation, or opening the odds would navigate to the fixture instead.
 *
 * WHAT IT SHOWS IS THE EVIDENCE FOR THE PRICE, not more prices to choose from. The best
 * is what a backer takes; the rest are there to answer whether the best is a market or
 * one book out on its own. See lib/bookQuotes for the two ways of being alone.
 *
 * EVERY ELEMENT HERE IS A SPAN ON PURPOSE, and that is not a style preference. ValueBoard
 * renders a market line inside a <p>, and a <div> inside a <p> is invalid HTML that the
 * browser silently repairs by CLOSING the paragraph early — which tears the row in half
 * and drops the panel somewhere else entirely. Spans nest legally, so they stay spans;
 * `block` and `flex` give them the layout a div would have.
 */
export default function BookOdds({ m, muted = false, className = "" }) {
  const [open, setOpen] = useState(false);
  const wrap = useRef(null);
  const id = useId();

  // Close on an outside click and on Escape. Without the first, a panel opened by tap on
  // a phone has no way of being dismissed except by opening another one.
  useEffect(() => {
    if (!open) return undefined;
    const away = (e) => { if (!wrap.current?.contains(e.target)) setOpen(false); };
    const key = (e) => { if (e.key === "Escape") setOpen(false); };
    document.addEventListener("mousedown", away);
    document.addEventListener("keydown", key);
    return () => {
      document.removeEventListener("mousedown", away);
      document.removeEventListener("keydown", key);
    };
  }, [open]);

  const price = typeof m?.book_odds === "number" ? m.book_odds.toFixed(2) : "—";
  // NO CONTROL WHERE THERE IS NOTHING BEHIND IT. Rows stored before the feed kept every
  // book carry no quotes, and a button that opens an empty panel is worse than plain text.
  if (!hasQuotes(m)) {
    return <span className={`${muted ? "text-muted-foreground" : "text-foreground"} ${className}`}>{price}</span>;
  }

  const rows = quoteList(m);
  const alone = isOutlier(m);
  const warning = quoteWarning(m);

  return (
    <span ref={wrap} className={`relative inline-block ${className}`}
      onMouseEnter={() => setOpen(true)}
      onMouseLeave={() => setOpen(false)}>
      <button
        type="button"
        data-testid="book-odds-trigger"
        aria-expanded={open}
        aria-controls={id}
        title={quoteSummary(m)}
        onClick={(e) => { e.stopPropagation(); setOpen((v) => !v); }}
        className={`inline-flex items-center gap-1 rounded px-0.5 -mx-0.5
          underline decoration-dotted underline-offset-4 decoration-border
          hover:decoration-foreground/60 focus:outline-none focus-visible:ring-1
          focus-visible:ring-primary ${muted ? "text-muted-foreground" : "text-foreground"}`}>
        {price}
        {/* The warning rides on the TRIGGER, not only inside the panel: a reader who
            never opens it still has to see that the price is unsupported. */}
        {alone && <AlertTriangle className="h-3 w-3 text-amber-400" aria-hidden="true" />}
        <span className="sr-only">
          {` — ${quoteSummary(m)}. Show every bookmaker's price.`}
        </span>
      </button>

      {open && (
        <span
          id={id}
          role="group"
          data-testid="book-odds-panel"
          onClick={(e) => e.stopPropagation()}
          className="absolute left-0 top-full z-30 mt-1 block w-60 rounded-lg border
            border-border bg-card p-2 text-left shadow-xl">
          <span className="mb-1 block px-1 text-[10px] uppercase tracking-wider
            text-muted-foreground">
            {quoteSummary(m)}
          </span>
          {rows.map((q) => (
            <span key={q.book}
              data-testid="book-odds-row"
              className={`flex items-baseline justify-between gap-3 rounded px-1 py-0.5
                text-xs ${q.isBest ? "text-foreground font-semibold" : "text-muted-foreground"}`}>
              <span className="truncate">{q.book}</span>
              <span className="flex items-baseline gap-1.5 tabular-nums">
                <span>{q.price.toFixed(2)}</span>
                {/* How much of the return this book gives up against the top. The best
                    row says "best" rather than "0% behind", which reads as a defect. */}
                <span className="w-12 text-right text-[10px] text-muted-foreground/70">
                  {q.isBest ? "best" : `−${q.behind}%`}
                </span>
              </span>
            </span>
          ))}
          {warning && (
            <span className="mt-1.5 block border-t border-border/60 px-1 pt-1.5
              text-[10px] leading-snug text-amber-400/90">
              {warning}
            </span>
          )}
        </span>
      )}
    </span>
  );
}
