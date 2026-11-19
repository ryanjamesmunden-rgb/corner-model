import { useState } from "react";
import { CalendarDays, Check, Loader2 } from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { telegramDay, dayHeading } from "@/lib/anglePost";
import { boardParams, dayOf } from "@/lib/valueQuery";

// THE WHOLE DAY AS ONE MESSAGE.
//
// CopyAngle solved this a row at a time, which is right when a game is the thing being
// posted and wrong when a DAY is: eight taps, eight pastes, eight chances to drop one or
// paste the same game twice, and no heading tying them together. The channel gets one
// card a day; the board should produce one card a day.
//
// IT FETCHES ON CLICK, AND ASKS FOR THE LADDER.
//
// The board's rows carry `best` plus three alternatives — four markets sliced by EV
// across home, away and total together — which is why CopyAngle stopped building posts
// from them: a fixture whose four best markets are all match totals has a perfectly good
// team angle sitting in a ladder the board never sent. `ladder=true` returns every rung,
// and the note on /value-board explains why it is off by default: roughly 24 markets per
// row across up to 40 rows, several hundred KB, on every single load. One request when
// somebody actually wants the card is the cheaper half of that trade.
//
// AND IT ASKS THE SAME QUESTION THE SCREEN IS SHOWING. boardParams is shared with the
// board rather than rebuilt here, so the card cannot quietly be a different day or a
// different floor from the rows the person is looking at when they press it.
export default function CopyDay({ when, floor, label = "",
                                  site = "thecornermodel.com", className = "" }) {
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(false);

  // A day, or nothing. See the note at the call site.
  if (!dayOf(when)) return null;

  const copy = async () => {
    if (busy) return;
    setBusy(true);
    try {
      const d = await api.valueBoard(boardParams(when, floor, { ladder: true }));
      const rows = (Array.isArray(d) ? d : []).filter((r) => !r.status || r.status === "ok");
      // THE FLOOR, BUT NEVER BELOW ZERO. "Everything I've priced" is -100 and is a
      // sensible thing to look at; it is not a sensible thing to post. A card is a list
      // of bets, so the rungs on it have to be ones the model actually likes.
      const text = telegramDay(rows, {
        site, heading: dayHeading(rows[0]?.date) || (label ? `📅 ${label}` : ""),
        minEv: Math.max(0, Number(floor)),
      });
      if (!text) {
        // SAID, NOT SHRUGGED AT — the same rule CopyAngle follows. A button that quietly
        // does nothing is indistinguishable from one that is broken.
        toast.message(`No EV+ angle on ${label.toLowerCase() || "that day"}`, {
          description: rows.length
            ? `${rows.length} ${rows.length === 1 ? "game is" : "games are"} priced, but nothing clears the floor at 6+ or shorter.`
            : "Nothing priced for that day yet.",
        });
        return;
      }
      await navigator.clipboard.writeText(text);
      setDone(true);
      setTimeout(() => setDone(false), 1800);
      // The count is what tells you it worked without pasting it somewhere to look.
      const games = text.split("\n\n").length - (text.startsWith("📅") ? 1 : 0);
      toast.success(`${games} ${games === 1 ? "game" : "games"} copied`, {
        description: "One angle per fixture, in kick-off order — paste into the channel.",
      });
    } catch {
      toast.error("Couldn't build that card — try again, or copy the games one at a time");
    } finally {
      setBusy(false);
    }
  };

  return (
    <button type="button" onClick={copy} disabled={busy}
      data-testid="copy-day"
      title={`Copy every EV+ angle for ${label.toLowerCase()} as one channel post`}
      className={`inline-flex items-center gap-1.5 h-8 px-2.5 rounded-md border
        border-primary/40 text-primary text-xs hover:bg-primary/10
        transition-colors disabled:opacity-50 ${className}`}>
      {busy ? <Loader2 className="h-3.5 w-3.5 animate-spin" />
            : done ? <Check className="h-3.5 w-3.5" />
                   : <CalendarDays className="h-3.5 w-3.5" />}
      {busy ? "Building" : done ? "Copied" : "Copy the day"}
    </button>
  );
}
