import { render, renderHook, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Link, MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it } from "vitest";

import { APP_TITLE, SCREEN_TITLES, formatPageTitle, usePageTitle } from "./pageTitle";

afterEach(() => {
  document.title = "";
});

describe("page titles (E11-S6 F-01, WCAG 2.4.2)", () => {
  it("formats every title as '<Screen> | CollectAI'", () => {
    expect(formatPageTitle("Dashboard")).toBe("Dashboard | CollectAI");
    expect(APP_TITLE).toBe("CollectAI");
  });

  it("gives every screen its own, non-empty title, none of them the bare app name", () => {
    const titles = Object.values(SCREEN_TITLES);

    expect(new Set(titles).size).toBe(titles.length);
    for (const title of titles) {
      expect(title.trim()).not.toBe("");
      expect(title).not.toBe(APP_TITLE);
    }
  });

  it("uses the repository's real screen names", () => {
    expect(SCREEN_TITLES).toMatchObject({
      dashboard: "Dashboard",
      portfolio: "Portfolio",
      customer360: "Customer 360",
      escalations: "Escalations",
      escalationCase: "Escalation Case",
      auditTrail: "Audit Trail",
      chat: "Chat",
    });
  });

  it("usePageTitle sets document.title on mount", () => {
    renderHook(() => usePageTitle(SCREEN_TITLES.dashboard));

    expect(document.title).toBe("Dashboard | CollectAI");
  });

  it("navigating between screens updates document.title each time", async () => {
    function Screen({ title }: { title: (typeof SCREEN_TITLES)[keyof typeof SCREEN_TITLES] }): JSX.Element {
      usePageTitle(title);
      return <h1>{title}</h1>;
    }
    render(
      <MemoryRouter initialEntries={["/portfolio"]}>
        <nav>
          <Link to="/portfolio">go portfolio</Link>
          <Link to="/escalations">go escalations</Link>
          <Link to="/audit">go audit</Link>
        </nav>
        <Routes>
          <Route path="/portfolio" element={<Screen title={SCREEN_TITLES.portfolio} />} />
          <Route path="/escalations" element={<Screen title={SCREEN_TITLES.escalations} />} />
          <Route path="/audit" element={<Screen title={SCREEN_TITLES.auditTrail} />} />
        </Routes>
      </MemoryRouter>,
    );
    const user = userEvent.setup();
    expect(document.title).toBe("Portfolio | CollectAI");

    await user.click(screen.getByRole("link", { name: "go escalations" }));
    expect(document.title).toBe("Escalations | CollectAI");

    await user.click(screen.getByRole("link", { name: "go audit" }));
    expect(document.title).toBe("Audit Trail | CollectAI");

    await user.click(screen.getByRole("link", { name: "go portfolio" }));
    expect(document.title).toBe("Portfolio | CollectAI");
  });
});
