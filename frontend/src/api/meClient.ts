import { apiFetch } from "./client";
import type { CustomerAccountPage } from "./meTypes";

/** `GET /api/me/accounts` (CUSTOMER, capability `self:read`). Used by the
 * Chat screen to auto-select the customer's account before starting a
 * conversation (E6-S5's simplified account-selection step -- see the
 * story's handback notes). */
export function getMyAccounts(): Promise<CustomerAccountPage> {
  return apiFetch<CustomerAccountPage>("/me/accounts");
}
