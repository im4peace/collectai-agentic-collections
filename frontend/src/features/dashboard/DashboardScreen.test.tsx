import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "../../api/errors";
import * as client from "../../api/kpiClient";
import type { Kpi, KpiResponse } from "../../api/kpiTypes";
import { RequireCapability } from "../../app/guards";
import { clearSession, setSession } from "../../auth/sessionStore";
import { DashboardScreen } from "./DashboardScreen";

vi.mock("../../api/kpiClient", () => ({ getKpis: vi.fn(), getEvalRuns: vi.fn() }));

function kpi(overrides: Partial<Kpi>): Kpi {
  return {
    kpi_id: "total_delinquent_accounts",
    name: "Total delinquent accounts",
    definition: "Accounts with an overdue amount.",
    formula: "count(accounts where overdue > 0)",
    data_label: "ILLUSTRATIVE",
    owner_persona: "COLLECTIONS_MANAGER",
    unit: "COUNT",
    value: "1000",
    numerator: null,
    denominator: null,
    sample_size: 1000,
    claim_status: "NOT_APPLICABLE",
    target: null,
    source_note: "Synthetic seed data",
    ...overrides,
  };
}

function response(overrides: Partial<KpiResponse["ai_quality"]> = {}): KpiResponse {
  return {
    generated_at: "2026-10-01T14:30:00Z",
    policy_version: "policy-v1",
    business: [kpi({})],
    operational: [
      kpi({ kpi_id: "review_queue_size", name: "Review queue size", value: "9", data_label: "ILLUSTRATIVE" }),
    ],
    ai_quality: {
      live_run_available: true,
      note: "MOCK results are never evidence of model quality.",
      mock: [
        kpi({
          kpi_id: "intent_classification_accuracy",
          name: "Intent classification accuracy",
          data_label: "MOCK",
          unit: "RATIO",
          value: "0.9400",
          claim_status: "OBSERVATION_ONLY",
          sample_size: 60,
        }),
      ],
      live: [
        kpi({
          kpi_id: "sensitive_category_recall_dispute",
          name: "Sensitive-category recall: Dispute",
          data_label: "LIVE",
          unit: "RATIO",
          value: "0.8333",
          numerator: "5",
          denominator: "6",
          sample_size: 6,
          claim_status: "OBSERVATION_ONLY",
          target: "0.9500",
        }),
        kpi({
          kpi_id: "intent_classification_accuracy",
          name: "Intent classification accuracy",
          data_label: "LIVE",
          unit: "RATIO",
          value: "0.9100",
          sample_size: 200,
          claim_status: "PASS",
          target: "0.9000",
        }),
      ],
      ...overrides,
    },
  };
}

function renderDashboard(): void {
  render(
    <MemoryRouter initialEntries={["/dashboard"]}>
      <Routes>
        <Route
          path="/dashboard"
          element={
            <RequireCapability capability="kpi:read">
              <DashboardScreen />
            </RequireCapability>
          }
        />
      </Routes>
    </MemoryRouter>,
  );
}

function loginAs(persona: string, capabilities: string[]): void {
  setSession({
    persona,
    customer_id: null,
    display_name: persona,
    capabilities,
    demo_label: "Demo persona - not real authentication",
    session_token: null,
    issued_at: "2026-10-01T14:30:00Z",
  } as Parameters<typeof setSession>[0]);
}

beforeEach(() => {
  vi.mocked(client.getEvalRuns).mockResolvedValue({
    items: [],
    page: { limit: 20, offset: 0, total: 0 },
  });
});

afterEach(() => {
  clearSession();
  vi.clearAllMocks();
});

