import { Link, useNavigate } from "react-router-dom";

import type { DataTableAriaSort, DataTableColumn } from "../../components/DataTable";
import { DataTable } from "../../components/DataTable";
import { Badge } from "../../components/Badge";
import { MoneyText } from "../../components/MoneyText";
import type { CollectionStatus, PortfolioItem, PriorityBand } from "../../api/types";
import { COLLECTION_STATUSES, PRIORITY_BANDS } from "../../api/types";
import {
  ACCOUNT_TYPE_LABELS,
  BUCKET_LABELS,
  formatStatusLabel,
  PRIORITY_BAND_DISPLAY,
} from "./portfolioLabels";
import type { PortfolioSortBy, PortfolioUrlState } from "./usePortfolioUrlState";
import { usePortfolioUrlState } from "./usePortfolioUrlState";
import { usePortfolioQuery } from "./usePortfolioQuery";

/** AC3: `aria-sort` for a sortable column, derived from the URL sort state
 * -- `"none"` for every column except the one currently active. */
function ariaSortFor(state: PortfolioUrlState, column: PortfolioSortBy): DataTableAriaSort {
  if (state.sortBy !== column) {
    return "none";
  }
  return state.sortDir === "asc" ? "ascending" : "descending";
}

function toggleInList<T extends string>(list: T[], value: T): T[] {
  return list.includes(value) ? list.filter((item) => item !== value) : [...list, value];
}

function buildColumns(
  state: PortfolioUrlState,
  setSortColumn: (column: PortfolioSortBy) => void,
): DataTableColumn<PortfolioItem>[] {
  return [
    {
      key: "customer",
      header: "Customer",
      renderCell: (row) => (
        // AC4: a real focusable link, not just the row's pointer-only
        // onClick (DataTable's own docstring: a <tr> click handler alone
        // is not keyboard operable) -- so Tab + Enter reaches Customer 360
        // exactly like a mouse click on the row does.
        <Link to={`/customers/${row.account_id}`}>
          <strong>{row.customer_name}</strong>
          <br />
          <span className="small muted mono">{row.account_id}</span>
        </Link>
      ),
    },
    {
      key: "account_type",
      header: "Product type",
      renderCell: (row) => ACCOUNT_TYPE_LABELS[row.account_type],
    },
    {
      key: "outstanding_balance",
      header: "Balance",
      align: "right",
      renderCell: (row) => <MoneyText amount={row.outstanding_balance} />,
    },
    {
      key: "overdue_amount",
      header: "Overdue",
      align: "right",
      sortable: true,
      ariaSort: ariaSortFor(state, "overdue_amount"),
      onSort: () => setSortColumn("overdue_amount"),
      renderCell: (row) => <MoneyText amount={row.overdue_amount} />,
    },
    {
      key: "dpd",
      header: "DPD",
      align: "right",
      sortable: true,
      ariaSort: ariaSortFor(state, "dpd"),
      onSort: () => setSortColumn("dpd"),
      renderCell: (row) => row.dpd,
    },
    {
      key: "bucket",
      header: "Bucket",
      renderCell: (row) => BUCKET_LABELS[row.bucket],
    },
    {
      key: "collection_status",
      header: "Status",
      renderCell: (row) => formatStatusLabel(row.collection_status),
    },
    {
      key: "priority_band",
      header: "Priority",
      renderCell: (row) => {
        const display = PRIORITY_BAND_DISPLAY[row.priority_band];
        return <Badge text={display.label} variant={display.variant} icon={display.icon} />;
      },
    },
  ];
}

function PriorityBandFilter({
  state,
  setPriorityBands,
}: {
  state: PortfolioUrlState;
  setPriorityBands: (bands: PriorityBand[]) => void;
}): JSX.Element {
  return (
    <fieldset>
      <legend>Priority band</legend>
      <div className="checks">
        {PRIORITY_BANDS.map((band) => (
          <label key={band}>
            <input
              type="checkbox"
              checked={state.priorityBands.includes(band)}
              onChange={() => setPriorityBands(toggleInList(state.priorityBands, band))}
            />
            {PRIORITY_BAND_DISPLAY[band].label}
          </label>
        ))}
      </div>
    </fieldset>
  );
}

