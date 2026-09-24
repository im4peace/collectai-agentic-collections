import type { DemoCustomer } from "../../api/types";

export interface DemoCustomerSelectProps {
  id: string;
  customers: DemoCustomer[];
  value: string;
  onChange: (customerId: string) => void;
  invalid: boolean;
}

/**
 * AC1: choosing CUSTOMER requires picking one seeded demo customer, whose
 * id the server binds to the session (the browser never sends it again).
 * `aria-required` plus the helper text make that server-side binding
 * explicit to assistive technology.
 */
export function DemoCustomerSelect({
  id,
  customers,
  value,
  onChange,
  invalid,
}: DemoCustomerSelectProps): JSX.Element {
  return (
    <label>
      Demo customer (bound server-side as customer_id)
      <select
        id={id}
        name="customer_id"
        aria-required="true"
        aria-invalid={invalid}
        aria-describedby="demo-customer-help"
        value={value}
        onChange={(event) => onChange(event.target.value)}
      >
        <option value="">Choose a demo customer...</option>
        {customers.map((customer) => (
          <option key={customer.customer_id} value={customer.customer_id}>
            {customer.display_name} - {customer.account_count} account
            {customer.account_count > 1 ? "s" : ""}
          </option>
        ))}
      </select>
      <span id="demo-customer-help">
        The server stores the binding in the demo session. The browser never sends a customer id
        on later calls.
      </span>
    </label>
  );
}
