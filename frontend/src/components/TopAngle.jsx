import { useState, useEffect } from "react";
import { Flame, ShieldOff, CalendarOff, Clock3, ChevronRight } from "lucide-react";
import { Link } from "react-router-dom";
import { api } from "@/lib/api";
import { withFlag } from "@/lib/countryFlag";
import { kickoffLabel } from "@/lib/kickoff";
import {
  angleLabel, deadMessage, hasPanel, runLabel, splitAngles, statedRecord, whyLabel,
} from "@/lib/angleOfDay";

// THE ANGLE OF THE DAY — the site's answer to "what do you actually like today".
//
// It sits at the top of the record on purpose. Every other panel here is history; this is
// the claim being made right now, and putting it directly above the graded results is the
// only arrangement where a reader can weigh one against the other without being asked to
// take anything on trust. The record is not decoration under the pick — it is the reason
// to read the pick, or not to.
//
// IT IS ALLOWED TO PUBLISH NOTHING, and it still draws when it does. That is the part
// worth defending in review: hiding the panel on a dead day would mean the only days
// anyone ever sees it are days it makes a call, and a reader who never sees the bar turn
// anything away has no reason to believe there is a bar. The refusal is the content.
//
// NOTHING HERE DECIDES ANYTHING. The rule lives in angle_of_day.py and the wording lives
// in lib/angleOfDay.js — this file renders what it is handed, so that "may we print a
// percentage" is one tested decision rather than a condition in a template.

const DEAD_ICON = { stale: Clock3, no_fixtures: CalendarOff, no_qualifier: ShieldOff };

export default function TopAngle({ count }) {
  const [data, setData] = useState(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    api.anglesToday(count).then(setData).catch(() => setFailed(true));
  }, [count]);

  // A FAILED LOAD DRAWS NOTHING RATHER THAN AN EMPTY PANEL. "No angle today" and "we could
  // not reach the backend" are opposite claims, and showing the first for the second would
  // report a quiet day that may have been a busy one.
  if (failed) return null;
  if (!data) return <div className="h-32 rounded-lg bg-secondary animate-pulse" />;
  if (!hasPanel(data)) return null;

  const dead = deadMessage(data);
  const { top, rest } = splitAngles(data);

  return (
    <section className="bg-card border border-border rounded-lg overflow-hidden"
      data-testid="top-angle">
      <header className="px-4 py-3 border-b border-border flex items-center gap-2 flex-wrap">
        <Flame className="h-4 w-4 text-primary shrink-0" />
        <span className="font-head font-semibold text-sm">Today's angle</span>
        <span className="font-mono-data text-[11px] text-muted-foreground">
          {dead ? "nothing published" : `${data.angles.length} of ${data.qualified} qualifying`}
        </span>
      </header>

      {dead ? <Dead dead={dead} data={data} /> : (
        <>
          <TopRow angle={top} />
          {rest.length > 0 && (
            <div className="divide-y divide-border border-t border-border">
              {rest.map((a, i) => <Row key={i} angle={a} />)}
            </div>
          )}
        </>
      )}

      <Record record={data.record} dead={Boolean(dead)} />
    </section>
  );
}

// THE DAY WITH NOTHING ON IT. Stated as a decision rather than an absence — "no angle
// today" reads as the site having nothing, "none of it clears the bar" reads as the site
// having standards, and only the second is true.
function Dead({ dead, data }) {
  const Icon = DEAD_ICON[dead.reason] || ShieldOff;
  return (
    <div className="px-4 py-5 flex gap-3" data-testid={`angle-dead-${dead.reason}`}>
      <Icon className="h-5 w-5 text-muted-foreground shrink-0 mt-0.5" />
      <div className="space-y-1.5">
        <p className="text-sm font-medium">{dead.title}</p>
        <p className="text-xs text-muted-foreground leading-relaxed max-w-xl">{dead.body}</p>
        {/* THE COUNT IS THE PROOF. Anyone can say they are being selective; "42 games and
            none of them" is the difference between a claim and a demonstration. */}
        {dead.reason === "no_qualifier" && data.fixtures_today > 0 && (
          <p className="text-[11px] text-muted-foreground font-mono-data">
            {data.fixtures_today} fixtures today · none qualifying
          </p>
        )}
      </div>
    </div>
  );
}

const fixtureLine = (a) => {
  const nf = a?.next_fixture || {};
  return `${nf.is_home ? "vs" : "@"} ${nf.opponent || "?"}`;
};

