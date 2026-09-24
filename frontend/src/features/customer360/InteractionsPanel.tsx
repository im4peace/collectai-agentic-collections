import { DataTable } from "../../components/DataTable";
import { formatDateTime } from "../../lib/formatDateTime";
import type { Interaction } from "../../api/customer360Types";
import { humanize } from "./customer360Labels";

export interface InteractionsPanelProps {
  interactions: Interaction[];
}

/** Contact history: simulated chat/call/message interactions and system
 * events (AC1). */
export function InteractionsPanel({ interactions }: InteractionsPanelProps): JSX.Element {
  if (interactions.length === 0) {
    return (
      <section className="panel" aria-labelledby="interactions-heading">
        <h2 id="interactions-heading">Interactions</h2>
        <div className="empty" role="status">
          No recorded interactions.
        </div>
      </section>
    );
  }

  return (
    <section className="panel" aria-labelledby="interactions-heading">
      <h2 id="interactions-heading">Interactions</h2>
      <DataTable
        columns={[
          {
            key: "occurred_at",
            header: "When",
            renderCell: (row) => formatDateTime(row.occurred_at),
          },
          { key: "channel", header: "Channel", renderCell: (row) => humanize(row.channel) },
          { key: "direction", header: "Direction", renderCell: (row) => humanize(row.direction) },
          {
            key: "outcome",
            header: "Outcome",
            renderCell: (row) => (row.outcome !== null ? humanize(row.outcome) : "-"),
          },
          { key: "summary", header: "Summary", renderCell: (row) => row.summary },
        ]}
        rows={interactions}
        getRowKey={(row) => row.interaction_id}
        caption={`${interactions.length} interactions`}
      />
    </section>
  );
}
