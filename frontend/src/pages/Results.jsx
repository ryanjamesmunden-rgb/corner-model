import { useState, useEffect } from "react";
import { CheckCircle2, XCircle, MinusCircle, Clock, ShieldCheck, Video } from "lucide-react";
import { api } from "@/lib/api";
import { withFlag } from "@/lib/countryFlag";
import StoryButton from "@/components/StoryButton";
import { renderResultStory } from "@/lib/storyImage";
import { canRecord, extFor, recordStoryVideo } from "@/lib/storyVideo";
import { kickoffLabel } from "@/lib/kickoff";
import SignedInOnly from "@/components/SignedInOnly";
import { renderRecordCard, renderDayCard } from "@/lib/storyImage";
import { cardFrom, dayCardFrom, settledDays } from "@/lib/recordCard";
import TopAngle from "@/components/TopAngle";
import ErrorBoundary from "@/components/ErrorBoundary";

// THE RECORD, behind a free account.
//
// It was open, and the reasoning was that this is the evidence the product is worth paying
// for — and evidence behind a login persuades nobody. That reasoning still holds; the
// trade was made anyway, because the record IS the list of picks this site made and the
// picks are the product. Signing in costs nothing, so it is a door and not a wall.
//
// WHICH IS WHY THE SHARE CARD MATTERS MORE NOW. The page is gated; the card is not. It
// carries the same fraction to somewhere a stranger will actually see it — see
// lib/recordCard for the three rules it has to obey to be worth anything.
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

// SHARE THE OUTCOME. The preview story asks people to believe a percentage; this one
// shows what happened, and it is the more persuasive of the two — "we said 63% chance of
// 5+" is a claim, "it finished on 11" is a fact anyone can check.
//
// Only on rows that have actually settled. A "to play" row has no result to animate, and
// a button that produces an image of nothing is worse than no button.
function ResultShare({ row }) {
  if (!row || row.result === "pending" || row.value == null) return null;
  const args = {
    homeName: row.is_home === false ? row.opponent : row.name,
    awayName: row.is_home === false ? row.name : row.opponent,
    leagueId: row.league_id, kickoff: kickoffLabel(row.kickoff),
    team: row.name, line: row.line, direction: row.direction, subject: row.subject,
    value: row.value, result: row.result, prob: row.prob ?? null, dist: row.dist || [],
  };
  const key = `result-${row.name}-${row.line}-${row.value}`.replace(/\s+/g, "-");
  return (
    <span className="flex items-center gap-1.5 shrink-0">
      <StoryButton days={[{ key }]} testId={`result-story-${key}`} label="Share"
        title="Instagram Story — the line called, and what the game produced"
        render={(canvas) => renderResultStory(canvas, args)} />
      {canRecord() && (
        <StoryButton days={[{ key }]} testId={`result-video-${key}`} icon={Video} label="Video"
          title="A Story video — the corner count climbs to what it finished on"
          makeFile={async (day) => {
            const canvas = document.createElement("canvas");
            const { blob, mime, type, ext } = await recordStoryVideo(canvas, (progress) =>
              renderResultStory(canvas, { ...args, progress }));
            const container = extFor(mime);
            return new File([blob], `corner-model-${day.key}.${ext || container}`,
                            { type: type || `video/${container}` });
          }} />
      )}
    </span>
  );
}

const weekLabel = (tag) => {
  if (!tag) return "";
  const d = new Date(`${tag}T00:00:00Z`);
  return Number.isNaN(d.getTime()) ? tag
    : d.toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" });
};

// BEHIND A FREE ACCOUNT NOW. This was the one deliberately open page — the record of
// every posted streak and how it landed — on the reasoning that evidence behind a login
// persuades nobody. That reasoning still holds and the trade was made anyway: the record
// is a list of the picks this site made, and the picks are the product.
//
// Signing in costs nothing, so this is a door and not a wall. What it stops is the record
// being read by someone who has given nothing at all. The API agrees — /api/results answers
// 401 to a guest — so this is the experience, not the gate.
export default function Results() {
  return (
    <SignedInOnly
      title="The record is for account holders"
      blurb="Every streak this site posted before kick-off, and how each one landed —
             wins, misses and voids, graded off a snapshot taken while it was still a
             prediction. It cannot flatter itself, which is the whole point of it.">
      <ResultsBoard />
    </SignedInOnly>
  );}

/**
 * Share the whole record, rather than one game.
 *
 * DRAWS NOTHING WHEN THERE IS NOTHING TO SHOW. cardFrom returns null before anything has
 * settled, and a button that produces a blank graphic is worse than no button — so it
 * disappears instead, and the reason is a real one rather than a disabled tooltip.
 */
