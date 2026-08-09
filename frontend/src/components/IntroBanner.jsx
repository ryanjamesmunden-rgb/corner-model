import { useState, useEffect } from "react";
import { X, HelpCircle, Target, Radar, Flame, TrendingUp } from "lucide-react";

const KEY = "cm2_intro_dismissed";

export default function IntroBanner() {
  const [open, setOpen] = useState(true);

  useEffect(() => {
    setOpen(localStorage.getItem(KEY) !== "1");
  }, []);

  const dismiss = () => {
    localStorage.setItem(KEY, "1");
    setOpen(false);
  };
  const reopen = () => {
    localStorage.removeItem(KEY);
    setOpen(true);
  };

  if (!open) {
    return (
      <button
        data-testid="intro-reopen"
        onClick={reopen}
        className="inline-flex items-center gap-1.5 text-xs text-muted-foreground hover:text-primary transition-colors duration-150"
      >
        <HelpCircle className="h-3.5 w-3.5" /> How the corner model works
      </button>
    );
  }

  return (
    <div
      data-testid="intro-banner"
      className="relative bg-card border border-border rounded-lg p-5 sm:p-6 overflow-hidden"
      style={{ borderTop: "2px solid hsl(187 100% 50%)" }}
    >
      <div
        className="pointer-events-none absolute -top-16 -right-16 h-48 w-48 rounded-full opacity-[0.07]"
        style={{ background: "radial-gradient(circle, hsl(187 100% 50%), transparent 70%)" }}
      />
      <button
        data-testid="intro-dismiss"
        onClick={dismiss}
        className="absolute top-3 right-3 text-muted-foreground hover:text-foreground transition-colors duration-150"
        aria-label="Dismiss"
      >
        <X className="h-4 w-4" />
      </button>

      <div className="flex items-center gap-2 text-primary mb-2">
        <Target className="h-4 w-4" />
        <span className="font-mono-data text-xs tracking-widest uppercase">The Corner Model</span>
      </div>
      <h2 className="font-head text-xl sm:text-2xl font-bold tracking-tight mb-2">
        Find corner value before the market moves
      </h2>
      <p className="text-sm text-muted-foreground max-w-3xl leading-relaxed">
        We pull real corner stats and fixtures across 20+ leagues, model each team's likely corner
        count, and flag where the bookies' price is beatable. The core angle:{" "}
        <span className="text-foreground font-medium">
          back a team's corner line when they're set up to chase the game
        </span>{" "}
        — a strong attacking side against a leaky defence keeps forcing corners, and once a team goes
        behind they push men forward, pile on shots, and rack up even more.
      </p>

      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 mt-4">
        <Step icon={TrendingUp} title="Best Bets Today" accent="#22D3EE"
          text="The single standout from each signal — start here for today's opportunities." />
        <Step icon={Radar} title="Quick Scan" accent="#10B981"
          text="Strong corner teams drawn against leaky defences — the cleanest chase spots." />
        <Step icon={Flame} title="Streaks" accent="#F59E0B"
          text="Teams that keep hitting a corner line game after game — consistency you can lean on." />
      </div>
    </div>
  );
}

const Step = ({ icon: Icon, title, text, accent }) => (
  <div className="bg-white/5 border border-border rounded-md p-3">
    <div className="flex items-center gap-2 mb-1">
      <Icon className="h-3.5 w-3.5" style={{ color: accent }} />
      <span className="font-head font-semibold text-sm">{title}</span>
    </div>
    <p className="text-xs text-muted-foreground leading-relaxed">{text}</p>
  </div>
);
