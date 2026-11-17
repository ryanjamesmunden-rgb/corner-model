// Render the mark: one static avatar, and the frames of the loop.
//
// SAME DRAWING FOR BOTH. The static PNG is frame 0 of the animation, so the Telegram
// video's resting state and the X avatar are the same picture — which is the only way the
// two read as one account rather than as two logos.
const { chromium } = require("playwright");
const { writeFileSync, mkdirSync } = require("fs");

const DIR = __dirname;
const FPS = 30, SECONDS = 4, N = FPS * SECONDS;

(async () => {
  const page = await (await chromium.launch()).newPage();
  await page.goto("file://" + DIR + "/mark.html");

  const save = (p, dataUrl) =>
    writeFileSync(p, Buffer.from(dataUrl.split(",")[1], "base64"));

  // X wants 400x400; render 1000 too so the downscale is clean and the file is reusable
  // elsewhere (Telegram's static photo, the site's icons) without going back to source.
  for (const size of [400, 1000]) {
    save(`${DIR}/avatar-${size}.png`,
         await page.evaluate(([s]) => window.__frame(s, 0), [size]));
  }

  mkdirSync(`${DIR}/frames`, { recursive: true });
  for (let i = 0; i < N; i++) {
    const t = i / N;  // 0 .. under 1, so frame N would be frame 0 again: a clean loop
    save(`${DIR}/frames/f${String(i).padStart(4, "0")}.png`,
         await page.evaluate(([s, tt]) => window.__frame(s, tt), [800, t]));
  }
  console.log(`${N} frames`);
  process.exit(0);
})();
