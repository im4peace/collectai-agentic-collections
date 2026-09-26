/**
 * Client-side checks for the demo-control forms (E9-S3). They mirror what the
 * API enforces (`ClockAdvanceRequest.days` 1-365; `SimulatePaymentRequest`
 * and `demo_service.simulate_payment`'s amount rules) so an obviously bad
 * value is refused before any request is sent. The server stays the
 * authority: these only save a round trip and let the form focus the field.
 * Money is never parsed to a number: a valid amount is returned as the
 * trimmed decimal string.
 */

export type Validation<T> = { ok: true; value: T } | { ok: false; message: string };

const DAYS_MESSAGE = "Enter a whole number of days from 1 to 365.";
export const ACCOUNT_MESSAGE = "Enter an account id such as acc_000123.";

export function validateDays(raw: string): Validation<number> {
  const text = raw.trim();
  if (!/^\d+$/.test(text)) {
    return { ok: false, message: DAYS_MESSAGE };
  }
  const days = Number(text);
  if (days < 1 || days > 365) {
    return { ok: false, message: DAYS_MESSAGE };
  }
  return { ok: true, value: days };
}

export function validateAccountId(raw: string): Validation<string> {
  const text = raw.trim();
  if (!/^acc_[A-Za-z0-9]+$/.test(text)) {
    return { ok: false, message: ACCOUNT_MESSAGE };
  }
  return { ok: true, value: text };
}

export function validateAmount(raw: string): Validation<string> {
  const text = raw.trim();
  if (text.startsWith("-")) {
    return { ok: false, message: "Amount cannot be negative." };
  }
  if (!/^\d+(\.\d+)?$/.test(text)) {
    return { ok: false, message: "Enter an amount as a decimal number, for example 50.00." };
  }
  const decimals = text.includes(".") ? text.split(".")[1].length : 0;
  if (decimals > 2) {
    return { ok: false, message: "Use at most 2 decimal places." };
  }
  if (!/[1-9]/.test(text)) {
    return { ok: false, message: "Amount must be greater than 0.00." };
  }
  return { ok: true, value: text };
}
