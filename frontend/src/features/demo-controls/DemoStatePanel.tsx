import { useId } from "react";

import type { DemoState } from "../../api/demoControlsTypes";
import { Badge } from "../../components/Badge";
import { formatDateTime } from "../../lib/formatDateTime";

/**
 * AC1: the AI mode is shown as **text** ("MOCK" or "LIVE"), never as colour
 * alone, next to the simulated clock and the active PolicyRuleSet version.
 * Read-only: it renders `GET /api/demo-controls/state`.
 */
export function DemoStatePanel({ state }: { state: DemoState }): JSX.Element {
  const headingId = useId();
  const simulated = state.clock.mode === "SIMULATED";

  return (
    <section className="panel" aria-labelledby={headingId}>
      <div className="ph">
        <h2 id={headingId}>Demo state</h2>
      </div>
      <dl>
        <dt>AI mode</dt>
        <dd>
          <Badge text={state.llm_mode} variant={state.llm_mode === "LIVE" ? "warn" : "info"} />
        </dd>
        <dt>{simulated ? "Simulated clock" : "Clock (real time)"}</dt>
        <dd>
          {formatDateTime(state.clock.current_time)}{" "}
          <span className="muted small">({state.clock.current_time})</span>
        </dd>
        <dt>Clock mode</dt>
        <dd>{state.clock.mode}</dd>
        <dt>Active policy version</dt>
        <dd>{state.policy_version ?? "none active"}</dd>
      </dl>
    </section>
  );
}
