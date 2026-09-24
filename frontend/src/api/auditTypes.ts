/**
 * Wire types for `GET /api/audit` and `GET /api/audit/chains`, mirrored
 * from `backend/src/collectai/api/schemas/audit.py` (E9-S1/E9-S2).
 */
import type { PageInfo } from "./types";

export const AUDIT_STAGES = [
  "INPUT",
  "AI_INTERPRETATION",
  "PROPOSAL",
  "RULE_VALIDATION",
  "HUMAN_DECISION",
  "FINAL_STATE",
] as const;
export type AuditStage = (typeof AUDIT_STAGES)[number];

export type ActorKind = "CUSTOMER" | "STAFF" | "SYSTEM" | "AI";
export type ProviderMode = "MOCK" | "LIVE";

export interface ToolCallRecord {
  tool_name: string;
  tool_type: string;
  arguments: Record<string, unknown>;
  result_status: string;
  idempotency_key: string | null;
  duration_ms: number;
}

export interface LatencyInfo {
  provider_latency_ms: number | null;
  tool_call_duration_ms: number | null;
  interaction_duration_ms: number | null;
}

export interface TokenUsage {
  input_tokens: number;
  output_tokens: number;
  estimated_cost_usd: string | null;
}

export interface AuditEvent {
  audit_event_id: string;
  sequence: number;
  timestamp: string;
  correlation_id: string;
  stage: AuditStage;
  event_type: string;
  actor_kind: ActorKind;
  actor_persona: string | null;
  customer_id: string | null;
  account_id: string | null;
  capability: string | null;
  provider: string | null;
  provider_mode: ProviderMode | null;
  model_id: string | null;
  prompt_version: string | null;
  policy_version: string | null;
  input_ref: string | null;
  ai_output: Record<string, unknown> | null;
  tool_calls: ToolCallRecord[];
  rule_results: Record<string, unknown> | null;
  human_override: Record<string, unknown> | null;
  final_action: string | null;
  reason_code: string | null;
  resource_type: string | null;
  resource_id: string | null;
  latency: LatencyInfo | null;
  token_usage: TokenUsage | null;
}

export interface AuditPage {
  items: AuditEvent[];
  page: PageInfo;
}

export interface AuditChainSummary {
  correlation_id: string;
  account_id: string | null;
  started_at: string;
  last_event_at: string;
  event_count: number;
  stages_present: AuditStage[];
  final_action: string | null;
  policy_version: string | null;
  model_id: string | null;
  prompt_version: string | null;
}

export interface AuditChainPage {
  items: AuditChainSummary[];
  page: PageInfo;
}
