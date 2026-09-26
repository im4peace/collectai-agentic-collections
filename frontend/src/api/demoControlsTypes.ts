import type { PaymentEvent, PaymentOutcome, PromiseToPay } from "./domainTypes";

/**
 * Wire shapes for the dev and demo controls (E9-S3), mirrored from
 * `backend/src/collectai/api/schemas/demo_controls.py` (the implemented
 * schemas, which are what the API actually returns; api-contracts.md 3.14
 * is the design source). `PaymentEvent` and `PromiseToPay` are the shared
 * shapes in `domainTypes.ts`.
 */

export type LlmMode = "MOCK" | "LIVE";
export type ClockMode = "SIMULATED" | "SYSTEM";

export interface ClockInfo {
  mode: ClockMode;
  /** UTC ISO-8601 instant. */
  current_time: string;
}

/** `GET /api/demo-controls/state`. Only reachable when the API's
 * `DEMO_CONTROLS_ENABLED` flag is true; otherwise every demo-control route
 * answers 404. */
export interface DemoState {
  llm_mode: LlmMode;
  clock: ClockInfo;
  demo_controls_enabled: boolean;
  policy_version: string | null;
}

export interface ClockAdvanceRequest {
  /** Whole days, 1 to 365. */
  days: number;
  refresh_snapshots: boolean;
}

export interface ClockAdvanceResult {
  clock: ClockInfo;
  snapshots_refreshed: number;
}

export interface LifecycleRunResult {
  evaluated: number;
  kept: number;
  broken: number;
  unchanged: number;
}

export interface SimulatePaymentRequest {
  account_id: string;
  /** A decimal string, never a number (money is never a float). */
  amount: string;
  outcome: PaymentOutcome;
}

export interface SimulatePaymentResult {
  payment_event: PaymentEvent;
  ptp: PromiseToPay | null;
  replayed: boolean;
}

export interface ReseedRequest {
  confirm: boolean;
}

export interface ReseedResult {
  customers: number;
  accounts: number;
  delinquency_records: number;
  delinquent_items: number;
  interactions: number;
  promise_to_pays: number;
}
