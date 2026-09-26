import { useCallback, useState } from "react";

import { ApiError } from "../../api/errors";
import { postDisputeResolve, postDisputeStartReview } from "../../api/disputesClient";
import type { Dispute, DisputeOutcome } from "../../api/customer360Types";

export interface UseDisputeResolutionResult {
  busy: boolean;
  errorMessage: string | null;
  /** A polite, screen-reader-announced confirmation of the last success. */
  notice: string | null;
  startReview: (dispute: Dispute) => Promise<boolean>;
  resolve: (dispute: Dispute, outcome: DisputeOutcome, reason: string) => Promise<boolean>;
}

const VERSION_CONFLICT_MESSAGE =
  "This dispute changed since you opened it. The case has been reloaded; review it and try again.";

function isVersionConflict(caught: unknown): boolean {
  return (
    caught instanceof ApiError &&
    caught.status === 409 &&
    caught.body.reason_code === "VERSION_CONFLICT"
  );
}

/**
 * Drives the existing dispute domain endpoints (E8-S4) from the case
 * screen. Every consequential submit sends the dispute's own `version` as
 * `expected_version` and a fresh `Idempotency-Key`; a stale version (409
 * VERSION_CONFLICT) is reported as a "changed, reloaded" message and the
 * parent reloads via `onChanged`, exactly like the reviewer-decision flow.
 * Returns whether the call succeeded. No client-side state transition is
 * ever assumed: the parent refetches and shows the server's own status.
 */
export function useDisputeResolution(onChanged: () => void): UseDisputeResolutionResult {
  const [busy, setBusy] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const run = useCallback(
    async (call: () => Promise<unknown>, successNotice: string): Promise<boolean> => {
      setBusy(true);
      setErrorMessage(null);
      setNotice(null);
      try {
        await call();
        setNotice(successNotice);
        onChanged();
        return true;
      } catch (caught) {
        if (isVersionConflict(caught)) {
          setErrorMessage(VERSION_CONFLICT_MESSAGE);
          onChanged();
        } else {
          setErrorMessage(
            caught instanceof ApiError ? caught.body.message : "Could not update this dispute.",
          );
        }
        return false;
      } finally {
        setBusy(false);
      }
    },
    [onChanged],
  );

  const startReview = useCallback(
    (dispute: Dispute) =>
      run(
        () =>
          postDisputeStartReview(
            dispute.dispute_id,
            { expected_version: dispute.version },
            crypto.randomUUID(),
          ),
        "Dispute review started.",
      ),
    [run],
  );

  const resolve = useCallback(
    (dispute: Dispute, outcome: DisputeOutcome, reason: string) =>
      run(
        () =>
          postDisputeResolve(
            dispute.dispute_id,
            { outcome, reason, expected_version: dispute.version },
            crypto.randomUUID(),
          ),
        "Dispute resolved.",
      ),
    [run],
  );

  return { busy, errorMessage, notice, startReview, resolve };
}
