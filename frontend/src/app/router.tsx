import { createBrowserRouter, useLocation } from "react-router-dom";

import { PersonaSwitcher } from "../features/session/PersonaSwitcher";
import { PortfolioScreen } from "../features/portfolio/PortfolioScreen";
import { useSession } from "../auth/sessionStore";
import { ForbiddenPage } from "./ForbiddenPage";
import { RequireCapability } from "./guards";
import { CustomerLayout } from "./layouts/CustomerLayout";
import { InternalLayout } from "./layouts/InternalLayout";
import { RouteStub } from "./RouteStub";

/** An unknown path is treated the same as a forbidden one: nothing this
 * persona (or no persona at all) may open, so it gets the same page. */
function NotFoundRoute(): JSX.Element {
  const location = useLocation();
  const session = useSession();
  return <ForbiddenPage persona={session?.persona ?? null} route={location.pathname} />;
}

/**
 * The route table (AC2, AC3), matching `specs/stories/E3-S4.md`'s route ->
 * capability table, which mirrors `backend/src/collectai/api/rbac.py`'s
 * `CAPABILITY_MATRIX`. `/` is the persona switcher and is reachable by
 * everyone (public, no `RequireCapability`) — it is how a fresh session is
 * created in the first place. Every other route is a guarded slot; most
 * still render `RouteStub` (`/portfolio` is E3-S3's real screen; later
 * Group G/H stories replace the rest) — see this story's handback notes
 * for how to plug a real screen in.
 */
export const router = createBrowserRouter([
  {
    element: <InternalLayout />,
    children: [
      { path: "/", element: <PersonaSwitcher /> },
      {
        path: "/portfolio",
        element: (
          <RequireCapability capability="portfolio:read">
            <PortfolioScreen />
          </RequireCapability>
        ),
      },
      {
        path: "/customers/:customerId",
        element: (
          <RequireCapability capability="customer360:read">
            <RouteStub title="Customer 360" />
          </RequireCapability>
        ),
      },
      {
        path: "/escalations",
        element: (
          <RequireCapability capability="escalation:review">
            <RouteStub title="Escalations" />
          </RequireCapability>
        ),
      },
      {
        path: "/dashboard",
        element: (
          <RequireCapability capability="kpi:read">
            <RouteStub title="Dashboard" />
          </RequireCapability>
        ),
      },
      {
        path: "/audit",
        element: (
          <RequireCapability capability="audit:read">
            <RouteStub title="Audit Trail" />
          </RequireCapability>
        ),
      },
      {
        path: "/compliance-review",
        element: (
          <RequireCapability capability="compliance:decide">
            <RouteStub title="Compliance review queue" />
          </RequireCapability>
        ),
      },
      { path: "*", element: <NotFoundRoute /> },
    ],
  },
  {
    element: <CustomerLayout />,
    children: [
      {
        path: "/chat",
        element: (
          <RequireCapability capability="chat:use">
            <RouteStub title="Chat" />
          </RequireCapability>
        ),
      },
    ],
  },
]);
