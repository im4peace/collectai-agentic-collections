/**
 * Wire shapes shared by more than one feature area (Customer 360, chat
 * confirm outcomes, `/api/me/*`), mirrored field-for-field from
 * `backend/src/collectai/api/schemas/me.py`. Kept in one place so
 * `customer360Types.ts` and `chatTypes.ts` both import the same
 * `PromiseToPay`/`PaymentEvent`/`EscalationCustomerView` shape rather than
 * declaring two field-for-field copies that could drift apart.
 */

export const PTP_STATUSES = ["PENDING", "KEPT", "BROKEN", "CANCELLED"] as const;
export type PtpStatus = (typeof PTP_STATUSES)[number];

export type PtpSource = "OFFICER_MANUAL" | "CUSTOMER_CHAT";

export type Persona = "CUSTOMER" | "COLLECTIONS_OFFICER" | "COLLECTIONS_MANAGER" | "COMPLIANCE_RISK";

export interface PromiseToPay {
  ptp_id: string;
  account_id: string;
  promised_amount: string;
  promised_date: string;
  status: PtpStatus;
  cumulative_paid: string;
  remaining_amount: string;
  interaction_reference: string | null;
  source: PtpSource;
  created_by_persona: Persona;
  created_at: string;
  updated_at: string;
  kept_at: string | null;
  broken_at: string | null;
  cancelled_at: string | null;
  cancel_reason: string | null;
  policy_version: string;
  version: number;
}

export type PaymentOutcome = "SUCCEEDED" | "FAILED";
export type PaymentEventSource = "CUSTOMER_CHAT" | "DEMO_CONTROL";

export interface PaymentEvent {
  payment_event_id: string;
  account_id: string;
  amount: string;
  outcome: PaymentOutcome;
  source: PaymentEventSource;
  simulated: boolean;
  simulated_label: string;
  occurred_at: string;
  balance_after: string;
  applied_to_ptp_id: string | null;
}

export type CaseStatus = "OPEN" | "IN_REVIEW" | "AWAITING_INFORMATION" | "DECIDED" | "RE_ROUTED";

export interface EscalationCustomerView {
  case_id: string;
  account_id: string;
  status: CaseStatus;
  customer_message: string;
  created_at: string;
  decided_at: string | null;
}
