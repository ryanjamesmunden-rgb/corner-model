import { useEffect, useState } from "react";
import { History, Loader2 } from "lucide-react";
import { api } from "@/lib/api";
import { withFlag } from "@/lib/countryFlag";
import { kickoffDay } from "@/lib/kickoff";
import {
  gameRows, headline, lineText, RESULT_TONE, scoreline,
} from "@/lib/review";

/**
 * The week in review: played games, the prices that were on them, and what landed.
 *
 * WHY A FIXTURE SHOULD NOT VANISH AT KICK-OFF. Until this page every board dropped a game
 * the moment it started, and its twenty-odd stored lines went with it — so the question
 * behind every week, "which of the edges we published actually landed and at what price",
 * had nothing to read. The prices were in the database the whole time; nobody had written
 * the join.
 *
 * THE HEADLINE IS THE +EV RATE AND NOT THE HIT RATE. Every stored ladder carries rungs
 * nobody would back — a 2+ team line at 1.07 lands almost always — so a rate across all of
 * them describes the ladder and flatters the model. The number worth reading weekly is how
 * the lines the model CALLED value actually did.
 *
 * LOSERS ARE NOT FOLDED AWAY. The +EV lines are shown in full, winners and misses
 * together, because a review that listed only what came in is a tipster's results page and
 * would never show the model being wrong about which line to like.
 */

const WINDOWS = [
  { v: 3, l: "Last 3 days" },
  { v: 7, l: "Last week" },
  { v: 14, l: "Last 2 weeks" },
  { v: 30, l: "Everything kept" },
];

function Stat({ label, value, sub }) {
  return (
    <div className="min-w-0">
      <p className="font-mono-data text-2xl font-bold leading-none">{value}</p>
      <p className="mt-1.5 text-[11px] text-muted-foreground">
        {label}{sub && <span className="block">{sub}</span>}
      </p>
    </div>
  );
}

function Line({ l }) {
  return (
    <li className={`text-sm ${RESULT_TONE[l.result] || "text-muted-foreground"}`}>
      {lineText(l)}
      {typeof l.ev === "number" && (
        <span className="ml-1.5 text-[11px] text-muted-foreground">
          model said {l.ev > 0 ? "+" : ""}{l.ev.toFixed(0)}%
        </span>
      )}
    </li>
  );
}

function Game({ row }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="space-y-1.5 px-3 py-3">
      <div className="flex flex-wrap items-baseline gap-x-2 text-sm">
        <span className="font-medium">
          {withFlag(row.league, `${row.home} v ${row.away}`)}
        </span>
        <span className="text-xs text-muted-foreground">{kickoffDay(row.date)}</span>
        <span className="text-xs text-muted-foreground">· {scoreline(row)}</span>
        {row.evPlus > 0 && (
          <span className="ml-auto text-xs text-muted-foreground">
            {row.evPlusLanded}/{row.evPlus} of its +EV lines landed
          </span>
        )}
      </div>

      {row.evLines.length > 0 ? (
        <ul className="space-y-0.5">
          {row.evLines.map((l) => <Line key={l.key} l={l} />)}
        </ul>
      ) : (
        <p className="text-sm text-muted-foreground">
          {row.priced > 0
            ? `${row.priced} lines priced, none the model called value.`
            : "No price was ever stored on this game."}
        </p>
      )}

      {row.otherLines.length > 0 && (
        <>
          <button type="button" onClick={() => setOpen(!open)}
            className="text-xs text-muted-foreground hover:text-foreground">
            {open ? "hide" : `the other ${row.otherLines.length} priced lines`}
          </button>
          {open && (
            <ul className="space-y-0.5 border-t border-border/50 pt-1.5">
              {row.otherLines.map((l) => <Line key={l.key} l={l} />)}
            </ul>
          )}
        </>
      )}
    </div>
  );
}

