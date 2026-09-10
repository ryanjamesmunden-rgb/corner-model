import { useState, useEffect } from "react";
import { CheckCircle2, XCircle, MinusCircle, Clock, ShieldCheck } from "lucide-react";
import { api } from "@/lib/api";
import { withFlag } from "@/lib/countryFlag";

// THE RECORD. The only page here anyone can read without an account.
//
// Everything else on this site is either the product or a tease for it. This is the
// evidence that the product is worth paying for, and evidence behind a login persuades
// nobody — so it is open, and it stays open.
//
// WHAT MAKES IT WORTH READING is that it cannot flatter itself. Every row comes from a
// list frozen BEFORE kick-off, so what is graded is what was claimed. Grading the streak
// board as it looks afterwards would count only the survivors — a team that misses drops
// off the board — and would publish a near-perfect week, every week, forever.
//
// NOTHING IS TIDIED AWAY. Misses are shown, pushes are shown, games still to settle are
// shown. A page that lists only the winners is an advert with a percentage on it, and a
// reader who checks one row against the actual result would catch it immediately.

const MARK = {
  win: { Icon: CheckCircle2, word: "Landed",
         cls: "text-tone-strong-fg border-tone-strong/45 bg-tone-strong/15" },
  loss: { Icon: XCircle, word: "Missed",
          cls: "text-tone-under-fg border-tone-under/45 bg-tone-under/15" },
  void: { Icon: MinusCircle, word: "Push",
          cls: "text-muted-foreground border-border" },
  pending: { Icon: Clock, word: "To play",
             cls: "text-tone-streak-fg border-tone-streak/40 bg-tone-streak/10" },
};

// Icon AND word, never the colour alone — the site's four tones are close enough under
// colour blindness that none of them is allowed to carry a meaning by itself.
function Mark({ result }) {
  const m = MARK[result] || MARK.pending;
  return (
    <span data-testid={`mark-${result}`}
      className={`inline-flex items-center gap-1 text-[10px] px-1.5 py-0.5 rounded border font-mono-data shrink-0 ${m.cls}`}>
      <m.Icon className="h-2.5 w-2.5" /> {m.word}
    </span>
  );
}

const weekLabel = (tag) => {
  if (!tag) return "";
  const d = new Date(`${tag}T00:00:00Z`);
  return Number.isNaN(d.getTime()) ? tag
    : d.toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" });
};

