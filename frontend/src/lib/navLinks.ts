/**
 * Route -> capability -> nav label table (AC2), matching the route table in
 * `specs/stories/E3-S4.md`'s teammate brief exactly, which in turn mirrors
 * `backend/src/collectai/api/rbac.py`'s `CAPABILITY_MATRIX`. A single
 * source of truth here means the nav can never show a link the API would
 * 403, or hide one the API allows: whether a link appears is always
 * `capabilities.includes(link.capability)`, nothing persona-name-specific.
 *
 * COLLECTIONS_OFFICER and COMPLIANCE_RISK both hold `escalation:read`
 * (E7-S3 AC6): the "Escalations" link is gated on that shared capability,
 * not `escalation:review` (COLLECTIONS_OFFICER-only), so both personas see
 * it and land on the one screen, which branches its own queue scope and
 * action controls by persona -- see `router.tsx`'s own note on this.
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
  /** Shown only while the API's demo-controls flag is on (E9-S3 AC1). The flag
   * is not part of the session, so the caller passes it in (see
   * `navLinksForCapabilities`); the capability alone is never enough. */
  requiresDemoControls?: boolean;
}

export const NAV_LINKS: readonly NavLinkConfig[] = [
  { label: "Chat", path: "/chat", capability: "chat:use" },
  { label: "Portfolio", path: "/portfolio", capability: "portfolio:read" },
  // Demo shortcut: the real entry point is a row click on /portfolio
  // (E3-S3), which will carry a real customer id. This nav item exists so
  // COLLECTIONS_OFFICER always has a direct link, per AC2.
  { label: "Customer 360", path: "/customers/acc_000123", capability: "customer360:read" },
  { label: "Escalations", path: "/escalations", capability: "escalation:read" },
  { label: "Dashboard", path: "/dashboard", capability: "kpi:read" },
  { label: "Audit Trail", path: "/audit", capability: "audit:read" },
  // Last, so it never becomes an officer's default landing route. Hidden
  // unless the demo-controls flag is on (E9-S3 AC1: no dead link when off).
  {
    label: "Demo controls",
    path: "/demo-controls",
    capability: "demo_controls:use",
    requiresDemoControls: true,
  },
] as const;

export interface NavLinkOptions {
  /** Whether the API's demo-controls flag is on. Defaults to false, so a
   * caller that does not know the flag never offers the link. */
  demoControlsEnabled?: boolean;
}

export function navLinksForCapabilities(
  capabilities: readonly string[],
  options: NavLinkOptions = {},
): NavLinkConfig[] {
  return NAV_LINKS.filter(
    (link) =>
      capabilities.includes(link.capability) &&
      (link.requiresDemoControls !== true || options.demoControlsEnabled === true),
  );
}

/** Where the persona switcher sends a persona after a successful submit:
 * that persona's first permitted nav link, or `/` if it somehow has none. */
export function defaultRouteForCapabilities(capabilities: readonly string[]): string {
  const [first] = navLinksForCapabilities(capabilities);
  return first?.path ?? "/";
}
