import { useParams } from "react-router-dom";

import { useSession } from "../../auth/sessionStore";
import { formatDateTime } from "../../lib/formatDateTime";
import { AiPanel } from "./AiPanel";
import { DeterministicPanel } from "./DeterministicPanel";
import { FRESHNESS_DISPLAY } from "./customer360Labels";
import { HardshipDisputesPanel } from "./HardshipDisputesPanel";
import { InteractionsPanel } from "./InteractionsPanel";
import { ItemsPanel } from "./ItemsPanel";
import { PaymentEventsPanel } from "./PaymentEventsPanel";
import { ProfileAccountPanel } from "./ProfileAccountPanel";
import { PtpHistoryPanel } from "./PtpHistoryPanel";
import { useCustomer360Query } from "./useCustomer360Query";

/** E4-S2: the officer-facing Customer 360 screen. Route param is named
 * `customerId` by `app/router.tsx` (`/customers/:customerId`), but the
 * value it carries is an account id (`GET /api/customers/{account_id}/360`)
 * -- matching the Portfolio screen's own row links (`/customers/${row
 * .account_id}`), which this screen is reached from. */
export function Customer360Screen(): JSX.Element {
  const { customerId: accountId } = useParams<{ customerId: string }>();
  const session = useSession();
  const { status, data, errorMessage, refetch } = useCustomer360Query(accountId ?? "");

  if (accountId === undefined) {
    return (
      <div className="banner danger" role="alert">
        <div>No account id was given.</div>
      </div>
    );
  }

  return (
    <div className="pagehead-wrap">
      <div className="pagehead">
        <h1>Customer 360</h1>
      </div>

      {status === "loading" && (
        <p role="status" aria-live="polite">
          Loading customer record&hellip;
        </p>
      )}

      {status === "not-found" && (
        <div className="banner danger" role="alert">
          <div>{errorMessage ?? `No account was found for ${accountId}.`}</div>
        </div>
      )}

      {status === "error" && (
        <div className="banner danger" role="alert">
          <div>
            {errorMessage ?? "This customer's record could not be loaded."}{" "}
            <button type="button" className="btn secondary" onClick={refetch}>
              Retry
            </button>
          </div>
        </div>
      )}

      {status === "loaded" && data !== null && (
        <div className="checks" style={{ flexDirection: "column", alignItems: "stretch", gap: 12 }}>
          {data.snapshot.freshness !== "FRESH" && (
            <div className="banner warn" role="status">
              <div>
                {FRESHNESS_DISPLAY[data.snapshot.freshness].label}
                {data.snapshot.as_of !== null && ` - as of ${formatDateTime(data.snapshot.as_of)}`}.{" "}
                <button type="button" className="btn secondary" onClick={refetch}>
                  Refresh
                </button>
              </div>
            </div>
          )}

          <ProfileAccountPanel profile={data.profile} account={data.account} escalation={data.escalation} />
          <div className="row" style={{ alignItems: "stretch" }}>
            <div style={{ flex: 1, minWidth: 280 }}>
              <DeterministicPanel deterministic={data.deterministic} />
            </div>
            <div style={{ flex: 1, minWidth: 280 }}>
              <AiPanel ai={data.ai} deterministicStatus={data.deterministic.status} />
            </div>
          </div>
          <ItemsPanel items={data.items} />
          <PtpHistoryPanel
            ptpHistory={data.ptp_history}
            accountId={data.account_id}
            recordVersion={data.snapshot.record_version}
            snapshotAsOf={data.snapshot.as_of}
            canRecord={session?.capabilities.includes("ptp:record") ?? false}
            onRecorded={refetch}
          />
          <PaymentEventsPanel paymentEvents={data.payment_events} />
          <InteractionsPanel interactions={data.interactions} />
          <HardshipDisputesPanel hardshipCases={data.hardship_cases} disputes={data.disputes} />
        </div>
      )}
    </div>
  );
}
