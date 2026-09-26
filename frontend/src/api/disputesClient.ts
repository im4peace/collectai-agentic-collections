import { apiFetch } from "./client";
import type {
  DisputeResolveRequest,
  DisputeStartReviewRequest,
  DisputeTransitionResult,
} from "./disputesTypes";

/** `POST /api/disputes/{dispute_id}/start-review` (COLLECTIONS_OFFICER only,
 * capability `dispute:resolve`): OPEN -> UNDER_REVIEW. Requires a
 * caller-supplied `idempotencyKey`, fresh per attempt (the same convention
 * as `escalationsClient.postReviewDecision`). */
export function postDisputeStartReview(
  disputeId: string,
  body: DisputeStartReviewRequest,
  idempotencyKey: string,
): Promise<DisputeTransitionResult> {
  return apiFetch<DisputeTransitionResult>(`/disputes/${disputeId}/start-review`, {
    method: "POST",
    body: JSON.stringify(body),
    headers: { "Idempotency-Key": idempotencyKey },
  });
}

/** `POST /api/disputes/{dispute_id}/resolve`: UNDER_REVIEW -> RESOLVED with
 * a mandatory outcome and reason (the API 422s without either). */
export function postDisputeResolve(
  disputeId: string,
  body: DisputeResolveRequest,
  idempotencyKey: string,
): Promise<DisputeTransitionResult> {
  return apiFetch<DisputeTransitionResult>(`/disputes/${disputeId}/resolve`, {
    method: "POST",
    body: JSON.stringify(body),
    headers: { "Idempotency-Key": idempotencyKey },
  });
}
