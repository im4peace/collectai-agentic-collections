import { useEffect, useState } from "react";

import { getEscalations } from "../../api/escalationsClient";
import type { EscalationPage, ReviewQueue } from "../../api/escalationsTypes";
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
 * (`OPEN`/`IN_REVIEW`/`AWAITING_INFORMATION`, the backend's own default).
 * `queues` (E7-S3 AC5): an officer's own filter selection; `undefined` or
 * empty means "every queue", matching the backend's own unrestricted
 * default for COLLECTIONS_OFFICER. Re-fetches whenever `queues` changes. */
export function useEscalationsQuery(queues?: ReviewQueue[]): UseEscalationsQueryResult {
  const [status, setStatus] = useState<EscalationsQueryStatus>("loading");
  const [data, setData] = useState<EscalationPage | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [refetchToken, setRefetchToken] = useState(0);
  const queueKey = (queues ?? []).slice().sort().join(",");

  useEffect(() => {
    let cancelled = false;
    setStatus("loading");
    getEscalations({ limit: 100, queue: queues && queues.length > 0 ? queues : undefined })
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
    // eslint-disable-next-line react-hooks/exhaustive-deps -- `queueKey` is the stable, comparable form of `queues`
  }, [refetchToken, queueKey]);

  return { status, data, errorMessage, refetch: () => setRefetchToken((token) => token + 1) };
}
