import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import * as client from "../../api/escalationsClient";
import type { EscalationCaseDetail } from "../../api/escalationsTypes";
import { clearSession, setSession } from "../../auth/sessionStore";
import { EscalationCaseDetailScreen } from "./EscalationCaseDetailScreen";

vi.mock("../../api/escalationsClient", () => ({
  getEscalationCaseDetail: vi.fn(),
  postReviewDecision: vi.fn(),
  postComplianceDecision: vi.fn(),
}));

function baseDetail(overrides: Partial<EscalationCaseDetail> = {}): EscalationCaseDetail {
  const base: EscalationCaseDetail = {
    case_id: "esc_000001",
    reason: "REQUEST_HUMAN",
    queue: "COLLECTIONS_REVIEW",
    reviewer_role: "COLLECTIONS_OFFICER",
    priority: "URGENT",
    status: "OPEN",
    source: "CUSTOMER",
    created_at: "2026-09-24T09:00:00Z",
    age_hours: 5,
    aging_warning: false,
    customer_id: "cus_000101",
    customer_name: "Priya Raman",
    account_id: "acc_000123",
    customer_360_path: "/customers/acc_000123",
    version: 1,
    conversation: [
      {
        message_id: "msg_1",
        conversation_id: "conv_1",
        role: "CUSTOMER",
        content: "I need to speak with someone.",
        content_source: "CUSTOMER_INPUT",
        labels: [],
        created_at: "2026-09-24T09:00:00Z",
      },
    ],
    ai_recommendation: null,
    rule_results: {
      summary: "Customer explicitly requested a human.",
      requested_terms: null,
      exception_types: null,
      routing_flags: [],
      routing_policy_version: "policy-v1",
    },
    approve_permitted: false,
  };
  return { ...base, ...overrides };
}

function renderScreen(persona: "COLLECTIONS_OFFICER" | "COMPLIANCE_RISK" | "COLLECTIONS_MANAGER") {
  setSession({
    persona,
    customer_id: null,
    display_name: persona,
    capabilities: ["escalation:read", "escalation:review", "compliance:decide"],
    demo_label: "Demo persona - not real authentication",
    session_token: null,
    issued_at: "2026-10-01T14:30:00Z",
  });
  return render(
    <MemoryRouter initialEntries={["/escalations/esc_000001"]}>
      <Routes>
        <Route path="/escalations/:caseId" element={<EscalationCaseDetailScreen />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("EscalationCaseDetailScreen", () => {
  afterEach(() => {
    vi.clearAllMocks();
    clearSession();
  });

  it("shows the conversation, AI recommendation and rule results in three separately labelled sections (AC2)", async () => {
    vi.mocked(client.getEscalationCaseDetail).mockResolvedValue(baseDetail());
    renderScreen("COLLECTIONS_OFFICER");

    expect(await screen.findByRole("heading", { name: "Conversation" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "AI recommendation" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Deterministic rule results" })).toBeInTheDocument();
    expect(screen.getByText("I need to speak with someone.")).toBeInTheDocument();
    expect(screen.getByText("No AI recommendation is attached to this case.")).toBeInTheDocument();
    expect(screen.getByText("Customer explicitly requested a human.")).toBeInTheDocument();
  });

  it("hides Approve when approve_permitted is false but still shows Reject, Modify and Escalate (AC3)", async () => {
    vi.mocked(client.getEscalationCaseDetail).mockResolvedValue(
      baseDetail({ approve_permitted: false }),
    );
    renderScreen("COLLECTIONS_OFFICER");

    await screen.findByRole("heading", { name: "Reviewer decision" });
    expect(screen.queryByRole("button", { name: "Approve" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Reject" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Modify" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Escalate" })).toBeInTheDocument();
  });

  it("shows Approve when the API reports it is permitted (AC3)", async () => {
    vi.mocked(client.getEscalationCaseDetail).mockResolvedValue(
      baseDetail({ approve_permitted: true }),
    );
    renderScreen("COLLECTIONS_OFFICER");

    expect(await screen.findByRole("button", { name: "Approve" })).toBeInTheDocument();
  });

  it("the Reject dialog's Confirm button stays disabled until a reason is entered (AC3)", async () => {
    vi.mocked(client.getEscalationCaseDetail).mockResolvedValue(baseDetail());
    renderScreen("COLLECTIONS_OFFICER");

    fireEvent.click(await screen.findByRole("button", { name: "Reject" }));
    const dialog = await screen.findByRole("dialog", { name: "Reject this case?" });
    const confirmButton = within(dialog).getByRole("button", { name: "Reject" });
    expect(confirmButton).toBeDisabled();

    fireEvent.change(within(dialog).getByLabelText("Reason"), {
      target: { value: "Not eligible." },
    });
    expect(confirmButton).toBeEnabled();
  });

  it("COMPLIANCE_RISK sees compliance controls, not reviewer controls, on a COMPLIANCE_REVIEW case (AC6)", async () => {
    vi.mocked(client.getEscalationCaseDetail).mockResolvedValue(
      baseDetail({ queue: "COMPLIANCE_REVIEW", reviewer_role: "COMPLIANCE_RISK" }),
    );
    renderScreen("COMPLIANCE_RISK");

    expect(await screen.findByRole("heading", { name: "Compliance decision" })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Reviewer decision" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Clear" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Not cleared" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Remediation required" })).toBeInTheDocument();
  });

  it("COLLECTIONS_OFFICER never sees compliance controls, even on a COMPLIANCE_REVIEW case (AC6)", async () => {
    vi.mocked(client.getEscalationCaseDetail).mockResolvedValue(
      baseDetail({ queue: "COMPLIANCE_REVIEW", reviewer_role: "COMPLIANCE_RISK" }),
    );
    renderScreen("COLLECTIONS_OFFICER");

    await waitFor(() => expect(client.getEscalationCaseDetail).toHaveBeenCalled());
    expect(screen.queryByRole("heading", { name: "Compliance decision" })).not.toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Reviewer decision" })).not.toBeInTheDocument();
  });

  it("no action controls render once the case is already decided", async () => {
    vi.mocked(client.getEscalationCaseDetail).mockResolvedValue(
      baseDetail({ status: "DECIDED", approve_permitted: false }),
    );
    renderScreen("COLLECTIONS_OFFICER");

    await waitFor(() => expect(client.getEscalationCaseDetail).toHaveBeenCalled());
    expect(screen.queryByRole("heading", { name: "Reviewer decision" })).not.toBeInTheDocument();
  });
});
