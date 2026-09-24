/**
 * Wire types for `GET /api/escalations`, mirrored from
 * `backend/src/collectai/api/schemas/escalations.py` (E7-S1/E7-S6).
 */
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
