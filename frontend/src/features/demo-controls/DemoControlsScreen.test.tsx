import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import * as client from "../../api/demoControlsClient";
import type { DemoState, SimulatePaymentResult } from "../../api/demoControlsTypes";
import type { PromiseToPay } from "../../api/domainTypes";
import { ApiError } from "../../api/errors";
import { DemoControlsScreen } from "./DemoControlsScreen";

// Every write here goes through this mocked client: no test in this file can
// reach a real clock, database or payment. The browser (Playwright) tests are
// read-only by design.
vi.mock("../../api/demoControlsClient", () => ({
  getDemoState: vi.fn(),
  postClockAdvance: vi.fn(),
  postRunPtpLifecycle: vi.fn(),
  postSimulatePayment: vi.fn(),
  postReseed: vi.fn(),
}));

function demoState(overrides: Partial<DemoState> = {}): DemoState {
  return {
    llm_mode: "MOCK",
    clock: { mode: "SIMULATED", current_time: "2026-10-01T10:00:00Z" },
    demo_controls_enabled: true,
    policy_version: "policy-v1",
    ...overrides,
  };
}

function apiError(status: number, reasonCode: string | null, message: string): ApiError {
  return new ApiError(status, {
    code: "ERROR",
    reason_code: reasonCode,
    message,
    correlation_id: "c1",
  } as ConstructorParameters<typeof ApiError>[1]);
}

function ptp(overrides: Partial<PromiseToPay> = {}): PromiseToPay {
  return {
    ptp_id: "ptp_1",
    account_id: "acc_000123",
    promised_amount: "50.00",
    promised_date: "2026-10-15",
    status: "KEPT",
    cumulative_paid: "50.00",
    remaining_amount: "0.00",
    interaction_reference: null,
    source: "CUSTOMER_CHAT",
    created_by_persona: "CUSTOMER",
    created_at: "2026-10-01T09:00:00Z",
    updated_at: "2026-10-01T10:00:00Z",
    kept_at: "2026-10-01T10:00:00Z",
    broken_at: null,
    cancelled_at: null,
    cancel_reason: null,
    policy_version: "policy-v1",
    version: 2,
    ...overrides,
  };
}

function payment(overrides: Partial<SimulatePaymentResult> = {}): SimulatePaymentResult {
  return {
    payment_event: {
      payment_event_id: "pay_1",
      account_id: "acc_000123",
      amount: "50.00",
      outcome: "SUCCEEDED",
      source: "DEMO_CONTROL",
      simulated: true,
      simulated_label: "Simulated payment",
      occurred_at: "2026-10-01T10:00:00Z",
      balance_after: "4770.35",
      applied_to_ptp_id: "ptp_1",
    },
    ptp: ptp(),
    replayed: false,
    ...overrides,
  };
}

function writeMocks(): unknown[] {
  return [
    client.postClockAdvance,
    client.postRunPtpLifecycle,
    client.postSimulatePayment,
    client.postReseed,
  ].map((call) => vi.mocked(call));
}

function expectNoWrites(): void {
  for (const call of writeMocks()) {
    expect(call).not.toHaveBeenCalled();
  }
}

async function renderReady(state: DemoState = demoState()): Promise<void> {
  vi.mocked(client.getDemoState).mockResolvedValue(state);
  render(<DemoControlsScreen />);
  await screen.findByRole("heading", { name: "Advance clock" });
}

afterEach(() => {
  vi.resetAllMocks();
  document.title = "";
});

