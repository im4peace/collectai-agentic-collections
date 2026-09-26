import { useId } from "react";

import { postRunPtpLifecycle } from "../../api/demoControlsClient";
import { DemoFeedback } from "./DemoFeedback";
import { useDemoAction } from "./useDemoAction";

/**
 * AC2 (second half): runs the PTP breakage job now, under the current
 * (simulated) clock. It is the same job the scheduler runs, and it is safe
 * to rerun: settled promises are never transitioned twice.
 */
export function PtpLifecyclePanel(): JSX.Element {
  const headingId = useId();
  const helpId = useId();
  const errorId = useId();
  const action = useDemoAction();

  function handleRun(): void {
    if (action.busy) {
      return;
    }
    void action.run(postRunPtpLifecycle, (result) => (
      <>
        Evaluated {result.evaluated}, kept {result.kept}, broken {result.broken}, unchanged{" "}
        {result.unchanged}.
      </>
    ));
  }

  return (
    <section className="panel" aria-labelledby={headingId}>
      <div className="ph">
        <h2 id={headingId}>Run PTP lifecycle</h2>
      </div>
      <p id={helpId} className="small muted">
        Runs the promise-to-pay breakage job now. Pending promises whose due date has passed
        without enough payment become BROKEN; fully paid ones become KEPT. Advance the clock past
        a due date first to see a promise break. Safe to run again.
      </p>
      <button
        type="button"
        className="btn"
        aria-disabled={action.busy}
        aria-describedby={helpId}
        onClick={handleRun}
      >
        {action.busy ? "Running..." : "Run PTP lifecycle now"}
      </button>
      <DemoFeedback errorId={errorId} error={action.error} notice={action.notice} />
    </section>
  );
}
