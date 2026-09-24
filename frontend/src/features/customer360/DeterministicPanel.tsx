import { Badge } from "../../components/Badge";
import { MoneyText } from "../../components/MoneyText";
import type { DeterministicBlock } from "../../api/customer360Types";
import { PAYABLE_OPTION_LABELS, PRIORITY_BAND_DISPLAY, humanize } from "./customer360Labels";

export interface DeterministicPanelProps {
  deterministic: DeterministicBlock;
}

/** The deterministic (rules-engine) panel (AC1, AC2): every field here is
 * server-calculated, never AI-generated, and always carries the backend's
 * own `label: "Rules engine"` text so that distinction is visible, not just
 * inferred from panel placement. Renders whatever IS present even when
 * `status === "POLICY_UNAVAILABLE"` (AC6) -- `priority`/`contact_policy`
 * are `null` in that case, but `treatment`/`payable_options`/`record_check`
 * still come from data already on the account. */
export function DeterministicPanel({ deterministic }: DeterministicPanelProps): JSX.Element {
  return (
    <section className="panel" aria-labelledby="deterministic-heading">
      <div className="ph">
        <h2 id="deterministic-heading">{deterministic.label}</h2>
        {deterministic.policy_version !== null && (
          <span className="small muted mono">policy {deterministic.policy_version}</span>
        )}
      </div>

      {deterministic.status === "POLICY_UNAVAILABLE" && (
        <div className="banner warn" role="status">
          <div>No active policy is available; priority cannot be calculated right now.</div>
        </div>
      )}

      {deterministic.priority !== null && (
        <div style={{ marginBottom: 10 }}>
          <div className="row">
            <Badge
              text={PRIORITY_BAND_DISPLAY[deterministic.priority.band].label}
              variant={PRIORITY_BAND_DISPLAY[deterministic.priority.band].variant}
              icon={PRIORITY_BAND_DISPLAY[deterministic.priority.band].icon}
            />
            <span className="small muted">score {deterministic.priority.score}</span>
          </div>
          {/* AC1: "priority band with each contributing factor" -- every
           * factor the score was computed from, not just the final band. */}
          <div className="tablewrap" style={{ marginTop: 6 }}>
            <table className="tight">
              <caption className="sr">Contributing factors</caption>
              <thead>
                <tr>
                  <th scope="col">Factor</th>
                  <th scope="col">Value</th>
                  <th scope="col" className="num">
                    Weight
                  </th>
                  <th scope="col" className="num">
                    Contribution
                  </th>
                </tr>
              </thead>
              <tbody>
                {deterministic.priority.factors.map((factor) => (
                  <tr key={factor.factor_id}>
                    <td>
                      <code>{factor.factor_id}</code>
                    </td>
                    <td>{factor.value}</td>
                    <td className="num">{factor.weight}</td>
                    <td className="num">{factor.contribution}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      <div className="row" style={{ marginBottom: 10 }}>
        <Badge
          text={deterministic.treatment.human_treatment ? "Human treatment required" : "Automated treatment eligible"}
          variant={deterministic.treatment.human_treatment ? "warn" : "ok"}
        />
        {deterministic.treatment.automated_treatment_suppressed && (
          <Badge text="Automated treatment suppressed" variant="danger" />
        )}
      </div>

      {deterministic.treatment.suppressions.length > 0 && (
        <ul className="small">
          {deterministic.treatment.suppressions.map((suppression) => (
            <li key={`${suppression.source_type}-${suppression.source_id}`}>
              {humanize(suppression.source_type)} suppression ({humanize(suppression.scope)}
              {suppression.item_id !== null ? ` - ${suppression.item_id}` : ""})
            </li>
          ))}
        </ul>
      )}

      {deterministic.payable_options.length > 0 && (
        <div className="row">
          {deterministic.payable_options.map((option) => (
            <div className="f" key={option.option}>
              <span className="small muted">{PAYABLE_OPTION_LABELS[option.option]}</span>
              <strong>
                <MoneyText amount={option.amount} />
              </strong>
            </div>
          ))}
        </div>
      )}

      {!deterministic.record_check.consistent && (
        <div className="banner danger" role="alert" style={{ marginTop: 10 }}>
          <div>
            Record consistency check failed
            {deterministic.record_check.reason_code !== null
              ? `: ${humanize(deterministic.record_check.reason_code)}`
              : "."}
          </div>
        </div>
      )}
    </section>
  );
}
