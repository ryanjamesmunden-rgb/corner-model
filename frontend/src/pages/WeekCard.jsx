import { Fragment, useEffect, useMemo, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { CalendarDays, ChevronRight, Loader2, TriangleAlert } from "lucide-react";
import { api } from "@/lib/api";
import { withFlag } from "@/lib/countryFlag";
import { kickoffTime } from "@/lib/kickoff";
import { historyLines, lastTimeShort, lastTimeText } from "@/lib/review";
import {
  boardLabel, cardNote, dayStrip, lineLabel, PICK_RESULT, priceOf, recordOf,
  recordText, resultText, STATE_LABEL, STATE_TONE, warningsOf,
} from "@/lib/weekCard";

/**
 * The week card: one day's games, both sides of each, written out the way you would by
 * hand before deciding anything.
 *
 * WHY THIS IS NOT ANOTHER BOARD. Every other screen here is team-shaped — one row per
 * side, sorted by how good that side looks — which answers "who is in form". None of
 * them answers the question somebody actually sits down with, which is "what is on
 * tomorrow, and for each game, what is the bet". A game has two sides and a total, and
 * assembling one fixture from three boards by hand is the job this replaces.
 *
 * SO IT IS A DIARY, NOT A RANKING. Kick-off order, every game with something on it, no
 * score and no verdict. The ordering question is answered next door.
 *
 * THE PRICE IS THE BIGGEST THING ON THE ROW. The first version of this screen set the
 * price in the same size as everything around it and buried it among an edge, a fair
 * price, a board list and a two-line game-state sentence — six lines a side, three
 * nested borders, and the one number you are actually being offered lost in the middle.
 * Now the price is the headline, the record sits under it in green, and everything else
 * is either small or behind the detail toggle.
 *
 * AND EVERY PRICE NOW CARRIES ITS OWN MEMORY. "6+ at 1.73" with a record beside it still
 * left the first question anybody asks — did this line land last time, and at what —
 * answerable only from memory, while the site held the answer all along: the same key was
 * priced on this team's last games and those games have been played and settled. The
 * backend joins it on; the card prints one muted sentence per bet.
 *
 * TWO LAYOUTS, chosen with `?layout=`. They are the same data and the same components;
 * only the arrangement differs. See the note above LAYOUTS.
 */

const MIN_RUNS = [
  { v: "0", l: "Every game" },
  { v: "7", l: "7+ hits behind it" },
  { v: "8", l: "8+ hits behind it" },
  { v: "9", l: "9+ hits behind it" },
];

// ROWS reads like the handwritten card — two sides on one line, nothing boxed. TABLE
// aligns every price in a column, which is the thing a table does that a list cannot:
// it makes the day scannable DOWN rather than across.
const LAYOUTS = [["rows", "Rows"], ["table", "Table"]];

/**
 * The red number, and nothing else at this size.
 *
 * A model price is NEVER drawn like a book price. They are different kinds of thing —
 * one is an offer, the other is an opinion — and on a screen people bet from they must
 * not be able to be mistaken for each other, so an unquoted line is muted and prefixed.
 */
function Price({ pick, big = false }) {
  const price = priceOf(pick);
  if (!price) return <span className="text-sm text-muted-foreground">—</span>;
  const size = big ? "text-2xl" : "text-lg";
  if (!price.quoted) {
    return (
      <span className="whitespace-nowrap text-sm text-muted-foreground">
        fair {price.odds.toFixed(2)}
      </span>
    );
  }
  return (
    <span className={`${size} font-bold tabular-nums leading-none text-rose-500`}>
      {price.odds.toFixed(2)}
    </span>
  );
}

const Line = ({ pick }) =>
  pick ? <span className="font-semibold tabular-nums">{lineLabel(pick)}</span> : null;

/**
 * What a pick did, once the game has been played.
 *
 * THE PRICE STAYS WHERE IT WAS. A result that replaced the number would answer "did it
 * land" and lose "at what" — and the second is the half you need to judge the first.
 */
function Outcome({ pick }) {
  const r = pick?.result && PICK_RESULT[pick.result];
  if (!r) return null;
  return (
    <span className={`whitespace-nowrap text-xs font-medium ${r.cls}`}>
      {r.word}
      {typeof pick.actual === "number" && (
        <span className="ml-1 text-muted-foreground">({pick.actual})</span>
      )}
    </span>
  );
}

/**
 * The green half: what has actually happened, never without its denominator.
 *
 * GREEN MEANS IT BACKS THE BET BESIDE IT, and nothing else. A run at a different line is
 * still worth seeing — it is the side's form — but it is not evidence for the price
 * printed next to it, so it is drawn muted with its own line in front. The colour does
 * the work a repeated "not this line" was doing badly.
 */
function Record({ side }) {
  const text = recordText(side);
  if (!text) return null;
  const rec = recordOf(side);
  return (
    <span className={`text-sm ${rec?.atPick
      ? "font-medium text-emerald-600 dark:text-emerald-400"
      : "text-muted-foreground"}`}
      title={rec?.atPick ? "" : `Record at ${rec?.lineLabel}, not at the line priced here`}>
      {text}
    </span>
  );
}

/**
 * What this same line did the last few times it was priced.
 *
 * THE FIRST QUESTION ANYBODY ASKS of a price, and until now the only place to ask it was
 * memory. The board held the answer the whole time: the line was priced on this team's
 * last games and those games have since been played and settled.
 *
 * DRAWN MUTED, NOT GREEN, even though it IS a record of this exact bet. Green on this
 * screen means one thing — the run above backs the price beside it — and a second green
 * sentence under it halves the meaning of both. The word carries the result instead.
 *
 * NOTHING AT ALL when the line has never been priced on this team: never priced and never
 * landed are different facts, and a blank is read as the second.
 */
function LastTime({ pick, short = false }) {
  const text = short ? lastTimeShort(pick?.history) : lastTimeText(pick?.history);
  if (!text) return null;
  return (
    <div className="max-w-[15rem] truncate text-xs text-muted-foreground"
      title={historyLines(pick.history).join("\n")}>
      {text}
    </div>
  );
}

/** Everything that is not the bet: boards, game state, warnings. Folded away by default. */
function Detail({ card }) {
  const warnings = warningsOf(card);
  const sides = [card.home, card.away].filter((s) => s?.name);
  if (!warnings.length && !sides.some((s) => s.boards?.length || s.game_state)) return null;
  return (
    <div className="space-y-1 border-t border-border/50 pt-2 text-xs">
      {sides.map((s) => {
        const state = s.game_state?.verdict;
        if (!s.boards?.length && !state) return null;
        return (
          <div key={s.name} className="flex flex-wrap gap-x-2 text-muted-foreground">
            <span className="font-medium text-foreground">{s.name}</span>
            {s.boards?.length > 0 && <span>{s.boards.map(boardLabel).join(" + ")}</span>}
            {state && (
              <span className={STATE_TONE[state] || STATE_TONE.neutral}>
                {STATE_LABEL[state] || state}
                {s.game_state?.reasons?.[0] && (
                  <span className="text-muted-foreground"> · {s.game_state.reasons[0]}</span>
                )}
              </span>
            )}
          </div>
        );
      })}
      {warnings.map((w) => (
        <div key={w} className="flex gap-1.5 text-amber-600 dark:text-amber-400">
          <TriangleAlert className="mt-0.5 h-3 w-3 shrink-0" />
          <span>{w}</span>
        </div>
      ))}
    </div>
  );
}

function Meta({ card, open, setOpen, navigate }) {
  return (
    <div className="flex flex-wrap items-baseline gap-x-2 text-xs text-muted-foreground">
      <span className="font-medium tabular-nums text-foreground">
        {kickoffTime(card.date)}
      </span>
      <span>{card.league_name || card.league_id}</span>
      {resultText(card) && (
        <span className="font-medium text-foreground">· {resultText(card)}</span>
      )}
      <span className="hidden sm:inline">· {cardNote(card)}</span>
      <button type="button" onClick={() => setOpen(!open)}
        className="ml-auto hover:text-foreground">
        {open ? "less" : "why"}
      </button>
      <button type="button" onClick={() => navigate(`/fixture/${card.fixture_id}`)}
        className="inline-flex items-center text-primary hover:underline">
        numbers <ChevronRight className="h-3 w-3" />
      </button>
    </div>
  );
}

/** One side as it appears in the ROWS layout: name, line, price, record. */
function RowSide({ side, leagueId }) {
  if (!side?.name) return null;
  return (
    <div className="flex min-w-0 flex-1 items-center gap-2">
      <div className="min-w-0 flex-1">
        <div className="truncate text-sm font-medium">
          {withFlag(leagueId, side.name)}
        </div>
        <Record side={side} />
        <LastTime pick={side.pick} />
      </div>
      <div className="flex shrink-0 flex-col items-end gap-0.5">
        <span className="flex items-baseline gap-1.5">
          <Line pick={side.pick} />
          <Price pick={side.pick} big />
        </span>
        <Outcome pick={side.pick} />
      </div>
    </div>
  );
}

function RowsLayout({ cards, navigate }) {
  const [open, setOpen] = useState({});
  return (
    <div className="divide-y divide-border rounded-xl border border-border bg-card">
      {cards.map((c) => (
        <div key={c.fixture_id} className="space-y-1.5 px-3 py-2.5">
          <Meta card={c} open={!!open[c.fixture_id]} navigate={navigate}
            setOpen={(v) => setOpen((o) => ({ ...o, [c.fixture_id]: v }))} />
          <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:gap-5">
            <RowSide side={c.home} leagueId={c.league_id} />
            <RowSide side={c.away} leagueId={c.league_id} />
          </div>
          {c.total && (
            <div className="flex flex-wrap items-baseline gap-x-1.5 text-xs
              text-muted-foreground">
              <span>Match</span>
              <Line pick={c.total} />
              <Price pick={c.total} />
              <Outcome pick={c.total} />
              <LastTime pick={c.total} />
            </div>
          )}
          {open[c.fixture_id] && <Detail card={c} />}
        </div>
      ))}
    </div>
  );
}

function TableLayout({ cards, navigate }) {
  const [open, setOpen] = useState({});
  const cell = "px-2 py-2 align-top";
  return (
    /* The only element on this page allowed to scroll sideways — a six-column table
       cannot wrap into 390px and stay a table. */
    <div className="overflow-x-auto rounded-xl border border-border bg-card">
      <table className="w-full min-w-[46rem] text-sm">
        <thead className="border-b border-border text-xs uppercase tracking-wide
          text-muted-foreground">
          <tr>
            <th className={`${cell} text-left font-medium`}>Time</th>
            <th className={`${cell} text-left font-medium`}>Home</th>
            <th className={`${cell} text-right font-medium`}>Line</th>
            <th className={`${cell} text-left font-medium`}>Away</th>
            <th className={`${cell} text-right font-medium`}>Line</th>
            <th className={`${cell} text-right font-medium`}>Match</th>
            <th className={cell} />
          </tr>
        </thead>
        <tbody className="divide-y divide-border/60">
          {cards.map((c) => (
            // A Fragment WITH A KEY, not `<>`: the shorthand cannot carry one, and each
            // game is two sibling rows — the game and its folded-out detail.
            <Fragment key={c.fixture_id}>
              <tr>
                <td className={`${cell} whitespace-nowrap tabular-nums`}>
                  <div>{kickoffTime(c.date)}</div>
                  <div className="text-xs text-muted-foreground">
                    {c.league_name || c.league_id}
                  </div>
                </td>
                {[c.home, c.away].map((s, i) => (
                  <Fragment key={i === 0 ? "home" : "away"}>
                    <td className={cell}>
                      <div className="font-medium">{withFlag(c.league_id, s?.name)}</div>
                      <Record side={s} />
                      <LastTime pick={s?.pick} short />
                    </td>
                    <td className={`${cell} whitespace-nowrap text-right`}>
                      <Line pick={s?.pick} /> <Price pick={s?.pick} />
                    </td>
                  </Fragment>
                ))}
                <td className={`${cell} text-right`}>
                  {c.total ? (
                    <>
                      <div className="whitespace-nowrap">
                        <Line pick={c.total} /> <Price pick={c.total} />
                      </div>
                      <div className="flex justify-end">
                        <LastTime pick={c.total} short />
                      </div>
                    </>
                  ) : <span className="text-muted-foreground">—</span>}
                </td>
                <td className={`${cell} whitespace-nowrap text-right text-xs`}>
                  <button type="button"
                    onClick={() => setOpen((o) => ({ ...o, [c.fixture_id]: !o[c.fixture_id] }))}
                    className="text-muted-foreground hover:text-foreground">
                    {open[c.fixture_id] ? "less" : "why"}
                  </button>
                  <button type="button" onClick={() => navigate(`/fixture/${c.fixture_id}`)}
                    className="ml-2 text-primary hover:underline">numbers</button>
                </td>
              </tr>
              {open[c.fixture_id] && (
                <tr>
                  <td className="px-2 pb-2" colSpan={7}><Detail card={c} /></td>
                </tr>
              )}
            </Fragment>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default function WeekCard() {
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const days = useMemo(() => dayStrip(new Date(), 7), []);
  // TODAY, NOT THE FIRST CHIP. The strip reaches backwards now, so days[0] is three days
  // ago — opening the page on a day of results nobody asked for.
  const todayValue = useMemo(() => (days.find((d) => !d.past) || days[0]).value, [days]);
  const day = params.get("day") || todayValue;
  const layout = params.get("layout") === "table" ? "table" : "rows";
  const [minRun, setMinRun] = useState("0");
  const [pricedOnly, setPricedOnly] = useState(false);
  const [data, setData] = useState(null);
  const [err, setErr] = useState("");
  const [loading, setLoading] = useState(true);

  const setParam = (k, v) => {
    const next = new URLSearchParams(params);
    if (v) next.set(k, v); else next.delete(k);
    setParams(next);
  };

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
  const Layout = layout === "table" ? TableLayout : RowsLayout;

  return (
    <div className="mx-auto w-full max-w-5xl space-y-4 px-4 py-6">
      <header className="space-y-1">
        <h1 className="flex items-center gap-2 text-2xl font-semibold">
          <CalendarDays className="h-6 w-6 text-primary" />
          The week card
        </h1>
        <p className="text-sm text-muted-foreground">
          Every game with a run or a price on it, both sides, in kick-off order. Price in
          red, what has actually happened in green. Nothing here is ranked.
        </p>
      </header>

      <div className="flex flex-wrap items-center gap-1.5">
        {days.map((d) => (
          <button key={d.value} type="button" onClick={() => setParam("day", d.value)}
            className={`rounded-full border px-3 py-1 text-sm transition ${
              d.value === day ? "border-primary bg-primary/10 font-medium text-foreground"
                : d.past ? "border-border/60 text-muted-foreground/70 hover:border-primary/50"
                : "border-border text-muted-foreground hover:border-primary/50"}`}>
            {d.short}
          </button>
        ))}
        <span className="ml-auto flex overflow-hidden rounded-full border border-border">
          {LAYOUTS.map(([v, l]) => (
            <button key={v} type="button"
              onClick={() => setParam("layout", v === "rows" ? "" : v)}
              className={`px-3 py-1 text-xs ${layout === v
                ? "bg-primary/10 font-medium text-foreground" : "text-muted-foreground"}`}>
              {l}
            </button>
          ))}
        </span>
      </div>

      <div className="flex flex-wrap items-center gap-3 text-sm">
        <select value={minRun} onChange={(e) => setMinRun(e.target.value)}
          className="rounded-md border border-border bg-background px-2 py-1"
          aria-label="Shortest run behind a game">
          {MIN_RUNS.map((o) => <option key={o.v} value={o.v}>{o.l}</option>)}
        </select>
        <label className="flex items-center gap-1.5 text-muted-foreground">
          <input type="checkbox" checked={pricedOnly}
            onChange={(e) => setPricedOnly(e.target.checked)} />
          Priced games only
        </label>
        {!loading && !err && cards.length > 0 && (
          <span className="text-muted-foreground">
            {cards.length} on {chosen?.label}
            {data.with_runs > 0 && `, ${data.with_runs} with a run`}
          </span>
        )}
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

      {!loading && !err && cards.length > 0 && <Layout cards={cards} navigate={navigate} />}

      <p className="text-xs text-muted-foreground">
        A figure in green is that side's record <em>at the line priced beside it</em>. A
        grey one names its own line first — it is the side's form, not evidence for this
        bet. A grey <em>fair</em> price is the model's number, not one a book is offering.
        A <em>Last</em> line is what this same bet did the last few times it was priced on
        this team — hover it for the games. Game state is a label to read beside the
        price, not a measured edge.
      </p>
    </div>
  );
}
