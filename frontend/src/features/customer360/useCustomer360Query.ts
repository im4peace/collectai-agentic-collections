import { useEffect, useState } from "react";

import { getCustomer360 } from "../../api/customer360Client";
import { ApiError } from "../../api/errors";
import type { Customer360 } from "../../api/customer360Types";

export type Customer360QueryStatus = "loading" | "loaded" | "not-found" | "error";

export interface UseCustomer360QueryResult {
  status: Customer360QueryStatus;
  data: Customer360 | null;
  errorMessage: string | null;
  /** Re-fetches `GET .../360` (E4-S2 AC6's stale-data banner "refresh"
   * action). There is no dedicated refresh endpoint (confirmed against
   * `api/routers/customer360.py`, which is read-only and does not define
   * one) -- a fresh read of current server truth is what the AC asks for,
   * and this hook already exposes exactly that as `refetch`, mirroring
   * `usePortfolioQuery`'s own pattern. */
  refetch: () => void;
}

/**
 * Fetches `GET /api/customers/{account_id}/360` for the officer-facing
 * Customer 360 screen (E4-S2). `"not-found"` is a distinct branch from
 * `"error"` (a 404 for an unknown account id is an expected, navigable
 * outcome -- e.g. a stale link -- not a generic failure), following the
 * same "explicit error handling" split `usePortfolioQuery` uses for
 * `POLICY_UNAVAILABLE`.
 */
export function useCustomer360Query(accountId: string): UseCustomer360QueryResult {
  const [status, setStatus] = useState<Customer360QueryStatus>("loading");
  const [data, setData] = useState<Customer360 | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [refetchToken, setRefetchToken] = useState(0);

  useEffect(() => {
    let cancelled = false;
    setStatus("loading");
    getCustomer360(accountId)
      .then((customer360) => {
        if (cancelled) return;
        setData(customer360);
        setStatus("loaded");
      })
      .catch((caught: unknown) => {
        if (cancelled) return;
        if (caught instanceof ApiError && caught.status === 404) {
          setStatus("not-found");
          setErrorMessage(caught.body.message);
          return;
        }
        setStatus("error");
        setErrorMessage(
          caught instanceof ApiError ? caught.body.message : "Could not load this customer's record.",
        );
      });
    return () => {
      cancelled = true;
    };
  }, [accountId, refetchToken]);

  return { status, data, errorMessage, refetch: () => setRefetchToken((token) => token + 1) };
}
