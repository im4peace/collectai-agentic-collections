import { Outlet } from "react-router-dom";

import { AppBar } from "./AppBar";

/**
 * Shell for staff-facing screens (Portfolio, Customer 360, Escalations,
 * Dashboard, Audit Trail) and the persona switcher itself before any
 * persona is chosen. Kept as a distinct component from
 * `CustomerLayout` so customer and internal navigation stay logically
 * separate (story description).
 */
export function InternalLayout(): JSX.Element {
  return (
    <div className="internal-layout">
      <AppBar />
      <main id="main" tabIndex={-1}>
        <Outlet />
      </main>
    </div>
  );
}
