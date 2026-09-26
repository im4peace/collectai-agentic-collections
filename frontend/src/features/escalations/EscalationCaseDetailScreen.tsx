import { useState } from "react";
import { Link, useParams } from "react-router-dom";

import { Badge } from "../../components/Badge";
import { ConfirmDialog } from "../../components/ConfirmDialog";
import { useSession } from "../../auth/sessionStore";
import type { ComplianceOutcome, EscalationReason } from "../../api/escalationsTypes";
import { ESCALATION_REASONS } from "../../api/escalationsTypes";
import { formatDateTime } from "../../lib/formatDateTime";
import type { ChatMessage } from "../../api/chatTypes";
import { PRIORITY_DISPLAY, QUEUE_LABELS, REASON_LABELS, STATUS_DISPLAY, formatAge } from "./escalationLabels";
import { DisputeResolutionPanel } from "./DisputeResolutionPanel";
import { ReasonActionDialog } from "./ReasonActionDialog";
import { useCaseDecision } from "./useCaseDecision";
import { useEscalationCaseDetail } from "./useEscalationCaseDetail";

type ActiveDialog = "REJECT" | "MODIFY" | "ESCALATE" | "APPROVE" | null;
type ActiveComplianceDialog = ComplianceOutcome | null;

const _ACTIONABLE_STATUSES = new Set(["OPEN", "IN_REVIEW", "AWAITING_INFORMATION"]);

const COMPLIANCE_OUTCOME_LABELS: Record<ComplianceOutcome, string> = {
  CLEARED: "Clear",
  NOT_CLEARED: "Not cleared",
  REMEDIATION_REQUIRED: "Remediation required",
};

/**
 * E7-S3 AC2, AC3, AC6, AC7: full case detail -- conversation, AI
 * recommendation and deterministic rule results in three separately
 * labelled sections, reviewer/compliance action controls gated by persona,
 * case ownership and `approve_permitted`, and a stale-version conflict that
 * reloads the case rather than silently failing.
 */
