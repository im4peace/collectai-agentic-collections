import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import * as client from "../../api/client";
import { ApiError } from "../../api/errors";
import type { PortfolioPage } from "../../api/types";
import { PORTFOLIO_FIXTURE_ITEMS } from "./portfolioFixtures";
import { PortfolioScreen } from "./PortfolioScreen";

vi.mock("../../api/client", () => ({ getPortfolio: vi.fn() }));

const PAGE: PortfolioPage = {
  items: PORTFOLIO_FIXTURE_ITEMS,
  page: { limit: 50, offset: 0, total: PORTFOLIO_FIXTURE_ITEMS.length },
  policy_version: "policy-v1",
};

function renderScreen() {
  return render(
    <MemoryRouter initialEntries={["/portfolio"]}>
      <PortfolioScreen />
    </MemoryRouter>,
  );
}

describe("PortfolioScreen", () => {
  afterEach(() => {
    vi.clearAllMocks();
  });

  it("renders customer, product type, AED balances and a text-plus-icon priority badge (AC1)", async () => {
    vi.mocked(client.getPortfolio).mockResolvedValue(PAGE);
    renderScreen();

    expect(await screen.findByText("Priya Raman")).toBeInTheDocument();
    const row = screen.getByText("Priya Raman").closest("tr") as HTMLElement;
    expect(within(row).getByText("Card")).toBeInTheDocument();
    expect(within(row).getByText("AED 4,820.35")).toBeInTheDocument();
    expect(within(row).getByText("AED 612.40")).toBeInTheDocument();
    expect(within(row).getByText("HIGH priority")).toBeInTheDocument();
  });

  it("links each row to Customer 360 by account id, reachable by keyboard (AC4)", async () => {
    vi.mocked(client.getPortfolio).mockResolvedValue(PAGE);
    renderScreen();

    const link = await screen.findByRole("link", { name: /Priya Raman/ });
    expect(link).toHaveAttribute("href", "/customers/acc_000123");
  });

  it("clicking the Overdue header sorts and sets aria-sort (AC3)", async () => {
    vi.mocked(client.getPortfolio).mockResolvedValue(PAGE);
    const user = userEvent.setup();
    renderScreen();
    await screen.findByText("Priya Raman");

    const header = screen.getByRole("columnheader", { name: /Overdue/ });
    expect(header).toHaveAttribute("aria-sort", "none");

    await user.click(screen.getByRole("button", { name: /Overdue/ }));

    await waitFor(() =>
      expect(client.getPortfolio).toHaveBeenLastCalledWith(
        expect.objectContaining({ sort_by: "overdue_amount", sort_dir: "desc" }),
      ),
    );
    expect(screen.getByRole("columnheader", { name: /Overdue/ })).toHaveAttribute(
      "aria-sort",
      "descending",
    );

    await user.click(screen.getByRole("button", { name: /Overdue/ }));
    await waitFor(() =>
      expect(client.getPortfolio).toHaveBeenLastCalledWith(
        expect.objectContaining({ sort_by: "overdue_amount", sort_dir: "asc" }),
      ),
    );
  });

  it("checking a priority band filter re-fetches with that band and clearing restores the full list (AC2)", async () => {
    vi.mocked(client.getPortfolio).mockResolvedValue(PAGE);
    const user = userEvent.setup();
    renderScreen();
    await screen.findByText("Priya Raman");

    await user.click(screen.getByRole("checkbox", { name: "HIGH priority" }));
    await waitFor(() =>
      expect(client.getPortfolio).toHaveBeenLastCalledWith(
        expect.objectContaining({ priority_band: ["HIGH"] }),
      ),
    );

    await user.click(screen.getByRole("button", { name: "Clear filters" }));
    await waitFor(() =>
      expect(client.getPortfolio).toHaveBeenLastCalledWith(
        expect.not.objectContaining({ priority_band: expect.anything() }),
      ),
    );
  });

  it("shows the fail-closed policy-unavailable banner distinctly from a generic error", async () => {
    vi.mocked(client.getPortfolio).mockRejectedValue(
      new ApiError(503, {
        code: "POLICY_UNAVAILABLE",
        reason_code: "POLICY_UNAVAILABLE",
        message: "No valid active PolicyRuleSet.",
        correlation_id: "c0ffee",
        details: [],
        alternatives: null,
        context: null,
      }),
    );
    renderScreen();

    expect(await screen.findByRole("alert")).toHaveTextContent(/no active policy is available/i);
  });
});
