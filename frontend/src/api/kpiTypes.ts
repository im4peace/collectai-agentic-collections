/**
 * Wire shapes for `GET /api/kpis` and `GET /api/kpis/eval-runs` (E10-S3),
 * mirrored field-for-field from `backend/src/collectai/api/schemas/kpi.py`.
 * Every numeric KPI value is a decimal *string* on the wire (never a float),
 * and this file keeps it that way so no rounding happens before display.
 */

export type DataLabel = "ILLUSTRATIVE" | "MOCK" | "LIVE";
export type KpiUnit = "COUNT" | "CURRENCY" | "RATIO" | "MILLISECONDS" | "USD_ESTIMATE";
export type ClaimStatus = "NOT_APPLICABLE" | "OBSERVATION_ONLY" | "PASS" | "FAIL";
export type ProviderMode = "MOCK" | "LIVE";

export interface Kpi {
  kpi_id: string;
  name: string;
  definition: string;
  formula: string;
  data_label: DataLabel;
  owner_persona: string;
  unit: KpiUnit;
  value: string | null;
  numerator: string | null;
  denominator: string | null;
  sample_size: number | null;
  claim_status: ClaimStatus;
  target: string | null;
  source_note: string | null;
}

export interface AiQualityKpis {
  mock: Kpi[];
  live: Kpi[];
  live_run_available: boolean;
  note: string;
}

export interface KpiResponse {
  generated_at: string;
  policy_version: string | null;
  business: Kpi[];
  operational: Kpi[];
  ai_quality: AiQualityKpis;
}

export interface PageInfo {
  limit: number;
  offset: number;
  total: number;
}

export interface EvalRunSummary {
  eval_run_id: string;
  mode: ProviderMode;
  dataset_version: string;
  model_id: string | null;
  prompt_version: string;
  policy_version: string;
  run_at: string;
  case_count: number;
  intent_accuracy: string | null;
  estimated_cost_usd: string | null;
}

export interface EvalRunPage {
  items: EvalRunSummary[];
  page: PageInfo;
}
