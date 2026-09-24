/**
 * Wire types for `GET /api/customers/{account_id}/360`, mirrored
 * field-for-field from `backend/src/collectai/api/schemas/customer360.py`
 * (E4-S1/E4-S2). snake_case kept as-is, matching `api/types.ts`'s own
 * convention of staying a direct, driftable copy of the Pydantic schema.
 */
import type { CaseStatus, PaymentEvent, PromiseToPay } from "./domainTypes";

export type Freshness = "FRESH" | "STALE" | "UNKNOWN";

export interface SnapshotInfo {
  as_of: string | null;
  record_version: number;
  freshness: Freshness;
  freshness_reason_code: string | null;
  max_age_minutes: number;
}

export const VULNERABILITY_CATEGORIES = [
  "BEREAVEMENT",
  "SERIOUS_ILLNESS_OR_DISABILITY",
  "MENTAL_HEALTH_CONCERN",
  "DOMESTIC_ABUSE_OR_COERCION",
  "LIMITED_CAPACITY_TO_UNDERSTAND",
  "LANGUAGE_OR_COMMUNICATION_BARRIER",
  "OTHER",
] as const;
export type VulnerabilityCategory = (typeof VULNERABILITY_CATEGORIES)[number];

export interface ProfileBlock {
  customer_id: string;
  display_name: string;
  email: string;
  phone: string;
  vulnerability_flag: boolean;
  vulnerability_category: VulnerabilityCategory | null;
}

export type AccountType = "CARD" | "PERSONAL_LOAN";
export type Bucket = "CURRENT" | "DPD_1_29" | "DPD_30_59" | "DPD_60_89" | "DPD_90_PLUS";
export type CollectionStatus =
  | "NEW"
  | "IN_PROGRESS"
  | "PTP_PENDING"
  | "ARRANGEMENT_ACTIVE"
  | "ESCALATED"
  | "RESOLVED";

export interface AccountBlock {
  account_id: string;
  account_type: AccountType;
  product_name: string;
  currency: string;
  opened_on: string;
  outstanding_balance: string;
  overdue_amount: string;
  undisputed_overdue_amount: string;
  dpd: number;
  bucket: Bucket;
  collection_status: CollectionStatus;
  product_attributes: Record<string, unknown>;
}

export type ItemKind = "INSTALLMENT" | "STATEMENT_CYCLE" | "FEE_OR_CHARGE";
export type ItemStatus = "OPEN" | "PAID";

export interface DelinquentItem {
  item_id: string;
  kind: ItemKind;
  label: string;
  amount_outstanding: string;
  due_date: string;
  status: ItemStatus;
  disputed: boolean;
}

export type SuppressionSource = "ESCALATION" | "HARDSHIP" | "DISPUTE" | "VULNERABLE";
export type SuppressionScope = "ITEM" | "ACCOUNT";

export interface SuppressionEntry {
  source_type: SuppressionSource;
  source_id: string;
  scope: SuppressionScope;
  item_id: string | null;
}

export interface TreatmentBlock {
  human_treatment: boolean;
  automated_treatment_suppressed: boolean;
  suppressions: SuppressionEntry[];
}

export interface ContactPolicyResult {
  contact_allowed: boolean;
  reason_code: string | null;
  next_allowed_at: string | null;
  attempts_in_period: number;
}

export type PayableOptionType = "OVERDUE_AMOUNT" | "FULL_BALANCE";

export interface PayableOption {
  option: PayableOptionType;
  amount: string;
}

export interface RecordCheck {
  consistent: boolean;
  reason_code: string | null;
}

export type PriorityBand = "HIGH" | "MEDIUM" | "LOW";

export interface Factor {
  factor_id: string;
  attribute: string;
  value: string;
  normalized_value: string;
  weight: string;
  contribution: string;
}

export interface PriorityResult {
  score: string;
  band: PriorityBand;
  factors: Factor[];
  policy_version: string;
}

export interface DeterministicBlock {
  source: "deterministic";
  label: "Rules engine";
  policy_version: string | null;
  status: "OK" | "POLICY_UNAVAILABLE";
  priority: PriorityResult | null;
  treatment: TreatmentBlock;
  contact_policy: ContactPolicyResult | null;
  payable_options: PayableOption[];
  record_check: RecordCheck;
}

export type NbaAction =
  | "CONTACT_CUSTOMER"
  | "REQUEST_PAYMENT"
  | "OFFER_ELIGIBLE_ARRANGEMENT"
  | "FOLLOW_UP_PTP"
  | "REFER_TO_HARDSHIP_WORKFLOW"
  | "ESCALATE_TO_HUMAN_REVIEW";

export type RecommendationStatus =
  | "GENERATED"
  | "SAFE_FALLBACK"
  | "HUMAN_REVIEW_ONLY"
  | "AI_UNAVAILABLE"
  | "NOT_GENERATED";

export type RecommendationDecision = "ACCEPTED" | "OVERRIDDEN";
export type ContentSource = "MODEL" | "TEMPLATE";

