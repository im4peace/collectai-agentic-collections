import { useEffect, useState } from "react";

import { ApiError } from "../../api/errors";
import { getEvalRuns, getKpis } from "../../api/kpiClient";
import type { EvalRunSummary, KpiResponse } from "../../api/kpiTypes";

export type KpiQueryStatus = "loading" | "loaded" | "error";

export interface UseKpiQueryResult {
  status: KpiQueryStatus;
  data: KpiResponse | null;
  errorMessage: string | null;
  /** The stored eval runs behind the AI tiles. `null` while loading or if
   * that (supplementary) request failed -- the KPI tiles never depend on it. */
  evalRuns: EvalRunSummary[] | null;
  refetch: () => void;
}

/**
 * Fetches `GET /api/kpis` (the tiles) and `GET /api/kpis/eval-runs` (the
 * supplementary run table). Only ever mounted behind `RequireCapability
 * capability="kpi:read"`, so a forbidden persona never triggers either
 * request (E10-S4 AC5). The runs request is best-effort: its failure leaves
 * the KPI tiles fully usable.
 */
export function useKpiQuery(): UseKpiQueryResult {
  const [status, setStatus] = useState<KpiQueryStatus>("loading");
  const [data, setData] = useState<KpiResponse | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [evalRuns, setEvalRuns] = useState<EvalRunSummary[] | null>(null);
  const [refetchToken, setRefetchToken] = useState(0);

  useEffect(() => {
    let cancelled = false;
    setStatus("loading");
    setErrorMessage(null);
    getKpis()
      .then((response) => {
        if (cancelled) return;
        setData(response);
        setStatus("loaded");
      })
      .catch((caught: unknown) => {
        if (cancelled) return;
        setStatus("error");
        setErrorMessage(
          caught instanceof ApiError ? caught.body.message : "The KPI data could not be loaded.",
        );
      });
    getEvalRuns()
      .then((page) => {
        if (!cancelled) setEvalRuns(page.items);
      })
      .catch(() => {
        if (!cancelled) setEvalRuns(null);
      });
    return () => {
      cancelled = true;
    };
  }, [refetchToken]);

  return {
    status,
    data,
    errorMessage,
    evalRuns,
    refetch: () => setRefetchToken((token) => token + 1),
  };
}
