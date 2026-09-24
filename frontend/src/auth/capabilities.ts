import type { SessionState } from "./sessionStore";

/**
 * Whether the current demo session holds `capability`. Mirrors
 * `backend/src/collectai/api/rbac.py::is_capability_allowed` client-side so
 * navigation and route guards match what the API will actually allow — but
 * this check is advisory only (AC2/AC3's UI concern); the API re-checks
 * every request regardless (CLAUDE.md: never trust the client for
 * authorization).
 */
export function hasCapability(session: SessionState | null, capability: string): boolean {
  return session !== null && session.capabilities.includes(capability);
}
