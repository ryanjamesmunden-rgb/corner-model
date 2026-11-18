import { useState } from "react";
import { Copy, Check, Loader2 } from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { telegramAngle } from "@/lib/anglePost";

// THE POST, READY TO PASTE, BESIDE THE ROW IT IS ABOUT.
//
// The channel block was already being produced — anglePost.js has built it since the
// threads went in — but only by a scheduled job, so getting one meant running a workflow
// and reading it out of a log. The board is where the angle is found, so the button
// belongs here.
//
// WHY RETYPING IT IS THE THING TO AVOID. The post quotes a price, a model price, a
// probability and an edge. Read off the screen and typed again, sooner or later it quotes
// a number the site never said — and the only reason the channel is worth reading is that
// every figure in it can be checked against the fixture page the post links to.
//
// IT FETCHES ON CLICK, AND THAT IS THE WHOLE DESIGN.
//
// The first version built the post from the row the board already had. That row carries
// `best` plus `marks[1:4]` — at most FOUR markets, sliced by EV across home, away and
// total together. Tested against that real shape: a typical row gave the right two-rung
// post, but a fixture whose four best markets were all match totals produced no button at
// all, while having a perfectly good team angle further down a ladder the board simply
// had not sent. Silently missing posts is worse than a slow one.
//
// Asking the board for `ladder=true` would fix it and costs roughly 24 markets per row
// across up to 40 rows on every single load — several hundred KB on a link this backend
// has measured at about 120 KB/s. One request when somebody actually wants a post is the
// cheaper half of that trade by a wide margin.
export default function CopyAngle({ row, site = "thecornermodel.com", className = "" }) {
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(false);
  // Which side went out last, so a second tap on a game where BOTH sides clear the floor
  // gives the other one instead of the same post twice.
  const [last, setLast] = useState("");

  if (!row?.fixture_id) return null;

  const copy = async (e) => {
    e.stopPropagation();          // the row itself navigates to the fixture
    if (busy) return;
    setBusy(true);
    try {
      const d = await api.fixture(row.fixture_id);
      const markets = d?.model?.markets || [];
      // The row supplies the names, league and kick-off; the fetch supplies the ladder.
      const full = { ...row, ladder: markets };
      const sides = ["home", "away"]
        .map((group) => ({
          group,
          team: group === "home" ? row.home_name : row.away_name,
          text: telegramAngle(full, { group, site }),
        }))
        .filter((s) => s.text);

      if (!sides.length) {
        // SAID, NOT SHRUGGED AT. A button that does nothing is the bug this page has
        // already had once; "there is no angle here" is a real answer.
        toast.message("No EV+ corner angle on this game", {
          description: "Nothing on either side clears the floor at 6+ or shorter.",
        });
        return;
      }

      // ONE SIDE PER POST. A fixture where both teams clear the floor is two separate
      // arguments about two different corner distributions, and one post carrying five
      // picks is priced by the ledger at -4.4% over 112u against +13.0% for one or two.
      const pick = sides.find((s) => s.group !== last) || sides[0];
      await navigator.clipboard.writeText(pick.text);
      setLast(pick.group);
      setDone(true);
      setTimeout(() => setDone(false), 1500);

      const other = sides.find((s) => s.group !== pick.group);
      toast.success(`${pick.team} copied — paste into the channel`, {
        description: other ? `${other.team} also has an angle — tap again for it.` : undefined,
      });
    } catch {
      // Not silent: the clipboard is refused outright in some app webviews, and a button
      // that looks like it worked is worse than one that admits it did not.
      toast.error("Couldn't build that post — try the fixture page");
    } finally {
      setBusy(false);
    }
  };

  return (
    <button type="button" onClick={copy} disabled={busy}
      data-testid="copy-angle"
      title="Copy this game's EV+ ladder in the channel's format"
      className={`inline-flex items-center gap-1 text-[10px] text-primary
        hover:text-primary/80 transition-colors disabled:opacity-50 ${className}`}>
      {busy ? <Loader2 className="h-3 w-3 animate-spin" />
            : done ? <Check className="h-3 w-3" />
                   : <Copy className="h-3 w-3" />}
      {busy ? "Building" : done ? "Copied" : "Copy post"}
    </button>
  );
}
