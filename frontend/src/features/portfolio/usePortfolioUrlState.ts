import { useSearchParams } from "react-router-dom";

import type { CollectionStatus, PriorityBand } from "../../api/types";

export type PortfolioSortBy = "overdue_amount" | "dpd" | "priority_score";
export type PortfolioSortDir = "asc" | "desc";

const VALID_SORT_BY: readonly PortfolioSortBy[] = ["overdue_amount", "dpd", "priority_score"];
export const DEFAULT_SORT_BY: PortfolioSortBy = "priority_score";
export const DEFAULT_SORT_DIR: PortfolioSortDir = "desc";

export interface PortfolioUrlState {
  dpdMin: string;
  dpdMax: string;
  priorityBands: PriorityBand[];
  statuses: CollectionStatus[];
  sortBy: PortfolioSortBy;
  sortDir: PortfolioSortDir;
}

function readSortBy(value: string | null): PortfolioSortBy {
  return (VALID_SORT_BY as readonly string[]).includes(value ?? "") ? (value as PortfolioSortBy) : DEFAULT_SORT_BY;
}

function readSortDir(value: string | null): PortfolioSortDir {
  return value === "asc" ? "asc" : DEFAULT_SORT_DIR;
}

export function parsePortfolioUrlState(searchParams: URLSearchParams): PortfolioUrlState {
  return {
    dpdMin: searchParams.get("dpd_min") ?? "",
    dpdMax: searchParams.get("dpd_max") ?? "",
    priorityBands: searchParams.getAll("priority_band") as PriorityBand[],
    statuses: searchParams.getAll("status") as CollectionStatus[],
    sortBy: readSortBy(searchParams.get("sort_by")),
    sortDir: readSortDir(searchParams.get("sort_dir")),
  };
}

export interface UsePortfolioUrlStateResult {
  state: PortfolioUrlState;
  setDpdMin: (value: string) => void;
  setDpdMax: (value: string) => void;
  setPriorityBands: (bands: PriorityBand[]) => void;
  setStatuses: (statuses: CollectionStatus[]) => void;
  /** Clicking a sortable column header (AC3): toggles asc/desc when `column`
   * is already the active sort, otherwise switches to `column` descending. */
  setSortColumn: (column: PortfolioSortBy) => void;
  clearFilters: () => void;
}

/**
 * The URL query string is the single source of truth for Portfolio's filter
 * and sort state (AC2, code-gen skill: "one clear source of truth") -- no
 * parallel `useState` that could drift from it. Every setter reads the
 * current `URLSearchParams`, mutates a copy, and writes it back with
 * `useSearchParams`'s own setter.
 */
export function usePortfolioUrlState(): UsePortfolioUrlStateResult {
  const [searchParams, setSearchParams] = useSearchParams();
  const state = parsePortfolioUrlState(searchParams);

  function updateParams(mutate: (params: URLSearchParams) => void): void {
    const next = new URLSearchParams(searchParams);
    mutate(next);
    setSearchParams(next, { replace: true });
  }

  function setOrDelete(params: URLSearchParams, key: string, value: string): void {
    if (value === "") {
      params.delete(key);
    } else {
      params.set(key, value);
    }
  }

  function setMulti(params: URLSearchParams, key: string, values: string[]): void {
    params.delete(key);
    for (const value of values) {
      params.append(key, value);
    }
  }

  return {
    state,
    setDpdMin: (value) => updateParams((params) => setOrDelete(params, "dpd_min", value)),
    setDpdMax: (value) => updateParams((params) => setOrDelete(params, "dpd_max", value)),
    setPriorityBands: (bands) => updateParams((params) => setMulti(params, "priority_band", bands)),
    setStatuses: (statuses) => updateParams((params) => setMulti(params, "status", statuses)),
    setSortColumn: (column) =>
      updateParams((params) => {
        const isAlreadyActive = readSortBy(params.get("sort_by")) === column;
        const currentDir = readSortDir(params.get("sort_dir"));
        params.set("sort_by", column);
        params.set("sort_dir", isAlreadyActive && currentDir === "desc" ? "asc" : "desc");
      }),
    clearFilters: () => setSearchParams(new URLSearchParams(), { replace: true }),
  };
}
