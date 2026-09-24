import { describe, expect, it } from "vitest";

import { formatDateTime } from "./formatDateTime";

describe("formatDateTime", () => {
  it("renders a UTC ISO timestamp in fixed UTC+4 (GST) with no DST", () => {
    expect(formatDateTime("2026-10-01T14:30:00Z")).toBe("2026-10-01 18:30 GST");
  });

  it("rolls the date forward across midnight when the UTC+4 offset crosses a day boundary", () => {
    expect(formatDateTime("2026-10-01T21:15:00Z")).toBe("2026-10-02 01:15 GST");
  });

  it("pads single-digit month, day, hour and minute values", () => {
    expect(formatDateTime("2026-01-02T03:04:00Z")).toBe("2026-01-02 07:04 GST");
  });

  it("returns a placeholder for a null or empty timestamp", () => {
    expect(formatDateTime(null)).toBe("-");
    expect(formatDateTime("")).toBe("-");
  });
});
