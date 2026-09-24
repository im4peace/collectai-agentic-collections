import { apiFetch } from "./client";
import type { PromiseToPay } from "./domainTypes";
import type { PtpCreateRequest, PtpValidateRequest, PtpValidationResult } from "./ptpTypes";

/** `POST /api/ptps/validate`: dry-run only, never mutates, no
 * `Idempotency-Key` needed. Always 200; `valid: false` carries
 * `reason_codes`/`alternatives` for the form's live feedback. */
export function validatePtp(body: PtpValidateRequest): Promise<PtpValidationResult> {
  return apiFetch<PtpValidationResult>("/ptps/validate", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

/** `POST /api/ptps` (capability `ptp:record`, officer only). Requires a
 * caller-supplied `idempotencyKey` (e.g. `crypto.randomUUID()`) unique per
 * submission attempt -- retrying the exact same attempt should reuse the
 * same key so a duplicate click never records two PTPs. `record_version`/
 * `snapshot_as_of` in `body` must come from the Customer 360 snapshot
 * currently on screen, never hand-typed (E4-S2 constraint). */
export function createPtp(body: PtpCreateRequest, idempotencyKey: string): Promise<PromiseToPay> {
  return apiFetch<PromiseToPay>("/ptps", {
    method: "POST",
    body: JSON.stringify(body),
    headers: { "Idempotency-Key": idempotencyKey },
  });
}
