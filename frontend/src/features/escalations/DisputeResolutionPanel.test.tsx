import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { Dispute } from "../../api/customer360Types";
import * as client from "../../api/disputesClient";
import { ApiError } from "../../api/errors";
import { DisputeResolutionPanel } from "./DisputeResolutionPanel";

vi.mock("../../api/disputesClient", () => ({
  postDisputeStartReview: vi.fn(),
  postDisputeResolve: vi.fn(),
}));

function dispute(overrides: Partial<Dispute> = {}): Dispute {
  return {
    dispute_id: "dsp_1",
    account_id: "acc_000101",
    customer_id: "cus_000101",
    item_id: null,
    category: "NOT_MY_DEBT",
    customer_reason: "This is not my debt.",
    status: "UNDER_REVIEW",
    outcome: null,
    resolution_reason: null,
    conversation_id: "conv_1",
    escalation_case_id: "esc_1",
    created_at: "2026-10-01T09:00:00Z",
    resolved_at: null,
    version: 2,
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

const transition = (d: Dispute) => ({ dispute: d, replayed: false });

afterEach(() => {
  vi.clearAllMocks();
});

describe("DisputeResolutionPanel", () => {
  it("keeps Resolve disabled until both an outcome and a non-blank reason are supplied", async () => {
    const user = userEvent.setup();
    render(<DisputeResolutionPanel dispute={dispute()} canResolve onChanged={vi.fn()} />);
    const resolve = screen.getByRole("button", { name: "Resolve dispute" });

    expect(resolve).toBeDisabled();

    await user.selectOptions(screen.getByLabelText("Outcome"), "REJECTED");
    expect(resolve).toBeDisabled();

    await user.type(screen.getByLabelText("Reason"), "   ");
    expect(resolve).toBeDisabled();

    await user.type(screen.getByLabelText("Reason"), "Verified against the ledger.");
    expect(resolve).toBeEnabled();

    await user.selectOptions(screen.getByLabelText("Outcome"), "");
    expect(resolve).toBeDisabled();
  });

  it("sends the outcome, trimmed reason, the dispute's expected_version and a fresh Idempotency-Key, then reloads", async () => {
    const user = userEvent.setup();
    const onChanged = vi.fn();
    vi.mocked(client.postDisputeResolve).mockResolvedValue(
      transition(dispute({ status: "RESOLVED", outcome: "REJECTED" })),
    );
    render(<DisputeResolutionPanel dispute={dispute()} canResolve onChanged={onChanged} />);

    await user.selectOptions(screen.getByLabelText("Outcome"), "REJECTED");
    await user.type(screen.getByLabelText("Reason"), "  Verified against the ledger.  ");
    await user.click(screen.getByRole("button", { name: "Resolve dispute" }));

    await waitFor(() => expect(client.postDisputeResolve).toHaveBeenCalledTimes(1));
    const [disputeId, body, key] = vi.mocked(client.postDisputeResolve).mock.calls[0];
    expect(disputeId).toBe("dsp_1");
    expect(body).toEqual({
      outcome: "REJECTED",
      reason: "Verified against the ledger.",
      expected_version: 2,
    });
    expect(key).toMatch(/^[0-9a-f-]{36}$/);
    await waitFor(() => expect(onChanged).toHaveBeenCalledTimes(1));
    expect(await screen.findByText("Dispute resolved.")).toBeInTheDocument();
  });

  it("uses a different Idempotency-Key for each separate submit", async () => {
    const user = userEvent.setup();
    vi.mocked(client.postDisputeResolve).mockRejectedValue(
      apiError(422, "REASON_REQUIRED", "A reason is required."),
    );
    render(<DisputeResolutionPanel dispute={dispute()} canResolve onChanged={vi.fn()} />);

    await user.selectOptions(screen.getByLabelText("Outcome"), "UPHELD");
    await user.type(screen.getByLabelText("Reason"), "Because.");
    await user.click(screen.getByRole("button", { name: "Resolve dispute" }));
    await screen.findByRole("alert");
    await user.click(screen.getByRole("button", { name: "Resolve dispute" }));
    await waitFor(() => expect(client.postDisputeResolve).toHaveBeenCalledTimes(2));

    const keys = vi.mocked(client.postDisputeResolve).mock.calls.map((call) => call[2]);
    expect(keys[0]).not.toBe(keys[1]);
  });

  it("starts review from OPEN with the expected_version and a fresh key", async () => {
    const user = userEvent.setup();
    const onChanged = vi.fn();
    vi.mocked(client.postDisputeStartReview).mockResolvedValue(
      transition(dispute({ status: "UNDER_REVIEW", version: 2 })),
    );
    render(
      <DisputeResolutionPanel
        dispute={dispute({ status: "OPEN", version: 1 })}
        canResolve
        onChanged={onChanged}
      />,
    );

    expect(screen.queryByRole("button", { name: "Resolve dispute" })).toBeNull();
    await user.click(screen.getByRole("button", { name: "Start review" }));

    await waitFor(() => expect(client.postDisputeStartReview).toHaveBeenCalledTimes(1));
    const [disputeId, body, key] = vi.mocked(client.postDisputeStartReview).mock.calls[0];
    expect(disputeId).toBe("dsp_1");
    expect(body).toEqual({ expected_version: 1 });
    expect(key).toMatch(/^[0-9a-f-]{36}$/);
    await waitFor(() => expect(onChanged).toHaveBeenCalled());
  });

  it("on a stale-version 409 shows a changed message and reloads instead of pretending success", async () => {
    const user = userEvent.setup();
    const onChanged = vi.fn();
    vi.mocked(client.postDisputeResolve).mockRejectedValue(
      apiError(409, "VERSION_CONFLICT", "stale"),
    );
    render(<DisputeResolutionPanel dispute={dispute()} canResolve onChanged={onChanged} />);

    await user.selectOptions(screen.getByLabelText("Outcome"), "WITHDRAWN");
    await user.type(screen.getByLabelText("Reason"), "Customer withdrew.");
    await user.click(screen.getByRole("button", { name: "Resolve dispute" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(/changed since you opened it/i);
    expect(onChanged).toHaveBeenCalledTimes(1);
    expect(screen.queryByText("Dispute resolved.")).toBeNull();
  });

  it("shows the server's message for any other failure and does not reload", async () => {
    const user = userEvent.setup();
    const onChanged = vi.fn();
    vi.mocked(client.postDisputeResolve).mockRejectedValue(
      apiError(403, "FORBIDDEN", "You may not resolve this dispute."),
    );
    render(<DisputeResolutionPanel dispute={dispute()} canResolve onChanged={onChanged} />);

    await user.selectOptions(screen.getByLabelText("Outcome"), "UPHELD");
    await user.type(screen.getByLabelText("Reason"), "Because.");
    await user.click(screen.getByRole("button", { name: "Resolve dispute" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("You may not resolve this dispute.");
    expect(onChanged).not.toHaveBeenCalled();
  });

  it("renders a RESOLVED dispute read-only with its outcome and reason", () => {
    render(
      <DisputeResolutionPanel
        dispute={dispute({
          status: "RESOLVED",
          outcome: "UPHELD",
          resolution_reason: "Charge reversed.",
          version: 3,
        })}
        canResolve
        onChanged={vi.fn()}
      />,
    );

    expect(screen.getByText("Upheld")).toBeInTheDocument();
    expect(screen.getByText("Charge reversed.")).toBeInTheDocument();
    expect(screen.queryByRole("button")).toBeNull();
  });

  it("shows no action controls to a session without dispute:resolve", () => {
    render(<DisputeResolutionPanel dispute={dispute()} canResolve={false} onChanged={vi.fn()} />);

    expect(screen.getByText("This is not my debt.")).toBeInTheDocument();
    expect(screen.queryByRole("button")).toBeNull();
    expect(screen.queryByLabelText("Outcome")).toBeNull();
  });
});
