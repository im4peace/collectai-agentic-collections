import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Badge } from "./Badge";

describe("Badge", () => {
  it("renders the given text with a variant class, for any caller's label (not priority-band-specific)", () => {
    render(<Badge text="In stock" variant="ok" />);
    const badge = screen.getByText("In stock");
    expect(badge).toHaveClass("chip", "ok");
  });

  it("always renders a visible text label alongside color, never color alone", () => {
    render(<Badge text="HIGH priority" variant="danger" icon="▲" />);
    expect(screen.getByText("HIGH priority")).toBeInTheDocument();
  });

  it("marks a decorative icon aria-hidden so it is not announced twice", () => {
    render(<Badge text="Escalated" variant="warn" icon="!" />);
    const icon = screen.getByText("!");
    expect(icon).toHaveAttribute("aria-hidden", "true");
  });

  it("renders with no icon element when none is given", () => {
    const { container } = render(<Badge text="Neutral" variant="neutral" />);
    expect(container.querySelectorAll("[aria-hidden]")).toHaveLength(0);
  });
});