export function EscalationCaseDetailScreen(): JSX.Element {
  const { caseId } = useParams<{ caseId: string }>();
  const session = useSession();
  const { status, data, errorMessage, refetch } = useEscalationCaseDetail(caseId ?? "");
  const decision = useCaseDecision();
  const [activeDialog, setActiveDialog] = useState<ActiveDialog>(null);
  const [activeComplianceDialog, setActiveComplianceDialog] = useState<ActiveComplianceDialog>(null);
  const [escalateReason, setEscalateReason] = useState<EscalationReason>(ESCALATION_REASONS[0]);

  if (status === "loading" && data === null) {
    // A background refetch (e.g. AC4's post-conflict reload) keeps
    // rendering the already-loaded `data` below instead of replacing the
    // whole screen with this loading state -- otherwise the "this case
    // changed" banner below would be unmounted the instant the reload
    // starts, before anyone could read it.
    return (
      <p role="status" aria-live="polite">
        Loading case&hellip;
      </p>
    );
  }

  if (status === "not_found") {
    return (
      <div className="pagehead-wrap">
        <h1>Case not found</h1>
        <p>
          <Link to="/escalations">Back to escalations</Link>
        </p>
      </div>
    );
  }

  if (status === "error" || data === null) {
    return (
      <div className="banner danger" role="alert">
        <strong>This case could not be loaded.</strong> {errorMessage ?? "Please try again."}{" "}
        <button type="button" className="btn secondary" onClick={refetch}>
          Retry
        </button>
      </div>
    );
  }

  const persona = session?.persona ?? null;
  const isActionable = _ACTIONABLE_STATUSES.has(data.status);
  const showOfficerControls =
    persona === "COLLECTIONS_OFFICER" && data.reviewer_role === "COLLECTIONS_OFFICER" && isActionable;
  const showComplianceControls =
    persona === "COMPLIANCE_RISK" && data.queue === "COMPLIANCE_REVIEW" && isActionable;

  /** After a decision attempt that reached the server's verdict -- recorded
   * (`success`) or rejected as stale (`version_conflict`) -- close the dialog
   * and reload the case, so the screen shows the server's current version and
   * the next action uses it. Any other failure leaves the dialog open with its
   * error message, exactly as before. Nothing is ever retried automatically. */
  function closeAndReload(closeDialog: () => void): void {
    closeDialog();
    refetch();
  }

  async function handleReviewConfirm(reason: string): Promise<void> {
    if (data === null || activeDialog === null) return;
    const outcome = await decision.submitReviewDecision(data.case_id, data.version, {
      action: activeDialog,
      reason,
      escalateReason: activeDialog === "ESCALATE" ? escalateReason : undefined,
    });
    if (outcome !== "error") closeAndReload(() => setActiveDialog(null));
  }

  async function handleApproveConfirm(): Promise<void> {
    if (data === null) return;
    const outcome = await decision.submitReviewDecision(data.case_id, data.version, {
      action: "APPROVE",
      reason: "Approved by reviewer.",
    });
    if (outcome !== "error") closeAndReload(() => setActiveDialog(null));
  }

  async function handleComplianceConfirm(reason: string): Promise<void> {
    if (data === null || activeComplianceDialog === null) return;
    const outcome = await decision.submitComplianceDecision(
      data.case_id,
      data.version,
      activeComplianceDialog,
      reason,
    );
    if (outcome !== "error") closeAndReload(() => setActiveComplianceDialog(null));
  }

  const priorityDisplay = PRIORITY_DISPLAY[data.priority];
  const statusDisplay = STATUS_DISPLAY[data.status];

  return (
    <div className="pagehead-wrap">
      <div className="pagehead">
        <div>
          <h1>{REASON_LABELS[data.reason]}</h1>
          <p className="muted">
            <Link to={data.customer_360_path}>{data.customer_name}</Link> &middot; {data.account_id}
          </p>
        </div>
        <div className="row">
          <Badge text={priorityDisplay.label} variant={priorityDisplay.variant} icon={priorityDisplay.icon} />
          <Badge text={statusDisplay.label} variant={statusDisplay.variant} />
        </div>
      </div>

      <div className="row small muted" style={{ marginBottom: 16 }}>
        <span>Queue: {QUEUE_LABELS[data.queue]}</span>
        <span>
          Age: {formatAge(data.age_hours)}
          {data.aging_warning && (
            <>
              {" "}
              <Badge text="AGING" variant="warn" />
            </>
          )}
        </span>
        <span>Opened: {formatDateTime(data.created_at)}</span>
      </div>

      {decision.versionConflict && (
        <div className="banner warn" role="alert">
          This case changed since it was loaded. Reloading&hellip;
        </div>
      )}
      {decision.errorMessage !== null && (
        <div className="banner danger" role="alert">
          {decision.errorMessage}
        </div>
      )}

      <section className="panel" aria-labelledby="conversation-heading">
        <h2 id="conversation-heading">Conversation</h2>
        {data.conversation.length === 0 ? (
          <p className="muted">No conversation is attached to this case.</p>
        ) : (
          <ConversationTranscript messages={data.conversation} />
        )}
      </section>

      <section className="panel" aria-labelledby="ai-recommendation-heading">
        <h2 id="ai-recommendation-heading">AI recommendation</h2>
        {data.ai_recommendation === null ? (
          <p className="muted">No AI recommendation is attached to this case.</p>
        ) : (
          <div>
            <p>
              <strong>{humanizeActionName(data.ai_recommendation.action)}</strong>
            </p>
            <p>{data.ai_recommendation.rationale}</p>
            <div className="row small muted">
              <span>content: {data.ai_recommendation.content_source}</span>
              {data.ai_recommendation.model_id !== null && (
                <span>model: {data.ai_recommendation.model_id}</span>
              )}
              {data.ai_recommendation.prompt_version !== null && (
                <span>prompt: {data.ai_recommendation.prompt_version}</span>
              )}
              <span>policy: {data.ai_recommendation.policy_version}</span>
            </div>
          </div>
        )}
      </section>

      <section className="panel" aria-labelledby="rule-results-heading">
        <h2 id="rule-results-heading">Deterministic rule results</h2>
        <p>{data.rule_results.summary}</p>
        <div className="row small muted">
          <span>Routing policy: {data.rule_results.routing_policy_version ?? "-"}</span>
        </div>
        {data.rule_results.exception_types !== null && data.rule_results.exception_types.length > 0 && (
          <p className="small">Exception types: {data.rule_results.exception_types.join(", ")}</p>
        )}
        {data.rule_results.routing_flags.length > 0 && (
          <p className="small">Routing flags: {data.rule_results.routing_flags.join(", ")}</p>
        )}
        {data.rule_results.requested_terms !== null && (
          <p className="small">
            Requested terms: {JSON.stringify(data.rule_results.requested_terms)}
          </p>
        )}
      </section>

      {data.dispute != null && (
        <DisputeResolutionPanel
          dispute={data.dispute}
          canResolve={session?.capabilities.includes("dispute:resolve") === true}
          onChanged={refetch}
        />
      )}

      {showOfficerControls && (
        <section className="panel" aria-labelledby="officer-actions-heading">
          <h2 id="officer-actions-heading">Reviewer decision</h2>
          <div className="row">
            {data.approve_permitted && (
              <button type="button" className="btn" onClick={() => setActiveDialog("APPROVE")}>
                Approve
              </button>
            )}
            <button type="button" className="btn secondary" onClick={() => setActiveDialog("REJECT")}>
              Reject
            </button>
            <button type="button" className="btn secondary" onClick={() => setActiveDialog("MODIFY")}>
              Modify
            </button>
            <button type="button" className="btn secondary" onClick={() => setActiveDialog("ESCALATE")}>
              Escalate
            </button>
          </div>
        </section>
      )}

      {showComplianceControls && (
        <section className="panel" aria-labelledby="compliance-actions-heading">
          <h2 id="compliance-actions-heading">Compliance decision</h2>
          <div className="row">
            {(Object.keys(COMPLIANCE_OUTCOME_LABELS) as ComplianceOutcome[]).map((outcome) => (
              <button
                key={outcome}
                type="button"
                className="btn secondary"
                onClick={() => setActiveComplianceDialog(outcome)}
              >
                {COMPLIANCE_OUTCOME_LABELS[outcome]}
              </button>
            ))}
          </div>
        </section>
      )}

      <ReasonActionDialog
        isOpen={activeDialog === "REJECT"}
        title="Reject this case?"
        confirmLabel="Reject"
        busy={decision.busy}
        onClose={() => setActiveDialog(null)}
        onConfirm={handleReviewConfirm}
      />
      <ReasonActionDialog
        isOpen={activeDialog === "MODIFY"}
        title="Modify this case?"
        confirmLabel="Modify"
        busy={decision.busy}
        onClose={() => setActiveDialog(null)}
        onConfirm={handleReviewConfirm}
      />
      <ReasonActionDialog
        isOpen={activeDialog === "ESCALATE"}
        title="Escalate this case further?"
        confirmLabel="Escalate"
        busy={decision.busy}
        onClose={() => setActiveDialog(null)}
        onConfirm={handleReviewConfirm}
        extraFields={
          <div style={{ marginTop: 8 }}>
            <label htmlFor="escalate-reason-select">Escalate reason</label>
            <select
              id="escalate-reason-select"
              value={escalateReason}
              onChange={(event) => setEscalateReason(event.target.value as EscalationReason)}
            >
              {ESCALATION_REASONS.map((reasonOption) => (
                <option key={reasonOption} value={reasonOption}>
                  {REASON_LABELS[reasonOption]}
                </option>
              ))}
            </select>
          </div>
        }
      />

      <ConfirmApproveDialog
        isOpen={activeDialog === "APPROVE"}
        busy={decision.busy}
        onClose={() => setActiveDialog(null)}
        onConfirm={handleApproveConfirm}
        amount={data.rule_results.requested_terms}
      />

      {(["CLEARED", "NOT_CLEARED", "REMEDIATION_REQUIRED"] as ComplianceOutcome[]).map((outcome) => (
        <ReasonActionDialog
          key={outcome}
          isOpen={activeComplianceDialog === outcome}
          title={`Record outcome: ${COMPLIANCE_OUTCOME_LABELS[outcome]}?`}
          confirmLabel="Record decision"
          busy={decision.busy}
          onClose={() => setActiveComplianceDialog(null)}
          onConfirm={handleComplianceConfirm}
        />
      ))}
    </div>
  );
}

