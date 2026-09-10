import { useState } from "react";
import { Megaphone, Loader2 } from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";

// PUT A HAND-POSTED ANGLE ON THE RECORD.
//
// The scheduled snapshot only ever freezes the streak board. An angle picked off a
// fixture page and posted to Instagram was evidence of nothing afterwards, because
// nothing had written down that it was ever claimed — so the wins from those posts
// could not appear on /results at all.
//
// LOG IT WHEN YOU POST IT. The backend stamps whether the game had kicked off yet, from
// its own clock, and that stamp is what decides whether the angle counts towards the
// public strike rate. Logged while it is still a prediction, it counts. Logged
// afterwards, it is shown but not counted — because a percentage you can add winners to
// after the fact is not a percentage, and one checkable row would give it away.
export default function LogPostedAngle({ token }) {
  const [f, setF] = useState({
    team: "", opponent: "", line: "", direction: "over", subject: "team",
    kickoff: "", league_id: "", is_home: "true", posted_to: "instagram", prob: "",
  });
  const [busy, setBusy] = useState(false);
  const set = (k) => (e) => setF((v) => ({ ...v, [k]: e.target.value }));

  const submit = async () => {
    if (!f.team.trim() || !f.opponent.trim() || !f.line || !f.kickoff) {
      toast.error("Team, opponent, line and kick-off are all needed");
      return;
    }
    setBusy(true);
    try {
      const r = await api.logPostedAngle(token, {
        team: f.team.trim(), opponent: f.opponent.trim(),
        line: Number(f.line), direction: f.direction, subject: f.subject,
        kickoff: f.kickoff, league_id: f.league_id.trim() || undefined,
        is_home: f.is_home === "true", posted_to: f.posted_to,
        // Optional, and worth filling in: it is what lets the result image say "we called
        // 5+ at 63%" with the number people actually saw, rather than one recomputed later.
        prob: f.prob === "" ? undefined : Number(f.prob),
      });
      if (r.status === "exists") toast.success(`${r.name} is already on the record`);
      else if (r.before_kickoff) toast.success(`${r.name} logged — counts towards the record`);
      // Said plainly at the moment it happens, so it is never a surprise on the page.
      else toast.success(`${r.name} added — shown, but not counted (game already played)`);
      setF((v) => ({ ...v, team: "", opponent: "", line: "", kickoff: "", prob: "" }));
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Could not log that angle");
    } finally { setBusy(false); }
  };

  const input = "bg-[#121212] border border-border rounded px-2 py-1.5 text-sm font-mono-data";

  return (
    <div data-testid="log-posted-angle">
      <p className="text-xs text-muted-foreground mb-2 flex items-center gap-1.5">
        <Megaphone className="h-3.5 w-3.5 text-primary" />
        Posted an angle by hand? Log it here and it shows on{" "}
        <span className="text-foreground">/results</span> —{" "}
        <span className="text-amber-400">before kick-off to have it count</span>
      </p>
      <div className="flex flex-wrap items-center gap-2">
        <input value={f.team} onChange={set("team")} placeholder="Team"
          data-testid="angle-team" className={`${input} w-36`} />
        <select value={f.is_home} onChange={set("is_home")} data-testid="angle-venue" className={`${input} w-20`}>
          <option value="true">vs</option>
          <option value="false">@</option>
        </select>
        <input value={f.opponent} onChange={set("opponent")} placeholder="Opponent"
          data-testid="angle-opponent" className={`${input} w-36`} />
        <select value={f.direction} onChange={set("direction")} data-testid="angle-direction" className={`${input} w-24`}>
          <option value="over">over</option>
          <option value="under">under</option>
        </select>
        <input value={f.line} onChange={set("line")} type="number" min={1} max={30} placeholder="Line"
          data-testid="angle-line" className={`${input} w-20`} />
        <select value={f.subject} onChange={set("subject")} data-testid="angle-subject" className={`${input} w-32`}>
          <option value="team">team corners</option>
          <option value="match">match total</option>
        </select>
        <input value={f.kickoff} onChange={set("kickoff")} type="datetime-local"
          data-testid="angle-kickoff" className={`${input} w-52`} />
        <select value={f.posted_to} onChange={set("posted_to")}
          title="Where it went. VIP picks grade exactly like anything else — this just records which channel made the call."
          data-testid="angle-posted-to" className={`${input} w-28`}>
          <option value="instagram">Instagram</option>
          <option value="telegram">VIP Telegram</option>
          <option value="x">X</option>
        </select>
        <input value={f.prob} onChange={set("prob")} type="number" min={1} max={99} placeholder="% shown"
          title="The probability your post displayed. Kept so the result image can quote the number people actually saw."
          data-testid="angle-prob" className={`${input} w-24`} />
        <input value={f.league_id} onChange={set("league_id")} placeholder="league id (if ambiguous)"
          data-testid="angle-league" className={`${input} w-44`} />
        <button onClick={submit} disabled={busy} data-testid="angle-submit"
          className="text-xs px-3 py-1.5 rounded border border-primary/40 bg-primary/10 text-primary
                     hover:bg-primary/20 disabled:opacity-50 flex items-center gap-1.5">
          {busy ? <Loader2 className="h-3 w-3 animate-spin" /> : <Megaphone className="h-3 w-3" />}
          Log angle
        </button>
      </div>
      <p className="text-[11px] text-muted-foreground mt-2 leading-relaxed">
        The line is the number you posted — <span className="text-foreground">over 4</span> means
        4 or more corners. It settles itself off the synced result, exactly like the streak
        board does, so there is nothing to come back and mark.
      </p>
    </div>
  );
}
