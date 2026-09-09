import { pickVideoType, extFor } from "./storyVideo";

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
