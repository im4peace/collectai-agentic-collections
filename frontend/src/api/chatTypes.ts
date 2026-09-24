/**
 * Wire types for `/api/chat/*` (E6-S1/E6-S2/E6-S3/E6-S5), mirrored from
 * `backend/src/collectai/api/schemas/chat.py`,
 * `backend/src/collectai/api/schemas/chat_proposals.py` and
 * `backend/src/collectai/api/schemas/_chat_message.py`.
 */
import type { EscalationCustomerView, PaymentEvent, PromiseToPay } from "./domainTypes";

export type { EscalationCustomerView };

export type MessageRole = "CUSTOMER" | "ASSISTANT" | "SYSTEM";
export type MessageContentSource = "CUSTOMER_INPUT" | "MODEL" | "TEMPLATE";
export type MessageLabel = "AI_DISCLOSURE" | "SIMULATED" | "HUMAN_HANDOFF" | "SAFE_FALLBACK";

export interface ChatMessage {
  message_id: string;
  conversation_id: string;
  role: MessageRole;
  content: string;
  content_source: MessageContentSource;
  labels: MessageLabel[];
  created_at: string;
}

export type ConversationStatus = "ACTIVE" | "HANDED_OFF" | "CLOSED";

export interface Conversation {
  conversation_id: string;
  account_id: string;
  status: ConversationStatus;
  created_at: string;
  last_message_at: string | null;
}

export type Intent =
  | "PAY_NOW"
  | "PROMISE_TO_PAY"
  | "PAYMENT_PLAN"
  | "FINANCIAL_HARDSHIP"
  | "DISPUTE"
  | "REQUEST_HUMAN"
  | "UNKNOWN";
export type SpecialRequest = "NONE" | "SETTLEMENT" | "POLICY_EXCEPTION";

export interface IntentSummary {
  label: Intent;
  confidence: number;
  vulnerability_detected: boolean;
  special_request: SpecialRequest;
}

export type ProposalKind = "PTP" | "PAYMENT" | "ARRANGEMENT" | "EXCEPTION_REQUEST";
export type ProposalStatus = "PENDING_CONFIRMATION" | "CONFIRMED" | "CANCELLED" | "EXPIRED" | "INVALIDATED";

export interface PtpTerms {
  kind: "PTP";
  promised_amount: string;
  promised_date: string;
}

export interface PaymentTerms {
  kind: "PAYMENT";
  payment_option: string;
  payment_amount: string;
  simulated: true;
  simulated_label: string;
}

/** `terms` is a per-kind variant JSON object on the wire (discriminated by
 * `terms.kind`); only `PtpTerms`/`PaymentTerms` are ever produced by the
 * stories this screen calls (chat_proposals.py's own docstring), but a
 * `Proposal.terms` field is typed loosely here to match the backend's own
 * `dict[str, Any]` rather than asserting a union the server does not
 * guarantee. Callers narrow with `proposal.kind` before reading fields. */
export type ProposalTerms = PtpTerms | PaymentTerms | Record<string, unknown>;

export interface Proposal {
  proposal_id: string;
  conversation_id: string | null;
  kind: ProposalKind;
  status: ProposalStatus;
  terms: ProposalTerms;
  terms_hash: string;
  summary: string;
  simulated: boolean;
  record_version: number;
  created_at: string;
  expires_at: string;
}

export interface ConversationDetail {
  conversation: Conversation;
  messages: ChatMessage[];
  pending_proposal: Proposal | null;
  handoff: EscalationCustomerView | null;
}

export interface ConversationCreateResult {
  conversation: Conversation;
  greeting: ChatMessage;
  talk_to_human_available: boolean;
}

export type SafeState =
  | "NONE"
  | "AI_UNAVAILABLE"
  | "HANDOFF_CREATED"
  | "HANDOFF_FAILED"
  | "POLICY_UNAVAILABLE"
  | "AUDIT_UNAVAILABLE"
  | "TOOL_CAP_REACHED"
  | "STALE_DATA_REFRESHED";

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

export interface ChatTurnResponse {
  conversation_id: string;
  turn_id: string;
  customer_message: ChatMessage;
  assistant_message: ChatMessage;
  intent: IntentSummary | null;
  proposal: Proposal | null;
  handoff: EscalationCustomerView | null;
  safe_state: SafeState;
  talk_to_human_available: boolean;
  correlation_id: string;
  escalation_reported: boolean;
  escalation_reason: EscalationReason | null;
}

export interface ConfirmOutcome {
  kind: ProposalKind;
  ptp: PromiseToPay | null;
  payment_event: PaymentEvent | null;
  arrangement: unknown | null;
  escalation: EscalationCustomerView | null;
}

export interface ConfirmResult {
  proposal: Proposal | null;
  outcome: ConfirmOutcome;
  assistant_message: ChatMessage;
  replayed: boolean;
}

export interface CancelProposalResult {
  proposal: Proposal;
  assistant_message: ChatMessage;
}

export interface HandoffResult {
  escalation: EscalationCustomerView;
  assistant_message: ChatMessage;
  replayed: boolean;
}
