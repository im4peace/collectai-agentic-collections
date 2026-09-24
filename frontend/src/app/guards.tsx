import type { ReactNode } from "react";
import { useLocation } from "react-router-dom";

import { hasCapability } from "../auth/capabilities";
import { useSession } from "../auth/sessionStore";
import { ForbiddenPage } from "./ForbiddenPage";

export interface RequireCapabilityProps {
  capability: string;
  children: ReactNode;
}

/**
 * Route guard (AC3). Renders `children` only when the current persona
 * holds `capability`; otherwise renders `ForbiddenPage` **instead of**
 * `children`. This is the whole mechanism behind AC3's "does not render
 * restricted data": a denied screen's data-fetching component is never
 * mounted, so it never runs its effects or fires a request — there is no
 * request to fail into a 403 after the fact.
 */
export function RequireCapability({ capability, children }: RequireCapabilityProps): JSX.Element {
  const session = useSession();
  const location = useLocation();

  if (!hasCapability(session, capability)) {
    return <ForbiddenPage persona={session?.persona ?? null} route={location.pathname} />;
  }

  return <>{children}</>;
}
