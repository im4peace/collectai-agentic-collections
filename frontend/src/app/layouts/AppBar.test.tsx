import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it } from "vitest";

import { clearSession, setSession } from "../../auth/sessionStore";
import type { SessionInfo } from "../../api/types";
import { AppBar } from "./AppBar";

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
    clearSession();
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
        capabilities: ["portfolio:read", "customer360:read", "escalation:review", "session:read"],
      }),
    );
    renderAppBar();
    expect(screen.getByRole("link", { name: "Portfolio" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Customer 360" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Escalations" })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Dashboard" })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Audit Trail" })).not.toBeInTheDocument();
  });

  it("shows only Dashboard for COLLECTIONS_MANAGER", () => {
    setSession(personaSession({ persona: "COLLECTIONS_MANAGER", capabilities: ["kpi:read", "session:read"] }));
    renderAppBar();
    const nav = screen.getByRole("navigation", { name: "Main navigation" });
    expect(nav.querySelectorAll("a")).toHaveLength(1);
    expect(screen.getByRole("link", { name: "Dashboard" })).toBeInTheDocument();
  });

  it("shows Audit Trail and the compliance review queue for COMPLIANCE_RISK", () => {
    setSession(
      personaSession({
        persona: "COMPLIANCE_RISK",
        capabilities: ["audit:read", "compliance:decide", "escalation:read", "session:read"],
      }),
    );
    renderAppBar();
    expect(screen.getByRole("link", { name: "Audit Trail" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Compliance review queue" })).toBeInTheDocument();
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
