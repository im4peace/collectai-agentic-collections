import { Badge } from "../../components/Badge";
import { MoneyText } from "../../components/MoneyText";
import type { AccountBlock, EscalationBlock, ProfileBlock } from "../../api/customer360Types";
import { ACCOUNT_TYPE_LABELS, BUCKET_LABELS, formatStatusLabel, humanize } from "./customer360Labels";

export interface ProfileAccountPanelProps {
  profile: ProfileBlock;
  account: AccountBlock;
  escalation: EscalationBlock;
}

/** Profile identity, account summary and the escalation badge (AC1, AC5):
 * the top-of-screen "who is this and what is the current state" panel. A
 * vulnerability flag is always shown as text, never color alone, per this
 * codebase's accessibility convention (`Badge`'s own contract). */
export function ProfileAccountPanel({ profile, account, escalation }: ProfileAccountPanelProps): JSX.Element {
  return (
    <section className="panel" aria-labelledby="profile-heading">
      <div className="ph">
        <h2 id="profile-heading">{profile.display_name}</h2>
        <div className="row">
          {escalation.badge !== null && <Badge text={escalation.badge} variant="danger" icon="!" />}
          {profile.vulnerability_flag && (
            <Badge
              text={
                profile.vulnerability_category !== null
                  ? `Vulnerable customer - ${humanize(profile.vulnerability_category)}`
                  : "Vulnerable customer"
              }
              variant="warn"
            />
          )}
        </div>
      </div>
      <div className="row">
        <span className="small muted">{profile.customer_id}</span>
        <span className="small muted mono">{account.account_id}</span>
        <span className="small muted">{profile.email}</span>
        <span className="small muted">{profile.phone}</span>
      </div>
      <div className="row" style={{ marginTop: 10 }}>
        <div className="f">
          <span className="small muted">Product</span>
          <strong>
            {ACCOUNT_TYPE_LABELS[account.account_type]} - {account.product_name}
          </strong>
        </div>
        <div className="f">
          <span className="small muted">Outstanding balance</span>
          <strong>
            <MoneyText amount={account.outstanding_balance} />
          </strong>
        </div>
        <div className="f">
          <span className="small muted">Overdue amount</span>
          <strong>
            <MoneyText amount={account.overdue_amount} />
          </strong>
        </div>
        <div className="f">
          <span className="small muted">DPD / Bucket</span>
          <strong>
            {account.dpd} ({BUCKET_LABELS[account.bucket]})
          </strong>
        </div>
        <div className="f">
          <span className="small muted">Collection status</span>
          <strong>{formatStatusLabel(account.collection_status)}</strong>
        </div>
      </div>
    </section>
  );
}