describe("DashboardScreen", () => {
  it("AC1: renders Business, Operational and AI quality and governance as headed sections", async () => {
    loginAs("COLLECTIONS_MANAGER", ["kpi:read"]);
    vi.mocked(client.getKpis).mockResolvedValue(response());
    renderDashboard();

    expect(await screen.findByRole("heading", { level: 2, name: "Business" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 2, name: "Operational" })).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { level: 2, name: "AI quality and governance" }),
    ).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Total delinquent accounts" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Review queue size" })).toBeInTheDocument();
  });

  it("AC2: every tile carries a text badge, and MOCK and LIVE AI tiles are separate", async () => {
    loginAs("COLLECTIONS_MANAGER", ["kpi:read"]);
    vi.mocked(client.getKpis).mockResolvedValue(response());
    renderDashboard();

    const business = await screen.findByRole("heading", { name: "Total delinquent accounts" });
    expect(within(business.closest("article")!).getByText("ILLUSTRATIVE")).toBeInTheDocument();

    const mockSection = screen.getByRole("heading", { name: "MOCK regression results" });
    const liveSection = screen.getByRole("heading", { name: "LIVE evaluation results" });
    expect(mockSection).toBeInTheDocument();
    expect(liveSection).toBeInTheDocument();

    const tiles = screen.getAllByRole("article");
    const mockTiles = tiles.filter((tile) => within(tile).queryByText("MOCK") !== null);
    const liveTiles = tiles.filter((tile) => within(tile).queryByText("LIVE") !== null);
    expect(mockTiles).toHaveLength(1);
    expect(liveTiles).toHaveLength(2);
    for (const tile of mockTiles) {
      expect(within(tile).queryByText("LIVE")).toBeNull();
    }
  });

  it("AC3: a LIVE recall tile under 30 cases says 'observation only' with no percentage or pass/fail", async () => {
    loginAs("COLLECTIONS_MANAGER", ["kpi:read"]);
    vi.mocked(client.getKpis).mockResolvedValue(response());
    renderDashboard();

    const heading = await screen.findByRole("heading", { name: "Sensitive-category recall: Dispute" });
    const tile = heading.closest("article")!;
    expect(within(tile).getByText("Observation only")).toBeInTheDocument();
    expect(within(tile).getByText("observation only")).toBeInTheDocument();
    expect(tile.textContent).not.toMatch(/%/);
    expect(tile.textContent).not.toMatch(/PASS|FAIL/);
    expect(within(tile).getByText(/5 of 6/)).toBeInTheDocument();
  });

  it("a LIVE tile with an allowed claim shows its percentage and a text PASS indicator", async () => {
    loginAs("COLLECTIONS_MANAGER", ["kpi:read"]);
    vi.mocked(client.getKpis).mockResolvedValue(response());
    renderDashboard();

    const heading = await screen.findAllByRole("heading", { name: "Intent classification accuracy" });
    const liveTile = heading.map((h) => h.closest("article")!).find((a) => a.classList.contains("live"))!;
    expect(within(liveTile).getByText("91.00%")).toBeInTheDocument();
    expect(within(liveTile).getByText(/PASS vs target 90.00%/)).toBeInTheDocument();
  });

  it("a MOCK tile shows its figure as a regression check and never a pass/fail claim", async () => {
    loginAs("COLLECTIONS_MANAGER", ["kpi:read"]);
    vi.mocked(client.getKpis).mockResolvedValue(response());
    renderDashboard();

    const headings = await screen.findAllByRole("heading", { name: "Intent classification accuracy" });
    const mockTile = headings.map((h) => h.closest("article")!).find((a) => a.classList.contains("mock"))!;
    expect(within(mockTile).getByText("94.00%")).toBeInTheDocument();
    expect(within(mockTile).getByText(/not evidence of model quality/i)).toBeInTheDocument();
    expect(mockTile.textContent).not.toMatch(/PASS|FAIL/);
  });

  it("shows an honest 'No LIVE run' state and never copies MOCK figures into it", async () => {
    loginAs("COLLECTIONS_MANAGER", ["kpi:read"]);
    vi.mocked(client.getKpis).mockResolvedValue(response({ live_run_available: false, live: [] }));
    renderDashboard();

    expect(await screen.findByText("No LIVE run")).toBeInTheDocument();
    expect(screen.getAllByRole("article").filter((a) => a.classList.contains("live"))).toHaveLength(0);
  });

  it("AC4: has no mutation controls -- the only buttons are read-only", async () => {
    loginAs("COLLECTIONS_MANAGER", ["kpi:read"]);
    vi.mocked(client.getKpis).mockResolvedValue(response());
    renderDashboard();

    await screen.findByRole("heading", { name: "Business" });
    expect(screen.queryAllByRole("button")).toHaveLength(0);
    expect(screen.queryAllByRole("textbox")).toHaveLength(0);
  });

  it("shows an error state with Retry that re-reads, and no figures", async () => {
    loginAs("COLLECTIONS_MANAGER", ["kpi:read"]);
    vi.mocked(client.getKpis)
      .mockRejectedValueOnce(
        new ApiError(500, {
          code: "INTERNAL_ERROR",
          reason_code: null,
          message: "boom",
          correlation_id: "c1",
        } as ConstructorParameters<typeof ApiError>[1]),
      )
      .mockResolvedValueOnce(response());
    renderDashboard();

    expect(await screen.findByRole("alert")).toHaveTextContent("No figures are shown");
    expect(screen.queryByRole("heading", { name: "Business" })).toBeNull();

    await userEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(await screen.findByRole("heading", { name: "Business" })).toBeInTheDocument();
    expect(client.getKpis).toHaveBeenCalledTimes(2);
  });

  it("AC5: a non-manager persona sees the forbidden page and no KPI request is made", async () => {
    loginAs("COLLECTIONS_OFFICER", ["portfolio:read"]);
    vi.mocked(client.getKpis).mockResolvedValue(response());
    renderDashboard();

    expect(await screen.findByText(/403 - Forbidden/)).toBeInTheDocument();
    await waitFor(() => expect(client.getKpis).not.toHaveBeenCalled());
    expect(client.getEvalRuns).not.toHaveBeenCalled();
    expect(screen.queryByText("Total delinquent accounts")).toBeNull();
  });
});
