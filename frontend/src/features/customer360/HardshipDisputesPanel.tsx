import { Badge } from "../../components/Badge";
import { formatDateTime } from "../../lib/formatDateTime";
import type { Dispute, HardshipCase } from "../../api/customer360Types";
import { humanize } from "./customer360Labels";

export interface HardshipDisputesPanelProps {
  hardshipCases: HardshipCase[];
  disputes: Dispute[];
}

/** Financial-hardship cases and item disputes (AC1) -- both human-in-the-loop
 * workflows (CLAUDE.md: vulnerable-customer scenarios and policy exceptions
 * stay under human control), so this panel is read-only: no accept/reject
 * controls, only the current state. */
export function HardshipDisputesPanel({ hardshipCases, disputes }: HardshipDisputesPanelProps): JSX.Element {
  return (
    <section className="panel" aria-labelledby="hardship-disputes-heading">
      <h2 id="hardship-disputes-heading">Hardship and disputes</h2>

      <h3 className="small">Hardship cases</h3>
      {hardshipCases.length === 0 ? (
        <p className="muted small">None recorded.</p>
      ) : (
        <ul>
          {hardshipCases.map((hardshipCase) => (
            <li key={hardshipCase.hardship_case_id}>
              <Badge text={humanize(hardshipCase.status)} variant={hardshipCase.status === "DECIDED" ? "ok" : "warn"} />{" "}
              {hardshipCase.indicators.map((indicator) => humanize(indicator.indicator_type)).join(", ")} -{" "}
              <span className="small muted">{formatDateTime(hardshipCase.created_at)}</span>
            </li>
          ))}
        </ul>
      )}

      <h3 className="small">Disputes</h3>
      {disputes.length === 0 ? (
        <p className="muted small">None recorded.</p>
      ) : (
        <ul>
          {disputes.map((dispute) => (
            <li key={dispute.dispute_id}>
              <Badge text={humanize(dispute.status)} variant={dispute.status === "RESOLVED" ? "ok" : "warn"} />{" "}
              {humanize(dispute.category)}
              {dispute.outcome !== null ? ` - ${humanize(dispute.outcome)}` : ""} -{" "}
              <span className="small muted">{formatDateTime(dispute.created_at)}</span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
