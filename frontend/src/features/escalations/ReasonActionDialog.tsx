import type { ReactNode } from "react";
import { useId, useState } from "react";

import { ConfirmDialog } from "../../components/ConfirmDialog";

export interface ReasonActionDialogProps {
  isOpen: boolean;
  title: string;
  confirmLabel: string;
  busy: boolean;
  onClose: () => void;
  /** Called with the entered reason once Confirm is clicked. */
  onConfirm: (reason: string) => void;
  /** Extra fields rendered below the reason field (e.g. ESCALATE's
   * escalate-reason picker) -- receives nothing, manages its own state via
   * the caller, kept generic so this dialog stays reusable for every
   * reason-gated action. */
  extraFields?: ReactNode;
}

/**
 * E7-S3 AC3, AC7: the shared shape behind every reviewer/compliance action
 * dialog (REJECT, MODIFY, ESCALATE, compliance CLEARED/NOT_CLEARED/
 * REMEDIATION_REQUIRED). The reason `<textarea>` is the dialog's first
 * child, so `ConfirmDialog`'s own "focus the first focusable element on
 * open" behaviour already satisfies AC7's "focus moves into the reason
 * field on open" without this component doing anything extra. Confirm
 * stays disabled until the reason is non-empty (AC3), and the reason is
 * reset each time the dialog closes so a stale value from a previous
 * action never leaks into the next one.
 */
export function ReasonActionDialog({
  isOpen,
  title,
  confirmLabel,
  busy,
  onClose,
  onConfirm,
  extraFields,
}: ReasonActionDialogProps): JSX.Element {
  const [reason, setReason] = useState("");
  const fieldId = useId();

  function handleClose(): void {
    setReason("");
    onClose();
  }

  function handleConfirm(): void {
    onConfirm(reason);
    setReason("");
  }

  return (
    <ConfirmDialog
      isOpen={isOpen}
      title={title}
      onClose={handleClose}
      onConfirm={handleConfirm}
      confirmLabel={confirmLabel}
      confirmDisabled={reason.trim().length === 0}
      busy={busy}
    >
      <label htmlFor={fieldId}>Reason</label>
      <textarea
        id={fieldId}
        value={reason}
        onChange={(event) => setReason(event.target.value)}
        rows={3}
        style={{ width: "100%" }}
      />
      {extraFields}
    </ConfirmDialog>
  );
}
