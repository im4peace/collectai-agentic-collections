import { NavLink } from "react-router-dom";

import { DemoLabelChip } from "../../auth/demoLabel";
import { useSession } from "../../auth/sessionStore";
import { navLinksForCapabilities } from "../../lib/navLinks";
import { useDemoControlsEnabled } from "./useDemoControlsEnabled";

/**
 * The app shell header shared by `CustomerLayout` and `InternalLayout`
 * (AC2, AC4, AC5). Navigation links are derived purely from the current
 * session's `capabilities` (`lib/navLinks.ts`), never from the persona name
 * directly, so this can never drift from what the API actually allows.
 * `NavLink` sets `aria-current="page"` on the active route automatically.
 * The one exception to "capabilities only" is the "Demo controls" link, which
 * also needs the API's demo-controls flag (`useDemoControlsEnabled`).
 */
export function AppBar(): JSX.Element {
  const session = useSession();
  const demoControlsEnabled = useDemoControlsEnabled();
  const links = navLinksForCapabilities(session?.capabilities ?? [], { demoControlsEnabled });
  const personaText = session ? `Current persona: ${session.displayName}` : "Current persona: none selected";

  return (
    <header className="appbar">
      <div className="brand">
        <span aria-hidden="true">&#9670;</span> CollectAI
      </div>
      <nav aria-label="Main navigation">
        {links.map((link) => (
          <NavLink key={link.path} to={link.path}>
            {link.label}
          </NavLink>
        ))}
      </nav>
      <div className="who">
        <DemoLabelChip />
        <span role="status" aria-live="polite" aria-atomic="true">
          {personaText}
        </span>
      </div>
    </header>
  );
}