function StatusFilter({
  state,
  setStatuses,
}: {
  state: PortfolioUrlState;
  setStatuses: (statuses: CollectionStatus[]) => void;
}): JSX.Element {
  return (
    <fieldset>
      <legend>Status</legend>
      <div className="checks">
        {COLLECTION_STATUSES.map((status) => (
          <label key={status}>
            <input
              type="checkbox"
              checked={state.statuses.includes(status)}
              onChange={() => setStatuses(toggleInList(state.statuses, status))}
            />
            {formatStatusLabel(status)}
          </label>
        ))}
      </div>
    </fieldset>
  );
}

/**
 * The Portfolio screen (E3-S3): officer-facing table of delinquent accounts
 * with filter/sort synced to the URL (AC2, AC3) and a priority band shown
 * as text-plus-color (AC1, `portfolioLabels.PRIORITY_BAND_DISPLAY`).
 * Selecting a row navigates to Customer 360 (AC4); `DataTable`'s row click
 * is pointer-only, so the account id is also a real focusable link for
 * keyboard/screen-reader users. Reachable only via `RequireCapability`
 * (`portfolio:read`), so it never mounts -- and never fires
 * `usePortfolioQuery`'s request -- for a persona that cannot see it.
 */
export function PortfolioScreen(): JSX.Element {
  const navigate = useNavigate();
  const { state, setDpdMin, setDpdMax, setPriorityBands, setStatuses, setSortColumn, clearFilters } =
    usePortfolioUrlState();
  const { status, data, errorMessage, refetch } = usePortfolioQuery(state);

  const hasActiveFilters =
    state.dpdMin !== "" ||
    state.dpdMax !== "" ||
    state.priorityBands.length > 0 ||
    state.statuses.length > 0;

  const columns = buildColumns(state, setSortColumn);

  return (
    <div className="pagehead-wrap">
      <div className="pagehead">
        <div>
          <h1>Delinquent portfolio</h1>
          <p className="muted">Accounts requiring collections attention, ranked by priority.</p>
        </div>
      </div>

      <section className="panel" aria-labelledby="portfolio-filters-heading">
        <h2 id="portfolio-filters-heading" className="sr">
          Filters
        </h2>
        <div className="row" style={{ alignItems: "flex-end" }}>
          <label className="f">
            DPD min
            <input
              type="number"
              inputMode="numeric"
              min={0}
              value={state.dpdMin}
              onChange={(event) => setDpdMin(event.target.value)}
              style={{ width: 90 }}
            />
          </label>
          <label className="f">
            DPD max
            <input
              type="number"
              inputMode="numeric"
              min={0}
              value={state.dpdMax}
              onChange={(event) => setDpdMax(event.target.value)}
              style={{ width: 90 }}
            />
          </label>
          <PriorityBandFilter state={state} setPriorityBands={setPriorityBands} />
          <StatusFilter state={state} setStatuses={setStatuses} />
          <button type="button" className="btn secondary" onClick={clearFilters} disabled={!hasActiveFilters}>
            Clear filters
          </button>
        </div>
      </section>

      {status === "loading" && (
        <p role="status" aria-live="polite">
          Loading portfolio&hellip;
        </p>
      )}

      {status === "policy-unavailable" && (
        <div className="banner danger" role="alert">
          <span className="bi" aria-hidden="true">
            &#10007;
          </span>
          <div>
            <strong>No active policy is available.</strong> {errorMessage ?? "Portfolio priority cannot be calculated right now."}{" "}
            <button type="button" className="btn secondary" onClick={refetch}>
              Retry
            </button>
          </div>
        </div>
      )}

      {status === "error" && (
        <div className="banner danger" role="alert">
          <span className="bi" aria-hidden="true">
            &#10007;
          </span>
          <div>
            <strong>The portfolio could not be loaded.</strong> {errorMessage ?? "Please try again."}{" "}
            <button type="button" className="btn secondary" onClick={refetch}>
              Retry
            </button>
          </div>
        </div>
      )}

      {status === "loaded" && data !== null && data.items.length === 0 && (
        <div className="empty" role="status">
          No accounts match the current filters.
        </div>
      )}

      {status === "loaded" && data !== null && data.items.length > 0 && (
        <DataTable
          columns={columns}
          rows={data.items}
          getRowKey={(row) => row.account_id}
          caption={`${data.items.length} of ${data.page.total} accounts, sorted by ${state.sortBy} ${state.sortDir}`}
          onRowClick={(row) => navigate(`/customers/${row.account_id}`)}
        />
      )}
    </div>
  );
}
