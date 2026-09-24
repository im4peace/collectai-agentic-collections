import { render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { App } from "./App";
import { clearSession } from "./auth/sessionStore";

describe("App", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ personas: [], demo_customers: [] }), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
      ),
    );
  });

  afterEach(() => {
    clearSession();
    vi.unstubAllGlobals();
  });

  it("renders the router-driven shell without crashing", async () => {
    render(<App />);
    expect(await screen.findByText("CollectAI")).toBeInTheDocument();
  });

  it("always shows the demo persona disclosure (AC4)", async () => {
    render(<App />);
    expect(await screen.findByText("Demo persona - not real authentication")).toBeInTheDocument();
  });

  it("lands on the persona switcher at the default route", async () => {
    render(<App />);
    expect(await screen.findByRole("heading", { name: "Persona switcher" })).toBeInTheDocument();
  });
});
