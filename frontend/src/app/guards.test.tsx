import { render, screen } from "@testing-library/react";
import { useEffect } from "react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { clearSession, setSession } from "../auth/sessionStore";
import { RequireCapability } from "./guards";

const fetchRestrictedData = vi.fn();

function RestrictedScreen(): JSX.Element {
  useEffect(() => {
    fetchRestrictedData();
  }, []);
  return <p>Restricted portfolio data</p>;
}

function renderAt(path: string, element: JSX.Element) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path={path} element={element} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("RequireCapability", () => {
  afterEach(() => {
    clearSession();
    fetchRestrictedData.mockClear();
  });

  it("renders the guarded screen and lets it fetch when the persona holds the capability", () => {
    setSession({
      persona: "COLLECTIONS_OFFICER",
      customer_id: null,
      display_name: "Collections Officer",
      capabilities: ["portfolio:read"],
      demo_label: "Demo persona - not real authentication",
      session_token: null,
      issued_at: "2026-10-01T14:30:00Z",
    });

    renderAt(
      "/portfolio",
      <RequireCapability capability="portfolio:read">
        <RestrictedScreen />
      </RequireCapability>,
    );

    expect(screen.getByText("Restricted portfolio data")).toBeInTheDocument();
    expect(fetchRestrictedData).toHaveBeenCalledTimes(1);
  });

  it("shows the forbidden page and never mounts the guarded screen when the capability is missing", () => {
    setSession({
      persona: "COLLECTIONS_MANAGER",
      customer_id: null,
      display_name: "Collections Manager",
      capabilities: ["kpi:read"],
      demo_label: "Demo persona - not real authentication",
      session_token: null,
      issued_at: "2026-10-01T14:30:00Z",
    });

    renderAt(
      "/portfolio",
      <RequireCapability capability="portfolio:read">
        <RestrictedScreen />
      </RequireCapability>,
    );

    expect(screen.getByRole("alert")).toBeInTheDocument();
    expect(screen.queryByText("Restricted portfolio data")).not.toBeInTheDocument();
    expect(fetchRestrictedData).not.toHaveBeenCalled();
  });

  it("shows the forbidden page when there is no session at all yet", () => {
    renderAt(
      "/portfolio",
      <RequireCapability capability="portfolio:read">
        <RestrictedScreen />
      </RequireCapability>,
    );

    expect(screen.getByRole("alert")).toBeInTheDocument();
    expect(fetchRestrictedData).not.toHaveBeenCalled();
  });
});
