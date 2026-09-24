import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";

import { ForbiddenPage } from "./ForbiddenPage";

describe("ForbiddenPage", () => {
  it("is announced as an alert with the 403 heading", () => {
    render(
      <MemoryRouter>
        <ForbiddenPage persona="COLLECTIONS_MANAGER" route="/portfolio" />
      </MemoryRouter>,
    );
    expect(screen.getByRole("alert")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "403 - Forbidden" })).toBeInTheDocument();
  });

  it("states which persona and route were denied", () => {
    render(
      <MemoryRouter>
        <ForbiddenPage persona="COLLECTIONS_MANAGER" route="/portfolio" />
      </MemoryRouter>,
    );
    expect(screen.getByText(/COLLECTIONS_MANAGER/)).toBeInTheDocument();
    expect(screen.getByText(/\/portfolio/)).toBeInTheDocument();
  });

  it("explicitly states that no restricted data was requested", () => {
    render(
      <MemoryRouter>
        <ForbiddenPage persona="COLLECTIONS_MANAGER" route="/portfolio" />
      </MemoryRouter>,
    );
    expect(screen.getByText(/no restricted data was requested/i)).toBeInTheDocument();
  });

  it("falls back to a clear label when no persona has been selected yet", () => {
    render(
      <MemoryRouter>
        <ForbiddenPage persona={null} route="/portfolio" />
      </MemoryRouter>,
    );
    expect(screen.getByText(/no persona selected/i)).toBeInTheDocument();
  });
});
