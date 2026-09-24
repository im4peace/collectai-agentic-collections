import { Badge } from "../../components/Badge";
import type { AiBlock } from "../../api/customer360Types";
import { NBA_ACTION_LABELS } from "./customer360Labels";

export interface AiPanelProps {
  ai: AiBlock;
  /** AC6: when the deterministic side has no active policy, nothing can be
   * computed to ground an AI recommendation either, so this panel shows the
   * same "unavailable - manual workflow available" message regardless of
   * what `ai.status` itself says. */
  deterministicStatus: "OK" | "POLICY_UNAVAILABLE";
}

const UNAVAILABLE_MESSAGE = "AI unavailable - manual workflow available.";

/** The AI (next-best-action recommendation) panel (AC1, AC2, AC6): always
 * carries the backend's own `label: "AI-generated"` text, and never
 * fabricates a recommendation when one was not actually generated. */
export function AiPanel({ ai, deterministicStatus }: AiPanelProps): JSX.Element {
  const isUnavailable = deterministicStatus === "POLICY_UNAVAILABLE" || ai.status === "AI_UNAVAILABLE";

  return (
    <section className="panel" aria-labelledby="ai-heading">
      <div className="ph">
        <h2 id="ai-heading">{ai.label}</h2>
        <Badge text={ai.status.replace(/_/g, " ")} variant={isUnavailable ? "neutral" : "info"} />
      </div>

      {isUnavailable && (
        <div className="banner info" role="status">
          <div>{UNAVAILABLE_MESSAGE}</div>
        </div>
      )}

      {!isUnavailable && ai.recommendation === null && (
        <p className="muted">No recommendation has been generated for this account yet.</p>
      )}

      {!isUnavailable && ai.recommendation !== null && (
        <div>
          <p>
            <strong>{NBA_ACTION_LABELS[ai.recommendation.action]}</strong>
          </p>
          <p>{ai.recommendation.rationale}</p>
          <div className="row small muted">
            <span>content: {ai.recommendation.content_source}</span>
            {ai.recommendation.model_id !== null && <span>model: {ai.recommendation.model_id}</span>}
            {ai.recommendation.prompt_version !== null && (
              <span>prompt: {ai.recommendation.prompt_version}</span>
            )}
            <span>policy: {ai.recommendation.policy_version}</span>
          </div>
          {ai.recommendation.officer_decision !== null && (
            <p className="small">Officer decision: {ai.recommendation.officer_decision}</p>
          )}
        </div>
      )}
    </section>
  );
}
