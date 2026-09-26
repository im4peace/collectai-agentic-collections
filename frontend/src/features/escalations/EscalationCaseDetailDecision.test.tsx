import { act, fireEvent, render, renderHook, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "../../api/errors";
import * as client from "../../api/escalationsClient";
import type { EscalationCaseDetail } from "../../api/escalationsTypes";
import { clearSession, setSession } from "../../auth/sessionStore";
import { EscalationCaseDetailScreen } from "./EscalationCaseDetailScreen";
import { useCaseDecision } from "./useCaseDecision";

vi.mock("../../api/escalationsClient", () => ({
  getEscalationCaseDetail: vi.fn(),
  postReviewDecision: vi.fn(),
  postComplianceDecision: vi.fn(),
}));

function detail(overrides: Partial<EscalationCaseDetail> = {}): EscalationCaseDetail {
  return {
    case_id: "esc_000001",
    reason: "REQUEST_HUMAN",
    queue: "COLLECTIONS_REVIEW",
    reviewer_role: "COLLECTIONS_OFFICER",
    priority: "NORMAL",
    status: "OPEN",
    source: "CUSTOMER",
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
      summary: "Customer asked to speak with a human colleague.",
      requested_terms: null,
      exception_types: null,
      routing_flags: [],
      routing_policy_version: "policy-v1",
    },
    approve_permitted: false,
    ...overrides,
  };
}

function apiError(status: number, reasonCode: string, message: string): ApiError {
  return new ApiError(status, {
    code: "ERROR",
    reason_code: reasonCode,
    message,
    correlation_id: "c1",
  } as ConstructorParameters<typeof ApiError>[1]);
}

const staleVersion = () => apiError(409, "VERSION_CONFLICT", "stale");

function renderAs(persona: "COLLECTIONS_OFFICER" | "COMPLIANCE_RISK"): void {
  setSession({
    persona,
    customer_id: null,
    display_name: persona,
    capabilities: ["escalation:read", "escalation:review", "compliance:decide"],
    demo_label: "Demo persona - not real authentication",
    session_token: null,
    issued_at: "2026-10-01T14:30:00Z",
  });
  render(
    <MemoryRouter initialEntries={["/escalations/esc_000001"]}>
      <Routes>
        <Route path="/escalations/:caseId" element={<EscalationCaseDetailScreen />} />
      </Routes>
    </MemoryRouter>,
  );
}

async function submitReject(reason: string): Promise<void> {
  fireEvent.click(await screen.findByRole("button", { name: "Reject" }));
  const dialog = await screen.findByRole("dialog", { name: "Reject this case?" });
  fireEvent.change(within(dialog).getByLabelText("Reason"), { target: { value: reason } });
  fireEvent.click(within(dialog).getByRole("button", { name: "Reject" }));
}

afterEach(() => {
  clearSession();
  vi.clearAllMocks();
});

describe("useCaseDecision outcomes (E7-S3 AC4)", () => {
  it("resolves 'success' when the decision is recorded", async () => {
    vi.mocked(client.postReviewDecision).mockResolvedValue({} as never);
    const { result } = renderHook(() => useCaseDecision());

    let outcome: string | undefined;
    await act(async () => {
      outcome = await result.current.submitReviewDecision("esc_1", 3, { action: "REJECT", reason: "r" });
    });

    expect(outcome).toBe("success");
    expect(result.current.versionConflict).toBe(false);
    expect(result.current.errorMessage).toBeNull();
  });

  it("resolves 'version_conflict' on a 409 VERSION_CONFLICT, from that very call, and sets the flag", async () => {
    vi.mocked(client.postReviewDecision).mockRejectedValue(staleVersion());
    const { result } = renderHook(() => useCaseDecision());

    let outcome: string | undefined;
    await act(async () => {
      outcome = await result.current.submitReviewDecision("esc_1", 3, { action: "REJECT", reason: "r" });
    });

    expect(outcome).toBe("version_conflict");
    expect(result.current.versionConflict).toBe(true);
    expect(result.current.errorMessage).toBeNull();
    expect(client.postReviewDecision).toHaveBeenCalledTimes(1);
  });

  it("resolves 'error' for any other failure, with its message, and does not flag a conflict", async () => {
    vi.mocked(client.postComplianceDecision).mockRejectedValue(apiError(422, "REASON_REQUIRED", "A reason is required."));
    const { result } = renderHook(() => useCaseDecision());

    let outcome: string | undefined;
    await act(async () => {
      outcome = await result.current.submitComplianceDecision("esc_1", 3, "CLEARED", "r");
    });

    expect(outcome).toBe("error");
    expect(result.current.versionConflict).toBe(false);
    expect(result.current.errorMessage).toBe("A reason is required.");
  });

  it("treats a 409 that is not VERSION_CONFLICT as an ordinary error", async () => {
    vi.mocked(client.postReviewDecision).mockRejectedValue(
      apiError(409, "CASE_ALREADY_DECIDED", "Already decided."),
    );
    const { result } = renderHook(() => useCaseDecision());

    let outcome: string | undefined;
    await act(async () => {
      outcome = await result.current.submitReviewDecision("esc_1", 3, { action: "REJECT", reason: "r" });
    });

    expect(outcome).toBe("error");
    expect(result.current.versionConflict).toBe(false);
  });
});