function RecordCardButtons({ data }) {
  const feed = cardFrom(data, { shape: "feed" });
  if (!feed) return null;
  const shapes = [
    { key: "feed", label: "Feed card", shape: "feed",
      title: "1080x1350 — the record as an Instagram feed post" },
    { key: "story", label: "Story card", shape: "story",
      title: "1080x1920 — the record as a Story" },
  ];
  // THE LAST DAY THAT SETTLED ANYTHING, which is almost always the one worth posting and
  // is never a day you have to go looking for.
  const lastDay = settledDays(data)[0];
  const day = lastDay ? dayCardFrom(data, { date: lastDay, shape: "feed" }) : null;
  return (
    <span className="flex gap-2 flex-wrap">
      {shapes.map((s) => (
        <StoryButton key={s.key} days={[{ key: `record-${s.key}` }]}
          testId={`record-card-${s.key}`} label={s.label} title={s.title}
          render={(canvas) => renderRecordCard(canvas, {
            card: cardFrom(data, { shape: s.shape }), shape: s.shape })} />
      ))}
      {/* ONE DAY, WITH THE MONTH ON IT. A day card is chosen and the chosen day is the
          good one, so on its own it is a true number arranged into a false impression —
          see dayCardFrom for why the running record is not optional on it. */}
      {day && shapes.map((s) => (
        <StoryButton key={`day-${s.key}`} days={[{ key: `day-${s.key}` }]}
          testId={`day-card-${s.key}`} label={`${s.label.split(" ")[0]} · ${day.big}`}
          title={`${s.title.split(" — ")[0]} — the last day that settled, with the month on it`}
          render={(canvas) => renderDayCard(canvas, {
            card: dayCardFrom(data, { date: lastDay, shape: s.shape }), shape: s.shape })} />
      ))}
    </span>
  );
}

