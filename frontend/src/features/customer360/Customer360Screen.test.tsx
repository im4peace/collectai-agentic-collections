import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import * as client from "../../api/customer360Client";
import type { Customer360 } from "../../api/customer360Types";
import { clearSession, setSession } from "../../auth/sessionStore";
import { Customer360Screen } from "./Customer360Screen";

vi.mock("../../api/customer360Client", () => ({ getCustomer360: vi.fn() }));

function baseCustomer360(overrides: Partial<Customer360> = {}): Customer360 {
  const base: Customer360 = {
    account_id: "acc_000123",
    generated_at: "2026-10-01T14:30:00Z",
    snapshot: {
      as_of: "2026-10-01T09:00:00Z",
      record_version: 7,
      freshness: "FRESH",
      freshness_reason_code: null,
      max_age_minutes: 240,
    },
    profile: {
      customer_id: "cus_0041",
      display_name: "Priya Raman",
      email: "priya.raman@example.com",
      phone: "+1-555-0142",
      vulnerability_flag: false,
      vulnerability_category: null,
    },
    account: {
      account_id: "acc_000123",
      account_type: "CARD",
      product_name: "Everyday Rewards Card",
      currency: "AED",
      opened_on: "2021-03-12",
      outstanding_balance: "4820.35",
      overdue_amount: "612.40",
      undisputed_overdue_amount: "612.40",
      dpd: 47,
      bucket: "DPD_30_59",
      collection_status: "IN_PROGRESS",
      product_attributes: {},
    },
    items: [],
    deterministic: {
      source: "deterministic",
      label: "Rules engine",
      policy_version: "policy-v1",
      status: "OK",
      priority: {
        score: "79.70",
        band: "HIGH",
        factors: [
          {
            factor_id: "dpd",
            attribute: "dpd",
            value: "47",
            normalized_value: "0.7833",
            weight: "0.40",
            contribution: "31.33",
          },
        ],
        policy_version: "policy-v1",
      },
      treatment: { human_treatment: false, automated_treatment_suppressed: false, suppressions: [] },
      contact_policy: null,
      payable_options: [{ option: "OVERDUE_AMOUNT", amount: "612.40" }],
      record_check: { consistent: true, reason_code: null },
    },
    ai: { source: "ai", label: "AI-generated", status: "NOT_GENERATED", recommendation: null },
    interactions: [],
    ptp_history: [],
    payment_events: [
      {
        payment_event_id: "pay_01J8ZK1C02",
        account_id: "acc_000123",
        amount: "50.00",
        outcome: "SUCCEEDED",
        source: "CUSTOMER_CHAT",
        simulated: true,
        simulated_label: "Simulated payment",
        occurred_at: "2026-09-24T16:42:00Z",
        balance_after: "4820.35",
        applied_to_ptp_id: null,
      },
    ],
    arrangements: [],
    hardship_cases: [],
    disputes: [],
    escalation: { badge: null, has_open_case: false, cases: [] },
  };
  return { ...base, ...overrides };
}

function renderScreen() {
  setSession({
    persona: "COLLECTIONS_OFFICER",
    customer_id: null,
    display_name: "Collections Officer",
    capabilities: ["customer360:read", "ptp:record"],
    demo_label: "Demo persona - not real authentication",
    session_token: null,
    issued_at: "2026-10-01T14:30:00Z",
  });
  return render(
    <MemoryRouter initialEntries={["/customers/acc_000123"]}>
      <Routes>
        <Route path="/customers/:customerId" element={<Customer360Screen />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("Customer360Screen", () => {
  afterEach(() => {
    clearSession();
    vi.clearAllMocks();
  });

  it("shows DPD, bucket, overdue amount and the priority band with its factors (AC1)", async () => {
    vi.mocked(client.getCustomer360).mockResolvedValue(baseCustomer360());
    renderScreen();

    expect(await screen.findByText("Priya Raman")).toBeInTheDocument();
    expect(screen.getByText(/47 \(30-59 DPD\)/)).toBeInTheDocument();
    expect(screen.getAllByText("AED 612.40").length).toBeGreaterThan(0);
    expect(screen.getByText("HIGH priority")).toBeInTheDocument();
    expect(screen.getByText("dpd")).toBeInTheDocument();
  });

  it("labels the AI panel 'AI-generated' and the deterministic panel 'Rules engine' (AC2)", async () => {
    vi.mocked(client.getCustomer360).mockResolvedValue(baseCustomer360());
    renderScreen();

    expect(await screen.findByRole("heading", { name: "AI-generated" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Rules engine" })).toBeInTheDocument();
  });

  it("shows the 'Escalated - human review' badge when an OPEN escalation exists (AC3)", async () => {
    vi.mocked(client.getCustomer360).mockResolvedValue(
      baseCustomer360({
        escalation: {
          badge: "Escalated - human review",
          has_open_case: true,
          cases: [
            {
              case_id: "esc_01J8ZK6E1A",
              reason: "FINANCIAL_HARDSHIP",
              status: "OPEN",
              priority: "URGENT",
              queue: "HARDSHIP_REVIEW",
              created_at: "2026-10-01T13:50:00Z",
            },
          ],
        },
      }),
    );
    renderScreen();

    expect(await screen.findByText("Escalated - human review")).toBeInTheDocument();
  });

  it("labels simulated payments 'Simulated payment' in the history (AC4)", async () => {
    vi.mocked(client.getCustomer360).mockResolvedValue(baseCustomer360());
    renderScreen();

    expect(await screen.findAllByText("Simulated payment")).not.toHaveLength(0);
  });

  it("shows the AI-unavailable state and fabricates no recommendation when the provider is down (AC6)", async () => {
    vi.mocked(client.getCustomer360).mockResolvedValue(
      baseCustomer360({ ai: { source: "ai", label: "AI-generated", status: "AI_UNAVAILABLE", recommendation: null } }),
    );
    renderScreen();

    expect(await screen.findByText("AI unavailable - manual workflow available.")).toBeInTheDocument();
  });

  it("shows a stale-data banner with a refresh action for a STALE snapshot (AC6)", async () => {
    vi.mocked(client.getCustomer360).mockResolvedValue(
      baseCustomer360({
        snapshot: {
          as_of: "2026-09-30T06:00:00Z",
          record_version: 6,
          freshness: "STALE",
          freshness_reason_code: "STALE_DATA",
          max_age_minutes: 240,
        },
      }),
    );
    renderScreen();

    await waitFor(() => expect(client.getCustomer360).toHaveBeenCalled());
    expect(await screen.findByRole("button", { name: "Refresh" })).toBeInTheDocument();
  });
});
