import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { formatMoney, MoneyText } from "./MoneyText";

describe("formatMoney", () => {
  it("comma-groups the whole part and prefixes AED, per the mockup's money() convention", () => {
    expect(formatMoney("1234.56")).toBe("AED 1,234.56");
  });

  it("does not add a comma below 1,000", () => {
    expect(formatMoney("980.00")).toBe("AED 980.00");
  });

  it("groups amounts of six or more digits with multiple commas", () => {
    expect(formatMoney("1234567.89")).toBe("AED 1,234,567.89");
  });

  it("keeps the negative sign before the AED prefix", () => {
    expect(formatMoney("-245.10")).toBe("-AED 245.10");
  });

  it("returns the raw string unchanged when it is not a 2dp decimal string", () => {
    expect(formatMoney("not-a-number")).toBe("not-a-number");
  });
});

describe("MoneyText", () => {
  it("renders a decimal-string amount as formatted money text, generically (not portfolio-specific)", () => {
    render(<MoneyText amount="4820.35" />);
    expect(screen.getByText("AED 4,820.35")).toBeInTheDocument();
  });
});
