import { renderFormStory } from "./storyImage";

// THE STORY RENDERERS HAD NO TEST AT ALL, and this one could not be looked at: it is drawn on
// a canvas, and the only way to see it before now was to tap the button on a deployed page.
// A recording 2D context is the honest substitute. It cannot tell you the picture is
// beautiful; it can tell you it does not THROW at any progress value, that the claim on it is
// the claim it was given, and that no price ever reaches it — which are the three ways this
// can be wrong without anybody noticing until a post has gone out.
//
// A THROW MID-ANIMATION IS THE REAL RISK. recordStoryVideo calls the renderer ~150 times with
// progress from 0 to 1, and a NaN coordinate or an empty array reached at frame 3 fails after
// the user has already tapped Video and waited.

/** A canvas 2D context that records what was asked of it. */
function mockCanvas() {
  const calls = { text: [], fills: [], dashes: [], fonts: [] };
  const ctx = {
    canvas: null,
    set fillStyle(v) { calls.fills.push(v); this._fill = v; },
    get fillStyle() { return this._fill; },
    set font(v) { calls.fonts.push(v); this._font = v; },
    get font() { return this._font; },
    strokeStyle: "", lineWidth: 0, globalAlpha: 1, textAlign: "left",
    textBaseline: "top", letterSpacing: "0px",
    fillText: (t, x, y) => {
      // A NaN coordinate draws nothing and reports no error — the exact silent failure a
      // mock can catch and a screenshot cannot.
      if (!Number.isFinite(x) || !Number.isFinite(y)) {
        throw new Error(`fillText("${t}") at non-finite coords (${x}, ${y})`);
      }
      calls.text.push(String(t));
    },
    measureText: (t) => ({ width: String(t).length * 14 }),
    fillRect: () => {},
    beginPath: () => {}, moveTo: () => {}, lineTo: () => {}, stroke: () => {},
    closePath: () => {}, arcTo: () => {}, arc: () => {}, fill: () => {}, save: () => {},
    restore: () => {}, clip: () => {}, translate: () => {}, scale: () => {},
    drawImage: () => {}, filter: "none",
    setLineDash: (d) => calls.dashes.push(d),
    createRadialGradient: () => ({ addColorStop: () => {} }),
    createLinearGradient: () => ({ addColorStop: () => {} }),
  };
  const canvas = { width: 0, height: 0, getContext: () => ctx };
  ctx.canvas = canvas;
  return { canvas, calls, all: () => calls.text.join(" | ") };
}

const ARGS = {
  teamName: "Grimsby",
  // Oldest first, as the chart reads. Nine of these ten clear 5.
  values: [6, 7, 5, 8, 6, 5, 9, 2, 7, 6],
  line: 5,
  hits: 9,
  n: 10,
  claim: "cleared 5+ corners",
  windowLabel: "last 10 games",
  venueLabel: "at home",
  opponentLabel: "vs Bristol Rovers",
  leagueId: "eng-l2",
  leagueName: "League Two",
  kickoff: "Sat 12:30",
};

describe("it draws without throwing", () => {
  it("at the finished frame", () => {
    const { canvas } = mockCanvas();
    expect(() => renderFormStory(canvas, ARGS)).not.toThrow();
  });

  it("at every frame of the animation", () => {
    // THE ONE THAT MATTERS. recordStoryVideo drives this from 0 to 1; a failure at frame 3
    // happens after the user has tapped Video and waited for the encode.
    for (let i = 0; i <= 20; i += 1) {
      const { canvas } = mockCanvas();
      const p = i / 20;
      expect(() => renderFormStory(canvas, { ...ARGS, progress: p })).not.toThrow();
    }
  });

  it("with no games at all", () => {
    const { canvas } = mockCanvas();
    expect(() => renderFormStory(canvas, { ...ARGS, values: [], hits: 0, n: 0 })).not.toThrow();
  });

  it("with a single game", () => {
    // values.length - 1 is 0 here, which is a divide-by-zero in a naive stagger.
    const { canvas } = mockCanvas();
    expect(() => renderFormStory(canvas, { ...ARGS, values: [7], hits: 1, n: 1 })).not.toThrow();
  });

  it("with nothing passed at all", () => {
    const { canvas } = mockCanvas();
    expect(() => renderFormStory(canvas, {})).not.toThrow();
  });

  it("and it sizes the canvas to a story", () => {
    const { canvas } = mockCanvas();
    renderFormStory(canvas, ARGS);
    expect([canvas.width, canvas.height]).toEqual([1080, 1920]);
  });
});