describe("DemoControlsScreen: state and flag (AC1)", () => {
  it("shows the AI mode as text, the simulated clock and the active policy", async () => {
    await renderReady();

    expect(screen.getByRole("heading", { level: 1, name: "Demo controls" })).toBeInTheDocument();
    expect(screen.getByText("MOCK")).toBeInTheDocument();
    expect(screen.getByText(/2026-10-01 14:00 GST/)).toBeInTheDocument();
    expect(screen.getByText("Simulated clock")).toBeInTheDocument();
    expect(screen.getByText("policy-v1")).toBeInTheDocument();
    expect(document.title).toBe("Demo Controls | CollectAI");
  });

  it("shows LIVE as text when the API is in LIVE mode", async () => {
    await renderReady(demoState({ llm_mode: "LIVE" }));

    expect(screen.getByText("LIVE")).toBeInTheDocument();
    expect(screen.queryByText("MOCK")).not.toBeInTheDocument();
  });

  it("has one h1 and one h2 per section", async () => {
    await renderReady();

    const h2s = screen.getAllByRole("heading", { level: 2 }).map((heading) => heading.textContent);
    expect(h2s).toEqual([
      "Demo state",
      "Advance clock",
      "Run PTP lifecycle",
      "Simulate a payment",
      "Reseed data",
    ]);
    expect(screen.getAllByRole("heading", { level: 1 })).toHaveLength(1);
  });

  it("renders no control at all when the flag is off (404), only an explanation", async () => {
    vi.mocked(client.getDemoState).mockRejectedValue(apiError(404, null, "Demo controls are not enabled."));
    render(<DemoControlsScreen />);

    expect(await screen.findByRole("heading", { name: "Demo controls are turned off" })).toBeInTheDocument();
    expect(screen.getByText(/DEMO_CONTROLS_ENABLED=true/)).toBeInTheDocument();
    expect(screen.queryAllByRole("button")).toHaveLength(0);
    expect(screen.queryAllByRole("textbox")).toHaveLength(0);
    expectNoWrites();
  });

  it("shows an alert with Retry for any other failure, and Retry reloads", async () => {
    const user = userEvent.setup();
    vi.mocked(client.getDemoState).mockRejectedValueOnce(apiError(500, null, "Something broke."));
    render(<DemoControlsScreen />);

    expect(await screen.findByRole("alert")).toHaveTextContent("Something broke.");
    vi.mocked(client.getDemoState).mockResolvedValue(demoState());
    await user.click(screen.getByRole("button", { name: "Retry" }));

    expect(await screen.findByRole("heading", { name: "Advance clock" })).toBeInTheDocument();
  });

  it("explains a network failure without leaking internals", async () => {
    vi.mocked(client.getDemoState).mockRejectedValue(new TypeError("Failed to fetch"));
    render(<DemoControlsScreen />);

    expect(await screen.findByRole("alert")).toHaveTextContent(/Check that the API is running/);
  });
});

describe("DemoControlsScreen: safety (nothing writes on its own)", () => {
  it("sends exactly one GET on open and no write", async () => {
    await renderReady();

    expect(client.getDemoState).toHaveBeenCalledTimes(1);
    expectNoWrites();
  });

  it("sends nothing while fields are edited or the reseed dialog is opened and cancelled", async () => {
    const user = userEvent.setup();
    await renderReady();

    await user.type(screen.getByLabelText("Account id"), "acc_000123");
    await user.type(screen.getByLabelText("Amount (AED)"), "50");
    await user.click(screen.getByRole("checkbox", { name: "Refresh data snapshots" }));
    await user.click(screen.getByRole("button", { name: "Reseed data..." }));
    await user.click(screen.getByRole("button", { name: "Cancel" }));

    expectNoWrites();
  });
});

describe("DemoControlsScreen: accessibility structure", () => {
  it("has persistent, empty live regions in every panel before anything happens", async () => {
    await renderReady();

    const statuses = screen.getAllByRole("status");
    const alerts = screen.getAllByRole("alert");
    expect(statuses).toHaveLength(4);
    expect(alerts).toHaveLength(4);
    for (const region of [...statuses, ...alerts]) {
      expect(region).toBeEmptyDOMElement();
    }
  });

  it("labels every control and ties helper text to it", async () => {
    await renderReady();

    expect(screen.getByLabelText("Days to advance (1 to 365)")).toHaveAccessibleDescription(
      /cannot be moved back/,
    );
    expect(screen.getByLabelText("Refresh data snapshots")).toBeChecked();
    expect(screen.getByLabelText("Account id")).toHaveAccessibleDescription(/no real money moves/);
    expect(screen.getByLabelText("Amount (AED)")).toBeInTheDocument();
    expect(screen.getByLabelText("Outcome")).toBeInTheDocument();
  });

  it("uses text for the simulated indication, not colour alone", async () => {
    await renderReady();

    expect(screen.getByText("Simulated")).toBeInTheDocument();
  });
});