describe("EscalationCaseDetailScreen decisions (E7-S3 AC4)", () => {
  it("on a stale-version 409: shows the message, closes the dialog, refetches and renders the server's new state", async () => {
    vi.mocked(client.getEscalationCaseDetail)
      .mockResolvedValueOnce(detail({ version: 1, status: "OPEN" }))
      .mockResolvedValue(detail({ version: 2, status: "AWAITING_INFORMATION" }));
    vi.mocked(client.postReviewDecision).mockRejectedValue(staleVersion());
    renderAs("COLLECTIONS_OFFICER");

    expect(await screen.findByText("OPEN")).toBeInTheDocument();
    await submitReject("Stale attempt.");

    expect(await screen.findByRole("alert")).toHaveTextContent("This case changed");
    await waitFor(() =>
      expect(screen.queryByRole("dialog", { name: "Reject this case?" })).not.toBeInTheDocument(),
    );
    await waitFor(() => expect(client.getEscalationCaseDetail).toHaveBeenCalledTimes(2));
    expect(await screen.findByText("AWAITING INFORMATION")).toBeInTheDocument();
    expect(screen.queryByText("OPEN")).not.toBeInTheDocument();
    // F-03: a conflict is not a success -- no success announcement, no focus theft.
    expect(screen.queryByText(/decision recorded/i)).not.toBeInTheDocument();
    expect(screen.getByRole("group", { name: "Case status" })).not.toHaveFocus();
  });

  it("never retries the rejected action automatically, and the next attempt uses the reloaded version and a new key", async () => {
    vi.mocked(client.getEscalationCaseDetail)
      .mockResolvedValueOnce(detail({ version: 1 }))
      .mockResolvedValue(detail({ version: 2, status: "AWAITING_INFORMATION" }));
    vi.mocked(client.postReviewDecision)
      .mockRejectedValueOnce(staleVersion())
      .mockResolvedValueOnce({} as never);
    renderAs("COLLECTIONS_OFFICER");

    await submitReject("First attempt.");
    await screen.findByText("AWAITING INFORMATION");
    // Settled: still exactly one write attempt, made with the stale version.
    expect(client.postReviewDecision).toHaveBeenCalledTimes(1);
    expect(vi.mocked(client.postReviewDecision).mock.calls[0][1].expected_version).toBe(1);

    // A deliberate second attempt by the reviewer carries the reloaded version.
    await submitReject("Second, deliberate attempt.");
    await waitFor(() => expect(client.postReviewDecision).toHaveBeenCalledTimes(2));
    const [first, second] = vi.mocked(client.postReviewDecision).mock.calls;
    expect(second[1].expected_version).toBe(2);
    expect(second[2]).not.toBe(first[2]);
  });

  it("a successful decision still closes the dialog, refetches and shows the new state", async () => {
    vi.mocked(client.getEscalationCaseDetail)
      .mockResolvedValueOnce(detail({ version: 1 }))
      .mockResolvedValue(detail({ version: 2, status: "DECIDED" }));
    vi.mocked(client.postReviewDecision).mockResolvedValue({} as never);
    renderAs("COLLECTIONS_OFFICER");

    await submitReject("Reviewed.");

    await waitFor(() => expect(client.getEscalationCaseDetail).toHaveBeenCalledTimes(2));
    expect(await screen.findByText("DECIDED")).toBeInTheDocument();
    expect(screen.queryByRole("dialog", { name: "Reject this case?" })).not.toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("a non-409 error keeps the dialog open, shows the API's message and does not refetch", async () => {
    vi.mocked(client.getEscalationCaseDetail).mockResolvedValue(detail());
    vi.mocked(client.postReviewDecision).mockRejectedValue(
      apiError(422, "REASON_REQUIRED", "A reason is required."),
    );
    renderAs("COLLECTIONS_OFFICER");

    await submitReject("x");

    expect(await screen.findByText("A reason is required.")).toBeInTheDocument();
    expect(screen.getByRole("dialog", { name: "Reject this case?" })).toBeInTheDocument();
    expect(client.getEscalationCaseDetail).toHaveBeenCalledTimes(1);
    expect(screen.queryByText(/This case changed/)).not.toBeInTheDocument();
    expect(screen.queryByText(/decision recorded/i)).not.toBeInTheDocument();
    expect(screen.getByRole("group", { name: "Case status" })).not.toHaveFocus();
  });

  it("a stale compliance decision behaves the same way", async () => {
    const base = { queue: "COMPLIANCE_REVIEW", reviewer_role: "COMPLIANCE_RISK" } as const;
    vi.mocked(client.getEscalationCaseDetail)
      .mockResolvedValueOnce(detail({ ...base, version: 1 }))
      .mockResolvedValue(detail({ ...base, version: 2, status: "DECIDED" }));
    vi.mocked(client.postComplianceDecision).mockRejectedValue(staleVersion());
    renderAs("COMPLIANCE_RISK");

    fireEvent.click(await screen.findByRole("button", { name: "Clear" }));
    const dialog = await screen.findByRole("dialog", { name: "Record outcome: Clear?" });
    fireEvent.change(within(dialog).getByLabelText("Reason"), { target: { value: "ok" } });
    fireEvent.click(within(dialog).getByRole("button", { name: "Record decision" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("This case changed");
    await waitFor(() => expect(client.getEscalationCaseDetail).toHaveBeenCalledTimes(2));
    await waitFor(() =>
      expect(screen.queryByRole("dialog", { name: "Record outcome: Clear?" })).not.toBeInTheDocument(),
    );
    expect(client.postComplianceDecision).toHaveBeenCalledTimes(1);
  });
});

describe("EscalationCaseDetailScreen decision result: announcement and focus (E11-S6 F-03)", () => {
  it("announces the recorded decision and the new status, then focuses the case status (never <body>)", async () => {
    vi.mocked(client.getEscalationCaseDetail)
      .mockResolvedValueOnce(detail({ version: 1 }))
      .mockResolvedValue(detail({ version: 2, status: "DECIDED" }));
    vi.mocked(client.postReviewDecision).mockResolvedValue({} as never);
    renderAs("COLLECTIONS_OFFICER");

    await submitReject("Reviewed.");

    const announcement = await screen.findByText("Reject decision recorded. Case status: DECIDED.");
    // It sits in a polite status region, so assistive technology is told without being interrupted.
    expect(announcement.closest("[role='status']")).toHaveAttribute("aria-live", "polite");
    await waitFor(() => expect(screen.getByRole("group", { name: "Case status" })).toHaveFocus());
    expect(document.body).not.toHaveFocus();
    // The decision controls have gone with the new status; focus did not follow them.
    expect(screen.queryByRole("button", { name: "Reject" })).not.toBeInTheDocument();
  });

  it("the announcement describes the action and status only -- no ids, versions or debug detail", async () => {
    vi.mocked(client.getEscalationCaseDetail)
      .mockResolvedValueOnce(detail({ version: 7 }))
      .mockResolvedValue(detail({ version: 8, status: "DECIDED" }));
    vi.mocked(client.postReviewDecision).mockResolvedValue({} as never);
    renderAs("COLLECTIONS_OFFICER");

    await submitReject("Reviewed.");

    const text = (await screen.findByText(/decision recorded/i)).textContent ?? "";
    expect(text).toBe("Reject decision recorded. Case status: DECIDED.");
    expect(text).not.toMatch(/esc_|version|\b7\b|\b8\b|undefined|null|error/i);
  });

  it("waits for the reloaded case: nothing is announced or focused until the new status arrives", async () => {
    let releaseReload: (value: EscalationCaseDetail) => void = () => undefined;
    vi.mocked(client.getEscalationCaseDetail)
      .mockResolvedValueOnce(detail({ version: 1 }))
      .mockReturnValueOnce(new Promise((resolve) => (releaseReload = resolve)));
    vi.mocked(client.postReviewDecision).mockResolvedValue({} as never);
    renderAs("COLLECTIONS_OFFICER");

    await submitReject("Reviewed.");
    await waitFor(() => expect(client.getEscalationCaseDetail).toHaveBeenCalledTimes(2));
    expect(screen.queryByText(/decision recorded/i)).not.toBeInTheDocument();

    releaseReload(detail({ version: 2, status: "DECIDED" }));

    expect(await screen.findByText("Reject decision recorded. Case status: DECIDED.")).toBeInTheDocument();
    expect(screen.getByRole("group", { name: "Case status" })).toHaveFocus();
  });

  it("an Approve decision is announced the same way", async () => {
    vi.mocked(client.getEscalationCaseDetail)
      .mockResolvedValueOnce(detail({ version: 1, approve_permitted: true }))
      .mockResolvedValue(detail({ version: 2, status: "DECIDED" }));
    vi.mocked(client.postReviewDecision).mockResolvedValue({} as never);
    renderAs("COLLECTIONS_OFFICER");

    fireEvent.click(await screen.findByRole("button", { name: "Approve" }));
    const dialog = await screen.findByRole("dialog", { name: "Approve this case?" });
    fireEvent.click(within(dialog).getByRole("button", { name: "Approve" }));

    expect(await screen.findByText("Approve decision recorded. Case status: DECIDED.")).toBeInTheDocument();
    await waitFor(() => expect(screen.getByRole("group", { name: "Case status" })).toHaveFocus());
  });

  it("a compliance outcome is announced the same way", async () => {
    const base = { queue: "COMPLIANCE_REVIEW", reviewer_role: "COMPLIANCE_RISK" } as const;
    vi.mocked(client.getEscalationCaseDetail)
      .mockResolvedValueOnce(detail({ ...base, version: 1 }))
      .mockResolvedValue(detail({ ...base, version: 2, status: "DECIDED" }));
    vi.mocked(client.postComplianceDecision).mockResolvedValue({} as never);
    renderAs("COMPLIANCE_RISK");

    fireEvent.click(await screen.findByRole("button", { name: "Clear" }));
    const dialog = await screen.findByRole("dialog", { name: "Record outcome: Clear?" });
    fireEvent.change(within(dialog).getByLabelText("Reason"), { target: { value: "ok" } });
    fireEvent.click(within(dialog).getByRole("button", { name: "Record decision" }));

    expect(
      await screen.findByText("Compliance outcome recorded: Clear. Case status: DECIDED."),
    ).toBeInTheDocument();
    await waitFor(() => expect(screen.getByRole("group", { name: "Case status" })).toHaveFocus());
  });

  it("a stale-version conflict still shows the alert, still refetches, and never retries or announces success", async () => {
    vi.mocked(client.getEscalationCaseDetail)
      .mockResolvedValueOnce(detail({ version: 1 }))
      .mockResolvedValue(detail({ version: 2, status: "AWAITING_INFORMATION" }));
    vi.mocked(client.postReviewDecision).mockRejectedValue(staleVersion());
    renderAs("COLLECTIONS_OFFICER");

    await submitReject("Stale attempt.");

    expect(await screen.findByRole("alert")).toHaveTextContent("This case changed");
    await waitFor(() => expect(client.getEscalationCaseDetail).toHaveBeenCalledTimes(2));
    await screen.findByText("AWAITING INFORMATION");
    expect(client.postReviewDecision).toHaveBeenCalledTimes(1);
    expect(screen.queryByText(/decision recorded/i)).not.toBeInTheDocument();
    expect(screen.getByRole("group", { name: "Case status" })).not.toHaveFocus();
  });
});
