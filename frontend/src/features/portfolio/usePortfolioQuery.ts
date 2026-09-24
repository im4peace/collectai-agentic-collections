import { useEffect, useState } from "react";

import { getPortfolio } from "../../api/client";
import { ApiError } from "../../api/errors";
import type { PortfolioPage } from "../../api/types";
import type { PortfolioUrlState } from "./usePortfolioUrlState";

export type PortfolioQueryStatus = "loading" | "loaded" | "policy-unavailable" | "error";

export interface UsePortfolioQueryResult {
  status: PortfolioQueryStatus;
  data: PortfolioPage | null;
  errorMessage: string | null;
  refetch: () => void;
}

function toQueryParams(state: PortfolioUrlState) {
  return {
    dpd_min: state.dpdMin === "" ? undefined : Number(state.dpdMin),
    dpd_max: state.dpdMax === "" ? undefined : Number(state.dpdMax),
    priority_band: state.priorityBands.length > 0 ? state.priorityBands : undefined,
    status: state.statuses.length > 0 ? state.statuses : undefined,
    sort_by: state.sortBy,
    sort_dir: state.sortDir,
  };
}

/**
 * Fetches `GET /api/portfolio` for the current filter/sort state, with two
 * distinct failure branches (code-gen skill: "explicit error handling"):
 * `"policy-unavailable"` for the fail-closed 503 `POLICY_UNAVAILABLE`
 * envelope (CLAUDE.md: deterministic services fail closed, this is not a
 * generic error), and `"error"` for anything else (network failure, a
 * different `ApiError`, or an unparseable response).
 */
export function usePortfolioQuery(state: PortfolioUrlState): UsePortfolioQueryResult {
  const [status, setStatus] = useState<PortfolioQueryStatus>("loading");
  const [data, setData] = useState<PortfolioPage | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [refetchToken, setRefetchToken] = useState(0);

  const { dpdMin, dpdMax, sortBy, sortDir } = state;
  const priorityBandsKey = state.priorityBands.join(",");
  const statusesKey = state.statuses.join(",");

  useEffect(() => {
    let cancelled = false;
    setStatus("loading");
    getPortfolio(toQueryParams(state))
      .then((page) => {
        if (cancelled) return;
        setData(page);
        setStatus("loaded");
      })
      .catch((caught: unknown) => {
        if (cancelled) return;
        if (caught instanceof ApiError && caught.body.code === "POLICY_UNAVAILABLE") {
          setStatus("policy-unavailable");
          setErrorMessage(caught.body.message);
          return;
        }
        setStatus("error");
        setErrorMessage(caught instanceof ApiError ? caught.body.message : "Could not load the portfolio.");
      });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- refetch on the primitive filter/sort values, not on a new `state` object identity.
  }, [dpdMin, dpdMax, priorityBandsKey, statusesKey, sortBy, sortDir, refetchToken]);

  return { status, data, errorMessage, refetch: () => setRefetchToken((token) => token + 1) };
}
