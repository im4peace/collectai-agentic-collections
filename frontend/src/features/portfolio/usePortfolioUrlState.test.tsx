import { renderHook, act } from "@testing-library/react";
import type { ReactNode } from "react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";

import { parsePortfolioUrlState, usePortfolioUrlState } from "./usePortfolioUrlState";

function wrapper(initialEntry: string) {
  return function Wrapper({ children }: { children: ReactNode }) {
    return <MemoryRouter initialEntries={[initialEntry]}>{children}</MemoryRouter>;
  };
}

describe("parsePortfolioUrlState", () => {
  it("defaults to an empty filter and the API's default sort when the URL carries no query", () => {
    const state = parsePortfolioUrlState(new URLSearchParams(""));
    expect(state).toEqual({
      dpdMin: "",
      dpdMax: "",
      priorityBands: [],
      statuses: [],
      sortBy: "priority_score",
      sortDir: "desc",
    });
  });

  it("reads repeated priority_band/status params as arrays", () => {
    const state = parsePortfolioUrlState(new URLSearchParams("priority_band=HIGH&priority_band=LOW&status=NEW"));
    expect(state.priorityBands).toEqual(["HIGH", "LOW"]);
    expect(state.statuses).toEqual(["NEW"]);
  });

  it("falls back to the default sort_by for an unrecognized value rather than trusting the URL blindly", () => {
    expect(parsePortfolioUrlState(new URLSearchParams("sort_by=not_a_real_column")).sortBy).toBe("priority_score");
  });
});

describe("usePortfolioUrlState", () => {
  it("writes dpd_min into the URL and reads it back through state", () => {
    const { result } = renderHook(() => usePortfolioUrlState(), { wrapper: wrapper("/portfolio") });
    act(() => result.current.setDpdMin("30"));
    expect(result.current.state.dpdMin).toBe("30");
  });

  it("clears a filter field from the URL when set back to an empty string", () => {
    const { result } = renderHook(() => usePortfolioUrlState(), { wrapper: wrapper("/portfolio?dpd_min=30") });
    act(() => result.current.setDpdMin(""));
    expect(result.current.state.dpdMin).toBe("");
  });

  it("clicking an inactive sortable column switches to it, descending first (AC3)", () => {
    const { result } = renderHook(() => usePortfolioUrlState(), { wrapper: wrapper("/portfolio") });
    act(() => result.current.setSortColumn("overdue_amount"));
    expect(result.current.state.sortBy).toBe("overdue_amount");
    expect(result.current.state.sortDir).toBe("desc");
  });

  it("clicking the already-active sortable column toggles its direction (AC3)", () => {
    const { result } = renderHook(() => usePortfolioUrlState(), {
      wrapper: wrapper("/portfolio?sort_by=dpd&sort_dir=desc"),
    });
    act(() => result.current.setSortColumn("dpd"));
    expect(result.current.state.sortDir).toBe("asc");
    act(() => result.current.setSortColumn("dpd"));
    expect(result.current.state.sortDir).toBe("desc");
  });

  it("clearFilters resets both the visible filters and the URL to no query params (AC2)", () => {
    const { result } = renderHook(() => usePortfolioUrlState(), {
      wrapper: wrapper("/portfolio?dpd_min=10&priority_band=HIGH&sort_by=dpd&sort_dir=asc"),
    });
    act(() => result.current.clearFilters());
    expect(result.current.state).toEqual({
      dpdMin: "",
      dpdMax: "",
      priorityBands: [],
      statuses: [],
      sortBy: "priority_score",
      sortDir: "desc",
    });
  });

  it("setPriorityBands replaces the full set of selected bands", () => {
    const { result } = renderHook(() => usePortfolioUrlState(), {
      wrapper: wrapper("/portfolio?priority_band=HIGH"),
    });
    act(() => result.current.setPriorityBands(["MEDIUM", "LOW"]));
    expect(result.current.state.priorityBands).toEqual(["MEDIUM", "LOW"]);
  });
});
