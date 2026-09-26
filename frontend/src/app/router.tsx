import { createBrowserRouter, useLocation } from "react-router-dom";

import { AuditTrailViewer } from "../features/audit/AuditTrailViewer";
import { ChatScreen } from "../features/chat/ChatScreen";
import { Customer360Screen } from "../features/customer360/Customer360Screen";
import { DashboardScreen } from "../features/dashboard/DashboardScreen";
import { EscalationCaseDetailScreen } from "../features/escalations/EscalationCaseDetailScreen";
import { EscalationsScreen } from "../features/escalations/EscalationsScreen";
import { PersonaSwitcher } from "../features/session/PersonaSwitcher";
import { PortfolioScreen } from "../features/portfolio/PortfolioScreen";
import { useSession } from "../auth/sessionStore";
import { ForbiddenPage } from "./ForbiddenPage";
import { RequireCapability } from "./guards";
import { CustomerLayout } from "./layouts/CustomerLayout";
import { InternalLayout } from "./layouts/InternalLayout";

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
 * E3-S3, E4-S2, E6-S5, E9-S2, E7-S6 and E10-S4 have all replaced their
 * `RouteStub` with a real screen, so no stub route remains.
 *
 * `/escalations` widened from `escalation:review` to `escalation:read` by
 * E7-S3 AC6: COLLECTIONS_OFFICER and COMPLIANCE_RISK share the one screen,
 * which branches its own queue scope and action controls by persona rather
 * than each getting a separate route -- so the `/compliance-review` stub
 * (E7-S5's placeholder) is removed rather than built out; COMPLIANCE_RISK
 * reaches its queue through `/escalations` now. `/escalations/:caseId`
 * (E7-S3 AC2) is the case-detail view; both routes share the same
 * capability so a denied persona never reaches either.
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
          <RequireCapability capability="escalation:read">
            <EscalationsScreen />
          </RequireCapability>
        ),
      },
      {
        path: "/escalations/:caseId",
        element: (
          <RequireCapability capability="escalation:read">
            <EscalationCaseDetailScreen />
          </RequireCapability>
        ),
      },
      {
        path: "/dashboard",
        element: (
          <RequireCapability capability="kpi:read">
            <DashboardScreen />
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
