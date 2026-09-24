import { useEffect, useState } from "react";

import { getEscalations } from "../../api/escalationsClient";
import type { EscalationPage } from "../../api/escalationsTypes";
import { ApiError } from "../../api/errors";

export type EscalationsQueryStatus = "loading" | "loaded" | "error";

export interface UseEscalationsQueryResult {
  status: EscalationsQueryStatus;
  data: EscalationPage | null;
  errorMessage: string | null;
  refetch: () => void;
}

/** Fetches `GET /api/escalations`, already sorted by priority then age by
 * the backend (AC1) -- this hook never re-sorts. Open cases only
 * (`OPEN`/`IN_REVIEW`/`AWAITING_INFORMATION`, the backend's own default),
 * matching this Slice-1 screen's "cases needing attention now" scope. */
export function useEscalationsQuery(): UseEscalationsQueryResult {
  const [status, setStatus] = useState<EscalationsQueryStatus>("loading");
  const [data, setData] = useState<EscalationPage | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [refetchToken, setRefetchToken] = useState(0);

  useEffect(() => {
    let cancelled = false;
    setStatus("loading");
    getEscalations({ limit: 100 })
      .then((page) => {
        if (cancelled) return;
        setData(page);
        setStatus("loaded");
      })
      .catch((caught: unknown) => {
        if (cancelled) return;
        setStatus("error");
        setErrorMessage(
          caught instanceof ApiError ? caught.body.message : "Could not load the escalation list.",
        );
      });
    return () => {
      cancelled = true;
    };
  }, [refetchToken]);

  return { status, data, errorMessage, refetch: () => setRefetchToken((token) => token + 1) };
}
