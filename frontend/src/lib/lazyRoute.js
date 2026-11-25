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
 * arrives fresh. Three deploys in an afternoon makes this near-certain for anyone who
 * left a tab open, and the one page it breaks hardest is the one with the login on it.
 *
 * A RELOAD IS THE WHOLE FIX, because the reload fetches the new `index.html` with the
 * new chunk names. The only trick is doing it once: a reload that fails the same way
 * again would spin forever, so the attempt is recorded in sessionStorage first and a
 * second failure is allowed through to the error boundary, where at least it says
 * something. sessionStorage rather than localStorage so the flag dies with the tab and
 * the next deploy gets its own attempt.
 *
 * ONLY FOR A CHUNK THAT WOULD NOT LOAD. A module that throws while EVALUATING is a real
 * bug in the code, and reloading would hide it behind a flicker — so the reload is
 * limited to the shapes a failed fetch produces.
 */
import { lazy } from "react";

const FLAG = "cm2_chunk_reloaded";

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

const already = () => {
  try { return sessionStorage.getItem(FLAG) === "1"; } catch { return true; }
};

const mark = () => {
  // If sessionStorage cannot be written (private mode, blocked storage) the flag cannot
  // be kept, and a reload would be unbounded — so say it has already happened.
  try { sessionStorage.setItem(FLAG, "1"); return true; } catch { return false; }
};

/** Clear the guard once the app has got going, so a later deploy gets its own attempt. */
export const clearChunkReloadFlag = () => {
  try { sessionStorage.removeItem(FLAG); } catch { /* nothing to clear */ }
};

/**
 * `lazy()`, plus one reload when the chunk itself could not be fetched.
 *
 * `reload` and `hasReloaded` are injectable so the behaviour can be tested without a
 * real navigation.
 */
export const lazyRoute = (importer, {
  reload = () => window.location.reload(),
  hasReloaded = already,
  remember = mark,
} = {}) => lazy(() => importer().catch((err) => {
  if (isChunkLoadError(err) && !hasReloaded() && remember()) {
    reload();
    // Never resolves: the page is on its way out, and resolving with a placeholder
    // would paint a broken route for the moment before it goes.
    return new Promise(() => {});
  }
  throw err;
}));

export default lazyRoute;
