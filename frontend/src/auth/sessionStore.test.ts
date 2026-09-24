import { beforeEach, describe, expect, it, vi } from "vitest";

import type { SessionInfo } from "../api/types";

const OFFICER_SESSION: SessionInfo = {
  persona: "COLLECTIONS_OFFICER",
  customer_id: null,
  display_name: "Collections Officer",
  capabilities: ["portfolio:read", "customer360:read"],
  demo_label: "Demo persona - not real authentication",
  session_token: "officer-token",
  issued_at: "2026-10-01T14:30:00Z",
};

const CUSTOMER_SESSION: SessionInfo = {
  persona: "CUSTOMER",
  customer_id: "cus_0041",
  display_name: "Priya Raman",
  capabilities: ["chat:use", "self:read", "self:write", "session:read"],
  demo_label: "Demo persona - not real authentication",
  session_token: "customer-token",
  issued_at: "2026-10-01T14:31:00Z",
};

describe("sessionStore", () => {
  beforeEach(() => {
    vi.resetModules();
    window.sessionStorage.clear();
  });

  it("starts with no session before anything is set", async () => {
    const { getSession } = await import("./sessionStore");
    expect(getSession()).toBeNull();
  });

  it("stores the persona, capabilities and demo label from a created session", async () => {
    const { getSession, setSession } = await import("./sessionStore");
    setSession(OFFICER_SESSION);
    expect(getSession()).toMatchObject({
      persona: "COLLECTIONS_OFFICER",
      customerId: null,
      displayName: "Collections Officer",
      capabilities: ["portfolio:read", "customer360:read"],
      demoLabel: "Demo persona - not real authentication",
    });
  });

  it("binds the CUSTOMER persona to the seeded customer id from the server", async () => {
    const { getSession, setSession } = await import("./sessionStore");
    setSession(CUSTOMER_SESSION);
    expect(getSession()?.customerId).toBe("cus_0041");
    expect(getSession()?.sessionToken).toBe("customer-token");
  });

  it("notifies subscribers when the session changes", async () => {
    const { setSession, subscribe } = await import("./sessionStore");
    const listener = vi.fn();
    subscribe(listener);
    setSession(OFFICER_SESSION);
    expect(listener).toHaveBeenCalledTimes(1);
  });

  it("clears the session and stops persisting it", async () => {
    const { clearSession, getSession, setSession } = await import("./sessionStore");
    setSession(OFFICER_SESSION);
    clearSession();
    expect(getSession()).toBeNull();
    expect(window.sessionStorage.getItem("collectai.demoSession")).toBeNull();
  });

  it("rehydrates a persisted session for a fresh module load (simulating a page reload)", async () => {
    const first = await import("./sessionStore");
    first.setSession(OFFICER_SESSION);

    vi.resetModules();
    const second = await import("./sessionStore");
    expect(second.getSession()).toMatchObject({ persona: "COLLECTIONS_OFFICER" });
  });
});
