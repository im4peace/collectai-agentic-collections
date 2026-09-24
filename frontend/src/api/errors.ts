import type { ErrorBody, ErrorEnvelope } from "./types";

/** Narrows an unknown JSON body into an `ErrorEnvelope` (api-contracts.md 1.3). */
function isErrorEnvelope(value: unknown): value is ErrorEnvelope {
  if (typeof value !== "object" || value === null || !("error" in value)) {
    return false;
  }
  const error = (value as { error: unknown }).error;
  return (
    typeof error === "object" &&
    error !== null &&
    "code" in error &&
    "message" in error &&
    "correlation_id" in error
  );
}

/**
 * Typed error for a non-2xx API response. Carries the backend's
 * `ErrorEnvelope` shape (code, reason_code, message, correlation_id,
 * details, ...) so callers can branch on `code`/`reason_code` instead of
 * parsing free-form text (code-gen skill: "typed errors for the API
 * client").
 */
export class ApiError extends Error {
  readonly status: number;
  readonly body: ErrorBody;

  constructor(status: number, body: ErrorBody) {
    super(body.message);
    this.name = "ApiError";
    this.status = status;
    this.body = body;
  }
}

/** A response body that never matched the `ErrorEnvelope` shape at all
 * (network failure, HTML error page, malformed JSON) — distinct from a
 * well-formed `ApiError` so callers never mistake it for one. */
export class UnexpectedApiResponseError extends Error {
  readonly status: number;

  constructor(status: number, rawBody: string) {
    super(`Unexpected response (status ${status}): ${rawBody.slice(0, 200)}`);
    this.name = "UnexpectedApiResponseError";
    this.status = status;
  }
}

export async function toApiError(response: Response): Promise<ApiError | UnexpectedApiResponseError> {
  const rawBody = await response.text();
  let parsed: unknown;
  try {
    parsed = rawBody.length > 0 ? JSON.parse(rawBody) : null;
  } catch {
    return new UnexpectedApiResponseError(response.status, rawBody);
  }
  if (isErrorEnvelope(parsed)) {
    return new ApiError(response.status, parsed.error);
  }
  return new UnexpectedApiResponseError(response.status, rawBody);
}
