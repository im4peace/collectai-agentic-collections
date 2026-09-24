import { createBrowserRouter, useLocation } from "react-router-dom";

import { AuditTrailViewer } from "../features/audit/AuditTrailViewer";
import { ChatScreen } from "../features/chat/ChatScreen";
import { Customer360Screen } from "../features/customer360/Customer360Screen";
import { EscalationsScreen } from "../features/escalations/EscalationsScreen";
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
 * created in the first place. Every other route is a guarded slot; Groups
 * E3-S3, E4-S2, E6-S5, E9-S2 and E7-S6 have all replaced their `RouteStub`
 * with a real screen. Only `/dashboard` (E10-S4) and `/compliance-review`
 * (E7-S5) remain stubs, for stories not yet built.
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
            <Customer360Screen />
          </RequireCapability>
        ),
      },
      {
        path: "/escalations",
        element: (
          <RequireCapability capability="escalation:review">
            <EscalationsScreen />
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
            <AuditTrailViewer />
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
            <ChatScreen />
          </RequireCapability>
        ),
      },
    ],
  },
]);
