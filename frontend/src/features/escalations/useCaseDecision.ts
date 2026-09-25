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
  ) => Promise<boolean>;
  submitComplianceDecision: (
    caseId: string,
    expectedVersion: number,
    outcome: ComplianceOutcome,
    reason: string,
  ) => Promise<boolean>;
}

function isVersionConflict(caught: unknown): boolean {
  return (
    caught instanceof ApiError &&
    caught.status === 409 &&
    caught.body.reason_code === "VERSION_CONFLICT"
  );
}

/** Submits a reviewer or compliance decision (E7-S2/E7-S5, surfaced by
 * E7-S3's action dialogs). Returns whether the submit succeeded, so the
 * caller can close its dialog only on success. */
export function useCaseDecision(): UseCaseDecisionResult {
  const [busy, setBusy] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [versionConflict, setVersionConflict] = useState(false);

  const clearError = useCallback(() => {
    setErrorMessage(null);
    setVersionConflict(false);
  }, []);

  const submitReviewDecision = useCallback(
    async (caseId: string, expectedVersion: number, input: ReviewDecisionInput): Promise<boolean> => {
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
        return true;
      } catch (caught) {
        if (isVersionConflict(caught)) {
          setVersionConflict(true);
        } else {
          setErrorMessage(
            caught instanceof ApiError ? caught.body.message : "Could not record that decision.",
          );
        }
        return false;
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
    ): Promise<boolean> => {
      setBusy(true);
      clearError();
      try {
        await postComplianceDecision(
          caseId,
          { outcome, reason, expected_version: expectedVersion },
          crypto.randomUUID(),
        );
        return true;
      } catch (caught) {
        if (isVersionConflict(caught)) {
          setVersionConflict(true);
        } else {
          setErrorMessage(
            caught instanceof ApiError ? caught.body.message : "Could not record that decision.",
          );
        }
        return false;
      } finally {
        setBusy(false);
      }
    },
    [clearError],
  );

  return { busy, errorMessage, versionConflict, clearError, submitReviewDecision, submitComplianceDecision };
}
