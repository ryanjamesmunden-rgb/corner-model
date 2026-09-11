#!/usr/bin/env node
// Renders a story image from the SITE'S OWN canvas code, in a real browser.
//
// WHY A BROWSER, in a job that is otherwise plain Node. The picture is drawn by
// frontend/src/lib/storyImage.js — the same module the Share button on a fixture page
// uses. Redrawing it here with a server-side canvas library would be a second
// implementation of the layout, the palette and the blur, and the two would drift apart
// silently: the automated post would slowly stop looking like the one made by hand, which
// is the whole failure this repo keeps designing against.
//
// It also has to be a browser rather than node-canvas specifically because of the blur.
// The model's price is drawn and then BLURRED OUT — that is the tease — and `ctx.filter`
// is the one part of the Canvas2D API that server-side implementations handle differently
// or not at all. A blur that silently no-ops would publish the price.
//
// WHY AN HTTP SERVER for three local files. ES module imports from file:// are treated as
// cross-origin by Chromium and refused, so the harness is served over loopback instead.
//
// Usage:  node tools/render_story.mjs --args story.json --out story.png
// The args file is whatever renderFixtureStory takes: homeName, awayName, leagueId,
// kickoff, dist, group, markets.

import { readFileSync, writeFileSync, mkdirSync, rmSync, statSync } from "node:fs";
import { spawnSync } from "node:child_process";
import { createServer } from "node:http";
import { fileURLToPath } from "node:url";
import { dirname, resolve, extname } from "node:path";

const HERE = dirname(fileURLToPath(import.meta.url));
const LIB = resolve(HERE, "..", "frontend", "src", "lib");

const arg = (n, d = null) => {
  const i = process.argv.indexOf(`--${n}`);
  return i !== -1 && process.argv[i + 1] ? process.argv[i + 1] : d;
};
const ARGS = arg("args");
const OUT = arg("out", "story.png");
// With --video, the same drawing is rendered frame by frame and encoded instead of
// snapshotted. Timings match recordStoryVideo's defaults so the automated clip and the one
// the Share button makes are the same length and the same pace.
const VIDEO = arg("video", null);
const DURATION_MS = Number(arg("duration", "4200"));
const HOLD_MS = Number(arg("hold", "1100"));
const FPS = Number(arg("fps", "30"));
const fail = (m) => { console.error(`render_story: ${m}`); process.exit(1); };
if (!ARGS) fail("--args <file.json> is required");

const storyArgs = JSON.parse(readFileSync(ARGS, "utf8"));

// Playwright is a devDependency in the workflow and a global install in some sandboxes.
// Try the normal resolution first and fall back, rather than assuming either.
let chromium;
try {
  ({ chromium } = await import("playwright"));
} catch {
  try {
    ({ chromium } = await import("/opt/node22/lib/node_modules/playwright/index.mjs"));
  } catch {
    fail("playwright is not installed — `npm i -D playwright && npx playwright install chromium`");
  }
}

const TYPES = { ".js": "text/javascript", ".mjs": "text/javascript", ".html": "text/html" };

const HARNESS = `<!doctype html><meta charset="utf-8">
<style>html,body{margin:0;background:#000}</style>
<canvas id="c"></canvas>
<script type="module">
  import { renderFixtureStory } from "/lib/storyImage.js";
  window.__render = (a) => {
    const c = document.getElementById("c");
    renderFixtureStory(c, a);
    // toDataURL rather than an element screenshot: the canvas is 1080x1920 and the page
    // is not, so screenshotting would capture it scaled to the viewport.
    return c.toDataURL("image/png");
  };
  // The SAME call as the still, with progress threaded through — renderFixtureStory takes
  // progress and draws the finished frame at 1, so the video and the image cannot end up
  // being two different pictures.
  window.__renderFrame = (a, progress) => {
    const c = document.getElementById("c");
    renderFixtureStory(c, { ...a, progress });
    return c.toDataURL("image/jpeg", 0.95);
  };
  window.__ready = true;
</script>`;

const server = createServer((req, res) => {
  if (req.url === "/" || req.url.startsWith("/index")) {
    res.setHeader("content-type", "text/html");
    return res.end(HARNESS);
  }
  if (req.url.startsWith("/lib/")) {
    try {
      const body = readFileSync(resolve(LIB, req.url.slice(5).split("?")[0]));
      res.setHeader("content-type", TYPES[extname(req.url)] || "application/octet-stream");
      return res.end(body);
    } catch {
      res.statusCode = 404;
      return res.end("not found");
    }
  }
  res.statusCode = 404;
  res.end("not found");
});
await new Promise((r) => server.listen(0, "127.0.0.1", r));
const port = server.address().port;