export default function Results() {
  const [data, setData] = useState(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    api.results().then(setData).catch(() => setFailed(true));
  }, []);

  if (failed) {
    return <Panel>Couldn't load the record just now. Refresh in a moment.</Panel>;
  }
  if (!data) {
    return (
      <div className="space-y-3">
        {[0, 1].map((i) => <div key={i} className="h-28 rounded-lg bg-secondary animate-pulse" />)}
      </div>
    );
  }

  const { summary = {}, weeks = [], posted = {} } = data;

  return (
    <div className="space-y-4 max-w-4xl" data-testid="results-page">
      <header className="space-y-2">
        <h1 className="font-head text-2xl font-bold tracking-tight">The record</h1>
        <p className="text-sm text-muted-foreground leading-relaxed max-w-2xl">
          Every corner streak posted, and how it actually landed. The list is frozen before
          kick-off, so what you see graded here is exactly what was claimed — misses and all.
        </p>
      </header>

      {/* THE HEADLINE. Deliberately not a lone big number: the rate is meaningless
          without the count it came from, and a reader who cannot see the denominator
          has been given an advert.
          Hidden entirely when nothing has been posted at all — "nothing has settled"
          and "nothing has been posted" are different facts, and stacking both panels
          said the same thing twice. */}
      {weeks.length > 0 && (
      <section className="bg-card border border-border rounded-lg p-4 sm:p-5" data-testid="results-summary">
        {summary.settled > 0 ? (
          <div className="flex items-end gap-4 flex-wrap">
            <div>
              <p className="font-mono-data text-4xl font-bold text-tone-strong-fg leading-none"
                data-testid="results-rate">{summary.hit_rate}%</p>
              <p className="text-xs text-muted-foreground mt-2">
                of posted streaks landed —{" "}
                <span className="text-foreground font-medium">
                  {summary.landed} of {summary.settled}
                </span>{" "}
                settled, over {summary.weeks} {summary.weeks === 1 ? "week" : "weeks"}
              </p>
            </div>
            <div className="ml-auto flex gap-4 font-mono-data text-xs">
              <Stat n={summary.landed} label="landed" cls="text-tone-strong-fg" />
              <Stat n={summary.missed} label="missed" cls="text-tone-under-fg" />
              {summary.voided > 0 && <Stat n={summary.voided} label="push" cls="text-muted-foreground" />}
              {summary.pending > 0 && <Stat n={summary.pending} label="to play" cls="text-tone-streak-fg" />}
            </div>
          </div>
        ) : (
          // NOT "0%". Nothing settled and everything missed are different facts, and a
          // page that shows 0% for the first is lying about the second.
          <p className="text-sm text-muted-foreground" data-testid="results-empty">
            Nothing has settled yet. The moment a posted streak's game is played it appears
            here — landed or missed, both.
          </p>
        )}
      </section>
      )}

      {weeks.map((w) => (
        <section key={w.tag} className="bg-card border border-border rounded-lg overflow-hidden"
          data-testid="results-week">
          <div className="px-4 py-3 border-b border-border flex items-center gap-3 flex-wrap">
            <span className="font-head font-semibold text-sm">{weekLabel(w.tag)}</span>
            <span className="font-mono-data text-[11px] text-muted-foreground">
              {w.settled > 0
                ? <>{w.landed}/{w.settled} landed</>
                : <>{w.rows.length} posted · none settled yet</>}
              {w.voided > 0 && <> · {w.voided} push</>}
              {w.pending > 0 && <> · {w.pending} to play</>}
            </span>
          </div>
          <div className="divide-y divide-border">
            {w.rows.map((r, i) => (
              <div key={i} className="px-4 py-2.5 flex items-center gap-3" data-testid="results-row">
                <div className="min-w-0 flex-1">
                  <p className="text-sm truncate">
                    <span className="font-medium">{withFlag(r.league_id, r.name)}</span>
                    <span className="font-mono-data text-muted-foreground"> {r.line_label}</span>
                  </p>
                  <p className="text-[11px] text-muted-foreground truncate mt-0.5">
                    {r.is_home ? "vs" : "@"} {r.opponent}
                    {/* THE ACTUAL COUNT, so any row can be checked against the real
                        result by someone who does not trust the page. That is the
                        difference between a record and a claim. */}
                    {r.value != null && (
                      <><span className="mx-1.5 opacity-40">·</span>
                        <span className="font-mono-data text-foreground">{r.value}</span> corners</>
                    )}
                  </p>
                </div>
                <Mark result={r.result} />
              </div>
            ))}
          </div>
        </section>
      ))}

      {/* ANGLES POSTED BY HAND — the ones off a fixture page, put on Instagram or X.
          Two lists, and the split is the honest part rather than a technicality: one was
          on record while the game was still to play, the other was written down after
          the result was known. Both are shown. Only the first is in the number above. */}
      {posted.claimed?.rows?.length > 0 && (
        <AngleList title="Posted before kick-off" tally={posted.claimed}
          testId="posted-claimed"
          blurb="Called publicly while the game was still to play, so these count in the record above." />
      )}
      {posted.recalled?.rows?.length > 0 && (
        <AngleList title="Posted on social, logged here later" tally={posted.recalled}
          testId="posted-recalled" muted
          blurb="Called publicly before kick-off, but written down here after the result was known —
                 so the timing is on the original post rather than on this site, and these stay out
                 of the number above. Not a judgement on the call: the site simply cannot prove to
                 you when it was made, and a percentage that can absorb after-the-fact winners
                 would not be worth reading." />
      )}

      {weeks.length === 0 && posted.claimed?.rows?.length === 0
        && posted.recalled?.rows?.length === 0 && (
        <Panel>
          No streaks have been posted yet. Once they are, every one of them shows up here
          with its result.
        </Panel>
      )}

      {/* HOW IT IS GRADED, in plain words. A record that will not explain its own method
          is asking to be taken on trust, which is the thing it exists to replace. */}
      <section className="bg-card border border-border rounded-lg p-4 text-xs text-muted-foreground
                          leading-relaxed space-y-2" data-testid="results-method">
        <p className="flex items-center gap-2 text-foreground font-medium text-sm">
          <ShieldCheck className="h-4 w-4 text-primary" /> How this is graded
        </p>
        <p>
          The streaks are written down before the games kick off. That matters more than it
          sounds: a team that misses drops off the streak board completely, so scoring the
          board <span className="text-foreground">afterwards</span> would only ever count the
          survivors and would show a near-perfect week every week.
        </p>
        <p>
          Results come from the same match data the model runs on. A game that hasn't been
          played or hasn't synced yet reads{" "}
          <span className="text-foreground">to play</span> rather than being left out, and an
          under that lands exactly on its line is a{" "}
          <span className="text-foreground">push</span> — stake back, counted as neither.
        </p>
        <p>
          {/* The split has to be explained where a reader meets it, or the "not counted"
              chip looks like a hedge instead of the point. */}
          Angles posted by hand to Instagram or X are logged separately, and what separates them
          is <span className="text-foreground">when the site could see the claim</span>, not
          whether the call was good. Written down here while the game was still to play, it counts
          like anything else. Written down afterwards, the proof of timing lives on the original
          post rather than here, so it is shown in full and{" "}
          <span className="text-foreground">left out of the number above</span> — a percentage that
          can absorb after-the-fact winners would not be worth reading.
        </p>
        <p>
          {/* Stated, not glossed. Someone will ask what it paid, and the honest answer is
              that these were never priced — so inventing a return would be fiction. */}
          This is a strike rate, not a profit. The snapshots record the line that was posted,
          never the odds anyone actually took, so what it can tell you honestly is how often
          the run continued — not what it returned.
        </p>
      </section>
    </div>
  );
}

