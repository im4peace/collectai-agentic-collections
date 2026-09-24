import { getSession } from "../auth/sessionStore";
import { toApiError } from "./errors";
import type {
  CollectionStatus,
  PortfolioPage,
  PriorityBand,
  SessionCreateRequest,
  SessionInfo,
  SessionOptionsResponse,
} from "./types";

const PERSONA_HEADER = "X-Persona";
const DEMO_SESSION_HEADER = "X-Demo-Session";

/**
 * Minimal typed fetch wrapper for the backend's session endpoints
 * (`GET /api/session/options`, `POST /api/session`, `GET /api/session/me`).
 * Attaches `X-Persona`/`X-Demo-Session` automatically from the current
 * `auth` session, matching `api/deps.py`'s `_read_persona_header` and
 * `_resolve_customer_session` exactly: every persona sends `X-Persona`,
 * and only CUSTOMER additionally sends `X-Demo-Session`. Kept intentionally
 * narrow to this story's three endpoints; later stories extend it rather
 * than reusing it for unrelated routes.
 */
function personaHeaders(): HeadersInit {
  const session = getSession();
  if (session === null) {
    return {};
  }
  const headers: Record<string, string> = { [PERSONA_HEADER]: session.persona };
  if (session.persona === "CUSTOMER" && session.sessionToken !== null) {
    headers[DEMO_SESSION_HEADER] = session.sessionToken;
  }
  return headers;
}

async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`/api${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...personaHeaders(),
      ...init?.headers,
    },
  });
  if (!response.ok) {
    throw await toApiError(response);
  }
  return (await response.json()) as T;
}

export function getSessionOptions(): Promise<SessionOptionsResponse> {
  return apiFetch<SessionOptionsResponse>("/session/options");
}

export function createSession(body: SessionCreateRequest): Promise<SessionInfo> {
  return apiFetch<SessionInfo>("/session", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function getSessionMe(): Promise<SessionInfo> {
  return apiFetch<SessionInfo>("/session/me");
}

/**
 * Query params for `GET /api/portfolio`, kept in the same snake_case shape
 * as the URL query string itself (E3-S3's `usePortfolioUrlState` derives
 * this directly from `useSearchParams`, so there is exactly one place that
 * translates filter/sort state into request shape).
 */
export interface PortfolioQueryParams {
  dpd_min?: number;
  dpd_max?: number;
  priority_band?: PriorityBand[];
  status?: CollectionStatus[];
  sort_by?: "overdue_amount" | "dpd" | "priority_score";
  sort_dir?: "asc" | "desc";
  limit?: number;
  offset?: number;
}

function buildPortfolioQuery(params: PortfolioQueryParams): string {
  const query = new URLSearchParams();
  if (params.dpd_min !== undefined) {
    query.set("dpd_min", String(params.dpd_min));
  }
  if (params.dpd_max !== undefined) {
    query.set("dpd_max", String(params.dpd_max));
  }
  for (const band of params.priority_band ?? []) {
    query.append("priority_band", band);
  }
  for (const status of params.status ?? []) {
    query.append("status", status);
  }
  if (params.sort_by !== undefined) {
    query.set("sort_by", params.sort_by);
  }
  if (params.sort_dir !== undefined) {
    query.set("sort_dir", params.sort_dir);
  }
  if (params.limit !== undefined) {
    query.set("limit", String(params.limit));
  }
  if (params.offset !== undefined) {
    query.set("offset", String(params.offset));
  }
  return query.toString();
}

/** `GET /api/portfolio` (COLLECTIONS_OFFICER only, capability
 * `portfolio:read`). May reject with `ApiError` whose `body.code` is
 * `"POLICY_UNAVAILABLE"` (503, fail-closed with no active policy) -- a
 * distinct case from any other `ApiError`, per CLAUDE.md's human-in-the-loop
 * and fail-closed guidance. */
export function getPortfolio(params: PortfolioQueryParams = {}): Promise<PortfolioPage> {
  const queryString = buildPortfolioQuery(params);
  return apiFetch<PortfolioPage>(queryString === "" ? "/portfolio" : `/portfolio?${queryString}`);
}
