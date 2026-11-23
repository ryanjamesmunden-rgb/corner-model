import { useEffect, useMemo, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { CalendarDays, ChevronRight, Loader2, TriangleAlert } from "lucide-react";
import { api } from "@/lib/api";
import { withFlag } from "@/lib/countryFlag";
import { kickoffTime } from "@/lib/kickoff";
import TeamStar from "@/components/TeamStar";
import TierBadge from "@/components/TierBadge";
import {
  boardLabel, cardNote, dayStrip, lineLabel, priceOf, recordText,
  slotsOf, STATE_LABEL, STATE_TONE, warningsOf,
} from "@/lib/weekCard";

/**
 * The week card: one day's games, both sides of each, written out the way you would by
 * hand before deciding anything.
 *
 * WHY THIS IS NOT ANOTHER BOARD. Every other screen here is team-shaped — one row per
 * side, sorted by how good that side looks — which answers "who is in form". None of
 * them answers the question somebody actually sits down with, which is "what is on
 * tomorrow, and for each game, what is the bet and what is behind it". A game has two
 * sides and a total, and assembling one fixture from three boards by hand is the job
 * this replaces.
 *
 * SO IT IS A DIARY, NOT A RANKING. Kick-off order, every game with something on it, no
 * score and no verdict. The ordering question is already answered next door.
 *
 * RED IS THE PRICE, GREEN IS THE RECORD. Straight off the paper version, and the split
 * matters: one is a bookmaker's number and the other is a history, and reading them as a
 * single claim is how a 5+ record ends up credited to a 6+ bet. Where the run is at a
 * different line from the price, the green half says so in words.
 */

const MIN_RUNS = [
  { v: "0", l: "Every game" },
  { v: "7", l: "7+ hits behind it" },
  { v: "8", l: "8+ hits behind it" },
  { v: "9", l: "9+ hits behind it" },
];

function Price({ pick }) {
  const price = priceOf(pick);
  if (!price) return <span className="text-sm text-muted-foreground">No line</span>;
  return (
    <span className="flex flex-wrap items-baseline gap-x-2 gap-y-0.5">
      <span className="font-semibold text-foreground">{lineLabel(pick)}</span>
      {/* THE RED NUMBER. Only ever a price somebody is offering — a model price is drawn
          plainly and labelled, because the two cannot look alike on a card people bet
          from. */}
      {price.quoted ? (
        <span className="font-semibold tabular-nums text-rose-600 dark:text-rose-400">
          {price.odds.toFixed(2)}
        </span>
      ) : (
        <span className="text-sm text-muted-foreground">
          fair {price.odds.toFixed(2)} · no price yet
        </span>
      )}
      {price.quoted && price.ev !== null && (
        <span className="text-xs tabular-nums text-muted-foreground">
          {price.ev > 0 ? "+" : ""}{price.ev.toFixed(0)}% · fair {price.fair?.toFixed(2)}
        </span>
      )}
    </span>
  );
}

function Side({ side, venue, leagueId }) {
  if (!side?.name) return null;
  const record = recordText(side);
  const state = side.game_state?.verdict;
  return (
    <div className="flex-1 min-w-0 space-y-1 rounded-lg border border-border/60 bg-card/50 p-3">
      <div className="flex items-start justify-between gap-2">
        <span className="font-medium leading-tight">
          {withFlag(leagueId, side.name)}
          <span className="ml-1.5 text-xs text-muted-foreground">({venue})</span>
        </span>
        {side.team_id && <TeamStar teamId={side.team_id} teamName={side.name} />}
      </div>
      <Price pick={side.pick} />
      {/* THE GREEN NUMBER: what has actually happened, as many times out of how many.
          Never without its denominator — see the digest's own note on why. */}
      {record && (
        <div className="text-sm font-medium text-emerald-600 dark:text-emerald-400">
          {record}
        </div>
      )}
      {!record && side.pick && (
        <div className="text-sm text-muted-foreground">No run behind this one</div>
      )}
      {side.boards?.length > 0 && (
        <div className="text-xs text-muted-foreground">
          {side.boards.map(boardLabel).join(" + ")}
        </div>
      )}
      {state && (
        <div className={`text-xs ${STATE_TONE[state] || STATE_TONE.neutral}`}>
          {STATE_LABEL[state] || state}
          {side.game_state?.reasons?.[0] && (
            <span className="text-muted-foreground"> · {side.game_state.reasons[0]}</span>
          )}
        </div>
      )}
    </div>
  );
}

function Card({ card, navigate }) {
  const warnings = warningsOf(card);
  const total = card.total;
  return (
    <div className="rounded-xl border border-border bg-card p-3 sm:p-4 space-y-3">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-sm">
        <span className="font-medium tabular-nums">{kickoffTime(card.date)}</span>
        <span className="text-muted-foreground">{card.league_name || card.league_id}</span>
        <TierBadge tier={card.tier} />
        <span className="text-xs text-muted-foreground">{cardNote(card)}</span>
        {card.fixture_id && (
          <button
            type="button"
            onClick={() => navigate(`/fixture/${card.fixture_id}`)}
            className="ml-auto inline-flex items-center gap-1 text-xs text-primary hover:underline"
          >
            The numbers <ChevronRight className="h-3 w-3" />
          </button>
        )}
      </div>

      <div className="flex flex-col gap-2 sm:flex-row">
        {slotsOf(card).map(({ key, side, venue }) => (
          <Side key={key} side={side} venue={venue} leagueId={card.league_id} />
        ))}
      </div>

      {/* THE MATCH LINE UNDERNEATH, exactly where it goes on the paper card: it is the
          third bet on the game, not a property of either side. */}
      {total && (
        <div className="flex flex-wrap items-baseline gap-2 rounded-lg bg-muted/40 px-3 py-2 text-sm">
          <span className="text-muted-foreground">Match total</span>
          <Price pick={total} />
        </div>
      )}

      {warnings.length > 0 && (
        <ul className="space-y-0.5 text-xs text-amber-600 dark:text-amber-400">
          {warnings.map((w) => (
            <li key={w} className="flex gap-1.5">
              <TriangleAlert className="mt-0.5 h-3 w-3 shrink-0" />
              <span>{w}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export default function WeekCard() {
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const days = useMemo(() => dayStrip(new Date(), 7), []);
  const day = params.get("day") || days[0].value;
  const [minRun, setMinRun] = useState("0");
  const [pricedOnly, setPricedOnly] = useState(false);
  const [data, setData] = useState(null);
  const [err, setErr] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let live = true;
    setLoading(true);
    setErr("");
    api.weekCard({ day, minRun: Number(minRun), pricedOnly })
      .then((d) => { if (live) setData(d); })
      .catch((e) => {
        if (!live) return;
        const status = e?.response?.status;
        setErr(status === 401 ? "Sign in to see the card."
          : status === 402 ? "The card is part of the membership."
          : e?.message || "Could not load the card");
      })
      .finally(() => { if (live) setLoading(false); });
    return () => { live = false; };
  }, [day, minRun, pricedOnly]);

  const cards = data?.cards || [];
  const chosen = days.find((d) => d.value === day);

  return (
    <div className="mx-auto w-full max-w-4xl space-y-4 px-4 py-6">
      <header className="space-y-1">
        <h1 className="flex items-center gap-2 text-2xl font-semibold">
          <CalendarDays className="h-6 w-6 text-primary" />
          The week card
        </h1>
        <p className="text-sm text-muted-foreground">
          Every game with a run or a price on it, both sides, in kick-off order. The price
          is in red, what has actually happened is in green. Nothing here is ranked — the
          boards do that.
        </p>
      </header>

      <div className="flex flex-wrap gap-1.5">
        {days.map((d) => (
          <button
            key={d.value}
            type="button"
            onClick={() => setParams(d.value === days[0].value ? {} : { day: d.value })}
            className={`rounded-full border px-3 py-1 text-sm transition ${
              d.value === day
                ? "border-primary bg-primary/10 font-medium text-foreground"
                : "border-border text-muted-foreground hover:border-primary/50"
            }`}
          >
            {d.short}
          </button>
        ))}
      </div>

      <div className="flex flex-wrap items-center gap-3 text-sm">
        <select
          value={minRun}
          onChange={(e) => setMinRun(e.target.value)}
          className="rounded-md border border-border bg-background px-2 py-1"
          aria-label="Shortest run behind a game"
        >
          {MIN_RUNS.map((o) => <option key={o.v} value={o.v}>{o.l}</option>)}
        </select>
        <label className="flex items-center gap-1.5 text-muted-foreground">
          <input
            type="checkbox"
            checked={pricedOnly}
            onChange={(e) => setPricedOnly(e.target.checked)}
          />
          Priced games only
        </label>
      </div>

      {loading && (
        <div className="flex items-center gap-2 py-10 text-muted-foreground">
          <Loader2 className="h-4 w-4 animate-spin" /> Building {chosen?.label}…
        </div>
      )}

      {!loading && err && (
        <div className="rounded-lg border border-border bg-card p-4 text-sm">{err}</div>
      )}

      {!loading && !err && cards.length === 0 && (
        /* WHICH KIND OF NOTHING. A filter that removed everything and a day with no games
           look identical otherwise — the same reason the backend reports `considered`. */
        <div className="rounded-lg border border-border bg-card p-4 text-sm text-muted-foreground">
          {data?.considered
            ? `Nothing on ${chosen?.label} cleared that filter — ${data.considered} `
              + `${data.considered === 1 ? "game was" : "games were"} looked at.`
            : `Nothing with a run or a price on ${chosen?.label}.`}
        </div>
      )}

      {!loading && !err && cards.length > 0 && (
        <>
          <p className="text-sm text-muted-foreground">
            {cards.length} {cards.length === 1 ? "game" : "games"} on {chosen?.label}
            {data.with_runs > 0 && `, ${data.with_runs} with a run behind them`}.
            {data.considered > cards.length
              && ` ${data.considered - cards.length} filtered out.`}
          </p>
          <div className="space-y-3">
            {cards.map((c) => (
              <Card key={c.fixture_id} card={c} navigate={navigate} />
            ))}
          </div>
        </>
      )}

      <p className="text-xs text-muted-foreground">
        The green figure is that side's own record at the line printed above it; where the
        run is at a different line, it says so. Game state is a label to read beside the
        price, not a measured edge — it has not been replayed against a control yet.
      </p>
    </div>
  );
}
