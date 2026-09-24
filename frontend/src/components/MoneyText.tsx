const MONEY_PATTERN = /^(-?)(\d+)\.(\d{2})$/;

/**
 * `"1234.56"` -> `"AED 1,234.56"`. Ported from the design mockups' `money()`
 * helper (specs/design/mockups/E3-S3.html) so every screen formats a
 * decimal-string money amount the same way. Money is always a 2dp string on
 * the wire (never a float) per api-contracts.md, so this only ever needs to
 * add thousands separators and the currency prefix -- no rounding.
 */
export function formatMoney(amount: string): string {
  const match = MONEY_PATTERN.exec(amount);
  if (match === null) {
    return amount;
  }
  const [, sign, whole, fraction] = match;
  const groupedWhole = whole.replace(/\B(?=(\d{3})+(?!\d))/g, ",");
  return `${sign}AED ${groupedWhole}.${fraction}`;
}

export interface MoneyTextProps {
  /** A 2dp decimal-string money amount, e.g. `"1234.56"` or `"-245.10"`. */
  amount: string;
}

/** Generic money renderer: any screen with a decimal-string money field
 * (Portfolio, Customer 360, Dashboard, ...) uses this, not a bespoke
 * formatter. */
export function MoneyText({ amount }: MoneyTextProps): JSX.Element {
  return <>{formatMoney(amount)}</>;
}
