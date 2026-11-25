import { isChunkLoadError, lazyRoute } from "./lazyRoute";

// A deploy landing under an open tab is the failure this file is about: the cached
// index.html names chunks that no longer exist, the host answers the 404 with the SPA
// fallback, and the browser throws parsing HTML as JavaScript. The site is fine. The tab
// is not, and it looks identical to the site being down.

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
    // The actual message a browser gives when HTML arrives where JavaScript was asked
    // for — Chrome's wording and Firefox's.
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

describe("what the route does about it", () => {
  // lazy() defers the importer until React renders it, so the factory is reached
  // through the internal payload rather than by mounting a tree for each case.
  const run = (Comp) => Comp._payload._result();

  const harness = (over = {}) => {
    const calls = { reload: 0, remembered: 0 };
    let flag = false;
    return {
      calls,
      opts: {
        reload: () => { calls.reload += 1; },
        hasReloaded: () => flag,
        remember: () => { calls.remembered += 1; flag = true; return true; },
        ...over,
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

  it("does not reload twice, so a tab cannot spin", async () => {
    const h = harness({ hasReloaded: () => true });
    const C = lazyRoute(() => Promise.reject(new Error("Loading chunk 3 failed.")),
                        h.opts);
    await expect(run(C)).rejects.toThrow("Loading chunk 3 failed.");
    expect(h.calls.reload).toBe(0);
  });

  it("does not reload when storage will not hold the guard", async () => {
    // Private mode: the flag cannot be kept, so a reload would be unbounded.
    const h = harness({ remember: () => false });
    const C = lazyRoute(() => Promise.reject(new Error("Loading chunk 3 failed.")),
                        h.opts);
    await expect(run(C)).rejects.toThrow();
    expect(h.calls.reload).toBe(0);
  });

  it("lets a genuine error through to the boundary untouched", async () => {
    const h = harness();
    const C = lazyRoute(() => Promise.reject(new TypeError("x.map is not a function")),
                        h.opts);
    await expect(run(C)).rejects.toThrow("x.map is not a function");
    expect(h.calls.reload).toBe(0);
  });

  it("is an ordinary lazy route when the chunk loads", async () => {
    const h = harness();
    const mod = { default: () => null };
    const C = lazyRoute(() => Promise.resolve(mod), h.opts);
    await expect(run(C)).resolves.toBe(mod);
    expect(h.calls.reload).toBe(0);
    expect(h.calls.remembered).toBe(0);
  });
});
