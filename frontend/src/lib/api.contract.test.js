/**
 * `api` is an OBJECT of named calls. Calling it is a crash, and nothing caught it.
 *
 * WHAT HAPPENED. The calendar page shipped with `api(`/calendar?${qs}`)`. `api` is
 * `export const api = { ... }`, so that throws "api is not a function" on mount — every
 * mount, from the very first. The error boundary swallowed it into "This page couldn't be
 * displayed", the page never ran once, and three rounds of real fixes went into code
 * downstream of a line that always threw.
 *
 * 1681 tests passed throughout, because every one of them tests a pure function and
 * nothing renders a page. A full render test would be the proper answer and needs a
 * testing library this project does not have; this is the cheap guard that would have
 * caught this specific failure on the day it was written, and it needs nothing.
 *
 * It reads the source rather than importing the pages: importing them pulls in JSX,
 * axios and the whole component tree, which is the weight this file exists to avoid.
 */
import fs from "fs";
import path from "path";

const SRC = path.join(__dirname, "..");

const walk = (dir) => fs.readdirSync(dir, { withFileTypes: true }).flatMap((e) => {
  const p = path.join(dir, e.name);
  if (e.isDirectory()) return walk(p);
  return /\.jsx?$/.test(e.name) && !/\.test\.jsx?$/.test(e.name) ? [p] : [];
});

const files = walk(SRC);

describe("the api module's shape", () => {
  it("is an object of named calls, and is not itself callable", () => {
    // eslint-disable-next-line global-require
    const { api } = require("./api");
    expect(typeof api).toBe("object");
    expect(typeof api).not.toBe("function");
    expect(typeof api.calendar).toBe("function");
  });

  it("is never called as a bare function anywhere in the app", () => {
    const offenders = [];
    for (const file of files) {
      const src = fs.readFileSync(file, "utf8");
      // Only files that pull in the object can misuse it this way.
      if (!/import\s*\{[^}]*\bapi\b[^}]*\}\s*from\s*["']@?\/?.*lib\/api["']/.test(src)) continue;
      src.split("\n").forEach((line, i) => {
        // A comment is not a call site, and the note recording this bug quotes the bad
        // call verbatim. Matched on the leading marker only: stripping from any "//"
        // would also cut a line at an https:// inside a string.
        const trimmed = line.trim();
        if (trimmed.startsWith("//") || trimmed.startsWith("*")) return;
        // `api(` — but not `api.thing(`, and not a longer identifier ending in "api".
        if (/(^|[^\w.$])api\s*\(/.test(line)) {
          offenders.push(`${path.relative(SRC, file)}:${i + 1}  ${line.trim().slice(0, 90)}`);
        }
      });
    }
    expect(offenders).toEqual([]);
  });

  it("would catch the call that broke the calendar", () => {
    // The guard above only means anything if it actually fires on the real line.
    const bad = 'api(`/calendar?${qs}`)';
    const good = "api.calendar({ source, month })";
    expect(/(^|[^\w.$])api\s*\(/.test(bad)).toBe(true);
    expect(/(^|[^\w.$])api\s*\(/.test(good)).toBe(false);
  });
});
