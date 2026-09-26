/**
 * Wire types for `POST /api/disputes/{id}/start-review|resolve` (E8-S4),
 * mirrored from `backend/src/collectai/api/schemas/disputes.py`.
 */
import type { Dispute, DisputeOutcome } from "./customer360Types";

export interface DisputeStartReviewRequest {
  expected_version: number;
}

export interface DisputeResolveRequest {
  outcome: DisputeOutcome;
  reason: string;
  expected_version: number;
}

export interface DisputeTransitionResult {
  dispute: Dispute;
  replayed: boolean;
}