export interface Recommendation {
  recommendation_id: string;
  account_id: string;
  source: "ai";
  action: NbaAction;
  rationale: string;
  referenced_factor_ids: string[];
  status: RecommendationStatus;
  content_source: ContentSource;
  model_id: string | null;
  prompt_version: string | null;
  policy_version: string;
  record_version: number;
  created_at: string;
  audit_event_id: string;
  officer_decision: RecommendationDecision | null;
}

export interface AiBlock {
  source: "ai";
  label: "AI-generated";
  status: RecommendationStatus;
  recommendation: Recommendation | null;
}

export type InteractionChannel =
  | "SIMULATED_CHAT"
  | "SIMULATED_OUTBOUND_CALL"
  | "SIMULATED_OUTBOUND_MESSAGE"
  | "SYSTEM_EVENT";
export type InteractionDirection = "INBOUND" | "OUTBOUND" | "INTERNAL";
export type ContactOutcome =
  | "NO_CONTACT"
  | "CONTACT_NO_COMMITMENT"
  | "PTP_MADE"
  | "PTP_BROKEN"
  | "PAYMENT_MADE";

export interface Interaction {
  interaction_id: string;
  channel: InteractionChannel;
  direction: InteractionDirection;
  outcome: ContactOutcome | null;
  occurred_at: string;
  summary: string;
  counts_as_attempt: boolean;
  conversation_id: string | null;
}

export type HardshipIndicatorType =
  | "JOB_LOSS"
  | "INCOME_REDUCTION"
  | "MEDICAL_OR_FAMILY_EMERGENCY"
  | "TEMPORARY_FINANCIAL_DIFFICULTY"
  | "OTHER";
export type HardshipStatus = "OPEN" | "UNDER_REVIEW" | "DECIDED";

export interface HardshipIndicator {
  indicator_type: HardshipIndicatorType;
  customer_statement: string;
}

export interface HardshipCase {
  hardship_case_id: string;
  account_id: string;
  customer_id: string;
  conversation_id: string | null;
  status: HardshipStatus;
  indicators: HardshipIndicator[];
  escalation_case_id: string | null;
  created_at: string;
  decided_at: string | null;
}

export type DisputeCategory =
  | "AMOUNT_INCORRECT"
  | "NOT_MY_DEBT"
  | "ALREADY_PAID"
  | "FRAUD_OR_UNAUTHORIZED"
  | "FEE_OR_INTEREST_DISPUTE"
  | "OTHER";
export type DisputeStatus = "OPEN" | "UNDER_REVIEW" | "RESOLVED";
export type DisputeOutcome = "UPHELD" | "REJECTED" | "WITHDRAWN";

export interface Dispute {
  dispute_id: string;
  account_id: string;
  customer_id: string;
  item_id: string | null;
  category: DisputeCategory;
  customer_reason: string;
  status: DisputeStatus;
  outcome: DisputeOutcome | null;
  resolution_reason: string | null;
  conversation_id: string | null;
  escalation_case_id: string | null;
  created_at: string;
  resolved_at: string | null;
  version: number;
}

export type EscalationReason =
  | "REQUEST_HUMAN"
  | "UNRESOLVED_UNKNOWN"
  | "AI_FAILURE_FALLBACK"
  | "EXCEPTIONAL_ARRANGEMENT"
  | "FINANCIAL_HARDSHIP"
  | "DISPUTE"
  | "SETTLEMENT_REQUEST"
  | "AMBIGUOUS_VALIDATION"
  | "VULNERABLE_CUSTOMER"
  | "POLICY_EXCEPTION"
  | "HIGH_RISK_COMPLIANCE";
export type EscalationPriority = "NORMAL" | "ELEVATED" | "URGENT";
export type ReviewQueue =
  | "COLLECTIONS_REVIEW"
  | "COLLECTIONS_EXCEPTION_REVIEW"
  | "HARDSHIP_REVIEW"
  | "DISPUTE_REVIEW"
  | "VULNERABLE_CUSTOMER_REVIEW"
  | "COMPLIANCE_REVIEW";

export interface EscalationSummary {
  case_id: string;
  reason: EscalationReason;
  status: CaseStatus;
  priority: EscalationPriority;
  queue: ReviewQueue;
  created_at: string;
}

export interface EscalationBlock {
  badge: string | null;
  has_open_case: boolean;
  cases: EscalationSummary[];
}

export interface Customer360 {
  account_id: string;
  generated_at: string;
  snapshot: SnapshotInfo;
  profile: ProfileBlock;
  account: AccountBlock;
  items: DelinquentItem[];
  deterministic: DeterministicBlock;
  ai: AiBlock;
  interactions: Interaction[];
  ptp_history: PromiseToPay[];
  payment_events: PaymentEvent[];
  arrangements: unknown[];
  hardship_cases: HardshipCase[];
  disputes: Dispute[];
  escalation: EscalationBlock;
}
