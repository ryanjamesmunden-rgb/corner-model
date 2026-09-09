import { pickVideoType, extFor, baseMime } from "./storyVideo";

// The preference ORDER is the product decision here, and it is the part that will silently
// rot: a future edit that puts WebM first still passes every "does it record" check and
// only fails at the point someone tries to upload it to Instagram. So it is pinned.

const supports = (...ok) => (t) => ok.includes(t);

describe("it asks for MP4 before it settles for WebM", () => {
  it("takes H.264 baseline when the browser has it", () => {
    // avc1.42E01E is the profile every social platform is certain to decode.
    expect(pickVideoType(() => true)).toBe("video/mp4;codecs=avc1.42E01E,mp4a.40.2");
  });

  it("prefers any MP4 over any WebM", () => {
    const pick = pickVideoType(supports("video/mp4", "video/webm;codecs=vp9"));
    expect(pick).toBe("video/mp4");
  });

  it("falls back to WebM only when no MP4 is available", () => {
    // Chromium builds without proprietary codecs land here — it still produces a file,
    // which is better than nothing, but it is the last choice rather than the default.
    expect(pickVideoType(supports("video/webm;codecs=vp9", "video/webm")))
      .toBe("video/webm;codecs=vp9");
  });

  it("prefers vp9 to vp8 within WebM", () => {
    expect(pickVideoType(supports("video/webm;codecs=vp8", "video/webm;codecs=vp9")))
      .toBe("video/webm;codecs=vp9");
  });

  it("returns null when the browser can encode nothing", () => {
    expect(pickVideoType(() => false)).toBeNull();
  });

  it("treats a throwing isTypeSupported as unsupported rather than crashing", () => {
    // Some browsers throw on a malformed codec string instead of returning false.
    const throwy = (t) => {
      if (t.includes("mp4")) throw new TypeError("nope");
      return t === "video/webm";
    };
    expect(pickVideoType(throwy)).toBe("video/webm");
  });
});

describe("the file gets the extension its container actually is", () => {
  it.each([
    ["video/mp4;codecs=avc1.42E01E,mp4a.40.2", "mp4"],
    ["video/mp4", "mp4"],
    ["video/webm;codecs=vp9", "webm"],
    ["video/webm", "webm"],
  ])("%s → .%s", (mime, ext) => {
    expect(extFor(mime)).toBe(ext);
  });

  it("defaults to webm for an unknown or missing type rather than lying about mp4", () => {
    // Naming a WebM ".mp4" gets it rejected at upload with no useful error.
    expect(extFor("")).toBe("webm");
    expect(extFor(undefined)).toBe("webm");
  });
});

describe("the type a FILE gets, not the one the recorder wants", () => {
  test("strips the codec parameters MediaRecorder needs", () => {
    // The bug this fixes: the recorded Blob inherited the whole
    // "video/mp4;codecs=avc1.42E01E,mp4a.40.2" string, that became the File's type, and
    // the Android share sheet refused it with "Permission denied" — while the still
    // image, typed plainly "image/png", shared fine.
    expect(baseMime("video/mp4;codecs=avc1.42E01E,mp4a.40.2")).toBe("video/mp4");
    expect(baseMime("video/webm;codecs=vp9")).toBe("video/webm");
  });

  test("leaves a type that has nothing to strip alone", () => {
    expect(baseMime("video/mp4")).toBe("video/mp4");
    expect(baseMime("image/png")).toBe("image/png");
  });

  test("every type we might record is reduced to something shareable", () => {
    // Pinned across the WHOLE preference list, because the one that gets used depends on
    // the browser and a type that only works on the browsers I can test is not a fix.
    for (const t of ["video/mp4;codecs=avc1.42E01E,mp4a.40.2", "video/mp4;codecs=avc1.42E01E",
                     "video/mp4;codecs=h264", "video/mp4", "video/webm;codecs=vp9",
                     "video/webm;codecs=vp8", "video/webm"]) {
      expect(baseMime(t)).toMatch(/^video\/(mp4|webm)$/);
    }
  });

  test("survives junk without inventing a type", () => {
    expect(baseMime("")).toBe("");
    expect(baseMime()).toBe("");
    expect(baseMime("  VIDEO/MP4 ; codecs=x ")).toBe("video/mp4");
  });
});
