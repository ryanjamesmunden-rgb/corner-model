import { isGestureError } from "./userGesture";

// Why "copy the streaks" fails, and what to do instead of losing the text.
//
// THE BUG THIS EXISTS FOR. The menu did this:
//
//     const md = await api.exportStreaks(days);      // a network round trip
//     await navigator.clipboard.writeText(md);       // ...then the clipboard
//
// A clipboard write is only permitted while the user gesture that started it is still
// live — Chrome allows roughly five seconds from the click. The await in between is a call
// to a backend on Render's free tier, which SLEEPS: the first request after a quiet spell
// takes thirty to sixty seconds to answer. By the time the markdown arrives the gesture
// expired long ago, the write is refused with NotAllowedError, and the catch turns that
// into "Export failed".
//
// So on a cold backend it failed essentially every time, and said nothing useful about why.
// The same trap was already found and fixed for the share button — see lib/userGesture —
// and this menu never got the fix.
//
// THE ORDER OF ATTEMPTS, and why there are three:
//
//   1. Hand the clipboard the PROMISE, not the text. ClipboardItem accepts one, which is
//      exactly the API for "fetch then copy": the permission is taken while the gesture is
//      live and the data arrives later. Safari has wanted this for years; Chrome takes it too.
//   2. Await and write the text. For anything without ClipboardItem, and for the case where
//      the request was fast enough that the gesture is still good.
//   3. Download the file. If the clipboard cannot be had at all, the text still exists and
//      the person still wants it — a .md they can drag into a chat does the job, and losing
//      their data to a permission rule does not.
//
// THE REQUEST IS ONLY MADE ONCE. `fetchText()` is called before the first attempt and the
// same promise is reused by the fallbacks — a retry that re-fetched would double the wait
// on the exact backend whose slowness caused the problem.

/** Hand a string to the browser as a file. The last resort, and it always works. */
export function download(text, filename, mime = "text/markdown") {
  const blob = new Blob([text], { type: mime });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

/**
 * Fetch something and get it to the user, however the browser will allow.
 *
 * Returns {how} — "clipboard" or "download" — so the caller can say which happened. A
 * toast claiming the text was copied when it was actually downloaded sends someone to
 * paste an empty clipboard.
 */
export async function copyOrDownload(fetchText, filename, deps = {}) {
  const nav = deps.navigator ?? (typeof navigator !== "undefined" ? navigator : null);
  const Item = deps.ClipboardItem
    ?? (typeof ClipboardItem !== "undefined" ? ClipboardItem : null);
  const save = deps.download ?? download;

  // Started BEFORE any await, so the gesture is still live for attempt 1, and held so the
  // fallbacks reuse it rather than asking a sleeping backend twice.
  const pending = Promise.resolve().then(fetchText);
  // A rejection reaching the fallbacks unhandled would surface as an unhandled rejection
  // warning before the caller ever sees the error.
  pending.catch(() => {});

  if (Item && nav?.clipboard?.write) {
    // GUARDED SEPARATELY from `pending`. This is a derived promise, and if the browser
    // rejects write() without ever reading it — which is exactly what a refused permission
    // does — it rejects with nobody listening and surfaces as an unhandled rejection.
    const blob = pending.then((t) => new Blob([t], { type: "text/plain" }));
    blob.catch(() => {});
    try {
      await nav.clipboard.write([new Item({ "text/plain": blob })]);
      return { how: "clipboard" };
    } catch (err) {
      // A FAILED REQUEST IS NOT A CLIPBOARD PROBLEM and must not be reported as one. If
      // the fetch itself rejected, that is the error worth raising.
      await pending;
      if (!isGestureError(err) && err?.name !== "TypeError") throw err;
    }
  }

  const text = await pending;
  if (nav?.clipboard?.writeText) {
    try {
      await nav.clipboard.writeText(text);
      return { how: "clipboard" };
    } catch (err) {
      if (!isGestureError(err) && err?.name !== "NotAllowedError") throw err;
    }
  }

  save(text, filename);
  return { how: "download" };
}

/**
 * What to tell somebody when an export did not work.
 *
 * EVERY FAILURE USED TO READ "Export failed", which is three different problems wearing one
 * sentence: not a member, a backend that was asleep, and a browser refusing the clipboard.
 * Each has a different next step and only one of them is worth reporting as a fault.
 */
export function exportError(err) {
  const status = err?.response?.status;
  if (status === 401 || status === 403) {
    return "Exports are for members — sign in with the account that has the subscription.";
  }
  if (status === 503) {
    return "The model is not configured for exports yet.";
  }
  if (status >= 500) {
    return "The backend errored building that export. Try again in a moment.";
  }
  // No response at all: a timeout or a dropped connection. On a free instance that has
  // gone to sleep the first request routinely takes the best part of a minute, and a
  // second attempt usually lands — which is the single most useful thing to say here.
  if (err?.response === undefined) {
    return "The backend did not answer — it may be waking up. Try once more.";
  }
  return "Export failed.";
}
