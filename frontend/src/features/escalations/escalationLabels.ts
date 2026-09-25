import type { BadgeVariant } from "../../components/Badge";
import type {
  CaseStatus,
  EscalationPriority,
  EscalationReason,
  ReviewQueue,
} from "../../api/escalationsTypes";

export interface PriorityDisplay {
  label: string;
  variant: BadgeVariant;
  icon: string;
}

/** AC1: priority always shows a text label as well as color, never color
 * alone -- mirrors `portfolioLabels.PRIORITY_BAND_DISPLAY`'s own pattern. */
export const PRIORITY_DISPLAY: Record<EscalationPriority, PriorityDisplay> = {
  URGENT: { label: "URGENT", variant: "danger", icon: "▲" },
  ELEVATED: { label: "ELEVATED", variant: "warn", icon: "◆" },
  NORMAL: { label: "NORMAL", variant: "neutral", icon: "▼" },
};

export const STATUS_DISPLAY: Record<CaseStatus, { label: string; variant: BadgeVariant }> = {
  OPEN: { label: "OPEN", variant: "info" },
  IN_REVIEW: { label: "IN REVIEW", variant: "info" },
  AWAITING_INFORMATION: { label: "AWAITING INFORMATION", variant: "warn" },
  DECIDED: { label: "DECIDED", variant: "ok" },
  RE_ROUTED: { label: "RE-ROUTED", variant: "neutral" },
};

export const REASON_LABELS: Record<EscalationReason, string> = {
  REQUEST_HUMAN: "Customer asked for a human",
  UNRESOLVED_UNKNOWN: "Could not be resolved by chat",
  AI_FAILURE_FALLBACK: "AI assistant unavailable",
  EXCEPTIONAL_ARRANGEMENT: "Exceptional arrangement request",
  FINANCIAL_HARDSHIP: "Financial hardship",
  DISPUTE: "Dispute",
  SETTLEMENT_REQUEST: "Settlement request",
  AMBIGUOUS_VALIDATION: "Could not be automatically validated",
  VULNERABLE_CUSTOMER: "Vulnerable-customer signal",
  POLICY_EXCEPTION: "Policy exception request",
  HIGH_RISK_COMPLIANCE: "High-risk compliance flag",
};

/** E7-S3 AC5: the officer's queue filter needs a text label per queue (the
 * COMPLIANCE_RISK-only queue is included for completeness, though that
 * persona never sees the filter -- it is auto-scoped server-side). */
export const QUEUE_LABELS: Record<ReviewQueue, string> = {
  COLLECTIONS_REVIEW: "Collections review",
  COLLECTIONS_EXCEPTION_REVIEW: "Collections exception review",
  HARDSHIP_REVIEW: "Hardship review",
  DISPUTE_REVIEW: "Dispute review",
  VULNERABLE_CUSTOMER_REVIEW: "Vulnerable-customer review",
  COMPLIANCE_REVIEW: "Compliance review",
};

/** AC5: the officer-facing queue filter checkboxes -- exactly the five
 * queues an officer can be routed to (COMPLIANCE_REVIEW is COMPLIANCE_RISK-
 * only and never offered here). */
export const OFFICER_FILTERABLE_QUEUES: ReviewQueue[] = [
  "COLLECTIONS_REVIEW",
  "COLLECTIONS_EXCEPTION_REVIEW",
  "HARDSHIP_REVIEW",
  "DISPUTE_REVIEW",
  "VULNERABLE_CUSTOMER_REVIEW",
];

/** AC1's "age" column: whole hours under a day, otherwise whole days --
 * always a plain number-plus-unit label, matching `aging_warning`'s own
 * text-plus-color convention below. */
export function formatAge(ageHours: number): string {
  if (ageHours < 24) {
    return `${ageHours}h`;
  }
  const days = Math.floor(ageHours / 24);
  return `${days}d`;
}