describe("the claim on the picture", () => {
  it("is the fraction it was given, not a percentage", () => {
    // "90%" off ten games is the overclaim this site avoids; "9/10" carries its sample size.
    const { canvas, all } = mockCanvas();
    renderFormStory(canvas, ARGS);
    expect(all()).toContain("9/10");
    expect(all()).not.toContain("90%");
  });

  it("counts up, so the number is watched rather than read", () => {
    const { canvas, all } = mockCanvas();
    renderFormStory(canvas, { ...ARGS, progress: 0.2 });
    // Part-way through it is a smaller numerator over the same denominator.
    expect(all()).toMatch(/[0-8]\/10/);
    expect(all()).not.toContain("9/10");
  });

  it("names the line and is in the PAST TENSE", () => {
    // The only thing separating this image from the forecast one it is drawn to look like.
    const { canvas, all } = mockCanvas();
    renderFormStory(canvas, ARGS);
    expect(all()).toContain("cleared 5+ corners");
  });

  it("takes the whole phrase, so a conceded record does not read as 'cleared'", () => {
    // COMPOSING verb + noun PRODUCED NONSENSE HERE. A side does not "clear" corners it
    // shipped, and "cleared 5+ conceded" says the opposite of what the record is. Each
    // subject owns its own sentence — see SUBJECTS in consistency.js.
    const { canvas, all } = mockCanvas();
    renderFormStory(canvas, { ...ARGS, claim: "conceded 5+ corners" });
    expect(all()).toContain("conceded 5+ corners");
    expect(all()).not.toContain("cleared");
  });

  it("falls back to something true when no phrase is passed", () => {
    const { canvas, all } = mockCanvas();
    renderFormStory(canvas, { ...ARGS, claim: "" });
    expect(all()).toContain("5+ corners");
  });

  it("names the team, the window and the venue", () => {
    const { canvas, all } = mockCanvas();
    renderFormStory(canvas, ARGS);
    expect(all()).toContain("Grimsby");
    expect(all()).toContain("last 10 games");
    expect(all()).toContain("at home");
  });

  it("counts the misses in words rather than leaving it to colour", () => {
    const { canvas, all } = mockCanvas();
    renderFormStory(canvas, ARGS);
    expect(all()).toContain("9 over the line, 1 under it.");
  });

  it("says 'every one' when there were no misses", () => {
    const { canvas, all } = mockCanvas();
    renderFormStory(canvas, { ...ARGS, values: [6, 7, 5], line: 5, hits: 3, n: 3 });
    expect(all()).toContain("Every one of the last 3.");
  });

  it("says it is not a tip, on the image itself", () => {
    // A picture travels without its caption, and a record read as a tip is the one
    // misreading this can cause.
    const { canvas, all } = mockCanvas();
    renderFormStory(canvas, ARGS);
    expect(all()).toContain("What already happened — not a tip.");
  });
});

describe("no price reaches it", () => {
  it("draws no odds, no EV and no percentage anywhere", () => {
    // Every number here is a game that has been played, so there is nothing to hold back —
    // and nothing to leak. A change that put a price on this should fail rather than ship.
    const { canvas, all } = mockCanvas();
    renderFormStory(canvas, ARGS);
    expect(all()).not.toMatch(/\d+\.\d{2}\b/);
    expect(all()).not.toMatch(/\bEV\b/);
    expect(all()).not.toMatch(/%/);
  });
});

describe("the bars and the threshold", () => {
  it("prints every game's count under its bar", () => {
    const { canvas, all } = mockCanvas();
    renderFormStory(canvas, ARGS);
    ARGS.values.forEach((v) => expect(all()).toContain(String(v)));
  });

  it("draws the line as a dashed rule and labels it", () => {
    // THE THING THE PROBABILITY CHART CANNOT DO AND THIS NEEDS: with a rule at the line's own
    // height, "nine of these ten cleared it" is visible without counting.
    const { canvas, calls, all } = mockCanvas();
    renderFormStory(canvas, ARGS);
    expect(calls.dashes.some((d) => Array.isArray(d) && d.length === 2)).toBe(true);
    expect(all()).toContain("5+");
  });

  it("uses the dim tone for a game that missed", () => {
    const { canvas, calls } = mockCanvas();
    renderFormStory(canvas, ARGS);
    // #3B4654 is C.dim — the miss in this fixture set is the 2.
    expect(calls.fills).toContain("#3B4654");
  });

  it("uses no dim tone when nothing missed", () => {
    const { canvas, calls } = mockCanvas();
    renderFormStory(canvas, { ...ARGS, values: [6, 7, 8], line: 5, hits: 3, n: 3 });
    expect(calls.fills).not.toContain("#3B4654");
  });

  it("still draws the rule when every game cleared the line comfortably", () => {
    // Scaling to the tallest bar alone puts the threshold off the top of the panel in
    // exactly the case worth posting, so the scale includes the line.
    const { canvas, all } = mockCanvas();
    renderFormStory(canvas, { ...ARGS, values: [11, 12, 13], line: 4, hits: 3, n: 3 });
    expect(all()).toContain("4+");
  });
});
