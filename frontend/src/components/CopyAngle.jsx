import { useMemo, useState } from "react";
import { Copy, Check } from "lucide-react";
import { toast } from "sonner";
import { telegramAngle } from "@/lib/anglePost";

// THE POST, READY TO PASTE, BESIDE THE ROW IT IS ABOUT.
//
// The channel block was already being produced — anglePost.js has built it since the
// threads went in — but only by a scheduled job, so getting one meant running a workflow
// and reading it out of a log. The board is where the angle is actually found, so the
// button belongs here.
//
// WHY NOT RETYPE IT. The post quotes a price, a model price, a probability and an edge.
// Retyped off the screen, sooner or later it quotes a number the site never said — and
// the whole reason anybody trusts this channel is that the numbers can be checked against
// the fixture page the post links to.
//
// ONE BUTTON PER SIDE, and usually there is only one. A fixture where both teams clear
// the floor is two separate arguments about two different corner distributions, and
// running them together would read as one post with five picks in it. The ledger prices
// that at -4.4% over 112u against +13.0% for one or two, which is why angleThread splits
// them and why this does too.
export default function CopyAngle({ row, site = "thecornermodel.com", className = "" }) {
  const [done, setDone] = useState("");

  // Both sides, built once. telegramAngle returns "" where a side has no rung clearing
  // the floor, so an empty string here means "no button", not "a post with nothing in it".
  const sides = useMemo(() => ["home", "away"]
    .map((group) => ({
      group,
      team: group === "home" ? row?.home_name : row?.away_name,
      text: telegramAngle(row || {}, { group, site }),
    }))
    .filter((s) => s.text), [row, site]);

  if (!sides.length) return null;

  const copy = async (side, e) => {
    e.stopPropagation();        // the row itself navigates to the fixture
    try {
      await navigator.clipboard.writeText(side.text);
      setDone(side.group);
      setTimeout(() => setDone(""), 1500);
      toast.success(`${side.team || "Angle"} copied — paste into the channel`);
    } catch {
      // Not silent, and not a retry: the clipboard is refused outright in some app
      // webviews, and a button that looks like it worked is worse than one that says it
      // did not.
      toast.error("Couldn't copy — your browser blocked clipboard access");
    }
  };

  return (
    <span className={`inline-flex items-center gap-2 ${className}`} data-testid="copy-angle">
      {sides.map((side) => (
        <button key={side.group} type="button" onClick={(e) => copy(side, e)}
          data-testid={`copy-angle-${side.group}`}
          title={`Copy the ${side.team} angle in the channel's format`}
          className="inline-flex items-center gap-1 text-[10px] text-primary
            hover:text-primary/80 transition-colors">
          {done === side.group
            ? <Check className="h-3 w-3" />
            : <Copy className="h-3 w-3" />}
          {/* The team is named only when both sides have one, because on the usual row
              there is nothing to disambiguate and "Copy Leganes" beside a row that says
              Leganes v Burgos is the same word twice. */}
          {done === side.group ? "Copied"
            : sides.length > 1 ? `Copy ${side.team}` : "Copy post"}
        </button>
      ))}
    </span>
  );
}
