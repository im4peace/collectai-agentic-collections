import { useCallback, useEffect, useState } from "react";

import { getEscalationCaseDetail } from "../../api/escalationsClient";
import type { EscalationCaseDetail } from "../../api/escalationsTypes";
import { ApiError } from "../../api/errors";

export type CaseDetailStatus = "loading" | "loaded" | "error" | "not_found";

export interface UseEscalationCaseDetailResult {
  status: CaseDetailStatus;
  data: EscalationCaseDetail | null;
  errorMessage: string | null;
  refetch: () => void;
}

/** Fetches `GET /api/escalations/{case_id}` (E7-S3 AC2). `refetch` is also
 * how AC4's stale-version-conflict recovery reloads the case after an
 * action attempt is rejected with a 409. */
export function useEscalationCaseDetail(caseId: string): UseEscalationCaseDetailResult {
  const [status, setStatus] = useState<CaseDetailStatus>("loading");
  const [data, setData] = useState<EscalationCaseDetail | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [refetchToken, setRefetchToken] = useState(0);

  useEffect(() => {
    let cancelled = false;
    setStatus("loading");
    getEscalationCaseDetail(caseId)
      .then((detail) => {
        if (cancelled) return;
        setData(detail);
        setStatus("loaded");
      })
      .catch((caught: unknown) => {
        if (cancelled) return;
        if (caught instanceof ApiError && caught.status === 404) {
          setStatus("not_found");
          return;
        }
        setStatus("error");
        setErrorMessage(
          caught instanceof ApiError ? caught.body.message : "Could not load this case.",
        );
      });
    return () => {
      cancelled = true;
    };
  }, [caseId, refetchToken]);

  return {
    status,
    data,
    errorMessage,
    refetch: useCallback(() => setRefetchToken((token) => token + 1), []),
  };
}
