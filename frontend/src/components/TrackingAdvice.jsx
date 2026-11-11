import { Link } from "react-router-dom";
import { AlertTriangle, Sparkles, TrendingDown, TrendingUp } from "lucide-react";
import TeamStar from "@/components/TeamStar";
import { flagBullet } from "@/lib/countryFlag";

// WHEN TO START OR STOP TRACKING.
//
// Two lists, both prompts rather than predictions:
//   Worth tracking — sides in form (last 5 well above their own norm, or a live run) whose
//                    next few opponents give away more corners than the league average.
//   Heads up       — teams you already track or follow whose next opponents are stingy
//                    (consider pausing), or whose recent games have dropped off.
//
// Difficulty is the opponent's corners conceded at that venue over the league average,
// written as a plain label AND the number, so it never rests on colour.

export const FLAGS = {
  tough_run: { icon: AlertTriangle, text: "Tough run ahead", tone: "text-amber-400",
               say: "Their next opponents concede fewer corners than average — a fair time to pause." },
  good_spot: { icon: TrendingUp, text: "Good spot", tone: "text-primary",
               say: "In form with soft opponents coming up — the time to watch closely." },
  cooling: { icon: TrendingDown, text: "Cooling off", tone: "text-muted-foreground",
             say: "Their last five are well under their usual — worth a second look before trusting them." },
};

const LABEL = { soft: "Soft", normal: "Normal", tough: "Tough", unknown: "Unrated" };
const LABEL_TONE = { soft: "text-primary", normal: "text-muted-foreground", tough: "text-amber-400",
                     unknown: "text-muted-foreground/60" };
const day = (iso) => {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? "" : d.toLocaleDateString(undefined, { weekday: "short", day: "numeric", month: "short" });
};

/** The next few fixtures, each with how corner-friendly the opponent is. */
export function NextFixtures({ games }) {
  if (!games?.length) return <p className="text-[11px] text-muted-foreground">Nothing scheduled in the next three weeks.</p>;
  return (
    <div className="divide-y divide-border/50" data-testid="next-fixtures">
      {games.map((g) => (
        <Link key={g.fixture_id} to={`/fixture/${g.fixture_id}`}
          className="block py-1.5 text-[12px] hover:bg-white/5 rounded px-1">
          <span className="flex items-center gap-2">
            <span className="text-muted-foreground w-6 shrink-0">{g.is_home ? "vs" : "@"}</span>
            <span className="text-foreground truncate">{g.opponent}</span>
            <span className="text-[10px] text-muted-foreground whitespace-nowrap">{day(g.date)}</span>
            <span className={`ml-auto font-medium whitespace-nowrap ${LABEL_TONE[g.label]}`}>{LABEL[g.label]}</span>
          </span>
          {g.opp_conceded != null && (
            <span className="block pl-8 text-[10px] text-muted-foreground font-mono-data">
              they concede {g.opp_conceded.toFixed(1)} {g.is_home ? "away" : "at home"} · league avg {g.league_avg?.toFixed(1)}
            </span>
          )}
        </Link>
      ))}
    </div>
  );
}

function FormLine({ o }) {
  return (
    <span className="font-mono-data text-[10px] text-muted-foreground whitespace-nowrap">
      L5 {o.l5?.toFixed(1)} · L20 {o.l20?.toFixed(1)}{o.run >= 2 ? ` · ${o.run} in a row at ${o.line}+` : ""}
    </span>
  );
}

export default function TrackingAdvice({ data, onFocus }) {
  if (!data) return null;
  const watched = Object.values(data.watched || {}).filter((o) => o.flag);
  const sugg = data.suggestions || [];
  return (
    <div className="space-y-3 sm:space-y-4">
      {watched.length > 0 && (
        <section className="bg-card border border-border rounded-lg p-3 sm:p-4" data-testid="advice-watched">
          <h2 className="font-head font-semibold">Heads up on your teams</h2>
          <p className="text-[11px] text-muted-foreground mb-2">Based on their next three fixtures and their last five games.</p>
          <div className="divide-y divide-border/50">
            {watched.map((o) => {
              const f = FLAGS[o.flag];
              const Icon = f.icon;
              return (
                <div key={o.team_id} className="py-2" data-testid="advice-watched-row">
                  <div className="flex items-center gap-2">
                    <Icon className={`h-3.5 w-3.5 shrink-0 ${f.tone}`} />
                    <button type="button" onClick={() => onFocus?.(o)} className="text-sm text-foreground truncate hover:underline">
                      {flagBullet(o.league_id)} {o.name}
                    </button>
                    <span className={`text-[11px] ${f.tone}`}>{f.text}</span>
                    <span className="ml-auto text-[10px] text-muted-foreground">{o.list === "tracking" ? "Tracking" : "Favourite"}</span>
                    <TeamStar teamId={o.team_id} teamName={o.name} />
                  </div>
                  <p className="text-[11px] text-muted-foreground mt-0.5">{f.say} <FormLine o={o} /></p>
                </div>
              );
            })}
          </div>
        </section>
      )}

      <section className="bg-card border border-border rounded-lg p-3 sm:p-4" data-testid="advice-suggestions">
        <div className="flex items-center gap-2">
          <Sparkles className="h-4 w-4 text-primary" />
          <h2 className="font-head font-semibold">Worth tracking</h2>
        </div>
        <p className="text-[11px] text-muted-foreground mb-2">
          In form (last 5 a corner+ above their norm, or 3+ in a row) with a soft run of
          opponents coming up. Tap the eye to start tracking. A prompt to look, not a tip.
        </p>
        {sugg.length === 0 ? (
          <p className="text-[12px] text-muted-foreground py-2">
            Nobody fits right now — no in-form side has a soft run in the next three weeks.
          </p>
        ) : (
          <div className="divide-y divide-border/50">
            {sugg.map((o) => (
              <details key={o.team_id} className="py-2 group" data-testid="advice-suggestion">
                <summary className="flex items-center gap-2 cursor-pointer list-none">
                  <span className="text-sm text-foreground truncate">{flagBullet(o.league_id)} {o.name}</span>
                  <span className="text-[11px] text-primary whitespace-nowrap">Soft run · ×{o.schedule?.toFixed(2)}</span>
                  <span className="ml-auto" />
                  <TeamStar teamId={o.team_id} teamName={o.name} />
                </summary>
                <div className="mt-1"><FormLine o={o} /></div>
                <div className="mt-1"><NextFixtures games={o.next} /></div>
              </details>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