describe("DemoControlsScreen: advance clock (AC2)", () => {
  it("defaults to 1 day with snapshots refreshed, and reports the new time", async () => {
    const user = userEvent.setup();
    await renderReady();
    vi.mocked(client.postClockAdvance).mockResolvedValue({
      clock: { mode: "SIMULATED", current_time: "2026-10-02T10:00:00Z" },
      snapshots_refreshed: 1000,
    });
    vi.mocked(client.getDemoState).mockResolvedValue(
      demoState({ clock: { mode: "SIMULATED", current_time: "2026-10-02T10:00:00Z" } }),
    );

    const button = screen.getByRole("button", { name: "Advance clock" });
    await user.click(button);

    expect(client.postClockAdvance).toHaveBeenCalledTimes(1);
    expect(client.postClockAdvance).toHaveBeenCalledWith({ days: 1, refresh_snapshots: true });
    expect(
      await screen.findByText(
        "Clock advanced by 1 day. Simulated time is now 2026-10-02 14:00 GST. Snapshots refreshed: 1000.",
      ),
    ).toBeInTheDocument();
    // The state panel re-reads, and focus stays where the user left it.
    expect(await screen.findByText("(2026-10-02T10:00:00Z)")).toBeInTheDocument();
    expect(client.getDemoState).toHaveBeenCalledTimes(2);
    expect(screen.getByRole("button", { name: "Advance clock" })).toHaveFocus();
  });

  it("sends refresh_snapshots false when the box is unticked and the chosen days", async () => {
    const user = userEvent.setup();
    await renderReady();
    vi.mocked(client.postClockAdvance).mockResolvedValue({
      clock: { mode: "SIMULATED", current_time: "2026-10-31T10:00:00Z" },
      snapshots_refreshed: 0,
    });

    const days = screen.getByLabelText("Days to advance (1 to 365)");
    await user.clear(days);
    await user.type(days, "30");
    await user.click(screen.getByRole("checkbox", { name: "Refresh data snapshots" }));
    await user.click(screen.getByRole("button", { name: "Advance clock" }));

    expect(client.postClockAdvance).toHaveBeenCalledWith({ days: 30, refresh_snapshots: false });
    expect(await screen.findByText(/Clock advanced by 30 days\./)).toBeInTheDocument();
  });

  it.each(["", "0", "366", "1.5", "-2"])(
    "refuses days %j without sending anything, focuses the field and says why",
    async (value) => {
      const user = userEvent.setup();
      await renderReady();
      const days = screen.getByLabelText("Days to advance (1 to 365)");
      await user.clear(days);
      if (value !== "") {
        await user.type(days, value);
      }

      await user.click(screen.getByRole("button", { name: "Advance clock" }));

      expect(client.postClockAdvance).not.toHaveBeenCalled();
      expect(days).toHaveFocus();
      expect(days).toHaveAttribute("aria-invalid", "true");
      expect(screen.getAllByRole("alert")[0]).toHaveTextContent(
        "Enter a whole number of days from 1 to 365.",
      );
    },
  );

  it("clears the validation error once the value is edited", async () => {
    const user = userEvent.setup();
    await renderReady();
    const days = screen.getByLabelText("Days to advance (1 to 365)");
    await user.clear(days);
    await user.click(screen.getByRole("button", { name: "Advance clock" }));
    expect(days).toHaveAttribute("aria-invalid", "true");

    await user.type(days, "2");

    expect(days).toHaveAttribute("aria-invalid", "false");
    expect(screen.getAllByRole("alert")[0]).toBeEmptyDOMElement();
  });

  it("says nothing was changed when the audit write fails (503)", async () => {
    const user = userEvent.setup();
    await renderReady();
    vi.mocked(client.postClockAdvance).mockRejectedValue(
      apiError(503, "AUDIT_UNAVAILABLE", "Audit write failed; transition rolled back"),
    );

    await user.click(screen.getByRole("button", { name: "Advance clock" }));

    expect(await screen.findByText(/so nothing was changed/)).toBeInTheDocument();
    expect(screen.queryByText(/Clock advanced by/)).not.toBeInTheDocument();
    expect(client.getDemoState).toHaveBeenCalledTimes(1);
  });

  it("does not send a second request for a double click while one is in flight", async () => {
    const user = userEvent.setup();
    await renderReady();
    let finish: (value: Awaited<ReturnType<typeof client.postClockAdvance>>) => void = () => undefined;
    vi.mocked(client.postClockAdvance).mockReturnValue(
      new Promise((resolve) => {
        finish = resolve;
      }),
    );

    const button = screen.getByRole("button", { name: "Advance clock" });
    await user.click(button);
    await user.click(screen.getByRole("button", { name: "Advancing..." }));

    expect(client.postClockAdvance).toHaveBeenCalledTimes(1);
    expect(screen.getByRole("button", { name: "Advancing..." })).toHaveAttribute("aria-disabled", "true");
    finish({ clock: { mode: "SIMULATED", current_time: "2026-10-02T10:00:00Z" }, snapshots_refreshed: 5 });
    expect(await screen.findByText(/Clock advanced by 1 day\./)).toBeInTheDocument();
  });
});

