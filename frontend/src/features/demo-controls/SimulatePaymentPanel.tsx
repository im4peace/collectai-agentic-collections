import { useId, useRef, useState } from "react";
import type { FormEvent } from "react";

import { postSimulatePayment } from "../../api/demoControlsClient";
import type { PaymentOutcome } from "../../api/domainTypes";
import { Badge } from "../../components/Badge";
import { formatMoney } from "../../components/MoneyText";
import { DemoFeedback } from "./DemoFeedback";
import { validateAccountId, validateAmount } from "./demoValidation";
import { useDemoAction } from "./useDemoAction";

type FieldName = "account" | "amount";

/**
 * AC3: records a simulated payment (`source` DEMO_CONTROL, `simulated` true)
 * through the API. The account is a free-text `acc_...` id: the demo state
 * lists no accounts, and picking one is out of scope. The amount stays a
 * decimal string end to end. Each submit sends a fresh `Idempotency-Key`, so
 * two deliberate submits are two payments and a network retry cannot double
 * one. The result always says "Simulated payment": no money ever moves.
 */
export function SimulatePaymentPanel(): JSX.Element {
  const headingId = useId();
  const accountId = useId();
  const amountId = useId();
  const outcomeId = useId();
  const helpId = useId();
  const errorId = useId();
  const [account, setAccount] = useState("");
  const [amount, setAmount] = useState("");
  const [outcome, setOutcome] = useState<PaymentOutcome>("SUCCEEDED");
  const [invalidField, setInvalidField] = useState<FieldName | null>(null);
  const accountRef = useRef<HTMLInputElement>(null);
  const amountRef = useRef<HTMLInputElement>(null);
  const action = useDemoAction();

  function refuse(field: FieldName, message: string): void {
    setInvalidField(field);
    action.fail(message);
    (field === "account" ? accountRef : amountRef).current?.focus();
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    if (action.busy) {
      return;
    }
    const parsedAccount = validateAccountId(account);
    if (!parsedAccount.ok) {
      refuse("account", parsedAccount.message);
      return;
    }
    const parsedAmount = validateAmount(amount);
    if (!parsedAmount.ok) {
      refuse("amount", parsedAmount.message);
      return;
    }
    setInvalidField(null);
    await action.run(
      () =>
        postSimulatePayment(
          { account_id: parsedAccount.value, amount: parsedAmount.value, outcome },
          crypto.randomUUID(),
        ),
      ({ payment_event: event, ptp, replayed }) => (
        <>
          <Badge text={event.simulated_label || "Simulated payment"} variant="info" icon="◇" />{" "}
          {event.outcome === "SUCCEEDED" ? "Succeeded" : "Failed"} payment of{" "}
          {formatMoney(event.amount)} on {event.account_id}. Balance after:{" "}
          {formatMoney(event.balance_after)}.
          {ptp !== null && ` Promise-to-Pay ${ptp.ptp_id} is now ${ptp.status}.`}
          {replayed && " This request was a replay of an earlier one."}
        </>
      ),
    );
  }

  function clearFieldError(): void {
    setInvalidField(null);
    action.clearError();
  }

  return (
    <section className="panel" aria-labelledby={headingId}>
      <div className="ph">
        <h2 id={headingId}>Simulate a payment</h2>
        <Badge text="Simulated" variant="info" icon="◇" />
      </div>
      <form onSubmit={(event) => void handleSubmit(event)} noValidate>
        <div className="row" style={{ alignItems: "flex-end" }}>
          <label className="f" htmlFor={accountId}>
            Account id
            <input
              id={accountId}
              ref={accountRef}
              type="text"
              placeholder="acc_000123"
              autoComplete="off"
              value={account}
              aria-invalid={invalidField === "account"}
              aria-describedby={`${helpId} ${errorId}`}
              onChange={(event) => {
                setAccount(event.target.value);
                clearFieldError();
              }}
              style={{ width: 170 }}
            />
          </label>
          <label className="f" htmlFor={amountId}>
            Amount (AED)
            <input
              id={amountId}
              ref={amountRef}
              type="text"
              inputMode="decimal"
              placeholder="50.00"
              autoComplete="off"
              value={amount}
              aria-invalid={invalidField === "amount"}
              aria-describedby={`${helpId} ${errorId}`}
              onChange={(event) => {
                setAmount(event.target.value);
                clearFieldError();
              }}
              style={{ width: 130 }}
            />
          </label>
          <label className="f" htmlFor={outcomeId}>
            Outcome
            <select
              id={outcomeId}
              value={outcome}
              onChange={(event) => setOutcome(event.target.value as PaymentOutcome)}
            >
              <option value="SUCCEEDED">Succeeded</option>
              <option value="FAILED">Failed</option>
            </select>
          </label>
          <button type="submit" className="btn" aria-disabled={action.busy}>
            {action.busy ? "Recording..." : "Record simulated payment"}
          </button>
        </div>
        <p id={helpId} className="small muted">
          Records a simulated payment event; no real money moves. The amount is at most the
          account&apos;s outstanding balance, with at most 2 decimal places. A successful payment
          can satisfy a pending promise-to-pay.
        </p>
        <DemoFeedback errorId={errorId} error={action.error} notice={action.notice} />
      </form>
    </section>
  );
}
