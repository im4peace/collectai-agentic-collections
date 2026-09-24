import { apiFetch } from "./client";
import type { AuditChainPage, AuditPage } from "./auditTypes";

/** Query params for `GET /api/audit` (api-contracts.md 3.12). At least one
 * of `correlation_id`/`account_id`/`from`/`to` is required -- the backend
 * 422s with `FILTER_REQUIRED` otherwise (`useAuditSearch` never sends a
 * request without one). */
export interface AuditSearchParams {
  correlation_id?: string;
  account_id?: string;
  from?: string;
  to?: string;
  limit?: number;
  offset?: number;
}

// Typed as `object`, not `Record<string, ...>`: `AuditSearchParams`/
// `AuditChainSearchParams` are named interfaces with no index signature, so
// TS would otherwise reject passing them here even though every field is a
// `string | number | undefined`. The cast on the `Object.entries` result
// asserts that shape once, internally, rather than widening either
// interface's public type.
function buildQuery(params: object): string {
  const query = new URLSearchParams();
  const entries = Object.entries(params) as [string, string | number | undefined][];
  for (const [key, value] of entries) {
    if (value !== undefined) {
      query.set(key, String(value));
    }
  }
  return query.toString();
}

/** `GET /api/audit` (COMPLIANCE_RISK, capability `audit:read`). */
export function searchAuditEvents(params: AuditSearchParams): Promise<AuditPage> {
  const queryString = buildQuery(params);
  return apiFetch<AuditPage>(queryString === "" ? "/audit" : `/audit?${queryString}`);
}

export interface AuditChainSearchParams {
  account_id?: string;
  from?: string;
  to?: string;
  limit?: number;
  offset?: number;
}

/** `GET /api/audit/chains` (COMPLIANCE_RISK, capability `audit:read`). */
export function listAuditChains(params: AuditChainSearchParams): Promise<AuditChainPage> {
  const queryString = buildQuery(params);
  return apiFetch<AuditChainPage>(queryString === "" ? "/audit/chains" : `/audit/chains?${queryString}`);
}
