import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import * as demoClient from "../../api/demoControlsClient";
import { ApiError } from "../../api/errors";
import { clearSession, setSession } from "../../auth/sessionStore";
import type { SessionInfo } from "../../api/types";
import { AppBar } from "./AppBar";

// The AppBar only calls this for a persona holding `demo_controls:use`, so the
// older tests below (which never grant it) make no request at all.
vi.mock("../../api/demoControlsClient", () => ({ getDemoState: vi.fn() }));

function personaSession(overrides: Partial<SessionInfo>): SessionInfo {
  return {
    persona: "COLLECTIONS_OFFICER",
    customer_id: null,
    display_name: "Collections Officer",
    capabilities: [],
    demo_label: "Demo persona - not real authentication",
    session_token: null,
    issued_at: "2026-10-01T14:30:00Z",
    ...overrides,
  };
}

function renderAppBar(initialPath = "/") {
  return render(
    <MemoryRouter initialEntries={[initialPath]}>
      <AppBar />
    </MemoryRouter>,
  );
}

describe("AppBar", () => {
  afterEach(() => {
    cleanup(); // unmount before the session changes, so nothing re-renders outside act()
    clearSession();
    vi.resetAllMocks();
  });

  it("always shows the demo persona disclosure, even with no session", () => {
    renderAppBar();
    expect(screen.getByText("Demo persona - not real authentication")).toBeInTheDocument();
  });

  it("shows only Chat for CUSTOMER", () => {
    setSession(
      personaSession({
        persona: "CUSTOMER",
        display_name: "Priya Raman",
        capabilities: ["chat:use", "self:read", "self:write", "session:read"],
      }),
    );
    renderAppBar();
    const nav = screen.getByRole("navigation", { name: "Main navigation" });
    expect(screen.getAllByRole("link", { name: /^Chat$/ })).toHaveLength(1);
    expect(nav.querySelectorAll("a")).toHaveLength(1);
  });

  it("shows Portfolio, Customer 360 and Escalations for COLLECTIONS_OFFICER, not Dashboard or Audit", () => {
    setSession(
      personaSession({
        persona: "COLLECTIONS_OFFICER",
        capabilities: [
          "portfolio:read",
          "customer360:read",
          "escalation:read",
          "escalation:review",
          "session:read",
        ],
      }),
    );
    renderAppBar();
    expect(screen.getByRole("link", { name: "Portfolio" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Customer 360" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Escalations" })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Dashboard" })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Audit Trail" })).not.toBeInTheDocument();
  });

  describe("the Demo controls link (E9-S3 AC1)", () => {
    const officerWithDemo = ["portfolio:read", "customer360:read", "escalation:read", "demo_controls:use"];

    it("appears last for an officer when the API answers the demo state", async () => {
      vi.mocked(demoClient.getDemoState).mockResolvedValue({
        llm_mode: "MOCK",
        clock: { mode: "SIMULATED", current_time: "2026-10-01T10:00:00Z" },
        demo_controls_enabled: true,
        policy_version: "policy-v1",
      });
      setSession(personaSession({ capabilities: officerWithDemo }));
      renderAppBar();

      const link = await screen.findByRole("link", { name: "Demo controls" });
      const nav = screen.getByRole("navigation", { name: "Main navigation" });
      expect(link).toHaveAttribute("href", "/demo-controls");
      expect(Array.from(nav.querySelectorAll("a")).at(-1)).toBe(link);
    });

    it("stays hidden when the flag is off (the API answers 404)", async () => {
      vi.mocked(demoClient.getDemoState).mockRejectedValue(
        new ApiError(404, {
          code: "NOT_FOUND",
          reason_code: null,
          message: "Demo controls are not enabled.",
          correlation_id: "c1",
        } as ConstructorParameters<typeof ApiError>[1]),
      );
      setSession(personaSession({ capabilities: officerWithDemo }));
      renderAppBar();

      await waitFor(() => expect(demoClient.getDemoState).toHaveBeenCalledTimes(1));
      expect(screen.queryByRole("link", { name: "Demo controls" })).not.toBeInTheDocument();
      expect(screen.getByRole("link", { name: "Portfolio" })).toBeInTheDocument();
    });

    it("is never offered, and never probed, for a persona without the capability", () => {
      setSession(personaSession({ persona: "COLLECTIONS_MANAGER", capabilities: ["kpi:read", "session:read"] }));
      renderAppBar();

      expect(screen.queryByRole("link", { name: "Demo controls" })).not.toBeInTheDocument();
      expect(demoClient.getDemoState).not.toHaveBeenCalled();
    });
  });

  it("shows only Dashboard for COLLECTIONS_MANAGER", () => {
    setSession(personaSession({ persona: "COLLECTIONS_MANAGER", capabilities: ["kpi:read", "session:read"] }));
    renderAppBar();
    const nav = screen.getByRole("navigation", { name: "Main navigation" });
    expect(nav.querySelectorAll("a")).toHaveLength(1);
    expect(screen.getByRole("link", { name: "Dashboard" })).toBeInTheDocument();
  });

  it("shows Audit Trail and Escalations (E7-S3 AC6: shared with COLLECTIONS_OFFICER) for COMPLIANCE_RISK", () => {
    setSession(
      personaSession({
        persona: "COMPLIANCE_RISK",
        capabilities: ["audit:read", "compliance:decide", "escalation:read", "session:read"],
      }),
    );
    renderAppBar();
    expect(screen.getByRole("link", { name: "Audit Trail" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Escalations" })).toBeInTheDocument();
  });

  it("marks the active nav link with aria-current=page", () => {
    setSession(
      personaSession({
        persona: "COLLECTIONS_MANAGER",
        capabilities: ["kpi:read", "session:read"],
      }),
    );
    renderAppBar("/dashboard");
    expect(screen.getByRole("link", { name: "Dashboard" })).toHaveAttribute("aria-current", "page");
  });

  it("announces the current persona name to assistive technology and as visible text", () => {
    setSession(
      personaSession({
        persona: "COMPLIANCE_RISK",
        display_name: "Compliance / Risk",
        capabilities: ["audit:read", "session:read"],
      }),
    );
    renderAppBar();
    const status = screen.getByRole("status");
    expect(status).toHaveAttribute("aria-live", "polite");
    expect(status).toHaveTextContent("Current persona: Compliance / Risk");
  });
});
