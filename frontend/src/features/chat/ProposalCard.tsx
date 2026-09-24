import { useState } from "react";

import { Badge } from "../../components/Badge";
import { ConfirmDialog } from "../../components/ConfirmDialog";
import { MoneyText } from "../../components/MoneyText";
import type { Proposal } from "../../api/chatTypes";

export interface ProposalCardProps {
  proposal: Proposal;
  busy: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}

function proposalAmount(proposal: Proposal): string | null {
  if (proposal.kind === "PTP" && "promised_amount" in proposal.terms) {
    return String(proposal.terms.promised_amount);
  }
  if (proposal.kind === "PAYMENT" && "payment_amount" in proposal.terms) {
    return String(proposal.terms.payment_amount);
  }
  return null;
}

/**
 * A pending proposal (E6-S5 AC constraint: nothing is submitted until
 * Confirm is explicitly clicked). Confirm and Cancel each open the shared
 * `ConfirmDialog` so both actions get the same focus-trapped confirmation
 * step (AC7) rather than acting immediately on a single click. A `PAYMENT`
 * proposal, or any proposal with `simulated: true`, always shows a visible
 * "Simulated payment" label (AC constraint: no real money ever moves).
 */
export function ProposalCard({ proposal, busy, onConfirm, onCancel }: ProposalCardProps): JSX.Element {
  const [dialog, setDialog] = useState<"confirm" | "cancel" | null>(null);
  const amount = proposalAmount(proposal);

  function closeDialog(): void {
    setDialog(null);
  }

  function runConfirm(): void {
    onConfirm();
    closeDialog();
  }

  function runCancel(): void {
    onCancel();
    closeDialog();
  }

  return (
    <div className="panel" role="group" aria-label="Proposal awaiting confirmation">
      <div className="ph">
        <h2 className="small">Proposal</h2>
        {(proposal.kind === "PAYMENT" || proposal.simulated) && <Badge text="Simulated payment" variant="info" />}
      </div>
      <p>{proposal.summary}</p>
      {amount !== null && (
        <p>
          <strong>
            <MoneyText amount={amount} />
          </strong>
        </p>
      )}
      <div className="row">
        <button type="button" className="btn" onClick={() => setDialog("confirm")} disabled={busy}>
          Confirm
        </button>
        <button type="button" className="btn secondary" onClick={() => setDialog("cancel")} disabled={busy}>
          Cancel
        </button>
      </div>

      <ConfirmDialog
        isOpen={dialog === "confirm"}
        title="Confirm this proposal?"
        onClose={closeDialog}
        onConfirm={runConfirm}
        confirmLabel="Confirm"
        busy={busy}
      >
        <p>{proposal.summary}</p>
      </ConfirmDialog>

      <ConfirmDialog
        isOpen={dialog === "cancel"}
        title="Cancel this proposal?"
        onClose={closeDialog}
        onConfirm={runCancel}
        confirmLabel="Cancel proposal"
        cancelLabel="Keep proposal"
        busy={busy}
      >
        <p>This proposal will not be acted on.</p>
      </ConfirmDialog>
    </div>
  );
}
