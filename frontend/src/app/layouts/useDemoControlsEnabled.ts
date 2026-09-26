import { useEffect, useState } from "react";

import { getDemoState } from "../../api/demoControlsClient";
import { hasCapability } from "../../auth/capabilities";
import { useSession } from "../../auth/sessionStore";

/**
 * Whether the app bar should offer the "Demo controls" link. The link is
 * shown only to a persona that holds `demo_controls:use` (COLLECTIONS_OFFICER)
 * **and** only when the API's demo-controls flag is on, so a default
 * deployment never shows a dead link (E9-S3 AC1).
 *
 * The flag is not part of the session, so this asks the one read-only demo
 * endpoint, `GET /api/demo-controls/state`: success means enabled, and a 404
 * (flag off) or any other failure means "do not show the link". It is never
 * called for a persona without the capability, and it never sends anything
 * but that GET.
 */
export function useDemoControlsEnabled(): boolean {
  const session = useSession();
  const eligible = hasCapability(session, "demo_controls:use");
  const persona = session?.persona ?? null;
  const [enabled, setEnabled] = useState(false);

  useEffect(() => {
    if (!eligible) {
      setEnabled(false);
      return undefined;
    }
    let cancelled = false;
    getDemoState().then(
      () => {
        if (!cancelled) {
          setEnabled(true);
        }
      },
      () => {
        if (!cancelled) {
          setEnabled(false);
        }
      },
    );
    return () => {
      cancelled = true;
    };
  }, [eligible, persona]);

  return eligible && enabled;
}
