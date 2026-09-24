import { apiFetch } from "./client";
import type { Customer360 } from "./customer360Types";

/** `GET /api/customers/{account_id}/360` (COLLECTIONS_OFFICER, capability
 * `customer360:read`). 404s (`ApiError`, `body.code === "NOT_FOUND"`) for an
 * unknown account; otherwise always 200, even when
 * `deterministic.status === "POLICY_UNAVAILABLE"` (E4-S2 AC6). */
export function getCustomer360(accountId: string): Promise<Customer360> {
  return apiFetch<Customer360>(`/customers/${accountId}/360`);
}
