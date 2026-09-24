/**
 * Route -> capability -> nav label table (AC2), matching the route table in
 * `specs/stories/E3-S4.md`'s teammate brief exactly, which in turn mirrors
 * `backend/src/collectai/api/rbac.py`'s `CAPABILITY_MATRIX`. A single
 * source of truth here means the nav can never show a link the API would
 * 403, or hide one the API allows: whether a link appears is always
 * `capabilities.includes(link.capability)`, nothing persona-name-specific.
 *
 * COLLECTIONS_OFFICER and COMPLIANCE_RISK both hold `escalation:read`, but
 * only the officer holds `escalation:review` — the officer's own queue is
 * gated on `escalation:review` here, exactly as the design mockup does, so
 * COMPLIANCE_RISK never sees the officer's link.
 *
 * Pure, framework-free (no React, no `auth` import) so it stays usable from
 * both `app/layouts` and `features/session` without crossing the
 * "features do not import each other" boundary — `features/session` is
 * allowed to import `lib`, not `app`.
 */
export interface NavLinkConfig {
  label: string;
  path: string;
  capability: string;
}

export const NAV_LINKS: readonly NavLinkConfig[] = [
  { label: "Chat", path: "/chat", capability: "chat:use" },
  { label: "Portfolio", path: "/portfolio", capability: "portfolio:read" },
  // Demo shortcut: the real entry point is a row click on /portfolio
  // (E3-S3), which will carry a real customer id. This nav item exists so
  // COLLECTIONS_OFFICER always has a direct link, per AC2.
  { label: "Customer 360", path: "/customers/acc_000123", capability: "customer360:read" },
  { label: "Escalations", path: "/escalations", capability: "escalation:review" },
  { label: "Dashboard", path: "/dashboard", capability: "kpi:read" },
  { label: "Audit Trail", path: "/audit", capability: "audit:read" },
  { label: "Compliance review queue", path: "/compliance-review", capability: "compliance:decide" },
] as const;

export function navLinksForCapabilities(capabilities: readonly string[]): NavLinkConfig[] {
  return NAV_LINKS.filter((link) => capabilities.includes(link.capability));
}

/** Where the persona switcher sends a persona after a successful submit:
 * that persona's first permitted nav link, or `/` if it somehow has none. */
export function defaultRouteForCapabilities(capabilities: readonly string[]): string {
  const [first] = navLinksForCapabilities(capabilities);
  return first?.path ?? "/";
}
