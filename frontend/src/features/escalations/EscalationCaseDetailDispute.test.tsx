import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { Dispute } from "../../api/customer360Types";
import * as client from "../../api/escalationsClient";
import type { EscalationCaseDetail } from "../../api/escalationsTypes";
import { clearSession, setSession } from "../../auth/sessionStore";
import { EscalationCaseDetailScreen } from "./EscalationCaseDetailScreen";

vi.mock("../../api/escalationsClient", () => ({
  getEscalationCaseDetail: vi.fn(),
  postReviewDecision: vi.fn(),
  postComplianceDecision: vi.fn(),
}));
vi.mock("../../api/disputesClient", () => ({
  postDisputeStartReview: vi.fn(),
  postDisputeResolve: vi.fn(),
}));

const DISPUTE: Dispute = {
  dispute_id: "dsp_1",
  account_id: "acc_000123",
  customer_id: "cus_000101",
  item_id: null,
  category: "NOT_MY_DEBT",
  customer_reason: "This is not my debt.",
  status: "OPEN",
  outcome: null,
  resolution_reason: null,
  conversation_id: "conv_1",
  escalation_case_id: "esc_000001",
  created_at: "2026-09-24T09:00:00Z",
  resolved_at: null,
  version: 1,
};

function detail(dispute: Dispute | null | undefined): EscalationCaseDetail {
  return {
    case_id: "esc_000001",
    reason: "DISPUTE",
    queue: "DISPUTE_REVIEW",
    reviewer_role: "COLLECTIONS_OFFICER",
    priority: "ELEVATED",
    status: "OPEN",
    source: "SYSTEM",
    created_at: "2026-09-24T09:00:00Z",
    age_hours: 1,
    aging_warning: false,
    customer_id: "cus_000101",
    customer_name: "Priya Raman",
    account_id: "acc_000123",
    customer_360_path: "/customers/acc_000123",
    version: 1,
    conversation: [],
    ai_recommendation: null,
    rule_results: {
      summary: "Customer disputes an amount or item.",
      requested_terms: null,
      exception_types: null,
      routing_flags: [],
      routing_policy_version: "policy-v1",
    },
    approve_permitted: false,
    dispute,
  };
}

function renderAs(persona: string, capabilities: string[]): void {
  setSession({
    persona,
    customer_id: null,
    display_name: persona,
    capabilities,
    demo_label: "Demo persona - not real authentication",
    session_token: null,
    issued_at: "2026-10-01T14:30:00Z",
  } as Parameters<typeof setSession>[0]);
  render(
    <MemoryRouter initialEntries={["/escalations/esc_000001"]}>
      <Routes>
        <Route path="/escalations/:caseId" element={<EscalationCaseDetailScreen />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("EscalationCaseDetailScreen dispute panel (E11-S4 AC3)", () => {
  afterEach(() => {
    vi.clearAllMocks();
    clearSession();
  });

  it("shows the dispute-resolution panel with Start review for an officer holding dispute:resolve", async () => {
    vi.mocked(client.getEscalationCaseDetail).mockResolvedValue(detail(DISPUTE));
    renderAs("COLLECTIONS_OFFICER", ["escalation:read", "escalation:review", "dispute:resolve"]);

    expect(await screen.findByRole("heading", { name: "Dispute resolution" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Start review" })).toBeInTheDocument();
  });

  it("omits the panel when the API returns no dispute block", async () => {
    vi.mocked(client.getEscalationCaseDetail).mockResolvedValue(detail(null));
    renderAs("COLLECTIONS_OFFICER", ["escalation:read", "escalation:review", "dispute:resolve"]);

    await screen.findByRole("heading", { name: "Conversation" });
    expect(screen.queryByRole("heading", { name: "Dispute resolution" })).toBeNull();
  });

  it("omits the panel when the field is absent (older payloads, non-officer viewers)", async () => {
    vi.mocked(client.getEscalationCaseDetail).mockResolvedValue(detail(undefined));
    renderAs("COMPLIANCE_RISK", ["escalation:read", "compliance:decide"]);

    await screen.findByRole("heading", { name: "Conversation" });
    expect(screen.queryByRole("heading", { name: "Dispute resolution" })).toBeNull();
  });

  it("never offers resolve controls without the dispute:resolve capability", async () => {
    vi.mocked(client.getEscalationCaseDetail).mockResolvedValue(detail(DISPUTE));
    renderAs("COLLECTIONS_OFFICER", ["escalation:read"]);

    await screen.findByRole("heading", { name: "Dispute resolution" });
    expect(screen.queryByRole("button", { name: "Start review" })).toBeNull();
  });
});
