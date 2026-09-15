import { useEffect } from "react";
import { useNavigate, useLocation } from "react-router-dom";
import { Ellipsis, X } from "lucide-react";
import { splitNav } from "@/lib/mobileNav";

// THE PHONE'S NAVIGATION, AT THE BOTTOM WHERE THUMBS ARE.
//
// The header carried every destination as a 16px icon in a row: nine of them at 390px,
// beside Join, an account chip, a truncated league selector and an export button. It fit,
// in the sense that nothing overlapped. Nobody could hit any of it.
//
// Which four make the bar is decided in lib/mobileNav — see the note there.

function Item({ n, active, onClick, stacked }) {
  return (
    <button
      onClick={onClick}
      aria-current={active ? "page" : undefined}
      data-testid={`mnav-${n.to.slice(1)}`}
      className={stacked
        ? `flex items-center gap-3 w-full min-h-[44px] px-4 rounded-md text-sm
           ${active ? "bg-secondary text-foreground" : "text-muted-foreground"}`
        : `flex flex-col items-center justify-center gap-1 min-h-[44px] rounded-md
           ${active ? "text-primary" : "text-muted-foreground"}`}
    >
      <n.icon className={stacked ? "h-4 w-4" : "h-5 w-5"} />
      <span className={stacked ? "" : "text-[10px] leading-none font-medium"}>{n.label}</span>
    </button>
  );
}

export default function MobileNav({ nav, open, setOpen, extra = null }) {
  const navigate = useNavigate();
  const location = useLocation();
  const { bar, rest } = splitNav(nav);

  // A sheet that survives navigation is a sheet covering the page you just asked for.
  useEffect(() => { setOpen(false); }, [location.pathname, setOpen]);

  // Escape closes it, because on a phone-sized browser window there is a keyboard.
  useEffect(() => {
    if (!open) return;
    const onKey = (e) => { if (e.key === "Escape") setOpen(false); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, setOpen]);

  const go = (to) => { navigate(to); setOpen(false); };

  return (
    <>
      {open && (
        <div className="sm:hidden fixed inset-0 z-50 flex flex-col justify-end"
          data-testid="mnav-sheet">
          {/* Tapping away closes it. A sheet with only an X is a sheet people feel
              trapped by, and the backdrop is the gesture everyone tries first. */}
          <button aria-label="Close menu" onClick={() => setOpen(false)}
            className="absolute inset-0 bg-black/60 backdrop-blur-sm" />
          <div className="relative bg-card border-t border-border rounded-t-xl p-3
                          pb-[calc(0.75rem+env(safe-area-inset-bottom))] space-y-1">
            <div className="flex items-center justify-between px-2 pb-1">
              <span className="text-xs text-muted-foreground">More</span>
              <button onClick={() => setOpen(false)} aria-label="Close menu"
                className="h-11 w-11 -mr-2 flex items-center justify-center
                           text-muted-foreground hover:text-foreground">
                <X className="h-4 w-4" />
              </button>
            </div>
            {rest.map((n) => (
              <Item key={n.to} n={n} stacked active={location.pathname === n.to}
                onClick={() => go(n.to)} />
            ))}
            {extra && (
              <div className="pt-2 mt-1 border-t border-border px-2">{extra}</div>
            )}
          </div>
        </div>
      )}

      <nav
        aria-label="Main"
        data-testid="mobile-nav"
        className="sm:hidden fixed bottom-0 inset-x-0 z-40 border-t border-white/10
                   bg-[#0a0a0a]/95 backdrop-blur-xl px-2 pt-2
                   pb-[calc(0.5rem+env(safe-area-inset-bottom))]
                   grid grid-cols-5 gap-1"
      >
        {bar.map((n) => (
          <Item key={n.to} n={n} active={location.pathname === n.to}
            onClick={() => go(n.to)} />
        ))}
        <button
          onClick={() => setOpen((v) => !v)}
          aria-expanded={open}
          aria-label="More destinations"
          data-testid="mnav-more"
          className={`flex flex-col items-center justify-center gap-1 min-h-[44px] rounded-md
            ${open ? "text-foreground" : "text-muted-foreground"}`}
        >
          <Ellipsis className="h-5 w-5" />
          <span className="text-[10px] leading-none font-medium">More</span>
        </button>
      </nav>
    </>
  );
}
