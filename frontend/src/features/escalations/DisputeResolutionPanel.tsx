import type { FormEvent } from "react";
import { useId, useState } from "react";

import type { Dispute, DisputeOutcome } from "../../api/customer360Types";
import { Badge } from "../../components/Badge";
import { useDisputeResolution } from "./useDisputeResolution";

const OUTCOME_LABELS: Record<DisputeOutcome, string> = {
  UPHELD: "Upheld",
  REJECTED: "Rejected",
  WITHDRAWN: "Withdrawn",
};

const OUTCOMES = Object.keys(OUTCOME_LABELS) as DisputeOutcome[];

function humanize(value: string): string {
  const text = value.replace(/_/g, " ").toLowerCase();
  return text.charAt(0).toUpperCase() + text.slice(1);
}

export interface DisputeResolutionPanelProps {
  dispute: Dispute;
  /** Whether the session holds `dispute:resolve` (COLLECTIONS_OFFICER). The
   * API enforces it regardless; this only decides whether to show controls. */
  canResolve: boolean;
  /** Reload the case after a change (or a stale-version conflict). */
  onChanged: () => void;
}

/**
 * E11-S4 AC3: the reviewer's dispute-resolution panel on a DISPUTE_REVIEW
 * case. It drives the existing dispute endpoints only (start review, then
 * resolve) -- no parallel implementation. Resolve stays disabled until both
 * an outcome and a non-empty reason are supplied; the server re-validates
 * both (422) and enforces OPEN -> UNDER_REVIEW -> RESOLVED. A resolved
 * dispute is shown read-only.
 */
export function DisputeResolutionPanel({
  dispute,
  canResolve,
  onChanged,
}: DisputeResolutionPanelProps): JSX.Element {
  const { busy, errorMessage, notice, startReview, resolve } = useDisputeResolution(onChanged);
  const [outcome, setOutcome] = useState<DisputeOutcome | "">("");
  const [reason, setReason] = useState("");
  const outcomeId = useId();
  const reasonId = useId();

  const canSubmit = outcome !== "" && reason.trim().length > 0 && !busy;

  async function handleResolve(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    if (outcome === "" || reason.trim().length === 0) return;
    const ok = await resolve(dispute, outcome, reason.trim());
    if (ok) {
      setOutcome("");
      setReason("");
    }
  }

  return (
    <section className="panel" aria-labelledby="dispute-resolution-heading">
      <h2 id="dispute-resolution-heading">Dispute resolution</h2>
      <dl>
        <dt>Status</dt>
        <dd>
          <Badge
            text={humanize(dispute.status)}
            variant={dispute.status === "RESOLVED" ? "ok" : "warn"}
          />
        </dd>
        <dt>Category</dt>
        <dd>{humanize(dispute.category)}</dd>
        <dt>Customer&apos;s stated reason</dt>
        <dd>{dispute.customer_reason}</dd>
        {dispute.status === "RESOLVED" && (
          <>
            <dt>Outcome</dt>
            <dd>{dispute.outcome === null ? "-" : OUTCOME_LABELS[dispute.outcome]}</dd>
            <dt>Resolution reason</dt>
            <dd>{dispute.resolution_reason ?? "-"}</dd>
          </>
        )}
      </dl>

      {errorMessage !== null && (
        <div className="banner danger" role="alert">
          <div>{errorMessage}</div>
        </div>
      )}
      <p role="status" aria-live="polite">
        {notice}
      </p>

      {canResolve && dispute.status === "OPEN" && (
        <button
          type="button"
          className="btn"
          disabled={busy}
          onClick={() => void startReview(dispute)}
        >
          Start review
        </button>
      )}

      {canResolve && dispute.status === "UNDER_REVIEW" && (
        <form onSubmit={(event) => void handleResolve(event)} aria-label="Resolve dispute">
          <div className="row" style={{ alignItems: "flex-end" }}>
            <label className="f" htmlFor={outcomeId}>
              Outcome
              <select
                id={outcomeId}
                value={outcome}
                onChange={(event) => setOutcome(event.target.value as DisputeOutcome | "")}
              >
                <option value="">Select an outcome</option>
                {OUTCOMES.map((value) => (
                  <option key={value} value={value}>
                    {OUTCOME_LABELS[value]}
                  </option>
                ))}
              </select>
            </label>
          </div>
          <label className="f" htmlFor={reasonId}>
            Reason
            <textarea
              id={reasonId}
              rows={3}
              value={reason}
              onChange={(event) => setReason(event.target.value)}
              style={{ width: "100%" }}
            />
          </label>
          <p className="small muted">An outcome and a reason are both required to resolve.</p>
          <button type="submit" className="btn" disabled={!canSubmit}>
            Resolve dispute
          </button>
        </form>
      )}
    </section>
  );
}
