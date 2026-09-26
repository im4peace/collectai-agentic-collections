import { cleanup, render, screen } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
import type { RouteObject } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import * as demoClient from "../api/demoControlsClient";
import type { SessionInfo } from "../api/types";
import { clearSession, setSession } from "../auth/sessionStore";
import { router } from "./router";

// The real route table is rendered, so this proves the wiring (path ->
// capability -> screen), not just the guard component in isolation. Every
// demo-control call is mocked: nothing here can reach a real clock or database.
vi.mock("../api/demoControlsClient", () => ({
  getDemoState: vi.fn(),
  postClockAdvance: vi.fn(),
  postRunPtpLifecycle: vi.fn(),
  postSimulatePayment: vi.fn(),
  postReseed: vi.fn(),
}));

function session(persona: SessionInfo["persona"], capabilities: string[]): SessionInfo {
  return {
    persona,
    customer_id: null,
    display_name: persona,
    capabilities,
    demo_label: "Demo persona - not real authentication",
    session_token: null,
    issued_at: "2026-10-01T09:00:00Z",
  };
}

function renderAt(path: string): void {
  const memory = createMemoryRouter(router.routes as unknown as RouteObject[], {
    initialEntries: [path],
  });
  render(<RouterProvider router={memory} />);
}

afterEach(() => {
  cleanup(); // unmount before the session changes, so nothing re-renders outside act()
  clearSession();
  vi.resetAllMocks();
});

describe("route /demo-controls (E9-S3)", () => {
  it("opens for a persona holding demo_controls:use and shows the mode as text", async () => {
    vi.mocked(demoClient.getDemoState).mockResolvedValue({
      llm_mode: "MOCK",
      clock: { mode: "SIMULATED", current_time: "2026-10-01T10:00:00Z" },
      demo_controls_enabled: true,
      policy_version: "policy-v1",
    });
    setSession(session("COLLECTIONS_OFFICER", ["demo_controls:use", "portfolio:read"]));

    renderAt("/demo-controls");

    expect(await screen.findByRole("heading", { level: 1, name: "Demo controls" })).toBeInTheDocument();
    expect(await screen.findByText("MOCK")).toBeInTheDocument();
    expect(await screen.findByRole("link", { name: "Demo controls" })).toHaveAttribute(
      "aria-current",
      "page",
    );
  });

  it.each([
    ["COLLECTIONS_MANAGER", ["kpi:read", "session:read"]],
    ["COMPLIANCE_RISK", ["audit:read", "escalation:read", "session:read"]],
    ["COLLECTIONS_OFFICER", ["portfolio:read", "customer360:read"]],
  ] as const)(
    "shows Forbidden to %s without the capability and never calls the API",
    (persona, capabilities) => {
      setSession(session(persona, [...capabilities]));

      renderAt("/demo-controls");

      expect(screen.getByRole("heading", { name: "403 - Forbidden" })).toBeInTheDocument();
      expect(screen.queryByRole("heading", { name: "Demo controls" })).not.toBeInTheDocument();
      expect(demoClient.getDemoState).not.toHaveBeenCalled();
      expect(demoClient.postClockAdvance).not.toHaveBeenCalled();
    },
  );

  it("shows Forbidden with no session at all", () => {
    renderAt("/demo-controls");

    expect(screen.getByRole("heading", { name: "403 - Forbidden" })).toBeInTheDocument();
    expect(demoClient.getDemoState).not.toHaveBeenCalled();
  });
});