function TopRow({ angle }) {
  if (!angle) return null;
  return (
    <div className="px-4 py-4" data-testid="angle-top">
      <div className="flex items-start gap-3 flex-wrap">
        <div className="min-w-0 flex-1">
          <p className="font-head text-lg font-bold tracking-tight truncate">
            {withFlag(angle.league_id, angleLabel(angle))}
          </p>
          <p className="text-xs text-muted-foreground mt-1">
            {fixtureLine(angle)}
            <span className="mx-1.5 opacity-40">·</span>
            {kickoffLabel(angle.next_fixture?.date)}
          </p>
        </div>
        <span className="font-mono-data text-[11px] px-2 py-1 rounded border
                         border-tone-streak/40 bg-tone-streak/10 text-tone-streak-fg shrink-0">
          {runLabel(angle)}
        </span>
      </div>
      {/* WHY IT IS HERE AND NOT JUST THAT IT IS. The streak is one half; the opponent and
          the model's read of the fixture are the half that stops a quiet Tuesday filling
          up, so they are shown rather than applied silently. */}
      <p className="text-[11px] text-muted-foreground font-mono-data mt-1.5">
        {whyLabel(angle)}
      </p>
      {/* Guarded on the id the URL actually needs. A row can carry a team and no fixture
          id, and the link would then point at /fixture/undefined — a dead end offered as
          the evidence for the pick. */}
      {angle.next_fixture?.fixture_id && (
        <Link to={`/fixture/${angle.next_fixture.fixture_id}`}
          className="inline-flex items-center gap-1 text-xs text-primary mt-2 hover:underline">
          The numbers behind it <ChevronRight className="h-3 w-3" />
        </Link>
      )}
    </div>
  );
}

function Row({ angle }) {
  return (
    <div className="px-4 py-2.5 flex items-center gap-3" data-testid="angle-row">
      <div className="min-w-0 flex-1">
        <p className="text-sm truncate">{withFlag(angle.league_id, angleLabel(angle))}</p>
        <p className="text-[11px] text-muted-foreground truncate mt-0.5">
          {fixtureLine(angle)}
          <span className="mx-1.5 opacity-40">·</span>
          {kickoffLabel(angle.next_fixture?.date)}
        </p>
      </div>
      <span className="font-mono-data text-[10px] text-muted-foreground shrink-0">
        {runLabel(angle)}
      </span>
    </div>
  );
}

// HOW IT HAS DONE — two records, because the rule changed and one number cannot describe
// both. Shown on a dead day too: the record of a rule is not suspended because the rule
// declined to fire today.
//
// THE ORDER OF THESE IS THE HONEST PART. The rule's own record goes first even while it is
// empty, and the longer-running board record is labelled as the thing this filters rather
// than borrowed as though it belonged to the picks above. The tempting arrangement — lead
// with the bigger, better-looking sample — would be quoting one rule's history under
// another rule's list.
function Record({ record, dead }) {
  const rule = statedRecord(record?.rule?.shortlist);
  const ruleTop = statedRecord(record?.rule?.top);
  const board = statedRecord(record?.board?.shortlist);
  if (!rule && !board) return null;
  const started = (record?.rule_days || 0) > 0;
  return (
    <div className="px-4 py-3 border-t border-border bg-secondary/40 space-y-2"
      data-testid="angle-record">
      {started ? (
        <div className="flex items-baseline gap-4 flex-wrap">
          <Line label="This rule" stated={rule} />
          <Line label="Its lead angle" stated={ruleTop} />
        </div>
      ) : (
        // NOT A ZERO. The tightened rule has no record because it is new, which is a
        // different fact from having a bad one, and the bar cannot be applied backwards:
        // it depends on how leaky each opponent was on the day, and that has moved every
        // time those leagues have played since.
        <p className="text-xs text-foreground" data-testid="angle-record-new">
          This rule starts its record today. It cannot be graded backwards — the bar
          depends on how leaky the opponent was at the time, and that number has moved
          since.
        </p>
      )}
      {started && rule?.caveat && (
        <p className="text-[11px] text-muted-foreground">{rule.caveat}</p>
      )}
      {board && (
        <div className="pt-1 border-t border-border/60">
          <Line label={`The streak board it filters (top ${record.count}/day)`} stated={board} />
          <p className="text-[11px] text-muted-foreground mt-1 leading-relaxed max-w-2xl">
            The longer record, and a broader rule than the one above — every streak that
            was frozen, whether or not the fixture backed it up.
          </p>
        </div>
      )}
      <p className="text-[11px] text-muted-foreground leading-relaxed max-w-2xl">
        {/* WHAT THE NUMBER IS AND IS NOT, next to the number. It is a strike rate off
            frozen lists, not a return — the snapshots record the line that was posted and
            never the odds anyone got. */}
        Graded from lists frozen before kick-off. A strike rate, not a profit — the
        snapshots record the line, never the price.
      </p>
    </div>
  );
}

const Line = ({ label, stated }) => (stated ? (
  <span className="text-xs">
    <span className="text-muted-foreground">{label}: </span>
    {stated.strong && (
      <span className="font-mono-data font-semibold text-tone-strong-fg">{stated.strong} </span>
    )}
    <span className="text-foreground">{stated.text}</span>
  </span>
) : null);
