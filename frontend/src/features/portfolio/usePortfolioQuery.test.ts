import { renderHook, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import * as client from "../../api/client";
import { ApiError } from "../../api/errors";
import type { PortfolioPage } from "../../api/types";
import { PORTFOLIO_FIXTURE_ITEMS } from "./portfolioFixtures";
import type { PortfolioUrlState } from "./usePortfolioUrlState";
import { DEFAULT_SORT_BY, DEFAULT_SORT_DIR } from "./usePortfolioUrlState";
import { usePortfolioQuery } from "./usePortfolioQuery";

vi.mock("../../api/client", () => ({ getPortfolio: vi.fn() }));

const BASE_STATE: PortfolioUrlState = {
  dpdMin: "",
  dpdMax: "",
  priorityBands: [],
  statuses: [],
  sortBy: DEFAULT_SORT_BY,
  sortDir: DEFAULT_SORT_DIR,
};

const PAGE: PortfolioPage = {
  items: PORTFOLIO_FIXTURE_ITEMS,
  page: { limit: 50, offset: 0, total: PORTFOLIO_FIXTURE_ITEMS.length },
  policy_version: "policy-v1",
};

describe("usePortfolioQuery", () => {
  afterEach(() => {
    vi.clearAllMocks();
  });

  it("starts loading, then reports loaded with the fetched page", async () => {
    vi.mocked(client.getPortfolio).mockResolvedValue(PAGE);
    const { result } = renderHook(() => usePortfolioQuery({ ...BASE_STATE, priorityBands: [], statuses: [] }));
    expect(result.current.status).toBe("loading");
    await waitFor(() => expect(result.current.status).toBe("loaded"));
    expect(result.current.data).toEqual(PAGE);
  });

  it("distinguishes a fail-closed POLICY_UNAVAILABLE 503 from a generic error", async () => {
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
    const { result } = renderHook(() => usePortfolioQuery({ ...BASE_STATE }));
    await waitFor(() => expect(result.current.status).toBe("policy-unavailable"));
    expect(result.current.errorMessage).toBe("No valid active PolicyRuleSet.");
  });

  it("reports a generic error status for any other ApiError", async () => {
    vi.mocked(client.getPortfolio).mockRejectedValue(
      new ApiError(422, {
        code: "VALIDATION_FAILED",
        reason_code: "FIELD_INVALID",
        message: "dpd_max must be greater than or equal to dpd_min.",
        correlation_id: "c0ffee",
        details: [],
        alternatives: null,
        context: null,
      }),
    );
    const { result } = renderHook(() => usePortfolioQuery({ ...BASE_STATE }));
    await waitFor(() => expect(result.current.status).toBe("error"));
  });

  it("passes the filter/sort state through to getPortfolio as query params", async () => {
    vi.mocked(client.getPortfolio).mockResolvedValue(PAGE);
    renderHook(() =>
      usePortfolioQuery({
        dpdMin: "10",
        dpdMax: "60",
        priorityBands: ["HIGH", "MEDIUM"],
        statuses: ["ESCALATED"],
        sortBy: "dpd",
        sortDir: "asc",
      }),
    );
    await waitFor(() =>
      expect(client.getPortfolio).toHaveBeenCalledWith({
        dpd_min: 10,
        dpd_max: 60,
        priority_band: ["HIGH", "MEDIUM"],
        status: ["ESCALATED"],
        sort_by: "dpd",
        sort_dir: "asc",
      }),
    );
  });

  it("refetch triggers a new request", async () => {
    vi.mocked(client.getPortfolio).mockResolvedValue(PAGE);
    const { result } = renderHook(() => usePortfolioQuery({ ...BASE_STATE }));
    await waitFor(() => expect(result.current.status).toBe("loaded"));
    result.current.refetch();
    await waitFor(() => expect(client.getPortfolio).toHaveBeenCalledTimes(2));
  });
});
