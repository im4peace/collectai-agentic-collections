import { describe, expect, it } from "vitest";

import type { SessionState } from "./sessionStore";
import { hasCapability } from "./capabilities";

function sessionWith(capabilities: string[]): SessionState {
  return {
    persona: "COLLECTIONS_OFFICER",
    customerId: null,
    displayName: "Collections Officer",
    capabilities,
    demoLabel: "Demo persona - not real authentication",
    sessionToken: null,
    issuedAt: "2026-10-01T14:30:00Z",
  };
}

describe("hasCapability", () => {
  it("is true when the session's capability list includes the capability", () => {
    expect(hasCapability(sessionWith(["portfolio:read", "customer360:read"]), "portfolio:read")).toBe(
      true,
    );
  });

  it("is false when the session's capability list omits the capability", () => {
    expect(hasCapability(sessionWith(["portfolio:read"]), "escalation:review")).toBe(false);
  });

  it("is false when there is no session at all", () => {
    expect(hasCapability(null, "portfolio:read")).toBe(false);
  });

  it("distinguishes escalation:read from escalation:review, matching the backend matrix", () => {
    const session = sessionWith(["escalation:read"]);
    expect(hasCapability(session, "escalation:read")).toBe(true);
    expect(hasCapability(session, "escalation:review")).toBe(false);
  });
});
