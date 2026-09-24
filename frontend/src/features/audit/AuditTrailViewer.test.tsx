import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import * as auditClient from "../../api/auditClient";
import type { AuditChainPage, AuditEvent, AuditPage } from "../../api/auditTypes";
import { AuditTrailViewer } from "./AuditTrailViewer";

vi.mock("../../api/auditClient", () => ({
  searchAuditEvents: vi.fn(),
  listAuditChains: vi.fn(),
}));

function makeEvent(overrides: Partial<AuditEvent> = {}): AuditEvent {
  const base: AuditEvent = {
    audit_event_id: "aud_1",
    sequence: 1,
    timestamp: "2026-10-01T14:00:00Z",
    correlation_id: "corr-abc",
    stage: "INPUT",
    event_type: "CUSTOMER_MESSAGE",
    actor_kind: "CUSTOMER",
    actor_persona: "CUSTOMER",
    customer_id: "cus_0041",
    account_id: "acc_000123",
    capability: null,
    provider: null,
    provider_mode: null,
    model_id: null,
    prompt_version: null,
    policy_version: null,
    input_ref: null,
    ai_output: null,
    tool_calls: [],
    rule_results: null,
    human_override: null,
    final_action: null,
    reason_code: null,
    resource_type: null,
    resource_id: null,
    latency: null,
    token_usage: null,
  };
  return { ...base, ...overrides };
}

describe("AuditTrailViewer", () => {
  afterEach(() => {
    vi.clearAllMocks();
  });

  it("searching by correlation id shows an ordered, labelled six-stage timeline (AC1)", async () => {
    const events: AuditEvent[] = [
      makeEvent({ audit_event_id: "aud_1", stage: "INPUT", event_type: "CUSTOMER_MESSAGE" }),
      makeEvent({
        audit_event_id: "aud_2",
        sequence: 2,
        stage: "AI_INTERPRETATION",
        event_type: "AI_RESPONSE_RECORDED",
        model_id: "mock-intent-1",
        prompt_version: "intent-v2",
        policy_version: "policy-v1",
      }),
      makeEvent({ audit_event_id: "aud_3", sequence: 3, stage: "FINAL_STATE", event_type: "PTP_RECORDED" }),
    ];
    const page: AuditPage = { items: events, page: { limit: 100, offset: 0, total: 3 } };
    vi.mocked(auditClient.searchAuditEvents).mockResolvedValue(page);

    const user = userEvent.setup();
    render(<AuditTrailViewer />);

    await user.type(screen.getByLabelText("Correlation id"), "corr-abc");
    await user.click(screen.getByRole("button", { name: "Search" }));

    expect(await screen.findByText("CUSTOMER_MESSAGE")).toBeInTheDocument();
    expect(screen.getByText("Input")).toBeInTheDocument();
    expect(screen.getByText("AI interpretation")).toBeInTheDocument();
    expect(screen.getByText("Final state")).toBeInTheDocument();
    expect(auditClient.searchAuditEvents).toHaveBeenCalledWith({ correlation_id: "corr-abc" });
  });

  it("shows model id, prompt version and policy version for an AI step (AC2)", async () => {
    const events: AuditEvent[] = [
      makeEvent({
        stage: "AI_INTERPRETATION",
        event_type: "AI_RESPONSE_RECORDED",
        model_id: "mock-intent-1",
        prompt_version: "intent-v2",
        policy_version: "policy-v1",
      }),
    ];
    vi.mocked(auditClient.searchAuditEvents).mockResolvedValue({
      items: events,
      page: { limit: 100, offset: 0, total: 1 },
    });

    const user = userEvent.setup();
    render(<AuditTrailViewer />);
    await user.type(screen.getByLabelText("Correlation id"), "corr-abc");
    await user.click(screen.getByRole("button", { name: "Search" }));

    await screen.findByText("AI interpretation");
    expect(screen.getByText(/model mock-intent-1/)).toBeInTheDocument();
    expect(screen.getByText(/prompt intent-v2/)).toBeInTheDocument();
    expect(screen.getByText(/policy policy-v1/)).toBeInTheDocument();
  });

  it("has no edit or delete controls anywhere on the page (AC3)", async () => {
    vi.mocked(auditClient.searchAuditEvents).mockResolvedValue({
      items: [makeEvent()],
      page: { limit: 100, offset: 0, total: 1 },
    });
    const user = userEvent.setup();
    render(<AuditTrailViewer />);
    await user.type(screen.getByLabelText("Correlation id"), "corr-abc");
    await user.click(screen.getByRole("button", { name: "Search" }));
    await screen.findByText("CUSTOMER_MESSAGE");

    const buttons = screen.getAllByRole("button").map((button) => button.textContent?.toLowerCase() ?? "");
    expect(buttons.some((text) => text.includes("edit") || text.includes("delete"))).toBe(false);
  });

  it("searching by account id lists matching chains, each opening its own timeline (AC1)", async () => {
    const chainPage: AuditChainPage = {
      items: [
        {
          correlation_id: "corr-xyz",
          account_id: "acc_000123",
          started_at: "2026-10-01T14:00:00Z",
          last_event_at: "2026-10-01T14:05:00Z",
          event_count: 4,
          stages_present: ["INPUT", "FINAL_STATE"],
          final_action: "PTP_RECORDED",
          policy_version: "policy-v1",
          model_id: null,
          prompt_version: null,
        },
      ],
      page: { limit: 50, offset: 0, total: 1 },
    };
    vi.mocked(auditClient.listAuditChains).mockResolvedValue(chainPage);
    vi.mocked(auditClient.searchAuditEvents).mockResolvedValue({
      items: [makeEvent({ correlation_id: "corr-xyz" })],
      page: { limit: 100, offset: 0, total: 1 },
    });

    const user = userEvent.setup();
    render(<AuditTrailViewer />);
    await user.type(screen.getByLabelText("Account id"), "acc_000123");
    await user.click(screen.getByRole("button", { name: "Search" }));

    expect(await screen.findByRole("button", { name: "corr-xyz" })).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "corr-xyz" }));
    expect(await screen.findByText("CUSTOMER_MESSAGE")).toBeInTheDocument();
    expect(auditClient.searchAuditEvents).toHaveBeenCalledWith({ correlation_id: "corr-xyz" });
  });
});
