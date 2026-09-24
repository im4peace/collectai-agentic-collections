import { useEffect, useState } from "react";

import { ConfirmDialog } from "../../components/ConfirmDialog";
import { ApiError } from "../../api/errors";
import type { PromiseToPay } from "../../api/domainTypes";
import { createPtp, validatePtp } from "../../api/ptpClient";
import type { PtpValidationResult } from "../../api/ptpTypes";
import { humanize } from "./customer360Labels";

export interface RecordPtpDialogProps {
  isOpen: boolean;
  onClose: () => void;
  accountId: string;
  recordVersion: number;
  /** The Customer 360 snapshot's `as_of` currently on screen. `POST
   * /api/ptps` rejects a submission built from a stale snapshot, so this
   * always comes from the last `GET .../360` response, never hand-typed. */
  snapshotAsOf: string | null;
  onRecorded: (ptp: PromiseToPay) => void;
}

function describeValidation(result: PtpValidationResult): string {
  return result.reason_codes.map(humanize).join(", ");
}

/** Officer manual PTP form (E4-S2 AC8, E6-S6's `POST /api/ptps`). Has zero
 * AI dependency, so it stays usable even when `deterministic.status` or
 * `ai.status` report unavailable (AC6). Live validation
 * (`POST /api/ptps/validate`, dry-run only) runs as the officer fills in
 * amount and date; the actual submit is a separate `POST /api/ptps` call
 * with a fresh idempotency key. */
export function RecordPtpDialog({
  isOpen,
  onClose,
  accountId,
  recordVersion,
  snapshotAsOf,
  onRecorded,
}: RecordPtpDialogProps): JSX.Element {
  const [amount, setAmount] = useState("");
  const [date, setDate] = useState("");
  const [interactionReference, setInteractionReference] = useState("");
  const [liveValidation, setLiveValidation] = useState<PtpValidationResult | null>(null);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (amount.trim() === "" || date.trim() === "") {
      setLiveValidation(null);
      return undefined;
    }
    const timer = window.setTimeout(() => {
      validatePtp({ account_id: accountId, promised_amount: amount, promised_date: date })
        .then(setLiveValidation)
        .catch(() => setLiveValidation(null));
    }, 400);
    return () => window.clearTimeout(timer);
  }, [accountId, amount, date]);

  function resetForm(): void {
    setAmount("");
    setDate("");
    setInteractionReference("");
    setLiveValidation(null);
    setSubmitError(null);
  }

  function handleClose(): void {
    resetForm();
    onClose();
  }

  async function handleSubmit(): Promise<void> {
    if (snapshotAsOf === null) {
      setSubmitError("This account has no snapshot time yet; reload the page before recording a PTP.");
      return;
    }
    setBusy(true);
    setSubmitError(null);
    try {
      const created = await createPtp(
        {
          account_id: accountId,
          promised_amount: amount,
          promised_date: date,
          interaction_reference: interactionReference.trim() === "" ? undefined : interactionReference.trim(),
          record_version: recordVersion,
          snapshot_as_of: snapshotAsOf,
        },
        crypto.randomUUID(),
      );
      onRecorded(created);
      resetForm();
      onClose();
    } catch (caught) {
      setSubmitError(caught instanceof ApiError ? caught.body.message : "Could not record the promise-to-pay.");
    } finally {
      setBusy(false);
    }
  }

  const canSubmit = amount.trim() !== "" && date.trim() !== "" && !busy;

  return (
    <ConfirmDialog
      isOpen={isOpen}
      title="Record Promise-to-Pay"
      onClose={handleClose}
      onConfirm={handleSubmit}
      confirmLabel="Record PTP"
      confirmDisabled={!canSubmit}
      busy={busy}
    >
      <div className="checks" style={{ flexDirection: "column", alignItems: "stretch", gap: 10 }}>
        <label className="f">
          Promised amount (AED)
          <input
            type="text"
            inputMode="decimal"
            value={amount}
            onChange={(event) => setAmount(event.target.value)}
          />
        </label>
        <label className="f">
          Promised date
          <input type="date" value={date} onChange={(event) => setDate(event.target.value)} />
        </label>
        <label className="f">
          Interaction reference (optional)
          <input
            type="text"
            value={interactionReference}
            onChange={(event) => setInteractionReference(event.target.value)}
          />
        </label>
        {liveValidation !== null && !liveValidation.valid && (
          <p className="small" role="status">
            This may not be accepted: {describeValidation(liveValidation)}.
          </p>
        )}
        {submitError !== null && (
          <div className="banner danger" role="alert">
            <div>{submitError}</div>
          </div>
        )}
      </div>
    </ConfirmDialog>
  );
}
