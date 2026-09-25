import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import { useSession } from "../../auth/sessionStore";
import { Badge } from "../../components/Badge";
import type { DataTableColumn } from "../../components/DataTable";
import { DataTable } from "../../components/DataTable";
import type { EscalationListItem, ReviewQueue } from "../../api/escalationsTypes";
import {
  OFFICER_FILTERABLE_QUEUES,
  PRIORITY_DISPLAY,
  QUEUE_LABELS,
  REASON_LABELS,
  STATUS_DISPLAY,
  formatAge,
} from "./escalationLabels";
import { useEscalationsQuery } from "./useEscalationsQuery";

function buildColumns(): DataTableColumn<EscalationListItem>[] {
  return [
    {
      key: "reason",
      header: "Reason",
      renderCell: (row) => <Link to={`/escalations/${row.case_id}`}>{REASON_LABELS[row.reason]}</Link>,
    },
    {
      key: "queue",
      header: "Queue",
      renderCell: (row) => QUEUE_LABELS[row.queue],
    },
    {
      key: "priority",
      header: "Priority",
      renderCell: (row) => {
        const display = PRIORITY_DISPLAY[row.priority];
        return <Badge text={display.label} variant={display.variant} icon={display.icon} />;
      },
    },
    {
      key: "age_hours",
      header: "Age",
      align: "right",
      renderCell: (row) => (
        <span>
          {formatAge(row.age_hours)}
          {row.aging_warning && (
            <>
              {" "}
              <Badge text="AGING" variant="warn" />
            </>
          )}
        </span>
      ),
    },
    {
      key: "status",
      header: "Status",
      renderCell: (row) => {
        const display = STATUS_DISPLAY[row.status];
        return <Badge text={display.label} variant={display.variant} />;
      },
    },
    {
      key: "customer",
      header: "Customer",
      renderCell: (row) => (
        // AC2/AC4: a real focusable link (not just the row's pointer-only
        // onClick) so Tab + Enter opens Customer 360 exactly like a mouse
        // click on the row does -- same pattern as `PortfolioScreen`'s own
        // customer column.
        <Link to={row.customer_360_path}>
          <strong>{row.customer_name}</strong>
          <br />
          <span className="small muted mono">{row.account_id}</span>
        </Link>
      ),
    },
  ];
}

interface QueueFilterProps {
  selected: ReviewQueue[];
  onToggle: (queue: ReviewQueue) => void;
}

/** E7-S3 AC5: filter checkboxes for the five officer-facing queues.
 * COMPLIANCE_RISK never sees this -- it is auto-scoped to COMPLIANCE_REVIEW
 * server-side and has nothing to filter. */
function QueueFilter({ selected, onToggle }: QueueFilterProps): JSX.Element {
  return (
    <fieldset className="row">
      <legend className="sr">Filter by queue</legend>
      {OFFICER_FILTERABLE_QUEUES.map((queue) => (
        <label key={queue} className="row" style={{ gap: 4 }}>
          <input
            type="checkbox"
            checked={selected.includes(queue)}
            onChange={() => onToggle(queue)}
          />
          {QUEUE_LABELS[queue]}
        </label>
      ))}
    </fieldset>
  );
}

/**
 * E7-S3: the full review queue list -- reason, priority, aging, status,
 * queue and customer for every open case, already sorted by priority then
 * age by the backend (AC1). Reachable by both COLLECTIONS_OFFICER and
 * COMPLIANCE_RISK (`escalation:read`, AC6): COMPLIANCE_RISK's queue filter
 * is never shown (the backend auto-scopes it to COMPLIANCE_REVIEW and
 * rejects any other queue), and its compliance-decision controls live on
 * the case-detail screen, not here. Selecting a case's reason opens its
 * detail (E7-S3 AC2); the customer link still opens Customer 360, matching
 * E7-S6's original behaviour.
 */
export function EscalationsScreen(): JSX.Element {
  const navigate = useNavigate();
  const session = useSession();
  const [selectedQueues, setSelectedQueues] = useState<ReviewQueue[]>([]);
  const isOfficer = session?.persona === "COLLECTIONS_OFFICER";
  const { status, data, errorMessage, refetch } = useEscalationsQuery(
    isOfficer ? selectedQueues : undefined,
  );
  const columns = buildColumns();

  function toggleQueue(queue: ReviewQueue): void {
    setSelectedQueues((previous) =>
      previous.includes(queue) ? previous.filter((q) => q !== queue) : [...previous, queue],
    );
  }

  return (
    <div className="pagehead-wrap">
      <div className="pagehead">
        <div>
          <h1>Escalations</h1>
          <p className="muted">Cases needing attention now, sorted by priority then age.</p>
        </div>
      </div>

      {isOfficer && <QueueFilter selected={selectedQueues} onToggle={toggleQueue} />}

      {status === "loading" && (
        <p role="status" aria-live="polite">
          Loading escalations&hellip;
        </p>
      )}

      {status === "error" && (
        <div className="banner danger" role="alert">
          <span className="bi" aria-hidden="true">
            &#10007;
          </span>
          <div>
            <strong>The escalation list could not be loaded.</strong>{" "}
            {errorMessage ?? "Please try again."}{" "}
            <button type="button" className="btn secondary" onClick={refetch}>
              Retry
            </button>
          </div>
        </div>
      )}

      {status === "loaded" && data !== null && data.items.length === 0 && (
        <div className="empty" role="status">
          No open escalations right now.
        </div>
      )}

      {status === "loaded" && data !== null && data.items.length > 0 && (
        <DataTable
          columns={columns}
          rows={data.items}
          getRowKey={(row) => row.case_id}
          caption={`${data.items.length} of ${data.page.total} open escalations, sorted by priority then age`}
          onRowClick={(row) => navigate(`/escalations/${row.case_id}`)}
        />
      )}
    </div>
  );
}
