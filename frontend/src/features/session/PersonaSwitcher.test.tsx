import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import * as client from "../../api/client";
import type { SessionInfo, SessionOptionsResponse } from "../../api/types";
import { clearSession, getSession } from "../../auth/sessionStore";
import { PersonaSwitcher } from "./PersonaSwitcher";

vi.mock("../../api/client", () => ({
  getSessionOptions: vi.fn(),
  createSession: vi.fn(),
}));

const OPTIONS: SessionOptionsResponse = {
  personas: [
    {
      persona: "CUSTOMER",
      display_name: "Customer",
      description: "A customer viewing and managing their own account.",
      requires_customer_binding: true,
    },
    {
      persona: "COLLECTIONS_OFFICER",
      display_name: "Collections Officer",
      description: "Works the delinquent portfolio and individual customer accounts.",
      requires_customer_binding: false,
    },
    {
      persona: "COLLECTIONS_MANAGER",
      display_name: "Collections Manager",
      description: "Views collections and AI performance KPIs.",
      requires_customer_binding: false,
    },
    {
      persona: "COMPLIANCE_RISK",
      display_name: "Compliance / Risk",
      description: "Reviews AI-assisted decisions and records compliance decisions.",
      requires_customer_binding: false,
    },
  ],
  demo_customers: [
    { customer_id: "cus_0041", display_name: "Priya Raman", account_count: 1 },
    { customer_id: "cus_0052", display_name: "Marcus Feldman", account_count: 2 },
  ],
};

function renderSwitcher() {
  return render(
    <MemoryRouter>
      <PersonaSwitcher />
    </MemoryRouter>,
  );
}

describe("PersonaSwitcher", () => {
  beforeEach(() => {
    vi.mocked(client.getSessionOptions).mockResolvedValue(OPTIONS);
  });

  afterEach(() => {
    clearSession();
    vi.clearAllMocks();
  });

  it("lists exactly the four required personas, in order, once options load", async () => {
    renderSwitcher();
    const radios = await screen.findAllByRole("radio");
    expect(radios).toHaveLength(4);
    expect(radios.map((radio) => (radio as HTMLInputElement).value)).toEqual([
      "CUSTOMER",
      "COLLECTIONS_OFFICER",
      "COLLECTIONS_MANAGER",
      "COMPLIANCE_RISK",
    ]);
  });

  it("reveals a required demo-customer select only after choosing CUSTOMER", async () => {
    const user = userEvent.setup();
    renderSwitcher();
    expect(screen.queryByRole("combobox")).not.toBeInTheDocument();

    await user.click(await screen.findByRole("radio", { name: /CUSTOMER/ }));

    const select = screen.getByRole("combobox");
    expect(select).toHaveAttribute("aria-required", "true");
  });

  it("blocks submission and shows a validation message when CUSTOMER has no customer chosen", async () => {
    const user = userEvent.setup();
    renderSwitcher();

    await user.click(await screen.findByRole("radio", { name: /CUSTOMER/ }));
    await user.click(screen.getByRole("button", { name: "Use this persona" }));

    expect(
      await screen.findByText(/choose one seeded demo customer before continuing as customer/i),
    ).toBeInTheDocument();
    expect(client.createSession).not.toHaveBeenCalled();
  });

  it("submits CUSTOMER with the chosen customer_id and stores the returned session", async () => {
    const user = userEvent.setup();
    const info: SessionInfo = {
      persona: "CUSTOMER",
      customer_id: "cus_0041",
      display_name: "Priya Raman",
      capabilities: ["chat:use", "self:read", "self:write", "session:read"],
      demo_label: "Demo persona - not real authentication",
      session_token: "raw-token",
      issued_at: "2026-10-01T14:30:00Z",
    };
    vi.mocked(client.createSession).mockResolvedValue(info);
    renderSwitcher();

    await user.click(await screen.findByRole("radio", { name: /CUSTOMER/ }));
    await user.selectOptions(screen.getByRole("combobox"), "cus_0041");
    await user.click(screen.getByRole("button", { name: "Use this persona" }));

    await waitFor(() => {
      expect(client.createSession).toHaveBeenCalledWith({
        persona: "CUSTOMER",
        customer_id: "cus_0041",
      });
    });
    await waitFor(() => expect(getSession()?.customerId).toBe("cus_0041"));
  });

  it("submits a non-CUSTOMER persona without any customer_id field", async () => {
    const user = userEvent.setup();
    const info: SessionInfo = {
      persona: "COLLECTIONS_MANAGER",
      customer_id: null,
      display_name: "Collections Manager",
      capabilities: ["kpi:read", "session:read"],
      demo_label: "Demo persona - not real authentication",
      session_token: null,
      issued_at: "2026-10-01T14:30:00Z",
    };
    vi.mocked(client.createSession).mockResolvedValue(info);
    renderSwitcher();

    await user.click(await screen.findByRole("radio", { name: /COLLECTIONS_MANAGER/ }));
    await user.click(screen.getByRole("button", { name: "Use this persona" }));

    await waitFor(() => {
      expect(client.createSession).toHaveBeenCalledWith({ persona: "COLLECTIONS_MANAGER" });
    });
  });
});
