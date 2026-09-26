import { useId, useRef, useState } from "react";
import type { FormEvent } from "react";

import { postClockAdvance } from "../../api/demoControlsClient";
import { formatDateTime } from "../../lib/formatDateTime";
import { DemoFeedback } from "./DemoFeedback";
import { validateDays } from "./demoValidation";
import { useDemoAction } from "./useDemoAction";

/**
 * AC2 (first half): advances the simulated clock by a chosen number of days.
 * Clock advance and snapshot refresh are one control because the API takes
 * both in one request (`refresh_snapshots`, default true). The refresh only
 * marks every account's data snapshot fresh as of the new time; days past
 * due are not recalculated, and the panel says so. The clock cannot be moved
 * back, so the days field defaults to 1 and nothing submits by itself.
 */
export function AdvanceClockPanel({ onChanged }: { onChanged: () => void }): JSX.Element {
  const headingId = useId();
  const daysId = useId();
  const helpId = useId();
  const errorId = useId();
  const [days, setDays] = useState("1");
  const [refresh, setRefresh] = useState(true);
  const [invalid, setInvalid] = useState(false);
  const daysRef = useRef<HTMLInputElement>(null);
  const action = useDemoAction();

  async function handleSubmit(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    if (action.busy) {
      return;
    }
    const parsed = validateDays(days);
    if (!parsed.ok) {
      setInvalid(true);
      action.fail(parsed.message);
      daysRef.current?.focus();
      return;
    }
    setInvalid(false);
    const result = await action.run(
      () => postClockAdvance({ days: parsed.value, refresh_snapshots: refresh }),
      (advanced) => (
        <>
          Clock advanced by {parsed.value} {parsed.value === 1 ? "day" : "days"}. Simulated time is
          now {formatDateTime(advanced.clock.current_time)}. Snapshots refreshed:{" "}
          {advanced.snapshots_refreshed}.
        </>
      ),
    );
    if (result !== null) {
      onChanged();
    }
  }

  return (
    <section className="panel" aria-labelledby={headingId}>
      <div className="ph">
        <h2 id={headingId}>Advance clock</h2>
      </div>
      <form onSubmit={(event) => void handleSubmit(event)} noValidate>
        <div className="row" style={{ alignItems: "flex-end" }}>
          <label className="f" htmlFor={daysId}>
            Days to advance (1 to 365)
            <input
              id={daysId}
              ref={daysRef}
              type="number"
              inputMode="numeric"
              min={1}
              max={365}
              step={1}
              value={days}
              aria-invalid={invalid}
              aria-describedby={`${helpId} ${errorId}`}
              onChange={(event) => {
                setDays(event.target.value);
                setInvalid(false);
                action.clearError();
              }}
              style={{ width: 120 }}
            />
          </label>
          <div className="checks">
            <label>
              <input
                type="checkbox"
                checked={refresh}
                onChange={(event) => setRefresh(event.target.checked)}
              />
              Refresh data snapshots
            </label>
          </div>
          <button type="submit" className="btn" aria-disabled={action.busy}>
            {action.busy ? "Advancing..." : "Advance clock"}
          </button>
        </div>
        <p id={helpId} className="small muted">
          Moves the simulated clock forward. It cannot be moved back; restarting the API resets it.
          With the box ticked, every account&apos;s data snapshot is also marked fresh as of the new
          time, which is needed before a customer can confirm a proposal. Days past due are not
          recalculated.
        </p>
        <DemoFeedback errorId={errorId} error={action.error} notice={action.notice} />
      </form>
    </section>
  );
}
