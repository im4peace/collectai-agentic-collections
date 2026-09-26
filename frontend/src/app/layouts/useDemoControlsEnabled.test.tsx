import { cleanup, renderHook, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import * as client from "../../api/demoControlsClient";
import { ApiError } from "../../api/errors";
import type { SessionInfo } from "../../api/types";
import { clearSession, setSession } from "../../auth/sessionStore";
import { useDemoControlsEnabled } from "./useDemoControlsEnabled";

vi.mock("../../api/demoControlsClient", () => ({ getDemoState: vi.fn() }));

const DEMO_STATE = {
  llm_mode: "MOCK" as const,
  clock: { mode: "SIMULATED" as const, current_time: "2026-10-01T10:00:00Z" },
  demo_controls_enabled: true,
  policy_version: "policy-v1",
};

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

function notFound(): ApiError {
  return new ApiError(404, {
    code: "NOT_FOUND",
    reason_code: null,
    message: "Demo controls are not enabled.",
    correlation_id: "c1",
  } as ConstructorParameters<typeof ApiError>[1]);
}

afterEach(() => {
  cleanup(); // unmount before the session changes, so nothing re-renders outside act()
  clearSession();
  vi.resetAllMocks();
});

describe("useDemoControlsEnabled (the nav link's flag probe)", () => {
  it("is true for an officer when the state endpoint answers", async () => {
    vi.mocked(client.getDemoState).mockResolvedValue(DEMO_STATE);
    setSession(session("COLLECTIONS_OFFICER", ["demo_controls:use", "portfolio:read"]));

    const { result } = renderHook(() => useDemoControlsEnabled());

    await waitFor(() => expect(result.current).toBe(true));
    expect(client.getDemoState).toHaveBeenCalledTimes(1);
  });

  it("treats a 404 (flag off) as disabled", async () => {
    vi.mocked(client.getDemoState).mockRejectedValue(notFound());
    setSession(session("COLLECTIONS_OFFICER", ["demo_controls:use"]));

    const { result } = renderHook(() => useDemoControlsEnabled());

    await waitFor(() => expect(client.getDemoState).toHaveBeenCalled());
    expect(result.current).toBe(false);
  });

  it("treats any other failure as disabled too (never a dead link)", async () => {
    vi.mocked(client.getDemoState).mockRejectedValue(new TypeError("Failed to fetch"));
    setSession(session("COLLECTIONS_OFFICER", ["demo_controls:use"]));

    const { result } = renderHook(() => useDemoControlsEnabled());

    await waitFor(() => expect(client.getDemoState).toHaveBeenCalled());
    expect(result.current).toBe(false);
  });

  it("is false until the probe answers", () => {
    vi.mocked(client.getDemoState).mockReturnValue(new Promise(() => undefined));
    setSession(session("COLLECTIONS_OFFICER", ["demo_controls:use"]));

    const { result } = renderHook(() => useDemoControlsEnabled());

    expect(result.current).toBe(false);
  });

  it.each([
    ["COLLECTIONS_MANAGER", ["kpi:read", "session:read"]],
    ["COMPLIANCE_RISK", ["audit:read", "escalation:read", "session:read"]],
    ["CUSTOMER", ["chat:use", "self:read"]],
    ["COLLECTIONS_OFFICER", ["portfolio:read"]],
  ] as const)("never calls the API for %s without demo_controls:use", (persona, capabilities) => {
    setSession(session(persona, [...capabilities]));

    const { result } = renderHook(() => useDemoControlsEnabled());

    expect(result.current).toBe(false);
    expect(client.getDemoState).not.toHaveBeenCalled();
  });

  it("does not call the API with no session at all", () => {
    const { result } = renderHook(() => useDemoControlsEnabled());

    expect(result.current).toBe(false);
    expect(client.getDemoState).not.toHaveBeenCalled();
  });
});
