import type { FormEvent } from "react";
import { useState } from "react";

import { Badge } from "../../components/Badge";
import { ScrollRegion } from "../../components/ScrollRegion";
import { formatDateTime } from "../../lib/formatDateTime";
import type { AuditEvent } from "../../api/auditTypes";
import { STAGE_LABELS } from "./auditLabels";
import type { AuditSearchFilters } from "./useAuditSearch";
import { EMPTY_AUDIT_FILTERS, useAuditSearch } from "./useAuditSearch";
import { SCREEN_TITLES, usePageTitle } from "../../lib/pageTitle";

/** AC2: an AI step is one that actually carries AI-interaction metadata --
 * not every event has a model/prompt/policy version (e.g. a plain
 * ACCESS_DENIED has none of them), so the block only renders when at least
 * one is present. */
function hasAiMetadata(event: AuditEvent): boolean {
  return event.model_id !== null || event.prompt_version !== null || event.policy_version !== null;
}

function TimelineEvent({ event }: { event: AuditEvent }): JSX.Element {
  return (
    <li className="panel" style={{ marginBottom: 8 }}>
      <div className="row" style={{ justifyContent: "space-between", alignItems: "flex-start" }}>
        <div>
          {/* AC1, AC4: every stage identified by its real text label, never
           * color/position alone. */}
          <Badge text={STAGE_LABELS[event.stage]} variant="info" />{" "}
          <strong>{event.event_type}</strong>
        </div>
        <span className="small muted mono">{formatDateTime(event.timestamp)}</span>
      </div>
      <dl style={{ marginTop: 6 }}>
        <dt>actor</dt>
        <dd>
          {event.actor_kind}
          {event.actor_persona !== null ? ` (${event.actor_persona})` : ""}
        </dd>
        {event.final_action !== null && (
          <>
            <dt>final_action</dt>
            <dd>{event.final_action}</dd>
          </>
        )}
        {event.reason_code !== null && (
          <>
            <dt>reason_code</dt>
            <dd>{event.reason_code}</dd>
          </>
        )}
      </dl>
      {hasAiMetadata(event) && (
        <div className="small" style={{ marginTop: 6 }}>
          <span className="chip neutral">AI interaction</span>{" "}
          {event.model_id !== null && (
            <span className="mono small muted">model {event.model_id} &middot; </span>
          )}
          {event.prompt_version !== null && (
            <span className="mono small muted">prompt {event.prompt_version} &middot; </span>
          )}
          {event.policy_version !== null && (
            <span className="mono small muted">policy {event.policy_version}</span>
          )}
        </div>
      )}
    </li>
  );
}

/**
 * E9-S2: the compliance-facing audit trail viewer. Read-only by
 * construction (AC3: no button here ever writes anything) -- searching by
 * correlation id shows that chain's ordered six-stage timeline directly
 * (AC1); searching by account id/date lists the matching chains first, each
 * opening its own timeline on selection. Reachable only via
 * `RequireCapability capability="audit:read"` in `app/router.tsx`, matching
 * `api/rbac.py`'s COMPLIANCE_RISK-only grant for this capability (AC4).
 */
export function AuditTrailViewer(): JSX.Element {
  usePageTitle(SCREEN_TITLES.auditTrail);
  const [filters, setFilters] = useState<AuditSearchFilters>(EMPTY_AUDIT_FILTERS);
  const { status, chains, timeline, errorMessage, search, openChain } = useAuditSearch();

  function handleSubmit(event: FormEvent<HTMLFormElement>): void {
    event.preventDefault();
    search(filters);
  }

  return (
    <div className="pagehead-wrap">
      <div className="pagehead">
        <h1>Audit trail</h1>
        <p className="muted">Read-only decision-chain search. No edit or delete controls.</p>
      </div>

      <form className="panel" onSubmit={handleSubmit} aria-label="Search audit trail">
        <div className="row" style={{ alignItems: "flex-end" }}>
          <label className="f">
            Correlation id
            <input
              value={filters.correlationId}
              onChange={(e) => setFilters({ ...filters, correlationId: e.target.value })}
              placeholder="e.g. corr-..."
              style={{ width: 220 }}
            />
          </label>
          <label className="f">
            Account id
            <input
              value={filters.accountId}
              onChange={(e) => setFilters({ ...filters, accountId: e.target.value })}
              placeholder="e.g. acc_000123"
              style={{ width: 180 }}
            />
          </label>
          <label className="f">
            From
            <input
              type="date"
              value={filters.from}
              onChange={(e) => setFilters({ ...filters, from: e.target.value })}
            />
          </label>
          <label className="f">
            To
            <input
              type="date"
              value={filters.to}
              onChange={(e) => setFilters({ ...filters, to: e.target.value })}
            />
          </label>
          <button type="submit" className="btn">
            Search
          </button>
        </div>
      </form>

      {status === "loading" && (
        <p role="status" aria-live="polite">
          Searching&hellip;
        </p>
      )}

      {status === "error" && (
        <div className="banner danger" role="alert">
          <div>{errorMessage ?? "The search could not be completed."}</div>
        </div>
      )}

      {status === "chain-list" && chains.length === 0 && (
        <div className="empty" role="status">
          No matching audit chains.
        </div>
      )}

      {status === "chain-list" && chains.length > 0 && (
        <ScrollRegion className="tablewrap" label="Matching audit chains">
          <table>
            <caption className="sr">{chains.length} matching audit chains</caption>
            <thead>
              <tr>
                <th scope="col">Correlation id</th>
                <th scope="col">Account</th>
                <th scope="col">Started</th>
                <th scope="col">Last event</th>
                <th scope="col" className="num">
                  Events
                </th>
                <th scope="col">Stages</th>
              </tr>
            </thead>
            <tbody>
              {chains.map((chain) => (
                <tr key={chain.correlation_id}>
                  <td>
                    <button
                      type="button"
                      className="btn secondary"
                      onClick={() => openChain(chain.correlation_id)}
                    >
                      {chain.correlation_id}
                    </button>
                  </td>
                  <td>{chain.account_id ?? "-"}</td>
                  <td>{formatDateTime(chain.started_at)}</td>
                  <td>{formatDateTime(chain.last_event_at)}</td>
                  <td className="num">{chain.event_count}</td>
                  <td className="small">
                    {chain.stages_present.map((stage) => STAGE_LABELS[stage]).join(", ")}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </ScrollRegion>
      )}

      {status === "timeline" && timeline.length === 0 && (
        <div className="empty" role="status">
          No events found for this chain.
        </div>
      )}

      {status === "timeline" && timeline.length > 0 && (
        <section aria-labelledby="timeline-heading">
          <h2 id="timeline-heading" className="sr">
            Decision chain timeline
          </h2>
          {/* AC1: already ordered by (timestamp, sequence) --
           * `audit.queries.search`'s own contract -- so the true decision
           * order is preserved exactly as the API returned it, never
           * re-grouped by stage on the client (a stage can legitimately
           * repeat across a multi-turn chain). */}
          <ol style={{ listStyle: "none", padding: 0 }}>
            {timeline.map((event) => (
              <TimelineEvent key={event.audit_event_id} event={event} />
            ))}
          </ol>
        </section>
      )}
    </div>
  );
}