/** `NbaAction` values as text (e.g. `ESCALATE_TO_HUMAN_REVIEW` ->
 * "Escalate to human review"). Not a reuse of `features/customer360
 * .customer360Labels.NBA_ACTION_LABELS` -- same cross-feature-import
 * boundary as `ConversationTranscript` below; a plain string transform is
 * enough here since this AI-recommendation section only ever displays the
 * action, never branches on it. */
function humanizeActionName(action: string): string {
  const lower = action.toLowerCase().replace(/_/g, " ");
  return lower.charAt(0).toUpperCase() + lower.slice(1);
}

/** A read-only transcript for the case-detail conversation section (AC2).
 * Deliberately not a reuse of `features/chat/MessageList` -- `features/*`
 * modules never import each other (folder-structure.md's import-rules
 * table, enforced by `eslint.config.js`'s `no-restricted-imports`); this is
 * a small, self-contained renderer instead. */
function ConversationTranscript({ messages }: { messages: ChatMessage[] }): JSX.Element {
  return (
    <div className="chat-messages" aria-label="Conversation">
      {messages.map((message) => (
        <div
          key={message.message_id}
          className={`chat-message ${message.role === "CUSTOMER" ? "customer" : "assistant"}`}
        >
          <p style={{ margin: 0, whiteSpace: "pre-wrap" }}>{message.content}</p>
          <span className="small muted">{formatDateTime(message.created_at)}</span>
        </div>
      ))}
    </div>
  );
}

