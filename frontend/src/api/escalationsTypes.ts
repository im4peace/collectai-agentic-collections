/**
 * Wire types for `/api/escalations/*`, mirrored from
 * `backend/src/collectai/api/schemas/escalations.py` (E7-S1/E7-S6/E7-S2/
 * E7-S5/E7-S3).
 */
import type { ChatMessage } from "./chatTypes";
import type { Dispute, Recommendation } from "./customer360Types";
import type { PageInfo } from "./types";

export const ESCALATION_REASONS = [
  "REQUEST_HUMAN",
  "UNRESOLVED_UNKNOWN",
  "AI_FAILURE_FALLBACK",
  "EXCEPTIONAL_ARRANGEMENT",
  "FINANCIAL_HARDSHIP",
  "DISPUTE",
  "SETTLEMENT_REQUEST",
  "AMBIGUOUS_VALIDATION",
  "VULNERABLE_CUSTOMER",
  "POLICY_EXCEPTION",
  "HIGH_RISK_COMPLIANCE",
] as const;
export type EscalationReason = (typeof ESCALATION_REASONS)[number];

export const ESCALATION_PRIORITIES = ["NORMAL", "ELEVATED", "URGENT"] as const;
export type EscalationPriority = (typeof ESCALATION_PRIORITIES)[number];

export const CASE_STATUSES = [
  "OPEN",
  "IN_REVIEW",
  "AWAITING_INFORMATION",
  "DECIDED",
  "RE_ROUTED",
] as const;
export type CaseStatus = (typeof CASE_STATUSES)[number];

export type CaseSource = "AI" | "CUSTOMER" | "SYSTEM" | "REVIEWER";
export type ReviewerRole = "COLLECTIONS_OFFICER" | "COMPLIANCE_RISK";
export type ReviewQueue =
  | "COLLECTIONS_REVIEW"
  | "COLLECTIONS_EXCEPTION_REVIEW"
  | "HARDSHIP_REVIEW"
  | "DISPUTE_REVIEW"
  | "VULNERABLE_CUSTOMER_REVIEW"
  | "COMPLIANCE_REVIEW";

export interface EscalationListItem {
  case_id: string;
  reason: EscalationReason;
  queue: ReviewQueue;
  reviewer_role: ReviewerRole;
  priority: EscalationPriority;
  status: CaseStatus;
  source: CaseSource;
  created_at: string;
  age_hours: number;
  aging_warning: boolean;
  customer_id: string;
  customer_name: string;
  account_id: string;
  customer_360_path: string;
  version: number;
}

export interface EscalationPage {
  items: EscalationListItem[];
  page: PageInfo;
  policy_version: string | null;
}

export interface EscalationRuleResults {
  summary: string;
  requested_terms: Record<string, unknown> | null;
  exception_types: string[] | null;
  routing_flags: string[];
  routing_policy_version: string | null;
}

export interface EscalationCaseDetail extends EscalationListItem {
  conversation: ChatMessage[];
  ai_recommendation: Recommendation | null;
  rule_results: EscalationRuleResults;
  approve_permitted: boolean;
  /** E11-S4: the linked dispute for a DISPUTE_REVIEW case, COLLECTIONS_OFFICER
   * viewers only (absent or null otherwise). */
  dispute?: Dispute | null;
}

export const REVIEW_ACTIONS = [
  "APPROVE",
  "REJECT",
  "MODIFY",
  "REQUEST_MORE_INFORMATION",
  "ESCALATE",
] as const;
export type ReviewAction = (typeof REVIEW_ACTIONS)[number];

export interface ReviewDecisionRequest {
  action: ReviewAction;
  expected_version: number;
  reason?: string;
  note?: string;
  modification_option_id?: string;
  escalate_reason?: EscalationReason;
}

export interface ReviewDecisionResult {
  decision_id: string;
  case_id: string;
  action: ReviewAction;
  reason: string | null;
  note: string | null;
  modification_option_id: string | null;
  escalate_reason: EscalationReason | null;
  rerouted_case_id: string | null;
  reviewer_persona: string;
  decided_at: string;
  policy_version: string;
  case_status: CaseStatus;
  case_version: number;
  replayed: boolean;
}

export const COMPLIANCE_OUTCOMES = ["CLEARED", "NOT_CLEARED", "REMEDIATION_REQUIRED"] as const;
export type ComplianceOutcome = (typeof COMPLIANCE_OUTCOMES)[number];

export interface ComplianceDecisionRequest {
  outcome: ComplianceOutcome;
  reason: string;
  expected_version: number;
}

export interface ComplianceDecisionResult {
  decision_id: string;
  case_id: string;
  compliance_outcome: ComplianceOutcome;
  reason: string;
  reviewer_persona: string;
  decided_at: string;
  policy_version: string;
  case_status: CaseStatus;
  case_version: number;
  replayed: boolean;
}