describe("DemoControlsScreen: PTP lifecycle (AC2)", () => {
  it("runs the job once per click and shows the counts", async () => {
    const user = userEvent.setup();
    await renderReady();
    vi.mocked(client.postRunPtpLifecycle).mockResolvedValue({
      evaluated: 3,
      kept: 1,
      broken: 2,
      unchanged: 0,
    });

    await user.click(screen.getByRole("button", { name: "Run PTP lifecycle now" }));

    expect(client.postRunPtpLifecycle).toHaveBeenCalledTimes(1);
    expect(await screen.findByText("Evaluated 3, kept 1, broken 2, unchanged 0.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Run PTP lifecycle now" })).toHaveFocus();
  });

  it("shows a server error in the alert region", async () => {
    const user = userEvent.setup();
    await renderReady();
    vi.mocked(client.postRunPtpLifecycle).mockRejectedValue(apiError(500, null, "The job failed."));

    await user.click(screen.getByRole("button", { name: "Run PTP lifecycle now" }));

    expect(await screen.findByText("The job failed.")).toBeInTheDocument();
  });
});

describe("DemoControlsScreen: simulated payment (AC3)", () => {
  async function fill(user: ReturnType<typeof userEvent.setup>, account: string, amount: string) {
    const accountInput = screen.getByLabelText("Account id");
    const amountInput = screen.getByLabelText("Amount (AED)");
    await user.clear(accountInput);
    await user.clear(amountInput);
    if (account !== "") await user.type(accountInput, account);
    if (amount !== "") await user.type(amountInput, amount);
  }

  it("sends the amount as a decimal string with a fresh Idempotency-Key and shows the simulated result", async () => {
    const user = userEvent.setup();
    await renderReady();
    vi.mocked(client.postSimulatePayment).mockResolvedValue(payment());

    await fill(user, "acc_000123", "50.00");
    await user.click(screen.getByRole("button", { name: "Record simulated payment" }));

    expect(client.postSimulatePayment).toHaveBeenCalledTimes(1);
    const [body, key] = vi.mocked(client.postSimulatePayment).mock.calls[0];
    expect(body).toEqual({ account_id: "acc_000123", amount: "50.00", outcome: "SUCCEEDED" });
    expect(typeof body.amount).toBe("string");
    expect(typeof key).toBe("string");
    expect(key.length).toBeGreaterThan(10);
    expect(await screen.findByText(/Succeeded payment of AED 50\.00 on acc_000123\./)).toBeInTheDocument();
    expect(screen.getByText(/Balance after: AED 4,770\.35\./)).toBeInTheDocument();
    expect(screen.getByText("Simulated payment")).toBeInTheDocument();
    expect(screen.getByText(/Promise-to-Pay ptp_1 is now KEPT\./)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Record simulated payment" })).toHaveFocus();
  });

  it("sends the chosen outcome and uses a new Idempotency-Key for each submit", async () => {
    const user = userEvent.setup();
    await renderReady();
    vi.mocked(client.postSimulatePayment).mockResolvedValue(payment({ ptp: null }));

    await fill(user, "acc_000123", "10");
    await user.selectOptions(screen.getByLabelText("Outcome"), "FAILED");
    await user.click(screen.getByRole("button", { name: "Record simulated payment" }));
    await screen.findByText(/payment of AED 50\.00/);
    await user.click(screen.getByRole("button", { name: "Record simulated payment" }));

    const calls = vi.mocked(client.postSimulatePayment).mock.calls;
    expect(calls).toHaveLength(2);
    expect(calls[0][0]).toEqual({ account_id: "acc_000123", amount: "10", outcome: "FAILED" });
    expect(calls[0][1]).not.toBe(calls[1][1]);
    expect(screen.queryByText(/Promise-to-Pay/)).not.toBeInTheDocument();
  });

  it.each([
    ["", "50", "account", "Enter an account id such as acc_000123."],
    ["cus_000123", "50", "account", "Enter an account id such as acc_000123."],
    ["acc_000123", "", "amount", "Enter an amount as a decimal number, for example 50.00."],
    ["acc_000123", "-5", "amount", "Amount cannot be negative."],
    ["acc_000123", "0", "amount", "Amount must be greater than 0.00."],
    ["acc_000123", "1.234", "amount", "Use at most 2 decimal places."],
  ])(
    "refuses account %j / amount %j without sending, and focuses the %s field",
    async (account, amount, field, message) => {
      const user = userEvent.setup();
      await renderReady();
      await fill(user, account, amount);

      await user.click(screen.getByRole("button", { name: "Record simulated payment" }));

      expect(client.postSimulatePayment).not.toHaveBeenCalled();
      const target = screen.getByLabelText(field === "account" ? "Account id" : "Amount (AED)");
      expect(target).toHaveFocus();
      expect(target).toHaveAttribute("aria-invalid", "true");
      expect(screen.getAllByRole("alert")[2]).toHaveTextContent(message);
    },
  );

  it("shows the server's business-rule reason", async () => {
    const user = userEvent.setup();
    await renderReady();
    vi.mocked(client.postSimulatePayment).mockRejectedValue(
      apiError(422, "OVER_BALANCE", "Amount is more than the outstanding balance."),
    );

    await fill(user, "acc_000123", "99999");
    await user.click(screen.getByRole("button", { name: "Record simulated payment" }));

    expect(
      await screen.findByText("Amount is more than the outstanding balance. (OVER_BALANCE)"),
    ).toBeInTheDocument();
  });

  it("shows an unknown-account error", async () => {
    const user = userEvent.setup();
    await renderReady();
    vi.mocked(client.postSimulatePayment).mockRejectedValue(apiError(404, null, "Account not found."));

    await fill(user, "acc_999999", "5");
    await user.click(screen.getByRole("button", { name: "Record simulated payment" }));

    expect(await screen.findByText("Account not found.")).toBeInTheDocument();
  });
});

describe("DemoControlsScreen: reseed (AC4)", () => {
  async function openDialog(user: ReturnType<typeof userEvent.setup>) {
    await user.click(screen.getByRole("button", { name: "Reseed data..." }));
    return screen.getByRole("dialog", { name: "Reseed the demo data?" });
  }

  it("keeps Confirm disabled until the acknowledgement is ticked, then reseeds once", async () => {
    const user = userEvent.setup();
    await renderReady();
    vi.mocked(client.postReseed).mockResolvedValue({
      customers: 1000,
      accounts: 1000,
      delinquency_records: 1000,
      delinquent_items: 1500,
      interactions: 400,
      promise_to_pays: 40,
    });

    const dialog = await openDialog(user);
    const confirm = within(dialog).getByRole("button", { name: "Reseed data" });
    expect(confirm).toBeDisabled();
    await user.click(confirm);
    expect(client.postReseed).not.toHaveBeenCalled();

    await user.click(within(dialog).getByLabelText("I understand this resets the seeded demo data."));
    expect(confirm).toBeEnabled();
    await user.click(confirm);

    expect(client.postReseed).toHaveBeenCalledTimes(1);
    expect(client.postReseed).toHaveBeenCalledWith({ confirm: true });
    expect(await screen.findByText(/Seed data restored: 1000 customers, 1000 accounts/)).toBeInTheDocument();
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Reseed data..." })).toHaveFocus();
    expect(client.getDemoState).toHaveBeenCalledTimes(2);
  });

  it("does nothing on Cancel and returns focus to the button that opened it", async () => {
    const user = userEvent.setup();
    await renderReady();

    const dialog = await openDialog(user);
    await user.click(within(dialog).getByRole("button", { name: "Cancel" }));

    expect(client.postReseed).not.toHaveBeenCalled();
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Reseed data..." })).toHaveFocus();
  });

  it("does nothing on Escape, and the acknowledgement is cleared for next time", async () => {
    const user = userEvent.setup();
    await renderReady();

    const first = await openDialog(user);
    await user.click(within(first).getByLabelText("I understand this resets the seeded demo data."));
    await user.keyboard("{Escape}");
    expect(client.postReseed).not.toHaveBeenCalled();

    const second = await openDialog(user);
    expect(within(second).getByLabelText("I understand this resets the seeded demo data.")).not.toBeChecked();
    expect(within(second).getByRole("button", { name: "Reseed data" })).toBeDisabled();
  });

  it("states what is and is not restored, and shows a failure", async () => {
    const user = userEvent.setup();
    await renderReady();
    vi.mocked(client.postReseed).mockRejectedValue(
      apiError(503, "AUDIT_UNAVAILABLE", "Audit write failed"),
    );

    expect(screen.getByText(/every audit record are not deleted/)).toBeInTheDocument();
    const dialog = await openDialog(user);
    await user.click(within(dialog).getByLabelText("I understand this resets the seeded demo data."));
    await user.click(within(dialog).getByRole("button", { name: "Reseed data" }));

    expect(await screen.findByText(/so nothing was changed/)).toBeInTheDocument();
  });
});