export default function Review() {
  const [days, setDays] = useState(7);
  const [data, setData] = useState(null);
  const [err, setErr] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let live = true;
    setLoading(true);
    setErr("");
    api.review({ days })
      .then((d) => { if (live) setData(d); })
      .catch((e) => {
        if (!live) return;
        const s = e?.response?.status;
        setErr(s === 401 ? "Sign in to see the review."
          : s === 402 ? "The review is part of the membership."
          : e?.message || "Could not load the review");
      })
      .finally(() => { if (live) setLoading(false); });
    return () => { live = false; };
  }, [days]);

  const h = headline(data);
  const rows = gameRows(data);
  const best = Array.isArray(data?.best) ? data.best : [];

  return (
    <div className="mx-auto w-full max-w-4xl space-y-4 px-4 py-6">
      <header className="space-y-1">
        <h1 className="flex items-center gap-2 text-2xl font-semibold">
          <History className="h-6 w-6 text-primary" />
          The week in review
        </h1>
        <p className="text-sm text-muted-foreground">
          Games that have been played, with every price that was stored on them, settled.
          The rate below counts only the lines the model called value — the full ladder
          includes rungs nobody would back, and its hit rate flatters the model.
        </p>
      </header>

      <div className="flex flex-wrap gap-1.5">
        {WINDOWS.map((w) => (
          <button key={w.v} type="button" onClick={() => setDays(w.v)}
            className={`rounded-full border px-3 py-1 text-sm transition ${
              w.v === days ? "border-primary bg-primary/10 font-medium text-foreground"
                : "border-border text-muted-foreground hover:border-primary/50"}`}>
            {w.l}
          </button>
        ))}
      </div>

      {loading && (
        <div className="flex items-center gap-2 py-10 text-muted-foreground">
          <Loader2 className="h-4 w-4 animate-spin" /> Settling the week…
        </div>
      )}

      {!loading && err && (
        <div className="rounded-lg border border-border bg-card p-4 text-sm">{err}</div>
      )}

      {!loading && !err && (
        <>
          <section className="rounded-xl border border-border bg-card p-4">
            <div className="flex flex-wrap gap-x-8 gap-y-4">
              <Stat label="of the model's +EV lines landed"
                sub={h.settled ? `${h.evPlusLanded} of ${h.settled} settled` : null}
                value={h.rate === null ? "—" : `${h.rate}%`} />
              <Stat label="flat-stake units on those lines"
                value={h.profit === null ? "—"
                  : `${h.profit > 0 ? "+" : ""}${h.profit.toFixed(2)}u`} />
              <Stat label="games reviewed"
                sub={h.awaiting ? `${h.awaiting} still awaiting corners` : null}
                value={h.graded} />
              <Stat label="prices settled"
                sub={`${h.evPlus} of them +EV`} value={h.lines} />
            </div>
            {h.rate === null && (
              /* Nothing settled and everything missed are different facts. */
              <p className="mt-3 text-xs text-muted-foreground">
                Nothing has settled in this window yet — that is not a nil return.
              </p>
            )}
          </section>

          {best.length > 0 && (
            <section className="rounded-xl border border-border bg-card">
              <div className="px-3 pt-3 pb-1">
                <h2 className="text-sm font-semibold">The biggest edges that came in</h2>
                <p className="text-xs text-muted-foreground">
                  Ranked by the edge the model claimed, not by the price — the question is
                  whether it was right where it most disagreed with the book.
                </p>
              </div>
              <ul className="divide-y divide-border">
                {best.map((b) => (
                  <li key={`${b.fixture_id}-${b.key}`}
                    className="flex flex-wrap items-baseline gap-x-2 px-3 py-2 text-sm">
                    <span className="font-medium">{b.home_name} v {b.away_name}</span>
                    <span className={RESULT_TONE.won}>{lineText(b)}</span>
                    <span className="ml-auto text-xs text-muted-foreground">
                      model said +{Number(b.ev).toFixed(0)}%
                    </span>
                  </li>
                ))}
              </ul>
            </section>
          )}

          {rows.length === 0 ? (
            <div className="rounded-lg border border-border bg-card p-4 text-sm text-muted-foreground">
              No games played in this window yet.
            </div>
          ) : (
            <section className="divide-y divide-border rounded-xl border border-border bg-card">
              {rows.map((r) => <Game key={r.fixtureId} row={r} />)}
            </section>
          )}
        </>
      )}

      <p className="text-xs text-muted-foreground">
        The edge shown is the model as it stands <em>now</em>, against the price as it was
        stored — right for asking whether the model spots these, wrong for asking what the
        board showed on the day. The Results page grades the frozen claims for that.
      </p>
    </div>
  );
}
