import { describe, expect, it } from "vitest";

import { formatStatusLabel, PRIORITY_BAND_DISPLAY } from "./portfolioLabels";

describe("formatStatusLabel", () => {
  it("replaces underscores with spaces", () => {
    expect(formatStatusLabel("IN_PROGRESS")).toBe("IN PROGRESS");
  });

  it("leaves a single-word status unchanged", () => {
    expect(formatStatusLabel("ESCALATED")).toBe("ESCALATED");
  });
});

describe("PRIORITY_BAND_DISPLAY", () => {
  it("gives every band a non-empty text label distinct from color alone (AC1)", () => {
    expect(PRIORITY_BAND_DISPLAY.HIGH.label).toBe("HIGH priority");
    expect(PRIORITY_BAND_DISPLAY.MEDIUM.label).toBe("MEDIUM priority");
    expect(PRIORITY_BAND_DISPLAY.LOW.label).toBe("LOW priority");
  });

  it("maps HIGH/MEDIUM/LOW to distinct badge variants", () => {
    const variants = [
      PRIORITY_BAND_DISPLAY.HIGH.variant,
      PRIORITY_BAND_DISPLAY.MEDIUM.variant,
      PRIORITY_BAND_DISPLAY.LOW.variant,
    ];
    expect(new Set(variants).size).toBe(3);
  });
});
