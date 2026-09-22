import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { App } from "./App";

describe("App", () => {
  it("renders the CollectAI heading", () => {
    render(<App />);
    expect(screen.getByRole("heading", { name: "CollectAI" })).toBeInTheDocument();
  });

  it("renders the synthetic-data disclosure", () => {
    render(<App />);
    expect(screen.getByText(/synthetic data only/i)).toBeInTheDocument();
  });
});
