import { Badge } from "../../components/Badge";
import { DataTable } from "../../components/DataTable";
import { MoneyText } from "../../components/MoneyText";
import type { DelinquentItem } from "../../api/customer360Types";
import { ITEM_KIND_LABELS, ITEM_STATUS_LABELS } from "./customer360Labels";

export interface ItemsPanelProps {
  items: DelinquentItem[];
}

/** The account's delinquent line items (AC1): installments, statement
 * cycles and fees, each flagged when disputed (never color alone). */
export function ItemsPanel({ items }: ItemsPanelProps): JSX.Element {
  if (items.length === 0) {
    return (
      <section className="panel" aria-labelledby="items-heading">
        <h2 id="items-heading">Delinquent items</h2>
        <div className="empty" role="status">
          No delinquent items on this account.
        </div>
      </section>
    );
  }

  return (
    <section className="panel" aria-labelledby="items-heading">
      <h2 id="items-heading">Delinquent items</h2>
      <DataTable
        columns={[
          { key: "label", header: "Item", renderCell: (row) => row.label },
          { key: "kind", header: "Kind", renderCell: (row) => ITEM_KIND_LABELS[row.kind] },
          {
            key: "amount_outstanding",
            header: "Outstanding",
            align: "right",
            renderCell: (row) => <MoneyText amount={row.amount_outstanding} />,
          },
          {
            key: "due_date",
            header: "Due",
            // A date-only field (no time component on the wire), unlike
            // this screen's other timestamp fields -- rendered as-is
            // rather than through `formatDateTime`, which would invent a
            // GST time of day that was never part of the data.
            renderCell: (row) => row.due_date,
          },
          { key: "status", header: "Status", renderCell: (row) => ITEM_STATUS_LABELS[row.status] },
          {
            key: "disputed",
            header: "Disputed",
            renderCell: (row) =>
              row.disputed ? <Badge text="Disputed" variant="warn" /> : <Badge text="Not disputed" variant="neutral" />,
          },
        ]}
        rows={items}
        getRowKey={(row) => row.item_id}
        caption={`${items.length} delinquent items`}
      />
    </section>
  );
}
