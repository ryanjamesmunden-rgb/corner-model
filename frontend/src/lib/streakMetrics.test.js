import {
  METRICS, SUBJECTS, WIRE_SUBJECT, wireSubject, SUBJECT_LABEL,
  LADDERS, MIN_LINE, lineLabel,
} from "./streakMetrics";

describe("composing the API subject from two controls", () => {
  it("leaves the corner subjects exactly as they were", () => {
    expect(wireSubject("corners", "team")).toBe("team");
    expect(wireSubject("corners", "conceded")).toBe("conceded");
    expect(wireSubject("corners", "match")).toBe("match");
  });

  it("maps each subject onto its shots equivalent", () => {
    expect(wireSubject("shots", "team")).toBe("shots");
    expect(wireSubject("shots", "conceded")).toBe("shots_conceded");
    expect(wireSubject("shots", "match")).toBe("shots_match");
  });

  it("falls back to corners for an unknown metric", () => {
    // Defaulting to the stat with 99.7% coverage is the safe direction to be wrong in.
    expect(wireSubject("bananas", "team")).toBe("team");
  });

  it("covers every offered combination", () => {
    // A missing pair would send the subject through unmapped, so a Shots selection would
    // silently ask for corners and the board would look right and be the wrong stat.
    for (const m of METRICS) {
      for (const s of SUBJECTS) {
        expect(typeof wireSubject(m.v, s.v)).toBe("string");
        expect(WIRE_SUBJECT[m.v][s.v]).toBeTruthy();
      }
    }
  });
});

describe("every wire subject is fully configured", () => {
  const wires = METRICS.flatMap((m) => SUBJECTS.map((s) => wireSubject(m.v, s.v)));

  it("has an over ladder and an under ladder", () => {
    // THE SILENT FAILURE THIS FILE EXISTS FOR. `LADDERS[dir-subject] || []` falls back to
    // an empty list, and the threshold drop-down then offers only "auto" — or, worse, a
    // subject added to one direction and not the other reads as a broken filter.
    for (const w of wires) {
      expect(LADDERS[`over-${w}`]).toBeDefined();
      expect(LADDERS[`under-${w}`]).toBeDefined();
      expect(LADDERS[`over-${w}`].length).toBeGreaterThan(0);
      expect(LADDERS[`under-${w}`].length).toBeGreaterThan(0);
    }
  });

  it("has a min line and a label", () => {
    for (const w of wires) {
      expect(typeof MIN_LINE[w]).toBe("number");
      expect(SUBJECT_LABEL[w]).toBeTruthy();
    }
  });

  it("never offers an over below its own min line", () => {
    // Otherwise the menu shows a rung the server will refuse, and picking it returns an
    // empty board that looks like the team has no run.
    for (const w of wires) {
      expect(Math.min(...LADDERS[`over-${w}`])).toBeGreaterThanOrEqual(MIN_LINE[w]);
    }
  });

  it("keeps every ladder ascending", () => {
    for (const [key, ladder] of Object.entries(LADDERS)) {
      expect([...ladder].sort((a, b) => a - b)).toEqual(ladder);
      expect(new Set(ladder).size).toBe(ladder.length);
      expect(key).toMatch(/^(over|under)-/);
    }
  });
});

describe("the shots ladders sit on the shots scale", () => {
  it("starts well above the corner rungs", () => {
    // 13.17 shots a side measured. Offering the corner rungs would put "3+ shots" on the
    // menu, which every side in every division clears every week.
    expect(Math.min(...LADDERS["over-shots"])).toBeGreaterThan(
      Math.max(...LADDERS["over-team"]),
    );
  });

  it("puts match shots above team shots", () => {
    expect(Math.min(...LADDERS["over-shots_match"])).toBeGreaterThan(
      Math.max(...LADDERS["over-shots"]),
    );
  });

  it("treats shots faced on the same scale as shots taken", () => {
    // It is the same count from the other end of the same match, exactly as conceded
    // corners are.
    expect(LADDERS["over-shots_conceded"]).toEqual(LADDERS["over-shots"]);
  });
});

describe("the chip says what it is counting", () => {
  it("marks a shots line", () => {
    expect(lineLabel(13, "over", "shots")).toBe("13+ sh");
    expect(lineLabel(26, "over", "shots_match")).toBe("26+ sh");
    expect(lineLabel(10, "under", "shots")).toBe("U 10 sh");
  });

  it("names the direction of a shots-faced line", () => {
    expect(lineLabel(12, "over", "shots_conceded")).toBe("12+ sh faced");
  });

  it("leaves the corner chips alone", () => {
    expect(lineLabel(5, "over", "team")).toBe("5+");
    expect(lineLabel(5, "over", "conceded")).toBe("conc 5+");
    expect(lineLabel(8, "under", "match")).toBe("U 8");
  });

  it("never prints a bare number for a shots subject", () => {
    // A bare "13+" on a shots row is the same characters the rest of the site uses for
    // corners, which is the whole hazard.
    for (const w of ["shots", "shots_conceded", "shots_match"]) {
      for (const d of ["over", "under"]) {
        expect(lineLabel(13, d, w)).toMatch(/sh/);
      }
    }
  });
});
