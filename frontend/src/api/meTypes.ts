/**
 * Wire types for the customer self-service endpoints this app calls,
 * mirrored from `backend/src/collectai/api/schemas/me.py`. Only the shapes
 * the Chat screen needs (account auto-selection) -- not a full mirror of
 * every `/api/me/*` endpoint.
 */
import type { PageInfo } from "./types";

export type MeAccountType = "CARD" | "PERSONAL_LOAN";
export type MeCollectionStatus =
  | "NEW"
  | "IN_PROGRESS"
  | "PTP_PENDING"
  | "ARRANGEMENT_ACTIVE"
  | "ESCALATED"
  | "RESOLVED";

export interface CustomerAccountSummary {
  account_id: string;
  account_type: MeAccountType;
  product_name: string;
  currency: string;
  outstanding_balance: string;
  overdue_amount: string;
  collection_status: MeCollectionStatus;
}

export interface CustomerAccountPage {
  items: CustomerAccountSummary[];
  page: PageInfo;
}
