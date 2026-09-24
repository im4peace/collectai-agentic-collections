import type { BadgeVariant } from "../../components/Badge";
import type {
  AccountType,
  Bucket,
  CollectionStatus,
  Freshness,
  ItemKind,
  ItemStatus,
  NbaAction,
  PayableOptionType,
  PriorityBand,
} from "../../api/customer360Types";
import type { PtpStatus } from "../../api/domainTypes";

/** `"DISPUTED_ITEM"` -> `"Disputed item"`: shared by reason codes, hardship
 * indicator types, dispute categories and every other SCREAMING_SNAKE_CASE
 * enum this screen displays as prose, so each one reads as a label instead
 * of a raw wire value. */
export function humanize(value: string): string {
  const lower = value.replace(/_/g, " ").toLowerCase();
  return lower.charAt(0).toUpperCase() + lower.slice(1);
}

export const ACCOUNT_TYPE_LABELS: Record<AccountType, string> = {
  CARD: "Card",
  PERSONAL_LOAN: "Personal loan",
};

export const BUCKET_LABELS: Record<Bucket, string> = {
  CURRENT: "Current",
  DPD_1_29: "1-29 DPD",
  DPD_30_59: "30-59 DPD",
  DPD_60_89: "60-89 DPD",
  DPD_90_PLUS: "90+ DPD",
};

export function formatStatusLabel(status: CollectionStatus): string {
  return status.replace(/_/g, " ");
}

export interface PriorityBandDisplay {
  label: string;
  variant: BadgeVariant;
  icon: string;
}

export const PRIORITY_BAND_DISPLAY: Record<PriorityBand, PriorityBandDisplay> = {
  HIGH: { label: "HIGH priority", variant: "danger", icon: "▲" },
  MEDIUM: { label: "MEDIUM priority", variant: "warn", icon: "◆" },
  LOW: { label: "LOW priority", variant: "ok", icon: "▼" },
};

export interface FreshnessDisplay {
  label: string;
  variant: BadgeVariant;
}

export const FRESHNESS_DISPLAY: Record<Freshness, FreshnessDisplay> = {
  FRESH: { label: "Fresh", variant: "ok" },
  STALE: { label: "Stale - refresh recommended", variant: "warn" },
  UNKNOWN: { label: "Freshness unknown", variant: "neutral" },
};

export const ITEM_KIND_LABELS: Record<ItemKind, string> = {
  INSTALLMENT: "Installment",
  STATEMENT_CYCLE: "Statement cycle",
  FEE_OR_CHARGE: "Fee or charge",
};

export const ITEM_STATUS_LABELS: Record<ItemStatus, string> = {
  OPEN: "Open",
  PAID: "Paid",
};

export const PAYABLE_OPTION_LABELS: Record<PayableOptionType, string> = {
  OVERDUE_AMOUNT: "Overdue amount",
  FULL_BALANCE: "Full balance",
};

export const NBA_ACTION_LABELS: Record<NbaAction, string> = {
  CONTACT_CUSTOMER: "Contact customer",
  REQUEST_PAYMENT: "Request payment",
  OFFER_ELIGIBLE_ARRANGEMENT: "Offer eligible arrangement",
  FOLLOW_UP_PTP: "Follow up promise-to-pay",
  REFER_TO_HARDSHIP_WORKFLOW: "Refer to hardship workflow",
  ESCALATE_TO_HUMAN_REVIEW: "Escalate to human review",
};

export interface PtpStatusDisplay {
  label: string;
  variant: BadgeVariant;
}

export const PTP_STATUS_DISPLAY: Record<PtpStatus, PtpStatusDisplay> = {
  PENDING: { label: "Pending", variant: "info" },
  KEPT: { label: "Kept", variant: "ok" },
  BROKEN: { label: "Broken", variant: "danger" },
  CANCELLED: { label: "Cancelled", variant: "neutral" },
};
