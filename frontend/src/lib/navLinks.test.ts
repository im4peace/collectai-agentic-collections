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

  it("shows COMPLIANCE_RISK exactly Audit Trail and the compliance review queue", () => {
    const links = navLinksForCapabilities(["audit:read", "compliance:decide", "escalation:read", "session:read"]);
    expect(links.map((l) => l.label)).toEqual(["Audit Trail", "Compliance review queue"]);
  });

  it("hides the officer's escalation queue from a persona holding only escalation:read", () => {
    const links = navLinksForCapabilities(["audit:read", "escalation:read", "session:read"]);
    expect(links.some((l) => l.label === "Escalations")).toBe(false);
  });

  it("shows nothing for a persona with no matching capabilities", () => {
    expect(navLinksForCapabilities([])).toEqual([]);
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
