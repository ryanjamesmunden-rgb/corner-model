// Recording a story canvas to a video file, in the browser.
//
// WHY THE ORDER OF THESE MATTERS. Instagram and X want MP4/H.264. WebM is what every
// Chromium will happily produce and what neither platform reliably accepts, so it is a
// LAST resort rather than a default — a video that will not upload is worse than the still
// image, because the user only finds out at the point of posting.
//
// The list is walked in preference order and the first supported entry wins. `avc1.42E01E`
// is H.264 Baseline 3.0: the profile with the widest decoder support, and the one every
// social platform is certain to take.
const VIDEO_TYPES = [
  "video/mp4;codecs=avc1.42E01E,mp4a.40.2",
  "video/mp4;codecs=avc1.42E01E",
  "video/mp4;codecs=h264",
  "video/mp4",
  "video/webm;codecs=vp9",
  "video/webm;codecs=vp8",
  "video/webm",
];

/**
 * The best type this browser can actually encode, or null if it can encode none.
 *
 * `isSupported` is injected rather than reaching for MediaRecorder directly so the
 * preference order can be tested without a browser — the order is the product decision
 * here, and it is the part worth pinning.
 */
export const pickVideoType = (isSupported) => VIDEO_TYPES.find((t) => {
  try { return isSupported(t); } catch { return false; }
}) || null;

/** Container extension for a mime type. Instagram cares; the file picker cares more. */
export const extFor = (mime = "") => (String(mime).includes("mp4") ? "mp4" : "webm");

/** Does this browser have the pieces at all? Used to hide the button rather than fail it. */
export const canRecord = () =>
  typeof window !== "undefined"
  && typeof window.MediaRecorder !== "undefined"
  && typeof HTMLCanvasElement !== "undefined"
  && typeof HTMLCanvasElement.prototype.captureStream === "function"
  && pickVideoType((t) => window.MediaRecorder.isTypeSupported(t)) !== null;

/**
 * Draw `drawFrame(progress)` in real time for `durationMs` and return the recording.
 *
 * REAL TIME, on purpose. `captureStream(fps)` samples the canvas on the browser's own
 * clock, so the animation has to be driven by ELAPSED TIME rather than by frame count: on
 * a slow machine that drops frames instead of producing a video that runs long, which is
 * the right way round for something being posted to a timeline.
 *
 * `hold` keeps the finished frame on screen at the end. Without it the story cuts the
 * instant the last element lands, and the number nobody has finished reading is gone.
 */
export const recordStoryVideo = (canvas, drawFrame, {
  durationMs = 4200, holdMs = 1100, fps = 30,
} = {}) => new Promise((resolve, reject) => {
  const mime = pickVideoType((t) => window.MediaRecorder.isTypeSupported(t));
  if (!mime) { reject(new Error("no supported video encoding")); return; }

  // FRAMES ARE PUSHED, NOT SAMPLED.
  //
  // `captureStream(fps)` asks the browser to sample the canvas on its own clock, which
  // only works for a canvas the compositor is actually painting. This canvas is never
  // added to the document — it exists to be recorded — so automatic capture silently
  // under-delivers: measured here, 5.9s of real-time drawing produced 2.3s of video.
  //
  // `captureStream(0)` plus an explicit `requestFrame()` after each draw hands over every
  // frame instead of hoping one is noticed. Falls back to sampling where requestFrame is
  // missing, which is worse but still produces a file.
  let stream, track, manual = false;
  try {
    stream = canvas.captureStream(0);
    track = stream.getVideoTracks()[0];
    manual = typeof track?.requestFrame === "function";
    if (!manual) {
      stream.getTracks().forEach((t) => t.stop());
      stream = canvas.captureStream(fps);
    }
  } catch (e) { reject(e); return; }

  const chunks = [];
  let rec;
  try {
    rec = new window.MediaRecorder(stream, { mimeType: mime, videoBitsPerSecond: 8_000_000 });
  } catch (e) { reject(e); return; }

  rec.ondataavailable = (e) => { if (e.data && e.data.size) chunks.push(e.data); };
  rec.onerror = (e) => reject(e?.error || new Error("recorder failed"));
  rec.onstop = () => {
    stream.getTracks().forEach((t) => t.stop());
    const blob = new Blob(chunks, { type: mime });
    if (!blob.size) reject(new Error("recording produced nothing"));
    else resolve({ blob, mime, ext: extFor(mime) });
  };

  const total = durationMs + holdMs;
  const start = performance.now();
  let timer = null;

  const frame = (progress) => {
    drawFrame(progress);
    if (manual) track.requestFrame();
  };

  // Paced on setTimeout rather than rAF: the animation is a function of ELAPSED TIME, so
  // this needs a steady heartbeat rather than the compositor's. It also keeps running at
  // a sane rate if the tab is not frontmost, where rAF is throttled to a crawl.
  const tick = () => {
    const elapsed = performance.now() - start;
    // Clamped at 1 through the hold, so the last frames are the finished story rather
    // than an animation that has run past its own end.
    frame(Math.min(1, elapsed / durationMs));
    if (elapsed < total) {
      timer = setTimeout(tick, 1000 / fps);
    } else {
      frame(1);   // never end on a part-drawn state
      // A beat later: the last frame has to reach the encoder before it is asked to stop.
      setTimeout(() => { try { rec.stop(); } catch { /* already stopped */ } }, 150);
    }
  };

  rec.onstop = ((prev) => () => { clearTimeout(timer); prev(); })(rec.onstop);

  try {
    frame(0);
    rec.start();
    timer = setTimeout(tick, 1000 / fps);
  } catch (e) { reject(e); }
});
