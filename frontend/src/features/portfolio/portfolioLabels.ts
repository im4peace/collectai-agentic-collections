import type { AccountType, Bucket, CollectionStatus, PriorityBand } from "../../api/types";
import type { BadgeVariant } from "../../components/Badge";

/** `PortfolioItem` has no product name field, only `account_type` -- the
 * mockup's contract-gap note applies here too, so the column shows this
 * label map instead of the raw enum. */
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

/** "IN_PROGRESS" -> "IN PROGRESS": spaces instead of underscores, per the
 * mockup's status chip copy. */
export function formatStatusLabel(status: CollectionStatus): string {
  return status.replace(/_/g, " ");
}

export interface PriorityBandDisplay {
  label: string;
  variant: BadgeVariant;
  icon: string;
}

/** AC1: the priority band always shows a text label as well as color, never
 * color alone. */
export const PRIORITY_BAND_DISPLAY: Record<PriorityBand, PriorityBandDisplay> = {
  HIGH: { label: "HIGH priority", variant: "danger", icon: "▲" },
  MEDIUM: { label: "MEDIUM priority", variant: "warn", icon: "◆" },
  LOW: { label: "LOW priority", variant: "ok", icon: "▼" },
};
