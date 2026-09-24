import { Badge } from "../../components/Badge";
import { DataTable } from "../../components/DataTable";
import { MoneyText } from "../../components/MoneyText";
import { formatDateTime } from "../../lib/formatDateTime";
import type { PaymentEvent } from "../../api/domainTypes";

export interface PaymentEventsPanelProps {
  paymentEvents: PaymentEvent[];
}

/** Simulated payment history (E6-S3/E4-S2 AC4): every row is clearly
 * labelled "Simulated payment" -- no real money ever moves in this demo. */
export function PaymentEventsPanel({ paymentEvents }: PaymentEventsPanelProps): JSX.Element {
  if (paymentEvents.length === 0) {
    return (
      <section className="panel" aria-labelledby="payment-events-heading">
        <h2 id="payment-events-heading">Payment events</h2>
        <div className="empty" role="status">
          No payment events recorded.
        </div>
      </section>
    );
  }

  return (
    <section className="panel" aria-labelledby="payment-events-heading">
      <h2 id="payment-events-heading">Payment events</h2>
      <DataTable
        columns={[
          { key: "occurred_at", header: "When", renderCell: (row) => formatDateTime(row.occurred_at) },
          { key: "amount", header: "Amount", align: "right", renderCell: (row) => <MoneyText amount={row.amount} /> },
          {
            key: "outcome",
            header: "Outcome",
            renderCell: (row) => (
              <Badge text={row.outcome === "SUCCEEDED" ? "Succeeded" : "Failed"} variant={row.outcome === "SUCCEEDED" ? "ok" : "danger"} />
            ),
          },
          {
            key: "balance_after",
            header: "Balance after",
            align: "right",
            renderCell: (row) => <MoneyText amount={row.balance_after} />,
          },
          {
            key: "simulated_label",
            header: "Label",
            renderCell: (row) => <Badge text={row.simulated_label} variant="info" />,
          },
        ]}
        rows={paymentEvents}
        getRowKey={(row) => row.payment_event_id}
        caption={`${paymentEvents.length} payment events`}
      />
    </section>
  );
}
