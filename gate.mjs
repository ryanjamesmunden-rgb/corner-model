import { chromium } from "playwright";
const b = await chromium.launch({ executablePath: "/opt/pw-browsers/chromium" });
const p = await b.newPage({ viewport: { width: 1280, height: 900 } });
for (const path of ["/projections", "/results"]) {
  await p.goto("http://127.0.0.1:5055" + path, { waitUntil: "networkidle" });
  await p.waitForTimeout(1200);
  const wall = await p.getByTestId("signed-in-only").count();
  const txt = wall ? (await p.getByTestId("signed-in-only").innerText()).split("\n")[0] : "";
  console.log(path.padEnd(14), "wall:", wall, "|", txt);
}
await p.goto("http://127.0.0.1:5055/scanner", { waitUntil: "networkidle" });
await p.waitForTimeout(1200);
const nav = await p.locator("header").innerText();
console.log("nav (signed out):", nav.replace(/\n/g, " | ").slice(0, 160));
console.log("  Projected in nav?", nav.includes("Projected"), " Results in nav?", nav.includes("Results"));
await b.close();
