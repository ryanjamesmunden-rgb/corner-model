// The Telegram channel photo: the mark with the version under it, animated.
const { chromium } = require("playwright");
const { writeFileSync, mkdirSync, rmSync } = require("fs");

const DIR = __dirname;
const FPS = 30, SECONDS = 4, N = FPS * SECONDS;
const VERSION = "3.0", COLOR = "#F3F5F7";

(async () => {
  const page = await (await chromium.launch()).newPage();
  await page.goto("file://" + DIR + "/channel.html");
  // The face has to be rasterised before the first fillText, or frame 0 is drawn in the
  // fallback and every later frame in Inter — a one-frame flicker on every loop.
  await page.evaluate(() => document.fonts.ready);

  const save = (p, d) => writeFileSync(p, Buffer.from(d.split(",")[1], "base64"));

  for (const size of [400, 1000]) {
    save(`${DIR}/out/corner-model-channel-${size}.png`,
         await page.evaluate(([s, v, c]) => window.__frame(s, 0, v, c),
                             [size, VERSION, COLOR]));
  }

  rmSync(`${DIR}/cframes`, { recursive: true, force: true });
  mkdirSync(`${DIR}/cframes`, { recursive: true });
  for (let i = 0; i < N; i++) {
    save(`${DIR}/cframes/f${String(i).padStart(4, "0")}.png`,
         await page.evaluate(([s, t, v, c]) => window.__frame(s, t, v, c),
                             [800, i / N, VERSION, COLOR]));
  }
  console.log(`${N} frames`);
  process.exit(0);
})();
