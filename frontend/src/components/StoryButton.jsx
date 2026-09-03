import { Image as ImageIcon, Loader2 } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";
import { renderStory } from "@/lib/storyImage";

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
export default function StoryButton({ days = [], cta, className = "" }) {
  const [busy, setBusy] = useState(false);

  const draw = async (day) => {
    const canvas = document.createElement("canvas");
    renderStory(canvas, { title: day.title, subtitle: day.subtitle, rows: day.rows,
                          totalCount: day.totalCount, cta });
    const blob = await new Promise((res) => canvas.toBlob(res, "image/png"));
    if (!blob) throw new Error("canvas produced nothing");
    return new File([blob], `corner-model-${day.key}.png`, { type: "image/png" });
  };

  const make = async () => {
    if (busy || !days.length) return;
    setBusy(true);
    try {
      const files = [];
      for (const day of days) files.push(await draw(day));

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
    } catch (err) {
      // A dismissed share sheet throws AbortError. That is the user changing their mind,
      // not a failure, and reporting it as one would be a lie.
      if (err?.name !== "AbortError") toast.error("Couldn't make the story images");
    } finally {
      setBusy(false);
    }
  };

  const label = days.length > 1 ? `${days.length} stories` : "Story";
  return (
    <button
      onClick={make}
      disabled={busy || !days.length}
      data-testid="story-button"
      title={`Instagram ${days.length > 1 ? "Stories" : "Story"} — the games, with the model blurred out`}
      className={"flex items-center gap-1.5 text-xs px-2.5 py-1.5 rounded-md border border-border "
        + "bg-secondary text-muted-foreground hover:text-foreground hover:bg-white/10 "
        + "transition-colors duration-150 disabled:opacity-50 " + className}
    >
      {busy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <ImageIcon className="h-3.5 w-3.5" />}
      <span className="hidden sm:inline">{label}</span>
    </button>
  );
}
