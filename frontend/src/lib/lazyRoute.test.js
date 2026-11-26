import { claimReload, COOLDOWN_MS, isChunkLoadError, lazyRoute } from "./lazyRoute";

// A deploy landing under an open tab is the failure this file is about: the cached
// index.html names chunks that no longer exist, the host answers the 404 with the SPA
// fallback, and the browser throws parsing HTML as JavaScript. The site is fine. The tab
// is not, and it looks identical to the site being down.
//
// The second thing it is about is the first version of the fix, which reloaded in a loop
// — 328 page loads in 20 seconds against a chunk that never came back — because the
// guard was a boolean that App cleared on mount, and App mounts BEFORE a lazy route
// resolves. Half this file is that bug, pinned.

describe("telling a missing chunk from a broken one", () => {
  it("knows the shapes a failed chunk fetch takes", () => {
    expect(isChunkLoadError(Object.assign(new Error("x"), { name: "ChunkLoadError" })))
      .toBe(true);
    expect(isChunkLoadError(new Error("Loading chunk 42 failed."))).toBe(true);
    expect(isChunkLoadError(new Error("Loading CSS chunk 7 failed"))).toBe(true);
    expect(isChunkLoadError(
      new Error("Failed to fetch dynamically imported module: /static/js/3.ab.js")))
      .toBe(true);
  });

  it("knows what a 404 served as index.html looks like once parsed", () => {
    expect(isChunkLoadError(new SyntaxError("Unexpected token '<'"))).toBe(true);
    expect(isChunkLoadError(new SyntaxError("expected expression, got '<'"))).toBe(true);
  });

  it("does not call a real bug a missing chunk", () => {
    // A module that throws while EVALUATING is a fault in the code. Reloading would hide
    // it behind a flicker and the page would break again a second later.
    expect(isChunkLoadError(new TypeError("x.map is not a function"))).toBe(false);
    expect(isChunkLoadError(new Error("boom"))).toBe(false);
    expect(isChunkLoadError(null)).toBe(false);
  });
});

describe("claiming the one reload", () => {
  beforeEach(() => {
    try { sessionStorage.clear(); } catch { /* not available */ }
  });

  it("allows the first attempt and refuses the next one", () => {
    expect(claimReload(1000)).toBe(true);
    expect(claimReload(1060)).toBe(false);
  });

  it("refuses every attempt inside the cooldown, however fast they come", () => {
    // THE LOOP, measured: the old bug cycled about every 60ms. Sixty attempts at that
    // rate must produce exactly one reload.
    expect(claimReload(0)).toBe(true);
    const allowed = Array.from({ length: 60 }, (_, i) => claimReload(60 * (i + 1)))
      .filter(Boolean);
    expect(allowed).toHaveLength(0);
  });

  it("allows a fresh attempt once the window has passed, for a later deploy", () => {
    expect(claimReload(1000)).toBe(true);
    expect(claimReload(1000 + COOLDOWN_MS + 1)).toBe(true);
  });

  it("refuses when storage will not hold the guard", () => {
    // Private mode. A guard that cannot be kept is no guard, and reloading without one
    // is the loop.
    const spy = jest.spyOn(Storage.prototype, "setItem")
      .mockImplementation(() => { throw new Error("blocked"); });
    expect(claimReload(2000)).toBe(false);
    spy.mockRestore();
  });

  it("refuses when storage cannot even be read", () => {
    const spy = jest.spyOn(Storage.prototype, "getItem")
      .mockImplementation(() => { throw new Error("blocked"); });
    expect(claimReload(3000)).toBe(false);
    spy.mockRestore();
  });
});

describe("what the route does about it", () => {
  // lazy() defers the importer until React renders it, so the factory is reached
  // through the internal payload rather than by mounting a tree for each case.
  const run = (Comp) => Comp._payload._result();

  const harness = (allow = [true]) => {
    const calls = { reload: 0, claims: 0 };
    const queue = [...allow];
    return {
      calls,
      opts: {
        reload: () => { calls.reload += 1; },
        claim: () => { calls.claims += 1; return queue.shift() ?? false; },
      },
    };
  };

  it("reloads once when the chunk could not be fetched", async () => {
    const h = harness();
    const C = lazyRoute(() => Promise.reject(new Error("Loading chunk 3 failed.")),
                        h.opts);
    const pending = run(C);
    await Promise.resolve();
    expect(h.calls.reload).toBe(1);
    // The promise never settles on purpose: the page is leaving, and resolving would
    // paint a broken route for the moment before it goes.
    await expect(Promise.race([pending, Promise.resolve("still pending")]))
      .resolves.toBe("still pending");
  });

  it("gives up to the error boundary when the claim is refused", async () => {
    const h = harness([false]);
    const C = lazyRoute(() => Promise.reject(new Error("Loading chunk 3 failed.")),
                        h.opts);
    await expect(run(C)).rejects.toThrow("Loading chunk 3 failed.");
    expect(h.calls.reload).toBe(0);
  });

  it("lets a genuine error through without even asking to reload", async () => {
    const h = harness();
    const C = lazyRoute(() => Promise.reject(new TypeError("x.map is not a function")),
                        h.opts);
    await expect(run(C)).rejects.toThrow("x.map is not a function");
    expect(h.calls.reload).toBe(0);
    expect(h.calls.claims).toBe(0);
  });

  it("is an ordinary lazy route when the chunk loads", async () => {
    const h = harness();
    const mod = { default: () => null };
    const C = lazyRoute(() => Promise.resolve(mod), h.opts);
    await expect(run(C)).resolves.toBe(mod);
    expect(h.calls.reload).toBe(0);
    expect(h.calls.claims).toBe(0);
  });
});

describe("nothing outside this file may clear the guard", () => {
  it("exports no way to reset it", async () => {
    // THE REGRESSION TEST FOR THE LOOP. App cleared the flag on mount, App mounts before
    // a lazy route resolves, and every reload therefore wiped its own guard. There is no
    // longer anything to call.
    const mod = await import("./lazyRoute");
    expect(mod.clearChunkReloadFlag).toBeUndefined();
    expect(Object.keys(mod).filter((k) => /clear|reset/i.test(k))).toEqual([]);
  });
});
