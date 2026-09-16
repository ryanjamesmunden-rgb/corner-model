import { copyOrDownload, exportError } from "./exportCopy";

// "Copy this week's streaks" fetched the markdown and THEN wrote to the clipboard. A
// clipboard write is only permitted while the gesture that started it is live — about five
// seconds in Chrome — and the request in between goes to a backend on a free instance that
// sleeps, taking thirty to sixty. So on a cold backend it failed essentially every time,
// and reported "Export failed", which named none of it.

const gestureError = () => Object.assign(new Error("Must be handling a user gesture"),
                                         { name: "NotAllowedError" });

function fakeNav({ write, writeText } = {}) {
  return { clipboard: { ...(write ? { write } : {}), ...(writeText ? { writeText } : {}) } };
}

class FakeItem {
  constructor(parts) { this.parts = parts; }
}

describe("getting the text to the user", () => {
  test("the clipboard is handed the promise, not the awaited text", async () => {
    // This is the whole fix: the permission is taken while the gesture is live and the
    // data arrives later. Awaiting first is what expired the gesture.
    let resolved = false;
    const write = jest.fn(async () => {});
    const fetchText = () => new Promise((r) => setTimeout(() => { resolved = true; r("md"); }, 0));
    const out = await copyOrDownload(fetchText, "f.md",
      { navigator: fakeNav({ write }), ClipboardItem: FakeItem, download: jest.fn() });
    expect(out.how).toBe("clipboard");
    expect(write).toHaveBeenCalled();
    // write() was called with a ClipboardItem, before the fetch had settled.
    expect(write.mock.calls[0][0][0]).toBeInstanceOf(FakeItem);
    expect(resolved).toBe(false);
  });

  test("a browser without ClipboardItem still copies", async () => {
    const writeText = jest.fn(async () => {});
    const out = await copyOrDownload(async () => "md", "f.md",
      { navigator: fakeNav({ writeText }), ClipboardItem: null, download: jest.fn() });
    expect(out.how).toBe("clipboard");
    expect(writeText).toHaveBeenCalledWith("md");
  });

  test("a refused clipboard downloads the file rather than losing the text", async () => {
    // The person asked for their data. A permission rule is not a reason to drop it.
    const save = jest.fn();
    const out = await copyOrDownload(async () => "md", "streaks.md", {
      navigator: fakeNav({
        write: async () => { throw gestureError(); },
        writeText: async () => { throw gestureError(); },
      }),
      ClipboardItem: FakeItem,
      download: save,
    });
    expect(out.how).toBe("download");
    expect(save).toHaveBeenCalledWith("md", "streaks.md");
  });

  test("a browser with no clipboard at all downloads", async () => {
    const save = jest.fn();
    const out = await copyOrDownload(async () => "md", "f.md",
      { navigator: {}, ClipboardItem: null, download: save });
    expect(out.how).toBe("download");
  });

  test("the request is only made once, however many fallbacks run", async () => {
    // A retry that re-fetched would double the wait on the exact backend whose slowness
    // caused the problem in the first place.
    const fetchText = jest.fn(async () => "md");
    const save = jest.fn();
    await copyOrDownload(fetchText, "f.md", {
      navigator: fakeNav({
        write: async () => { throw gestureError(); },
        writeText: async () => { throw gestureError(); },
      }),
      ClipboardItem: FakeItem,
      download: save,
    });
    expect(fetchText).toHaveBeenCalledTimes(1);
  });

  test("a failed request is raised, not reported as a clipboard problem", async () => {
    // The two failures need different messages and only one of them is the browser's.
    const boom = Object.assign(new Error("nope"), { response: { status: 403 } });
    const save = jest.fn();
    await expect(copyOrDownload(async () => { throw boom; }, "f.md", {
      navigator: fakeNav({ write: async () => { throw gestureError(); } }),
      ClipboardItem: FakeItem,
      download: save,
    })).rejects.toBe(boom);
    expect(save).not.toHaveBeenCalled();
  });

  test("a real clipboard error is raised rather than silently downloaded", async () => {
    const weird = Object.assign(new Error("disk on fire"), { name: "DataError" });
    await expect(copyOrDownload(async () => "md", "f.md", {
      navigator: fakeNav({ writeText: async () => { throw weird; } }),
      ClipboardItem: null,
      download: jest.fn(),
    })).rejects.toBe(weird);
  });
});

describe("what the failure says", () => {
  // One sentence for three problems is one sentence that helps with none of them.
  test("a member-only endpoint says so", () => {
    expect(exportError({ response: { status: 403 } })).toMatch(/for members/);
    expect(exportError({ response: { status: 401 } })).toMatch(/for members/);
  });

  test("no response at all names the sleeping backend", () => {
    // The single most useful thing to say: a second attempt usually lands.
    expect(exportError(new Error("timeout of 0ms exceeded"))).toMatch(/waking up/);
  });

  test("a server error is separated from a wake-up", () => {
    expect(exportError({ response: { status: 500 } })).toMatch(/errored building/);
  });

  test("a missing configuration is its own answer", () => {
    expect(exportError({ response: { status: 503 } })).toMatch(/not configured/);
  });

  test("anything else still gets a sentence", () => {
    expect(exportError({ response: { status: 418 } })).toBe("Export failed.");
    expect(exportError(null)).toBeTruthy();
  });
});
