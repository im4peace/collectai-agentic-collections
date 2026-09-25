import { apiFetch } from "./client";
import type {
  ComplianceDecisionRequest,
  ComplianceDecisionResult,
  EscalationCaseDetail,
  EscalationPage,
  ReviewDecisionRequest,
  ReviewDecisionResult,
} from "./escalationsTypes";

export interface EscalationListParams {
  queue?: string[];
  status?: string[];
  priority?: string[];
  reason?: string[];
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
 * `escalation:read` -- see `router.tsx`). */
export function getEscalations(params: EscalationListParams = {}): Promise<EscalationPage> {
  const queryString = buildQuery(params);
  return apiFetch<EscalationPage>(queryString === "" ? "/escalations" : `/escalations?${queryString}`);
}

/** `GET /api/escalations/{case_id}` (E7-S3 AC2, same capability/object-level
 * scoping as the list). */
export function getEscalationCaseDetail(caseId: string): Promise<EscalationCaseDetail> {
  return apiFetch<EscalationCaseDetail>(`/escalations/${caseId}`);
}

/** `POST /api/escalations/{case_id}/decisions` (E7-S2, COLLECTIONS_OFFICER
 * only, capability `escalation:review`). Requires a caller-supplied
 * `idempotencyKey`, unique per decision attempt (mirrors `chatClient.
 * confirmProposal`'s own convention). */
export function postReviewDecision(
  caseId: string,
  body: ReviewDecisionRequest,
  idempotencyKey: string,
): Promise<ReviewDecisionResult> {
  return apiFetch<ReviewDecisionResult>(`/escalations/${caseId}/decisions`, {
    method: "POST",
    body: JSON.stringify(body),
    headers: { "Idempotency-Key": idempotencyKey },
  });
}

/** `POST /api/escalations/{case_id}/compliance-decision` (E7-S5,
 * COMPLIANCE_RISK only, capability `compliance:decide`). */
export function postComplianceDecision(
  caseId: string,
  body: ComplianceDecisionRequest,
  idempotencyKey: string,
): Promise<ComplianceDecisionResult> {
  return apiFetch<ComplianceDecisionResult>(`/escalations/${caseId}/compliance-decision`, {
    method: "POST",
    body: JSON.stringify(body),
    headers: { "Idempotency-Key": idempotencyKey },
  });
}
