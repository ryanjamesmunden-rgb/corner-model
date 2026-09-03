import { ChevronDown } from "lucide-react";
import { faqSections } from "@/lib/faq";

// The FAQ, rendered from lib/faq.js so /join and /faq cannot drift apart.
//
// Built on native <details>/<summary> rather than React state. It is keyboard-accessible
// and screen-reader-correct for free, it survives a JavaScript error elsewhere on the
// page, and — the part that matters here — a browser's own "find on page" can search
// inside a closed <details>. Someone hunting for the word "cancel" finds it.
//
// The cancelling section is deliberately NOT last. It is the question a nervous buyer
// wants answered before paying and the one a leaving customer needs answered fast, and
// burying it at the bottom is how a subscription gets disputed with a bank instead.

function Item({ q, a }) {
  return (
    <details className="group border-b border-border/60 last:border-0" data-testid="faq-item">
      <summary
        className="flex items-center justify-between gap-4 cursor-pointer list-none py-3
                   text-sm font-medium text-foreground hover:text-primary transition-colors
                   [&::-webkit-details-marker]:hidden"
      >
        {q}
        <ChevronDown className="h-4 w-4 shrink-0 text-muted-foreground transition-transform duration-150 group-open:rotate-180" />
      </summary>
      {/* whitespace-pre-line so the source can stay readable as indented template text */}
      <p className="pb-4 pr-8 text-sm text-muted-foreground leading-relaxed">
        {a.replace(/\s+/g, " ").trim()}
      </p>
    </details>
  );
}

export default function Faq({ price, instant = true, className = "" }) {
  return (
    <div className={`space-y-6 ${className}`} data-testid="faq">
      {faqSections({ price, instant }).map((section) => (
        <section key={section.title}>
          <h3 className="font-head font-semibold text-sm uppercase tracking-wider text-muted-foreground mb-1">
            {section.title}
          </h3>
          <div className="border border-border rounded-lg px-4">
            {section.items.map((item) => <Item key={item.q} {...item} />)}
          </div>
        </section>
      ))}
    </div>
  );
}
