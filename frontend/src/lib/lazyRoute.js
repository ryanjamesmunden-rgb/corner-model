/**
 * A lazily-loaded route that survives a deploy landing under an open tab.
 *
 * THE FAILURE THIS FIXES, which looks exactly like "the site is down". Every route here
 * is its own chunk, and `index.html` names those chunks by content hash. A browser that
 * has `index.html` cached from before a deploy asks for `main.4f2a.js`, which no longer
 * exists; the host answers a 404 with the SPA fallback, which is HTML; the browser tries
 * to parse HTML as JavaScript and throws `Unexpected token '<'`. The dynamic import
 * rejects, Suspense hands the rejection to the error boundary, and the visitor gets a
 * broken panel or a blank page — on a site that is working perfectly for anyone who
 * arrives fresh.
 *
 * A RELOAD IS THE WHOLE FIX, because the reload fetches the new `index.html` with the
 * new chunk names. The only hard part is doing it once.
 *
 * AND THE FIRST VERSION GOT THAT WRONG, in a way worth writing down because it is the
 * exact shape of bug this file exists to prevent. The guard was a boolean flag, set
 * before reloading and cleared by `App` on mount "so the next deploy gets its own
 * attempt". But `App` mounts BEFORE a lazy route resolves — the shell paints, then the
 * chunk is fetched — so every reload cleared the guard on the way past and the next
 * failure found it unset. Measured in a browser against a chunk that never came back:
 * 328 page loads in 20 seconds. The site did not look broken, it looked possessed.
 *
 * SO THE GUARD IS A TIMESTAMP AND NOTHING CLEARS IT. One reload per COOLDOWN_MS, full
 * stop. A deploy is a single failure and gets its single reload; a chunk that is
 * genuinely gone fails once more and goes to the error boundary, which at least says
 * something. A real deploy hours later is outside the window and gets its own attempt,
 * which is what the clearing was reaching for and the reason it is not needed.
 *
 * ONLY FOR A CHUNK THAT WOULD NOT LOAD. A module that throws while EVALUATING is a real
 * bug in the code, and reloading would hide it behind a flicker — so the reload is
 * limited to the shapes a failed fetch produces.
 */
import { lazy } from "react";

const KEY = "cm2_chunk_reload_at";

/**
 * How long one reload attempt suppresses the next.
 *
 * Long enough that a loop is impossible at any page-load speed — the old bug cycled in
 * about 60ms — and short enough that a second deploy in the same sitting still heals.
 */
export const COOLDOWN_MS = 10 * 60 * 1000;

/** Whether this looks like a chunk that could not be fetched, rather than one that threw. */
export const isChunkLoadError = (err) => {
  if (!err) return false;
  if (err.name === "ChunkLoadError") return true;
  const msg = String(err.message || err);
  return /Loading chunk \S+ failed/i.test(msg)
    || /Loading CSS chunk/i.test(msg)
    || /Failed to fetch dynamically imported module/i.test(msg)
    || /error loading dynamically imported module/i.test(msg)
    // What a 404 served as the SPA's index.html produces when parsed as JavaScript.
    || /Unexpected token '</.test(msg)
    || /expected expression, got '<'/i.test(msg);
};

/**
 * Record this attempt, and say whether it may go ahead.
 *
 * WRITTEN BEFORE THE RELOAD, NEVER AFTER — the page is about to be destroyed, so there
 * is no "after". Storage that refuses the write returns false: a guard that cannot be
 * kept is no guard, and reloading without one is the loop.
 */
export const claimReload = (now = Date.now(), cooldown = COOLDOWN_MS) => {
  let last = null;
  try {
    const raw = sessionStorage.getItem(KEY);
    // NOT `Number(raw) || null`. A stored 0 is a real timestamp and that idiom turns it
    // into "no attempt recorded" — which is this file's whole bug in miniature, since
    // the one value that must never read as absent is the one that stops the loop.
    const n = raw === null ? NaN : Number(raw);
    last = Number.isFinite(n) ? n : null;
  } catch {
    return false;                       // cannot read; assume we must not reload
  }
  if (last !== null && now - last < cooldown) return false;
  try {
    sessionStorage.setItem(KEY, String(now));
  } catch {
    return false;                       // cannot write; see above
  }
  return true;
};

/**
 * `lazy()`, plus at most one reload per cooldown when the chunk could not be fetched.
 *
 * `reload` and `claim` are injectable so the behaviour can be tested without a real
 * navigation.
 */
export const lazyRoute = (importer, {
  reload = () => window.location.reload(),
  claim = claimReload,
} = {}) => lazy(() => importer().catch((err) => {
  if (isChunkLoadError(err) && claim()) {
    reload();
    // Never resolves: the page is on its way out, and resolving with a placeholder
    // would paint a broken route for the moment before it goes.
    return new Promise(() => {});
  }
  throw err;
}));

export default lazyRoute;
