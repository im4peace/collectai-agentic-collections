import { apiFetch } from "./client";
import type { EscalationPage } from "./escalationsTypes";

export interface EscalationListParams {
  status?: string[];
  limit?: number;
  offset?: number;
}

// Typed as `object` -- see `auditClient.ts`'s own `buildQuery` docstring for
// why a named param interface needs this instead of `Record<string, ...>`.
function buildQuery(params: object): string {
  const query = new URLSearchParams();
  const entries = Object.entries(params) as [string, string | string[] | number | undefined][];
  for (const [key, value] of entries) {
    if (value === undefined) continue;
    if (Array.isArray(value)) {
      for (const item of value) query.append(key, item);
    } else {
      query.set(key, String(value));
    }
  }
  return query.toString();
}

/** `GET /api/escalations` (COLLECTIONS_OFFICER/COMPLIANCE_RISK, capability
 * `escalation:read`; this screen is reachable only via `escalation:review`,
 * COLLECTIONS_OFFICER-only -- see `router.tsx`). */
export function getEscalations(params: EscalationListParams = {}): Promise<EscalationPage> {
  const queryString = buildQuery(params);
  return apiFetch<EscalationPage>(queryString === "" ? "/escalations" : `/escalations?${queryString}`);
}
