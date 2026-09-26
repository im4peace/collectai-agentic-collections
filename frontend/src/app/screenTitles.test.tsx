import { render, waitFor } from "@testing-library/react";
import type { ReactElement } from "react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { clearSession, setSession } from "../auth/sessionStore";
import { AuditTrailViewer } from "../features/audit/AuditTrailViewer";
import { ChatScreen } from "../features/chat/ChatScreen";
import { Customer360Screen } from "../features/customer360/Customer360Screen";
import { DashboardScreen } from "../features/dashboard/DashboardScreen";
import { DemoControlsScreen } from "../features/demo-controls/DemoControlsScreen";
import { EscalationCaseDetailScreen } from "../features/escalations/EscalationCaseDetailScreen";
import { EscalationsScreen } from "../features/escalations/EscalationsScreen";
import { PortfolioScreen } from "../features/portfolio/PortfolioScreen";
import { PersonaSwitcher } from "../features/session/PersonaSwitcher";
import { ForbiddenPage } from "./ForbiddenPage";

// Every screen sets its title on mount, before any data arrives, so the API is
// never allowed to answer: each request stays pending.
vi.mock("../api/client", () => {
  const pending = (): Promise<never> => new Promise(() => undefined);
  return {
    apiFetch: pending,
    getPortfolio: pending,
    getSessionOptions: pending,
    createSession: pending,
    getSessionMe: pending,
  };
});

afterEach(() => {
  clearSession();
  document.title = "";
});

const SCREENS: { name: string; path: string; entry: string; element: ReactElement; title: string }[] = [
  { name: "Persona switcher", path: "/", entry: "/", element: <PersonaSwitcher />, title: "Persona Switcher | CollectAI" },
  { name: "Portfolio", path: "/portfolio", entry: "/portfolio", element: <PortfolioScreen />, title: "Portfolio | CollectAI" },
  { name: "Customer 360", path: "/customers/:customerId", entry: "/customers/acc_000123", element: <Customer360Screen />, title: "Customer 360 | CollectAI" },
  { name: "Escalations", path: "/escalations", entry: "/escalations", element: <EscalationsScreen />, title: "Escalations | CollectAI" },
  { name: "Escalation case", path: "/escalations/:caseId", entry: "/escalations/esc_000001", element: <EscalationCaseDetailScreen />, title: "Escalation Case | CollectAI" },
  { name: "Audit trail", path: "/audit", entry: "/audit", element: <AuditTrailViewer />, title: "Audit Trail | CollectAI" },
  { name: "Dashboard", path: "/dashboard", entry: "/dashboard", element: <DashboardScreen />, title: "Dashboard | CollectAI" },
  { name: "Chat", path: "/chat", entry: "/chat", element: <ChatScreen />, title: "Chat | CollectAI" },
  { name: "Demo controls", path: "/demo-controls", entry: "/demo-controls", element: <DemoControlsScreen />, title: "Demo Controls | CollectAI" },
  { name: "Forbidden page", path: "/dashboard", entry: "/dashboard", element: <ForbiddenPage persona="CUSTOMER" route="/dashboard" />, title: "Forbidden | CollectAI" },
];

describe("every screen exposes a meaningful document title (E11-S6 F-01)", () => {
  for (const screen of SCREENS) {
    it(`${screen.name}: "${screen.title}"`, async () => {
      setSession({
        persona: "COLLECTIONS_OFFICER",
        customer_id: null,
        display_name: "Officer",
        capabilities: [],
        demo_label: "Demo persona - not real authentication",
        session_token: null,
        issued_at: "2026-10-01T14:30:00Z",
      });
      render(
        <MemoryRouter initialEntries={[screen.entry]}>
          <Routes>
            <Route path={screen.path} element={screen.element} />
          </Routes>
        </MemoryRouter>,
      );

      await waitFor(() => expect(document.title).toBe(screen.title));
    });
  }

  it("no two screens share a title", () => {
    const titles = SCREENS.map((screen) => screen.title);

    expect(new Set(titles).size).toBe(titles.length);
  });
});
