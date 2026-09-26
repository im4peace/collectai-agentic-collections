import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

import { sessionHeaders } from "../fixtures/apiHelpers";
import { loginAsPersona } from "../fixtures/personaLogin";

/**
 * E10-S4 AC1, AC2, AC4, AC5: the manager dashboard against the real stack --
 * three headed sections, a text data-label badge on every tile, MOCK and LIVE
 * never mixed, no mutation controls, zero serious/critical axe violations,
 * keyboard operation, and the forbidden page (with no KPI request at all) for
 * every other persona.
 *
 * The fresh CI stack has no stored evaluation runs and a LIVE run is a manual,
 * paid step, so the AI assertions hold either way: with no run they check the
 * honest empty states ("No LIVE run"); when runs exist they check the labels
 * and that MOCK and LIVE tiles are separate.
 *
 * Requires a running backend reachable through the Vite dev proxy, per
 * `playwright.config.ts`.
 */

/** A tile's data-label badge: an icon glyph then exactly the label text. */
const LABEL_BADGE = /^.?(ILLUSTRATIVE|MOCK|LIVE)$/;

function seriousOrCritical(violations: { impact?: string | null }[]) {
  return violations.filter((v) => v.impact === "serious" || v.impact === "critical");
}

test.describe("Dashboard (COLLECTIONS_MANAGER)", () => {
  test("shows three headed sections, labelled tiles and no mutation controls (AC1, AC2, AC4)", async ({
    page,
  }) => {
    // The Manager's only nav link is Dashboard, so login lands on it (a
    // redundant `page.goto` here would reload and can race the session write).
    await loginAsPersona(page, "COLLECTIONS_MANAGER");

    await expect(
      page.getByRole("heading", { level: 1, name: "Collections and AI performance" }),
    ).toBeVisible();
    for (const name of ["Business", "Operational", "AI quality and governance"]) {
      await expect(page.getByRole("heading", { level: 2, name })).toBeVisible();
    }

    // AC1: each section lists its KPIs from the API.
    const business = page.locator("#kpi-business article.tile");
    const operational = page.locator("#kpi-operational article.tile");
    await expect(business.first()).toBeVisible();
    expect(await business.count()).toBeGreaterThanOrEqual(6);
    expect(await operational.count()).toBeGreaterThanOrEqual(1);

    // AC2: every tile carries a text badge; the synthetic business/operational
    // figures are ILLUSTRATIVE.
    for (const tile of await business.all()) {
      await expect(tile.locator(".chip", { hasText: "ILLUSTRATIVE" })).toBeVisible();
    }
    // Exactly one data-label badge per tile (the badge is an icon glyph plus
    // the label text, never colour alone).
    const allTiles = page.locator("article.tile");
    for (const tile of await allTiles.all()) {
      await expect(tile.locator(".chip", { hasText: LABEL_BADGE })).toHaveCount(1);
    }

    // AC2: MOCK and LIVE AI values are in separate tiles, and a tile never
    // carries the other's label.
    await expect(page.getByRole("heading", { name: "MOCK regression results" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "LIVE evaluation results" })).toBeVisible();
    for (const tile of await page.locator("article.tile.mock").all()) {
      await expect(tile.locator(".chip", { hasText: /^.?MOCK$/ })).toBeVisible();
      await expect(tile.locator(".chip", { hasText: /^.?LIVE$/ })).toHaveCount(0);
    }
    const liveTiles = page.locator("article.tile.live");
    if ((await liveTiles.count()) === 0) {
      // No LIVE run stored: the honest empty state, never MOCK figures.
      await expect(page.getByText("No LIVE run", { exact: true })).toBeVisible();
    }
    for (const tile of await liveTiles.all()) {
      await expect(tile.locator(".chip", { hasText: /^.?LIVE$/ })).toBeVisible();
      await expect(tile.locator(".chip", { hasText: /^.?MOCK$/ })).toHaveCount(0);
    }

    // AC4: read-only -- no buttons, inputs or forms anywhere on the screen.
    await expect(page.locator("main").getByRole("button")).toHaveCount(0);
    await expect(page.locator("main").getByRole("textbox")).toHaveCount(0);
    await expect(page.locator("main form")).toHaveCount(0);
  });

  test("has zero serious/critical axe violations (AC4)", async ({ page }) => {
    await loginAsPersona(page, "COLLECTIONS_MANAGER");
    await expect(page.getByRole("heading", { name: "Business" })).toBeVisible();
    await expect(page.locator("article.tile").first()).toBeVisible();

    const results = await new AxeBuilder({ page }).analyze();
    expect(
      seriousOrCritical(results.violations),
      JSON.stringify(results.violations, null, 2),
    ).toEqual([]);

    // Expanded definitions are part of the screen too.
    for (const summary of await page.locator("summary").all()) {
      await summary.click();
    }
    const expanded = await new AxeBuilder({ page }).analyze();
    expect(
      seriousOrCritical(expanded.violations),
      JSON.stringify(expanded.violations, null, 2),
    ).toEqual([]);
  });

  test("is fully keyboard operable (AC5)", async ({ page }) => {
    await loginAsPersona(page, "COLLECTIONS_MANAGER");
    await expect(page.getByRole("heading", { name: "Business" })).toBeVisible();

    // Tab reaches the jump links, and Enter follows one to its section.
    const aiLink = page.getByRole("link", { name: "AI quality and governance" });
    let reachedAiLink = false;
    for (let step = 0; step < 40 && !reachedAiLink; step += 1) {
      await page.keyboard.press("Tab");
      reachedAiLink = await aiLink.evaluate((element) => element === document.activeElement);
    }
    expect(reachedAiLink, "Tab must reach the AI section link").toBe(true);
    await page.keyboard.press("Enter");
    await expect(page).toHaveURL(/#kpi-ai$/);

    // Tab reaches a tile's "Definition and formula" control, and Enter opens it.
    const firstSummary = page.locator("summary").first();
    let reachedSummary = false;
    await page.locator("body").click({ position: { x: 1, y: 1 } });
    await page.evaluate(() => (document.activeElement as HTMLElement | null)?.blur());
    for (let step = 0; step < 60 && !reachedSummary; step += 1) {
      await page.keyboard.press("Tab");
      reachedSummary = await firstSummary.evaluate((element) => element === document.activeElement);
    }
    expect(reachedSummary, "Tab must reach a tile's definition control").toBe(true);
    await expect(firstSummary).toBeFocused();
    await page.keyboard.press("Enter");
    await expect(page.locator("details").first()).toHaveAttribute("open", "");
    await expect(page.locator("details").first().locator("dt", { hasText: "Formula" })).toBeVisible();
  });
});

test.describe("Dashboard is manager-only (AC5)", () => {
  for (const persona of ["COLLECTIONS_OFFICER", "COMPLIANCE_RISK", "CUSTOMER"]) {
    test(`${persona} sees the forbidden page, renders no KPI data and makes no KPI request`, async ({
      page,
      request,
    }) => {
      const kpiRequests: string[] = [];
      page.on("request", (candidate) => {
        if (candidate.url().includes("/api/kpis")) kpiRequests.push(candidate.url());
      });

      await loginAsPersona(page, persona);
      const headers = await sessionHeaders(page);
      await page.goto("/dashboard");

      await expect(page.getByRole("heading", { name: "403 - Forbidden" })).toBeVisible();
      await expect(page.getByRole("alert")).toContainText(persona);
      await expect(page.getByRole("heading", { name: "Business" })).toHaveCount(0);
      await expect(page.locator("article.tile")).toHaveCount(0);
      await expect(page.getByText("Total delinquent accounts")).toHaveCount(0);
      expect(kpiRequests, "a forbidden persona must never fetch KPI data").toEqual([]);

      // The server enforces it independently of the UI guard.
      const direct = await request.get("/api/kpis", { headers });
      expect(direct.status()).toBe(403);
    });
  }
});
