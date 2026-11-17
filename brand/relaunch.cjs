const { chromium } = require("playwright");
const DIR = __dirname;
(async () => {
  const b = await chromium.launch();
  const page = await b.newPage({ deviceScaleFactor: 1 });
  await page.goto("file://" + DIR + "/relaunch.html");
  // 3.0 follows the WEBSITE's 1.0 and 2.0. The old spreadsheet reached 6.0 on its
  // own count, which this lineage does not continue.
  for (const v of ["3.0"]) {
    await page.evaluate((vv) => {
      document.querySelectorAll(".v").forEach((e) => (e.textContent = vv));
    }, v);
    const tag = v.replace(".", "-");
    await page.locator("#header").screenshot({ path: `${DIR}/out/x-header-${tag}.png` });
    await page.locator("#card").screenshot({ path: `${DIR}/out/relaunch-card-${tag}.png` });
  }
  process.exit(0);
})();
