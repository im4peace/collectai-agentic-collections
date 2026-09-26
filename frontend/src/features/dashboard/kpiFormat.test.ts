import { describe, expect, it } from "vitest";

import type { Kpi } from "../../api/kpiTypes";
import { formatKpiValue, formatRatioAsPercent, isObservationOnly } from "./kpiFormat";

function kpi(overrides: Partial<Kpi>): Kpi {
  return {
    kpi_id: "x",
    name: "X",
    definition: "d",
    formula: "f",
    data_label: "ILLUSTRATIVE",
    owner_persona: "COLLECTIONS_MANAGER",
    unit: "COUNT",
    value: "1",
    numerator: null,
    denominator: null,
    sample_size: null,
    claim_status: "NOT_APPLICABLE",
    target: null,
    source_note: null,
    ...overrides,
  };
}

describe("formatRatioAsPercent", () => {
  it("shifts a 4dp ratio to a 2dp percent with string arithmetic only", () => {
    expect(formatRatioAsPercent("0.6120")).toBe("61.20%");
    expect(formatRatioAsPercent("1.0000")).toBe("100.00%");
    expect(formatRatioAsPercent("0")).toBe("0.00%");
    expect(formatRatioAsPercent("0.0005")).toBe("0.05%");
  });

  it("truncates rather than rounds a longer decimal, so it never overstates", () => {
    expect(formatRatioAsPercent("0.99999")).toBe("99.99%");
  });

  it("passes a non-numeric value through unchanged", () => {
    expect(formatRatioAsPercent("n/a")).toBe("n/a");
  });
});

describe("formatKpiValue", () => {
  it("formats each unit and renders null as a dash", () => {
    expect(formatKpiValue(kpi({ unit: "COUNT", value: "1000" }))).toBe("1,000");
    expect(formatKpiValue(kpi({ unit: "CURRENCY", value: "1284560.75" }))).toBe("AED 1,284,560.75");
    expect(formatKpiValue(kpi({ unit: "MILLISECONDS", value: "2310" }))).toBe("2,310 ms");
    expect(formatKpiValue(kpi({ unit: "RATIO", value: "0.5" }))).toBe("50.00%");
    expect(formatKpiValue(kpi({ value: null }))).toBe("-");
  });
});

describe("isObservationOnly (AC3)", () => {
  it("is true for a LIVE tile the API marks OBSERVATION_ONLY", () => {
    expect(isObservationOnly(kpi({ data_label: "LIVE", claim_status: "OBSERVATION_ONLY" }))).toBe(true);
  });

  it("is true for a LIVE recall tile under 30 cases even if the payload claims PASS", () => {
    expect(
      isObservationOnly(
        kpi({
          kpi_id: "sensitive_category_recall_dispute",
          data_label: "LIVE",
          claim_status: "PASS",
          sample_size: 29,
        }),
      ),
    ).toBe(true);
  });

  it("is false for a LIVE recall tile with 30 or more cases and a PASS", () => {
    expect(
      isObservationOnly(
        kpi({
          kpi_id: "sensitive_category_recall_dispute",
          data_label: "LIVE",
          claim_status: "PASS",
          sample_size: 30,
        }),
      ),
    ).toBe(false);
  });

  it("is false for MOCK and ILLUSTRATIVE tiles (a regression figure holds no claim to withhold)", () => {
    expect(isObservationOnly(kpi({ data_label: "MOCK", claim_status: "OBSERVATION_ONLY" }))).toBe(false);
    expect(isObservationOnly(kpi({ data_label: "ILLUSTRATIVE" }))).toBe(false);
  });
});
