import { Image as ImageIcon, Loader2, Share2 } from "lucide-react";
import { useState, useEffect } from "react";
import { toast } from "sonner";
import { renderStory } from "@/lib/storyImage";
import { hasLiveGesture, isGestureError } from "@/lib/userGesture";

/**
 * Generates one Instagram Story per matchday and hands them to the phone.
 *
 * ONE PER DAY, not one for everything: a single image covering three days makes a reader
 * work out which rows are tonight, and the rows they can act on now are the only ones
 * that convert. See mismatchStoryDays for how the days are cut, and why the weekend gets
 * a shorter list.
 *
 * TWO PATHS, AND WHY. On a phone this uses the Web Share API with the files attached, so
 * the OS share sheet opens and Instagram is one tap away — which is where these actually
 * get posted. `download` is the desktop path; on mobile Safari it is unreliable enough
 * that shipping only that would mean the feature quietly doesn't work on the device it
 * exists for.
 *
 * Images are drawn on demand rather than held in state: each is ~800KB of canvas, the
 * board underneath changes with every filter, and a stale story is worse than a slow one
 * — it would post yesterday's games under tonight's headline.
 */
export default function StoryButton({ days = [], cta, className = "",
                                      render, makeFile, icon: Icon = ImageIcon,
                                      testId = "story-button",
                                      label: labelOverride, title: titleOverride }) {
  const [busy, setBusy] = useState(false);

  // TWO LEVELS OF OVERRIDE, because callers need different amounts of control.
  // `render` swaps the DRAWING and keeps the PNG (the fixture story is a different
  // picture); `makeFile` swaps the whole file, which is what recording a video needs
  // since a video is not a canvas snapshot at all. Everything below them — the share
  // sheet, the desktop fallback, the AbortError handling — is the fiddly part, and is
  // worth having exactly once.
  const draw = async (day) => {
    if (makeFile) return makeFile(day);
    const canvas = document.createElement("canvas");
    if (render) render(canvas, day);
    else renderStory(canvas, { title: day.title, subtitle: day.subtitle, rows: day.rows,
                               totalCount: day.totalCount, cta });
    const blob = await new Promise((res) => canvas.toBlob(res, "image/png"));
    if (!blob) throw new Error("canvas produced nothing");
    return new File([blob], `corner-model-${day.key}.png`, { type: "image/png" });
  };

  // Handing the finished files to the OS. Split out from making them because this half
  // is the half that needs a live tap behind it.
  const deliver = async (files) => {
    // The share sheet, where it exists and will take the whole set. Checked with the
    // ACTUAL files rather than a probe: canShare's answer depends on count and size,
    // so a single-file test would green-light a set the sheet then refuses.
    if (navigator.canShare?.({ files })) {
      await navigator.share({ files, title: "Corner Model" });
      return;
    }
    for (const file of files) {
      const url = URL.createObjectURL(file);
      const a = document.createElement("a");
      a.href = url;
      a.download = file.name;
      a.click();
      // Revoked a frame later, not immediately: Safari cancels an in-flight download
      // when the URL it was handed stops resolving.
      requestAnimationFrame(() => URL.revokeObjectURL(url));
    }
    toast.success(`${files.length} ${files.length === 1 ? "story" : "stories"} saved — 1080×1920`);
  };

  // FILES THAT OUTLIVED THEIR TAP.
  //
  // A story VIDEO takes 5.3 seconds to record and a browser gives about five before it
  // stops treating the tap as live, so the share was being refused every time with
  // "Must be handling a user gesture" — the file was fine, the permission was not. When
  // that happens the files are kept and the button asks for one more tap, which is a
  // fresh gesture and always works. Nothing is re-recorded.
  const [pending, setPending] = useState(null);

  // A held file describes the board AS IT WAS. Moving the line or changing a filter
  // changes the day keys, and sharing the old picture under the new numbers is exactly
  // the stale-story failure the drawing is done on demand to avoid.
  const key = days.map((d) => d.key).join("|");
  useEffect(() => { setPending(null); }, [key]);

  const make = async () => {
    if (busy) return;

    // The second tap. This click IS the gesture the share needed.
    if (pending) {
      setBusy(true);
      try { await deliver(pending); setPending(null); }
      catch (err) { if (err?.name !== "AbortError") toast.error(err?.message || "Couldn't share that"); }
      finally { setBusy(false); }
      return;
    }

    if (!days.length) return;
    setBusy(true);
    // Declared out here so the recovery below can still reach the files it took five
    // seconds to make. Inside the try they would be gone exactly when they are needed.
    const files = [];
    try {
      for (const day of days) files.push(await draw(day));

      // Asked, not assumed. Where the browser will tell us the gesture has gone we skip
      // an attempt that can only fail, so the user never sees the error at all.
      if (!hasLiveGesture()) {
        setPending(files);
        toast.success("Ready — tap again to share it");
        return;
      }
      await deliver(files);
    } catch (err) {
      // Same recovery for a browser that would not tell us up front (Safari has no
      // userActivation): the attempt fails, and a second tap fixes it. Only worth
      // offering if the files actually got made — a gesture error with nothing to hand
      // over would promise a share that has nothing to share.
      if (isGestureError(err) && files.length) {
        setPending(files);
        toast.success("Ready — tap again to share it");
        return;
      }
      // A dismissed share sheet throws AbortError. That is the user changing their mind,
      // not a failure, and reporting it as one would be a lie.
      if (err?.name !== "AbortError") toast.error(err?.message || "Couldn't make the story");
    } finally {
      setBusy(false);
    }
  };

  const label = labelOverride || (days.length > 1 ? `${days.length} stories` : "Story");
  // The waiting state has to be visible WITHOUT the words: the label is hidden on a phone,
  // which is the only place this happens, so the icon and the colour are what say "tap me
  // again" to the person who is actually looking at it.
  const ShownIcon = busy ? Loader2 : pending ? Share2 : Icon;
  return (
    <button
      onClick={make}
      disabled={busy || (!days.length && !pending)}
      data-testid={testId}
      data-pending={pending ? "1" : "0"}
      title={pending
        ? "Ready — tap again to open the share sheet"
        : titleOverride
          || `Instagram ${days.length > 1 ? "Stories" : "Story"} — the games, with the model blurred out`}
      className={"flex items-center gap-1.5 text-xs px-2.5 py-1.5 rounded-md border "
        + "transition-colors duration-150 disabled:opacity-50 "
        + (pending
            ? "border-primary text-primary bg-primary/15 hover:bg-primary/25 "
            : "border-border bg-secondary text-muted-foreground hover:text-foreground hover:bg-white/10 ")
        + className}
    >
      <ShownIcon className={"h-3.5 w-3.5" + (busy ? " animate-spin" : "")} />
      <span className="hidden sm:inline">{pending ? "Share it" : label}</span>
    </button>
  );
}
