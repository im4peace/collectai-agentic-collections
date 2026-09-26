import { useCallback, useState } from "react";

import { postComplianceDecision, postReviewDecision } from "../../api/escalationsClient";
import type {
  ComplianceOutcome,
  EscalationReason,
  ReviewAction,
} from "../../api/escalationsTypes";
import { ApiError } from "../../api/errors";

export interface ReviewDecisionInput {
  action: ReviewAction;
  reason: string;
  escalateReason?: EscalationReason;
  modificationOptionId?: string;
}

/**
 * What one submit attempt came to, returned by the awaited call itself so the
 * caller reacts to *this* invocation's outcome -- never to hook state read from
 * its own render closure, which still holds the previous render's value right
 * after the `await` (the E7-S3 AC4 bug this type exists to prevent).
 *
 * - `success`: the decision was recorded.
 * - `version_conflict`: the API answered 409 VERSION_CONFLICT -- the case
 *   changed since it was loaded. Nothing was written and nothing is retried.
 * - `error`: any other failure (its message is in `errorMessage`).
 */
export type DecisionOutcome = "success" | "version_conflict" | "error";

export interface UseCaseDecisionResult {
  busy: boolean;
  errorMessage: string | null;
  /** AC4: a stale-version conflict (409 VERSION_CONFLICT) sets this instead
   * of `errorMessage`, so the screen can show the "this case changed"
   * message and reload rather than a generic error banner. */
  versionConflict: boolean;
  clearError: () => void;
  submitReviewDecision: (
    caseId: string,
    expectedVersion: number,
    input: ReviewDecisionInput,
  ) => Promise<DecisionOutcome>;
  submitComplianceDecision: (
    caseId: string,
    expectedVersion: number,
    outcome: ComplianceOutcome,
    reason: string,
  ) => Promise<DecisionOutcome>;
}

function isVersionConflict(caught: unknown): boolean {
  return (
    caught instanceof ApiError &&
    caught.status === 409 &&
    caught.body.reason_code === "VERSION_CONFLICT"
  );
}

/** Submits a reviewer or compliance decision (E7-S2/E7-S5, surfaced by
 * E7-S3's action dialogs). Each call sends the `expectedVersion` it is given
 * and a fresh `Idempotency-Key`, is never retried, and resolves to a
 * `DecisionOutcome` so the caller decides what to do next. */
export function useCaseDecision(): UseCaseDecisionResult {
  const [busy, setBusy] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [versionConflict, setVersionConflict] = useState(false);

  const clearError = useCallback(() => {
    setErrorMessage(null);
    setVersionConflict(false);
  }, []);

  const submitReviewDecision = useCallback(
    async (
      caseId: string,
      expectedVersion: number,
      input: ReviewDecisionInput,
    ): Promise<DecisionOutcome> => {
      setBusy(true);
      clearError();
      try {
        await postReviewDecision(
          caseId,
          {
            action: input.action,
            expected_version: expectedVersion,
            reason: input.reason,
            escalate_reason: input.escalateReason,
            modification_option_id: input.modificationOptionId,
          },
          crypto.randomUUID(),
        );
        return "success";
      } catch (caught) {
        if (isVersionConflict(caught)) {
          setVersionConflict(true);
          return "version_conflict";
        }
        setErrorMessage(
          caught instanceof ApiError ? caught.body.message : "Could not record that decision.",
        );
        return "error";
      } finally {
        setBusy(false);
      }
    },
    [clearError],
  );

  const submitComplianceDecision = useCallback(
    async (
      caseId: string,
      expectedVersion: number,
      outcome: ComplianceOutcome,
      reason: string,
    ): Promise<DecisionOutcome> => {
      setBusy(true);
      clearError();
      try {
        await postComplianceDecision(
          caseId,
          { outcome, reason, expected_version: expectedVersion },
          crypto.randomUUID(),
        );
        return "success";
      } catch (caught) {
        if (isVersionConflict(caught)) {
          setVersionConflict(true);
          return "version_conflict";
        }
        setErrorMessage(
          caught instanceof ApiError ? caught.body.message : "Could not record that decision.",
        );
        return "error";
      } finally {
        setBusy(false);
      }
    },
    [clearError],
  );

  return { busy, errorMessage, versionConflict, clearError, submitReviewDecision, submitComplianceDecision };
}