// A list of hand-posted angles. Same row shape as a snapshot week so the two read as
// one record, with the heading carrying the difference rather than the rows.
const AngleList = ({ title, tally, blurb, testId, muted = false }) => (
  <section className={`bg-card border rounded-lg overflow-hidden ${
    muted ? "border-dashed border-border" : "border-border"}`} data-testid={testId}>
    <div className="px-4 py-3 border-b border-border">
      <div className="flex items-center gap-3 flex-wrap">
        <span className="font-head font-semibold text-sm">{title}</span>
        <span className="font-mono-data text-[11px] text-muted-foreground">
          {tally.settled > 0 ? <>{tally.landed}/{tally.settled} landed</> : <>none settled yet</>}
          {tally.voided > 0 && <> · {tally.voided} push</>}
          {tally.pending > 0 && <> · {tally.pending} to play</>}
        </span>
        {muted && (
          <span className="text-[10px] px-1.5 py-0.5 rounded border border-border text-muted-foreground font-mono-data">
            not counted
          </span>
        )}
      </div>
      <p className="text-[11px] text-muted-foreground mt-1.5 leading-relaxed max-w-2xl">{blurb}</p>
    </div>
    <div className="divide-y divide-border">
      {tally.rows.map((r, i) => (
        <div key={i} className="px-4 py-2.5 flex items-center gap-3" data-testid="posted-row">
          <div className="min-w-0 flex-1">
            <p className="text-sm truncate">
              <span className="font-medium">{withFlag(r.league_id, r.name)}</span>
              <span className="font-mono-data text-muted-foreground"> {r.line_label}</span>
            </p>
            <p className="text-[11px] text-muted-foreground truncate mt-0.5">
              {r.is_home === false ? "@" : "vs"} {r.opponent}
              {r.value != null && (
                <><span className="mx-1.5 opacity-40">·</span>
                  <span className="font-mono-data text-foreground">{r.value}</span> corners</>
              )}
              {r.posted_to && <><span className="mx-1.5 opacity-40">·</span>{r.posted_to}</>}
            </p>
          </div>
          <Mark result={r.result} />
        </div>
      ))}
    </div>
  </section>
);

const Stat = ({ n, label, cls }) => (
  <span className="text-right">
    <span className={`block text-lg font-semibold leading-none ${cls}`}>{n}</span>
    <span className="block text-[10px] text-muted-foreground mt-1">{label}</span>
  </span>
);

const Panel = ({ children }) => (
  <p className="bg-card border border-border rounded-lg px-4 py-6 text-sm text-muted-foreground"
    data-testid="results-panel">{children}</p>
);
