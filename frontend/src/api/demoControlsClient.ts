import { apiFetch } from "./client";
import type {
  ClockAdvanceRequest,
  ClockAdvanceResult,
  DemoState,
  LifecycleRunResult,
  ReseedRequest,
  ReseedResult,
  SimulatePaymentRequest,
  SimulatePaymentResult,
} from "./demoControlsTypes";

/**
 * The five dev and demo control endpoints (E9-S3; api-contracts.md 3.14).
 * All are COLLECTIONS_OFFICER only (capability `demo_controls:use`) and all
 * answer 404 when the API's `DEMO_CONTROLS_ENABLED` flag is off, so a 404
 * from any of them means "demo controls are disabled", not "not found".
 * Every POST here changes shared demo state (the simulated clock, payments,
 * seed data), so callers only ever issue one from an explicit user action.
 */

/** `GET /api/demo-controls/state`: AI mode, simulated clock, policy version. */
export function getDemoState(): Promise<DemoState> {
  return apiFetch<DemoState>("/demo-controls/state");
}

/** `POST /api/demo-controls/clock/advance`: moves the simulated clock forward
 * by `days` and, when `refresh_snapshots` is true, marks every delinquency
 * snapshot fresh as of the new time. */
export function postClockAdvance(body: ClockAdvanceRequest): Promise<ClockAdvanceResult> {
  return apiFetch<ClockAdvanceResult>("/demo-controls/clock/advance", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

/** `POST /api/demo-controls/ptp-lifecycle/run`: the PTP breakage job, now. */
export function postRunPtpLifecycle(): Promise<LifecycleRunResult> {
  return apiFetch<LifecycleRunResult>("/demo-controls/ptp-lifecycle/run", { method: "POST" });
}

/** `POST /api/demo-controls/payments/simulate`. Requires a caller-supplied
 * `Idempotency-Key`, fresh per submit (the same convention as the other
 * mutating clients). */
export function postSimulatePayment(
  body: SimulatePaymentRequest,
  idempotencyKey: string,
): Promise<SimulatePaymentResult> {
  return apiFetch<SimulatePaymentResult>("/demo-controls/payments/simulate", {
    method: "POST",
    body: JSON.stringify(body),
    headers: { "Idempotency-Key": idempotencyKey },
  });
}

/** `POST /api/demo-controls/reseed`: the API rejects it unless `confirm` is true. */
export function postReseed(body: ReseedRequest): Promise<ReseedResult> {
  return apiFetch<ReseedResult>("/demo-controls/reseed", {
    method: "POST",
    body: JSON.stringify(body),
  });
}
