import { useState } from "react";

import { Badge } from "../../components/Badge";
import { DataTable } from "../../components/DataTable";
import { MoneyText } from "../../components/MoneyText";
import { formatDateTime } from "../../lib/formatDateTime";
import type { PromiseToPay } from "../../api/domainTypes";
import { PTP_STATUS_DISPLAY } from "./customer360Labels";
import { RecordPtpDialog } from "./RecordPtpDialog";

export interface PtpHistoryPanelProps {
  ptpHistory: PromiseToPay[];
  accountId: string;
  recordVersion: number;
  snapshotAsOf: string | null;
  canRecord: boolean;
  onRecorded: (ptp: PromiseToPay) => void;
}

/** Promise-to-Pay history plus the officer's "Record Promise-to-Pay" action
 * (AC1, AC8). `canRecord` gates the button on the `ptp:record` capability;
 * `RequireCapability` already keeps a non-officer off this whole route, but
 * a future multi-capability persona could still lack `ptp:record`
 * specifically. */
export function PtpHistoryPanel({
  ptpHistory,
  accountId,
  recordVersion,
  snapshotAsOf,
  canRecord,
  onRecorded,
}: PtpHistoryPanelProps): JSX.Element {
  const [dialogOpen, setDialogOpen] = useState(false);

  return (
    <section className="panel" aria-labelledby="ptp-history-heading">
      <div className="ph">
        <h2 id="ptp-history-heading">Promise-to-Pay history</h2>
        {canRecord && (
          <button type="button" className="btn" onClick={() => setDialogOpen(true)}>
            Record Promise-to-Pay
          </button>
        )}
      </div>

      {ptpHistory.length === 0 ? (
        <div className="empty" role="status">
          No promises-to-pay recorded.
        </div>
      ) : (
        <DataTable
          columns={[
            { key: "promised_date", header: "Promised date", renderCell: (row) => row.promised_date },
            {
              key: "promised_amount",
              header: "Promised amount",
              align: "right",
              renderCell: (row) => <MoneyText amount={row.promised_amount} />,
            },
            {
              key: "remaining_amount",
              header: "Remaining",
              align: "right",
              renderCell: (row) => <MoneyText amount={row.remaining_amount} />,
            },
            {
              key: "status",
              header: "Status",
              renderCell: (row) => (
                <Badge text={PTP_STATUS_DISPLAY[row.status].label} variant={PTP_STATUS_DISPLAY[row.status].variant} />
              ),
            },
            { key: "source", header: "Source", renderCell: (row) => row.source.replace(/_/g, " ") },
            { key: "created_at", header: "Created", renderCell: (row) => formatDateTime(row.created_at) },
          ]}
          rows={ptpHistory}
          getRowKey={(row) => row.ptp_id}
          caption={`${ptpHistory.length} promises-to-pay`}
        />
      )}

      <RecordPtpDialog
        isOpen={dialogOpen}
        onClose={() => setDialogOpen(false)}
        accountId={accountId}
        recordVersion={recordVersion}
        snapshotAsOf={snapshotAsOf}
        onRecorded={onRecorded}
      />
    </section>
  );
}
