import { useId, useState } from "react";

import { postReseed } from "../../api/demoControlsClient";
import { ConfirmDialog } from "../../components/ConfirmDialog";
import { DemoFeedback } from "./DemoFeedback";
import { useDemoAction } from "./useDemoAction";

/**
 * AC4 (reseed half): restores the seeded dataset. It is the one control that
 * can undo demo work, so it always goes through the shared `ConfirmDialog`
 * and an explicit acknowledgement checkbox; the Confirm button stays
 * disabled until the box is ticked. When the dialog closes the shared
 * dialog returns focus to the button that opened it. The audit event is
 * written by the API (`DEMO_RESEED`); this panel does not display audit rows.
 */
export function ReseedPanel({ onChanged }: { onChanged: () => void }): JSX.Element {
  const headingId = useId();
  const helpId = useId();
  const errorId = useId();
  const [open, setOpen] = useState(false);
  const [acknowledged, setAcknowledged] = useState(false);
  const action = useDemoAction();

  function close(): void {
    setOpen(false);
    setAcknowledged(false);
  }

  function confirm(): void {
    if (!acknowledged) {
      return;
    }
    close();
    void action
      .run(
        () => postReseed({ confirm: true }),
        (result) => (
          <>
            Seed data restored: {result.customers} customers, {result.accounts} accounts,{" "}
            {result.delinquency_records} delinquency records, {result.delinquent_items} items,{" "}
            {result.interactions} interactions, {result.promise_to_pays} promises to pay.
          </>
        ),
      )
      .then((result) => {
        if (result !== null) {
          onChanged();
        }
      });
  }

  return (
    <section className="panel" aria-labelledby={headingId}>
      <div className="ph">
        <h2 id={headingId}>Reseed data</h2>
      </div>
      <p id={helpId} className="small muted">
        Restores the seeded customers, accounts, delinquency records, items, interactions and
        promises to pay to their original seed values. Rows created during the demo (cases,
        disputes, chats, payments, new promises) and every audit record are not deleted.
      </p>
      <button
        type="button"
        className="btn secondary"
        aria-describedby={helpId}
        aria-disabled={action.busy}
        onClick={() => {
          if (!action.busy) {
            setOpen(true);
          }
        }}
      >
        {action.busy ? "Reseeding..." : "Reseed data..."}
      </button>
      <DemoFeedback errorId={errorId} error={action.error} notice={action.notice} />

      <ConfirmDialog
        isOpen={open}
        title="Reseed the demo data?"
        onClose={close}
        onConfirm={confirm}
        confirmLabel="Reseed data"
        confirmDisabled={!acknowledged}
      >
        <p>
          This resets the seeded records listed on the page. It cannot be undone, and it can change
          accounts that a demo journey is using.
        </p>
        <div className="checks">
          <label>
            <input
              type="checkbox"
              checked={acknowledged}
              onChange={(event) => setAcknowledged(event.target.checked)}
            />
            I understand this resets the seeded demo data.
          </label>
        </div>
      </ConfirmDialog>
    </section>
  );
}
