import { describe, expect, it } from "vitest";

import { defaultRouteForCapabilities, navLinksForCapabilities } from "./navLinks";

describe("navLinksForCapabilities", () => {
  it("shows CUSTOMER only Chat", () => {
    const links = navLinksForCapabilities(["chat:use", "self:read", "self:write", "session:read"]);
    expect(links.map((l) => l.label)).toEqual(["Chat"]);
  });

  it("shows COLLECTIONS_OFFICER exactly Portfolio, Customer 360 and Escalations", () => {
    const links = navLinksForCapabilities([
      "conversation:read",
      "customer360:read",
      "demo_controls:use",
      "dispute:read",
      "dispute:resolve",
      "escalation:read",
      "escalation:review",
      "hardship:read",
      "portfolio:read",
      "ptp:read",
      "ptp:record",
      "recommendation:decide",
      "recommendation:generate",
      "recommendation:read",
      "session:read",
      "snapshot:refresh",
    ]);
    expect(links.map((l) => l.label)).toEqual(["Portfolio", "Customer 360", "Escalations"]);
  });

  it("shows COLLECTIONS_MANAGER only Dashboard", () => {
    const links = navLinksForCapabilities(["kpi:read", "session:read"]);
    expect(links.map((l) => l.label)).toEqual(["Dashboard"]);
  });

  it("shows COMPLIANCE_RISK exactly Escalations and Audit Trail (E7-S3 AC6: shared escalation:read)", () => {
    const links = navLinksForCapabilities(["audit:read", "compliance:decide", "escalation:read", "session:read"]);
    expect(links.map((l) => l.label)).toEqual(["Escalations", "Audit Trail"]);
  });

  it("shows Escalations to any persona holding escalation:read, not just escalation:review", () => {
    const links = navLinksForCapabilities(["audit:read", "escalation:read", "session:read"]);
    expect(links.some((l) => l.label === "Escalations")).toBe(true);
  });

  it("shows nothing for a persona with no matching capabilities", () => {
    expect(navLinksForCapabilities([])).toEqual([]);
  });
});

describe("the Demo controls link (E9-S3 AC1: no dead link when the flag is off)", () => {
  const OFFICER = ["demo_controls:use", "portfolio:read", "customer360:read", "escalation:read"];

  it("is hidden when the flag is unknown or off, even though the officer holds the capability", () => {
    expect(navLinksForCapabilities(OFFICER).map((l) => l.label)).not.toContain("Demo controls");
    expect(
      navLinksForCapabilities(OFFICER, { demoControlsEnabled: false }).map((l) => l.label),
    ).not.toContain("Demo controls");
  });

  it("is shown last for an officer when the flag is on", () => {
    const links = navLinksForCapabilities(OFFICER, { demoControlsEnabled: true });

    expect(links.map((l) => l.label)).toEqual([
      "Portfolio",
      "Customer 360",
      "Escalations",
      "Demo controls",
    ]);
    expect(links[links.length - 1].path).toBe("/demo-controls");
  });

  it("is never shown without the capability, whatever the flag says", () => {
    for (const capabilities of [["kpi:read"], ["audit:read", "escalation:read"], ["chat:use"]]) {
      expect(
        navLinksForCapabilities(capabilities, { demoControlsEnabled: true }).map((l) => l.label),
      ).not.toContain("Demo controls");
    }
  });

  it("never becomes an officer's default landing route", () => {
    expect(defaultRouteForCapabilities(OFFICER)).toBe("/portfolio");
    expect(defaultRouteForCapabilities(["demo_controls:use"])).toBe("/");
  });
});

describe("defaultRouteForCapabilities", () => {
  it("routes a fresh CUSTOMER session straight to /chat", () => {
    expect(defaultRouteForCapabilities(["chat:use"])).toBe("/chat");
  });

  it("routes a fresh COLLECTIONS_MANAGER session to /dashboard", () => {
    expect(defaultRouteForCapabilities(["kpi:read"])).toBe("/dashboard");
  });

  it("falls back to / when no nav link is permitted", () => {
    expect(defaultRouteForCapabilities([])).toBe("/");
  });
});
