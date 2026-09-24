import { render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import * as escalationsClient from "../../api/escalationsClient";
import { ApiError } from "../../api/errors";
import type { EscalationPage } from "../../api/escalationsTypes";
import { EscalationsScreen } from "./EscalationsScreen";

vi.mock("../../api/escalationsClient", () => ({ getEscalations: vi.fn() }));

const PAGE: EscalationPage = {
  items: [
    {
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
    },
    {
      case_id: "esc_000002",
      reason: "FINANCIAL_HARDSHIP",
      queue: "HARDSHIP_REVIEW",
      reviewer_role: "COLLECTIONS_OFFICER",
      priority: "NORMAL",
      status: "IN_REVIEW",
      source: "AI",
      created_at: "2026-09-22T09:00:00Z",
      age_hours: 50,
      aging_warning: true,
      customer_id: "cus_000202",
      customer_name: "Omar Farouk",
      account_id: "acc_000456",
      customer_360_path: "/customers/acc_000456",
      version: 1,
    },
  ],
  page: { limit: 100, offset: 0, total: 2 },
  policy_version: "policy-v1",
};

function renderScreen() {
  return render(
    <MemoryRouter initialEntries={["/escalations"]}>
      <EscalationsScreen />
    </MemoryRouter>,
  );
}

describe("EscalationsScreen", () => {
  afterEach(() => {
    vi.clearAllMocks();
  });

  it("shows reason, priority, age, status and a customer/account reference, with text labels as well as color (AC1)", async () => {
    vi.mocked(escalationsClient.getEscalations).mockResolvedValue(PAGE);
    renderScreen();

    expect(await screen.findByText("Priya Raman")).toBeInTheDocument();
    const row = screen.getByText("Priya Raman").closest("tr") as HTMLElement;
    expect(within(row).getByText("Customer asked for a human")).toBeInTheDocument();
    expect(within(row).getByText("URGENT")).toBeInTheDocument();
    expect(within(row).getByText("5h")).toBeInTheDocument();
    expect(within(row).getByText("OPEN")).toBeInTheDocument();
    expect(within(row).getByText("acc_000123")).toBeInTheDocument();
  });

  it("shows an AGING text label for a case past its aging-warning threshold", async () => {
    vi.mocked(escalationsClient.getEscalations).mockResolvedValue(PAGE);
    renderScreen();

    const row = (await screen.findByText("Omar Farouk")).closest("tr") as HTMLElement;
    expect(within(row).getByText("2d")).toBeInTheDocument();
    expect(within(row).getByText("AGING")).toBeInTheDocument();
    const urgentRow = screen.getByText("Priya Raman").closest("tr") as HTMLElement;
    expect(within(urgentRow).queryByText("AGING")).not.toBeInTheDocument();
  });

  it("links each row to its Customer 360, reachable by keyboard (AC2)", async () => {
    vi.mocked(escalationsClient.getEscalations).mockResolvedValue(PAGE);
    renderScreen();

    const link = await screen.findByRole("link", { name: /Priya Raman/ });
    expect(link).toHaveAttribute("href", "/customers/acc_000123");
  });

  it("shows a retry-able error banner when the list fails to load", async () => {
    vi.mocked(escalationsClient.getEscalations).mockRejectedValue(
      new ApiError(500, {
        code: "INTERNAL_ERROR",
        reason_code: null,
        message: "Something went wrong.",
        correlation_id: "c0ffee",
        details: [],
        alternatives: null,
        context: null,
      }),
    );
    renderScreen();

    expect(await screen.findByRole("alert")).toHaveTextContent(
      /escalation list could not be loaded/i,
    );
  });
});
