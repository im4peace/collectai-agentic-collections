/**
 * Wire types for the session endpoints, mirrored field-for-field from
 * `backend/src/collectai/api/schemas/session.py` and
 * `specs/design/api-contracts.md` sections 1.3 and 3.2. snake_case is kept
 * as-is (not re-cased) so the shapes stay a direct, driftable copy of what
 * the server sends.
 */

/** Exactly the four personas the switcher may offer (AC1). */
export const PERSONAS = [
  "CUSTOMER",
  "COLLECTIONS_OFFICER",
  "COLLECTIONS_MANAGER",
  "COMPLIANCE_RISK",
] as const;

export type Persona = (typeof PERSONAS)[number];

export interface PersonaOption {
  persona: Persona;
  display_name: string;
  description: string;
  requires_customer_binding: boolean;
}

export interface DemoCustomer {
  customer_id: string;
  display_name: string;
  account_count: number;
}

export interface SessionOptionsResponse {
  personas: PersonaOption[];
  demo_customers: DemoCustomer[];
}

export interface SessionCreateRequest {
  persona: Persona;
  customer_id?: string;
}

export interface SessionInfo {
  persona: Persona;
  customer_id: string | null;
  display_name: string;
  capabilities: string[];
  demo_label: string;
  session_token?: string | null;
  issued_at: string;
}

export interface ErrorDetail {
  field: string | null;
  reason_code: string;
  message: string;
}

export interface ErrorBody {
  code: string;
  reason_code: string | null;
  message: string;
  correlation_id: string;
  details: ErrorDetail[];
  alternatives: Record<string, unknown> | null;
  context: Record<string, unknown> | null;
  policy_version?: string | null;
}

export interface ErrorEnvelope {
  error: ErrorBody;
}

/**
 * Wire types for `GET /api/portfolio`, mirrored field-for-field from
 * `backend/src/collectai/api/schemas/portfolio.py` and
 * `backend/src/collectai/types/enums/account.py` (E3-S3). Enum member lists
 * are the full backend lists, not just the subset the design mockup's
 * static demo data happens to use.
 */
export const ACCOUNT_TYPES = ["CARD", "PERSONAL_LOAN"] as const;
export type AccountType = (typeof ACCOUNT_TYPES)[number];

export const BUCKETS = ["CURRENT", "DPD_1_29", "DPD_30_59", "DPD_60_89", "DPD_90_PLUS"] as const;
export type Bucket = (typeof BUCKETS)[number];

export const COLLECTION_STATUSES = [
  "NEW",
  "IN_PROGRESS",
  "PTP_PENDING",
  "ARRANGEMENT_ACTIVE",
  "ESCALATED",
  "RESOLVED",
] as const;
export type CollectionStatus = (typeof COLLECTION_STATUSES)[number];

export const PRIORITY_BANDS = ["HIGH", "MEDIUM", "LOW"] as const;
export type PriorityBand = (typeof PRIORITY_BANDS)[number];

export interface PortfolioItem {
  account_id: string;
  customer_id: string;
  customer_name: string;
  account_type: AccountType;
  outstanding_balance: string;
  overdue_amount: string;
  dpd: number;
  bucket: Bucket;
  collection_status: CollectionStatus;
  priority_band: PriorityBand;
  priority_score: string;
  human_treatment: boolean;
  automated_treatment_suppressed: boolean;
  record_version: number;
}

export interface PageInfo {
  limit: number;
  offset: number;
  total: number;
}

export interface PortfolioPage {
  items: PortfolioItem[];
  page: PageInfo;
  policy_version: string;
}
