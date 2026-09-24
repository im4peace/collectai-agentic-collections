import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { clearSession, setSession } from "../auth/sessionStore";
import { ApiError } from "./errors";
import { createSession, getSessionMe, getSessionOptions } from "./client";
import type { SessionInfo, SessionOptionsResponse } from "./types";

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

describe("api/client", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn());
  });

  afterEach(() => {
    clearSession();
    vi.unstubAllGlobals();
  });

  it("sends no persona headers for the public options endpoint before any session exists", async () => {
    const options: SessionOptionsResponse = { personas: [], demo_customers: [] };
    vi.mocked(fetch).mockResolvedValueOnce(jsonResponse(200, options));

    await getSessionOptions();

    const [url, init] = vi.mocked(fetch).mock.calls[0];
    expect(url).toBe("/api/session/options");
    const headers = init?.headers as Record<string, string>;
    expect(headers["X-Persona"]).toBeUndefined();
    expect(headers["X-Demo-Session"]).toBeUndefined();
  });

  it("posts the persona and customer_id to create a session", async () => {
    const info: SessionInfo = {
      persona: "CUSTOMER",
      customer_id: "cus_0041",
      display_name: "Priya Raman",
      capabilities: ["chat:use"],
      demo_label: "Demo persona - not real authentication",
      session_token: "raw-token",
      issued_at: "2026-10-01T14:30:00Z",
    };
    vi.mocked(fetch).mockResolvedValueOnce(jsonResponse(201, info));

    const result = await createSession({ persona: "CUSTOMER", customer_id: "cus_0041" });

    expect(result.session_token).toBe("raw-token");
    const [, init] = vi.mocked(fetch).mock.calls[0];
    expect(init?.method).toBe("POST");
    expect(JSON.parse(init?.body as string)).toEqual({
      persona: "CUSTOMER",
      customer_id: "cus_0041",
    });
  });

  it("sends X-Persona only for a non-CUSTOMER session on later calls", async () => {
    setSession({
      persona: "COLLECTIONS_OFFICER",
      customer_id: null,
      display_name: "Collections Officer",
      capabilities: ["session:read"],
      demo_label: "Demo persona - not real authentication",
      session_token: "unused-token",
      issued_at: "2026-10-01T14:30:00Z",
    });
    vi.mocked(fetch).mockResolvedValueOnce(
      jsonResponse(200, {
        persona: "COLLECTIONS_OFFICER",
        customer_id: null,
        display_name: "Collections Officer",
        capabilities: ["session:read"],
        demo_label: "Demo persona - not real authentication",
        issued_at: "2026-10-01T14:31:00Z",
      }),
    );

    await getSessionMe();

    const [, init] = vi.mocked(fetch).mock.calls[0];
    const headers = init?.headers as Record<string, string>;
    expect(headers["X-Persona"]).toBe("COLLECTIONS_OFFICER");
    expect(headers["X-Demo-Session"]).toBeUndefined();
  });

  it("sends both X-Persona and X-Demo-Session for a CUSTOMER session", async () => {
    setSession({
      persona: "CUSTOMER",
      customer_id: "cus_0041",
      display_name: "Priya Raman",
      capabilities: ["self:read", "session:read"],
      demo_label: "Demo persona - not real authentication",
      session_token: "customer-token",
      issued_at: "2026-10-01T14:30:00Z",
    });
    vi.mocked(fetch).mockResolvedValueOnce(
      jsonResponse(200, {
        persona: "CUSTOMER",
        customer_id: "cus_0041",
        display_name: "Priya Raman",
        capabilities: ["self:read", "session:read"],
        demo_label: "Demo persona - not real authentication",
        issued_at: "2026-10-01T14:31:00Z",
      }),
    );

    await getSessionMe();

    const [, init] = vi.mocked(fetch).mock.calls[0];
    const headers = init?.headers as Record<string, string>;
    expect(headers["X-Persona"]).toBe("CUSTOMER");
    expect(headers["X-Demo-Session"]).toBe("customer-token");
  });

  it("throws a typed ApiError carrying the backend's error envelope on a non-2xx response", async () => {
    vi.mocked(fetch).mockResolvedValueOnce(
      jsonResponse(422, {
        error: {
          code: "VALIDATION_ERROR",
          reason_code: "CUSTOMER_ID_REQUIRED_OR_FORBIDDEN",
          message: "customer_id is required when persona is CUSTOMER.",
          correlation_id: "c0ffee1234abcd",
          details: [],
          alternatives: null,
          context: null,
        },
      }),
    );

    await expect(createSession({ persona: "CUSTOMER" })).rejects.toBeInstanceOf(ApiError);
  });
});
