import { apiFetch } from "./client";
import type { EvalRunPage, KpiResponse } from "./kpiTypes";

/** `GET /api/kpis` (COLLECTIONS_MANAGER only, capability `kpi:read`).
 * Read-only: this module deliberately exports no write call. */
export function getKpis(): Promise<KpiResponse> {
  return apiFetch<KpiResponse>("/kpis");
}

/** `GET /api/kpis/eval-runs` (COLLECTIONS_MANAGER only): the stored
 * `EvalRun`s behind the AI KPIs, newest first. */
export function getEvalRuns(limit = 20): Promise<EvalRunPage> {
  return apiFetch<EvalRunPage>(`/kpis/eval-runs?limit=${limit}`);
}
