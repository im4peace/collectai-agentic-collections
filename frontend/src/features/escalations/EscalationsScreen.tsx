import { Link, useNavigate } from "react-router-dom";

import { Badge } from "../../components/Badge";
import type { DataTableColumn } from "../../components/DataTable";
import { DataTable } from "../../components/DataTable";
import type { EscalationListItem } from "../../api/escalationsTypes";
import { PRIORITY_DISPLAY, REASON_LABELS, STATUS_DISPLAY, formatAge } from "./escalationLabels";
import { useEscalationsQuery } from "./useEscalationsQuery";

function buildColumns(): DataTableColumn<EscalationListItem>[] {
  return [
    {
      key: "reason",
      header: "Reason",
      renderCell: (row) => REASON_LABELS[row.reason],
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

/**
 * The minimal Slice-1 escalation list (E7-S6): reason, priority, age,
 * status and a customer/account reference for every open case, already
 * sorted by priority then age by the backend (AC1, `escalation_service`'s
 * `_PRIORITY_ORDER`) -- this screen never re-sorts. Selecting a row opens
 * the case's Customer 360 (AC2); that screen's own AI/deterministic panels
 * already surface the account's escalation status (E4-S2 AC3's "Escalated -
 * human review badge"), so no extra escalation-context payload needs to be
 * threaded through the navigation here.
 *
 * Reachable only via `RequireCapability capability="escalation:review"` in
 * `router.tsx` -- `escalation:review` is COLLECTIONS_OFFICER-only in
 * `rbac.CAPABILITY_MATRIX` (unlike `escalation:read`, which
 * COMPLIANCE_RISK also holds for a future review-queue screen), so this
 * component never mounts -- and never fires `useEscalationsQuery`'s
 * request -- for any other persona (AC3).
 */
export function EscalationsScreen(): JSX.Element {
  const navigate = useNavigate();
  const { status, data, errorMessage, refetch } = useEscalationsQuery();
  const columns = buildColumns();

  return (
    <div className="pagehead-wrap">
      <div className="pagehead">
        <div>
          <h1>Escalations</h1>
          <p className="muted">Cases needing officer attention now, sorted by priority then age.</p>
        </div>
      </div>

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
          onRowClick={(row) => navigate(row.customer_360_path)}
        />
      )}
    </div>
  );
}