const browser = await chromium.launch({
  args: ["--no-sandbox", "--disable-dev-shm-usage",
         // Deterministic text metrics: without it the runner's font stack decides where
         // lines wrap, and a caption that wraps differently is a differently laid out card.
         "--font-render-hinting=none"],
});
try {
  const page = await browser.newPage({ viewport: { width: 600, height: 900 } });
  const errors = [];
  page.on("pageerror", (e) => errors.push(String(e)));
  await page.goto(`http://127.0.0.1:${port}/`, { waitUntil: "networkidle" });
  await page.waitForFunction(() => window.__ready === true, { timeout: 15000 })
    .catch(() => fail(`the harness never loaded${errors.length ? ` — ${errors[0]}` : ""}`));

  if (VIDEO) {
    // FRAMES AND FFMPEG, NOT MediaRecorder.
    //
    // The site records with MediaRecorder because it is running in the user's own Chrome,
    // which ships proprietary codecs and can produce MP4 directly. Playwright's Chromium
    // does not: MediaRecorder there falls back to WebM, and WebM is a format Instagram
    // refuses. So the frames are drawn deterministically and handed to ffmpeg, which also
    // removes the one real flaw in recording — a slow machine dropping frames.
    //
    // JPEG for the intermediate frames. They are about to be H.264 encoded, so lossless
    // PNG buys nothing and costs roughly five times the transfer over CDP, across 150-odd
    // round trips.
    const frames = Math.round((DURATION_MS / 1000) * FPS);
    const holds = Math.round((HOLD_MS / 1000) * FPS);
    const dir = resolve(process.cwd(), ".story_frames");
    mkdirSync(dir, { recursive: true });
    let n = 0;
    for (let i = 0; i < frames + holds; i += 1) {
      // Past `frames` the progress pins at 1: that is the HOLD, and it exists because a
      // story that cuts the instant the last element lands takes the number away from
      // whoever is still reading it.
      const progress = Math.min(1, i / Math.max(1, frames - 1));
      const url = await page.evaluate(
        ([a, p]) => window.__renderFrame(a, p), [storyArgs, progress]);
      writeFileSync(resolve(dir, `f${String(n).padStart(5, "0")}.jpg`),
                    Buffer.from(url.split(",")[1], "base64"));
      n += 1;
    }
    // yuv420p and an even frame size, because a phone that cannot decode the pixel format
    // shows a black rectangle rather than an error. The silent audio track is there for
    // the same defensive reason: some uploaders reject a video with no audio stream at all.
    const ff = spawnSync("ffmpeg", [
      "-y", "-hide_banner", "-loglevel", "error",
      "-framerate", String(FPS), "-i", resolve(dir, "f%05d.jpg"),
      "-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=44100",
      "-shortest",
      "-c:v", "libx264", "-preset", "medium", "-crf", "20",
      "-pix_fmt", "yuv420p", "-movflags", "+faststart",
      "-c:a", "aac", "-b:a", "64k",
      VIDEO,
    ], { encoding: "utf8" });
    rmSync(dir, { recursive: true, force: true });
    if (ff.status !== 0) fail(`ffmpeg failed — ${(ff.stderr || "").trim().split("\n").pop()}`);
    const size = statSync(VIDEO).size;
    if (size < 20000) fail(`encoded video is only ${size} bytes — it encoded nothing`);
    console.log(`render_story: wrote ${VIDEO} (${Math.round(size / 1024)} KB, `
      + `${n} frames, ${(n / FPS).toFixed(1)}s)`);
  } else {
    const dataUrl = await page.evaluate((a) => window.__render(a), storyArgs);
    if (!dataUrl || !dataUrl.startsWith("data:image/png;base64,")) {
      fail("the canvas produced no PNG");
    }
    const buf = Buffer.from(dataUrl.split(",")[1], "base64");
    // A 1080x1920 card is tens of kilobytes at minimum. A few hundred bytes means the
    // canvas drew nothing and we are about to post a black rectangle.
    if (buf.length < 10000) fail(`rendered image is only ${buf.length} bytes — it drew nothing`);
    writeFileSync(OUT, buf);
    console.log(`render_story: wrote ${OUT} (${Math.round(buf.length / 1024)} KB)`);
  }
} finally {
  await browser.close();
  server.close();
}
