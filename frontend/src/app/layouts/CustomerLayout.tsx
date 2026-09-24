import { Outlet } from "react-router-dom";

import { AppBar } from "./AppBar";

/**
 * Shell for CUSTOMER-facing screens (currently just `/chat`). Kept as a
 * distinct component from `InternalLayout` so customer and staff screens
 * stay logically separate (story description), even though both currently
 * render the same `AppBar` chrome.
 */
export function CustomerLayout(): JSX.Element {
  return (
    <div className="customer-layout">
      <AppBar />
      <main id="main" tabIndex={-1}>
        <Outlet />
      </main>
    </div>
  );
}