function ResultsBoard() {
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

  const { summary = {}, weeks = [], posted = {}, archive = null } = data;
  // THE RECORD STARTS AGAIN AT THE RULE CHANGE, so on day one there is nothing in it. That
  // is the honest state of a two-day-old rule and it has to be said in words — an empty
  // panel where a percentage used to be reads as the site having lost the record.
  const archiveWeeks = archive?.weeks || [];

  return (
    <div className="space-y-4 max-w-4xl" data-testid="results-page">
      <header className="space-y-2">
        <div className="flex items-start gap-3 flex-wrap">
          <h1 className="font-head text-2xl font-bold tracking-tight">The record</h1>
          {/* THE PAGE IS GATED; THIS IS NOT. A card is how the fraction reaches someone
              who has not signed in — which, now that the record is behind an account, is
              the only way it reaches them at all. Two shapes because Instagram wants a
              1080x1350 feed post and a 1080x1920 story, and one cropped into the other
              loses either the headline or the strip. */}
          <RecordCardButtons data={data} />
        </div>
        <p className="text-sm text-muted-foreground leading-relaxed max-w-2xl">
          Every corner streak posted, and how it actually landed. The list is frozen before
          kick-off, so what you see graded here is exactly what was claimed — misses and all.
        </p>
      </header>

      {/* THE CLEAN SLATE, SAID OUT LOUD. The picks used to need only a streak; they now
          need the fixture to back it up. One percentage across both would be an average of
          two rules with no way for a reader to tell which they were being sold, so the
          record starts again — and on day one that means it is nearly empty. Saying why
          is the difference between a new record and a lost one. */}
      {archiveWeeks.length > 0 && (
        <p className="text-xs text-muted-foreground bg-secondary/40 border border-border
                      rounded-lg px-4 py-3 leading-relaxed max-w-2xl"
          data-testid="results-rule-change">
          <span className="text-foreground font-medium">The record below starts from the
          rule change.</span>{" "}
          A streak used to be enough on its own; it now has to be backed by the fixture —
          a weak opponent and a model probability above the bar. Mixing the two would
          average two different methods into one number that describes neither. Everything
          from before is kept in full{" "}
          <a href="#earlier-rule" className="text-primary underline">further down</a>, graded
          the same way and counted separately.
        </p>
      )}

      {/* TODAY'S CALL, DIRECTLY ABOVE THE GRADED HISTORY OF THE RULE THAT MADE IT.
          That arrangement is the argument: every other panel on this page is what the site
          said and how it landed, and the one thing missing was what it is saying now. Put
          anywhere else it would be a tip; put here it is a tip with its own record under
          it, and a reader can decide how much that record is worth.

          WRAPPED, because this panel calls a different endpoint from the rest of the page
          and a failure in it must not take the record down with it — the record is the
          thing this page is for. */}
      <ErrorBoundary label="Today's angle">
        <TopAngle />
      </ErrorBoundary>

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

      {weeks.map((w) => <WeekBlock key={w.tag} w={w} />)}

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

      {/* NOTHING UNDER THE NEW RULE YET, WHICH IS NOT THE SAME AS NOTHING AT ALL. With an
          archive present this must not say "no streaks have been posted" — the site has
          posted plenty, under a rule that has since changed, and claiming otherwise reads
          as the record having been lost rather than restarted. */}
      {weeks.length === 0 && archiveWeeks.length > 0 && (
        <Panel>
          Nothing has been posted under the new rule yet. The first night it publishes an
          angle, it appears here — and the earlier record is below, untouched.
        </Panel>
      )}

      {weeks.length === 0 && archiveWeeks.length === 0
        && posted.claimed?.rows?.length === 0
        && posted.recalled?.rows?.length === 0 && (
        <Panel>
          No streaks have been posted yet. Once they are, every one of them shows up here
          with its result.
        </Panel>
      )}

      {/* THE EARLIER RULE. Kept whole, graded the same way, counted on its own. Those calls
          were made before kick-off and they landed or they did not — hiding them because
          the method has moved on is how a record turns into a highlight reel. It also
          cannot be rebuilt: a snapshot is the only evidence of what was claimed before a
          game was played, and recomputing it afterwards counts only the survivors. */}
      {archiveWeeks.length > 0 && (
        <section id="earlier-rule" className="space-y-4 pt-2" data-testid="results-archive">
          <div className="flex items-baseline gap-3 flex-wrap border-t border-border pt-5">
            <h2 className="font-head text-lg font-semibold">Under the earlier rule</h2>
            <span className="font-mono-data text-[11px] text-muted-foreground">
              {archive.summary?.settled > 0
                ? <>{archive.summary.landed}/{archive.summary.settled} landed</>
                : <>none settled</>}
              {archive.summary?.pending > 0 && <> · {archive.summary.pending} to play</>}
            </span>
            <span className="text-[10px] px-1.5 py-0.5 rounded border border-border
                             text-muted-foreground font-mono-data">
              not counted above
            </span>
          </div>
          <p className="text-xs text-muted-foreground leading-relaxed max-w-2xl">
            A streak alone put these on the board. They are graded exactly the same way and
            kept in full, because they were real calls made before kick-off — but a rate
            spanning two selection rules describes neither, so they sit on their own.
          </p>
          {archiveWeeks.map((w) => <WeekBlock key={`a-${w.tag}`} w={w} />)}
        </section>
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

// ONE RENDERER FOR BOTH ERAS. The archive shows the same rows graded the same way, so
// it must not be a second copy of this markup — two copies drift, and the drift would be
// between how the site presents the record it is selling and the record it is not.
function WeekBlock({ w }) {
  return (
      <section className="bg-card border border-border rounded-lg overflow-hidden"
      data-testid="results-week">
        <div className="px-4 py-3 border-b border-border flex items-center gap-3 flex-wrap">
          {/* A WEEK, NOT A NIGHT. The snapshot went daily and every one of them became
              its own section here, so a month arrived as thirty blocks under a heading
              that still said "week". The label comes from the backend so the page and
              the record cannot disagree about which week a row belongs to. */}
          <span className="font-head font-semibold text-sm">{w.label || weekLabel(w.tag)}</span>
          <span className="font-mono-data text-[11px] text-muted-foreground">
            {w.settled > 0
              ? <>{w.landed}/{w.settled} landed</>
              : <>{w.rows.length} posted · none settled yet</>}
            {w.voided > 0 && <> · {w.voided} push</>}
            {w.pending > 0 && <> · {w.pending} to play</>}
          </span>
          {/* WHAT WAS ON THE BOARD AND NOT PUBLISHED. The snapshot freezes the top 25
              every night, which on a Saturday is a selection and on a ten-fixture
              Tuesday is the whole board including the bottom of it. Those are not
              claims the site made, so they are not counted — and the gap is worth
              showing, because on a quiet midweek it IS the story. */}
          {w.held?.rows?.length > 0 && (
            <span className="font-mono-data text-[10px] text-muted-foreground/70 border
                             border-dashed border-border rounded px-1.5 py-0.5"
              data-testid="week-held">
              {w.held.rows.length} on the board, not published
            </span>
          )}
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
              <ResultShare row={r} />
            </div>
          ))}
        </div>
      </section>
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
          <ResultShare row={r} />
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