interface ConfirmApproveDialogProps {
  isOpen: boolean;
  busy: boolean;
  onClose: () => void;
  onConfirm: () => void;
  amount: Record<string, unknown> | null;
}

/** AC3: APPROVE is gated only on `approve_permitted` (already checked
 * before this dialog's trigger button is even rendered), never on a typed
 * reason -- unlike REJECT/MODIFY/ESCALATE, so this is a plain confirm
 * dialog, not a `ReasonActionDialog`. The backend's `reason` column is
 * still `NOT NULL` for every action including APPROVE (migration 0005's
 * `review_decision_check2`), so a fixed, non-editable reason string is
 * sent -- never a free-form reviewer reason no UI element asked for. */
function ConfirmApproveDialog({
  isOpen,
  busy,
  onClose,
  onConfirm,
  amount,
}: ConfirmApproveDialogProps): JSX.Element {
  const installmentCount =
    amount !== null && typeof amount.installment_count === "number" ? amount.installment_count : null;
  return (
    <ConfirmDialog
      isOpen={isOpen}
      title="Approve this case?"
      confirmLabel="Approve"
      busy={busy}
      onClose={onClose}
      onConfirm={onConfirm}
    >
      <p>Approving records a reviewer decision and, for an exceptional arrangement, creates it.</p>
      {installmentCount !== null && (
        <p className="small muted">Requested installment count: {installmentCount}</p>
      )}
    </ConfirmDialog>
  );
}
