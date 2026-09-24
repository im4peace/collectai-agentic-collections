import type { BadgeVariant } from "../../components/Badge";
import type { CaseStatus, EscalationPriority, EscalationReason } from "../../api/escalationsTypes";

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
