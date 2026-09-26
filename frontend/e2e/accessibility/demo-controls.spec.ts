import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";
import type { APIRequestContext, Page } from "@playwright/test";

import { sessionHeaders } from "../fixtures/apiHelpers";
import { loginAsPersona } from "../fixtures/personaLogin";

/**
 * E9-S3: the demo-controls screen against the real stack -- navigation and
 * access by persona, rendering, zero serious/critical axe violations, and
 * keyboard operation.
 *
 * **This file is read-only by design.** The stack's simulated clock, payments
 * and seed data are shared with every other spec (the journeys run in parallel
 * and depend on them), so nothing here may advance the clock, run the PTP
 * lifecycle, record a payment or reseed. It never activates a write button,
 * and `guardWrites` aborts any non-GET request to `/api/demo-controls` as a
 * second line of defence, failing the test if one was attempted. The write
 * paths are covered by the mocked Vitest tests and the backend API tests.
 *
 * The screen only exists when the API runs with `DEMO_CONTROLS_ENABLED=true`
 * (CI: `docker-compose.test.yml`). Against a stack where it is off, the tests
 * that need the screen skip, and the flag-off behaviour (no link, no controls)
 * is asserted instead.
 *
 * Requires a running backend reachable through the Vite dev proxy, per
 * `playwright.config.ts`.
 */

function seriousOrCritical(violations: { impact?: string | null }[]) {
  return violations.filter((v) => v.impact === "serious" || v.impact === "critical");
}

/** Records every demo-control request, and aborts anything that is not a GET. */
async function guardWrites(page: Page): Promise<{ blocked: string[]; all: string[] }> {
  const seen = { blocked: [] as string[], all: [] as string[] };
  await page.route("**/api/demo-controls/**", (route) => {
    const request = route.request();
    seen.all.push(`${request.method()} ${new URL(request.url()).pathname}`);
    if (request.method() !== "GET") {
      seen.blocked.push(`${request.method()} ${new URL(request.url()).pathname}`);
      return route.abort();
    }
    return route.continue();
  });
  return seen;
}

/** The flag as the API reports it: 200 means on, 404 means off. */
async function demoControlsEnabled(page: Page, request: APIRequestContext): Promise<boolean> {
  const response = await request.get("/api/demo-controls/state", {
    headers: await sessionHeaders(page),
  });
  expect([200, 404]).toContain(response.status());
  return response.status() === 200;
}

async function openDemoControls(page: Page): Promise<void> {
  await page.getByRole("link", { name: "Demo controls" }).click();
  await expect(page).toHaveURL(/\/demo-controls$/);
  await expect(page.getByRole("heading", { level: 1, name: "Demo controls" })).toBeVisible();
  await expect(page.getByRole("heading", { level: 2, name: "Advance clock" })).toBeVisible();
}

test.describe("Demo controls (COLLECTIONS_OFFICER)", () => {
  test("the link and the screen match the API flag, and render the AI mode as text", async ({
    page,
    request,
  }) => {
    const writes = await guardWrites(page);
    await loginAsPersona(page, "COLLECTIONS_OFFICER");
    const enabled = await demoControlsEnabled(page, request);
    const link = page.getByRole("link", { name: "Demo controls" });

    if (!enabled) {
      // Flag off: no dead link, and the route shows no control at all.
      await expect(page.getByRole("link", { name: "Portfolio" })).toBeVisible();
      await expect(link).toHaveCount(0);
      await page.goto("/demo-controls");
      await expect(page.getByRole("heading", { name: "Demo controls are turned off" })).toBeVisible();
      await expect(page.locator("main").getByRole("button")).toHaveCount(0);
      await expect(page.locator("main").getByRole("textbox")).toHaveCount(0);
      expect(writes.blocked).toEqual([]);
      return;
    }

    // Flag on: the link is the last one, and Portfolio is still the landing page.
    await expect(link).toBeVisible();
    const links = page.getByRole("navigation", { name: "Main navigation" }).getByRole("link");
    await expect(links.last()).toHaveText("Demo controls");
    await expect(page).toHaveURL(/\/portfolio$/);

    await openDemoControls(page);
    await expect(page).toHaveTitle("Demo Controls | CollectAI");
    await expect(link).toHaveAttribute("aria-current", "page");

    // AC1: the mode is text, MOCK or LIVE.
    const statePanel = page.getByRole("region", { name: "Demo state" });
    await expect(statePanel.getByText(/^(MOCK|LIVE)$/)).toBeVisible();
    await expect(statePanel.getByText("Simulated clock")).toBeVisible();
    await expect(statePanel.getByText("Active policy version")).toBeVisible();

    for (const name of ["Advance clock", "Run PTP lifecycle", "Simulate a payment", "Reseed data"]) {
      await expect(page.getByRole("heading", { level: 2, name })).toBeVisible();
    }
    // Every control is labelled, and the refresh box starts ticked.
    await expect(page.getByLabel("Days to advance (1 to 365)")).toHaveValue("1");
    await expect(page.getByRole("checkbox", { name: "Refresh data snapshots" })).toBeChecked();
    await expect(page.getByLabel("Account id")).toBeVisible();
    await expect(page.getByLabel("Amount (AED)")).toBeVisible();
    await expect(page.getByLabel("Outcome")).toBeVisible();

    // Persistent, empty live regions: four status and four alert, one per panel.
    await expect(page.locator("main [role=status]")).toHaveCount(4);
    await expect(page.locator("main [role=alert]")).toHaveCount(4);
    for (const region of await page.locator("main [role=alert]").all()) {
      await expect(region).toBeEmpty();
    }

    // Opening the screen only ever read state.
    expect(writes.all.every((entry) => entry.startsWith("GET "))).toBe(true);
    expect(writes.blocked).toEqual([]);
  });

  test("has zero serious/critical axe violations, including with the reseed dialog open", async ({
    page,
    request,
  }) => {
    const writes = await guardWrites(page);
    await loginAsPersona(page, "COLLECTIONS_OFFICER");
    test.skip(!(await demoControlsEnabled(page, request)), "demo controls are off on this stack");
    await openDemoControls(page);

    const screen = await new AxeBuilder({ page }).analyze();
    expect(seriousOrCritical(screen.violations), JSON.stringify(screen.violations, null, 2)).toEqual([]);

    // Opening the dialog sends nothing; it is only closed again, never confirmed.
    await page.getByRole("button", { name: "Reseed data..." }).click();
    await expect(page.getByRole("dialog", { name: "Reseed the demo data?" })).toBeVisible();
    const dialog = await new AxeBuilder({ page }).analyze();
    expect(seriousOrCritical(dialog.violations), JSON.stringify(dialog.violations, null, 2)).toEqual([]);
    await page.keyboard.press("Escape");
    await expect(page.getByRole("dialog")).toHaveCount(0);

    expect(writes.blocked).toEqual([]);
  });

  test("every control is reachable by Tab in order with a visible focus ring, and the dialog is keyboard-safe", async ({
    page,
    request,
  }) => {
    const writes = await guardWrites(page);
    await loginAsPersona(page, "COLLECTIONS_OFFICER");
    test.skip(!(await demoControlsEnabled(page, request)), "demo controls are off on this stack");
    await openDemoControls(page);

    const targets = [
      page.getByLabel("Days to advance (1 to 365)"),
      page.getByRole("checkbox", { name: "Refresh data snapshots" }),
      page.getByRole("button", { name: "Advance clock" }),
      page.getByRole("button", { name: "Run PTP lifecycle now" }),
      page.getByLabel("Account id"),
      page.getByLabel("Amount (AED)"),
      page.getByLabel("Outcome"),
      page.getByRole("button", { name: "Record simulated payment" }),
      page.getByRole("button", { name: "Reseed data..." }),
    ];

    // Start from a non-interactive point and only ever press Tab: pressing
    // Enter or Space on a write button would submit it.
    await page.getByRole("heading", { level: 1, name: "Demo controls" }).click();
    const reached: number[] = [];
    for (let step = 0; step < 60 && reached.length < targets.length; step += 1) {
      await page.keyboard.press("Tab");
      for (const [index, target] of targets.entries()) {
        if (await target.evaluate((element) => element === document.activeElement)) {
          const outline = await target.evaluate((element) => getComputedStyle(element).outlineWidth);
          expect(outline, `control ${index} needs a visible focus indicator`).not.toBe("0px");
          reached.push(index);
        }
      }
    }
    expect(reached, "Tab must reach every control, in reading order").toEqual(
      targets.map((_, index) => index),
    );

    // Focus is on the Reseed button. Enter only opens the dialog (nothing is sent).
    await expect(targets[8]).toBeFocused();
    await page.keyboard.press("Enter");
    const dialog = page.getByRole("dialog", { name: "Reseed the demo data?" });
    await expect(dialog).toBeVisible();
    for (let step = 0; step < 6; step += 1) {
      await page.keyboard.press("Tab");
      expect(
        await dialog.evaluate((element) => element.contains(document.activeElement)),
        "Tab must stay inside the open dialog",
      ).toBe(true);
    }
    await page.keyboard.press("Escape");
    await expect(dialog).toHaveCount(0);
    await expect(targets[8]).toBeFocused();

    expect(writes.blocked).toEqual([]);
  });
});

test.describe("Demo controls are officer-only", () => {
  for (const persona of ["COLLECTIONS_MANAGER", "COMPLIANCE_RISK", "CUSTOMER"]) {
    test(`${persona} has no link, sees the forbidden page and makes no demo-control request`, async ({
      page,
      request,
    }) => {
      const writes = await guardWrites(page);
      await loginAsPersona(page, persona);
      const headers = await sessionHeaders(page);
      const links = page.getByRole("navigation", { name: "Main navigation" });
      await expect(links).toBeVisible();
      await expect(links.getByRole("link", { name: "Demo controls" })).toHaveCount(0);

      await page.goto("/demo-controls");
      await expect(page.getByRole("heading", { name: "403 - Forbidden" })).toBeVisible();
      await expect(page.getByRole("alert")).toContainText(persona);
      await expect(page.getByRole("heading", { name: "Advance clock" })).toHaveCount(0);
      expect(writes.all, "a forbidden persona must never call the demo-control API").toEqual([]);

      // The server enforces it independently of the UI guard (404 before any
      // persona check when the flag is off, 403 when it is on).
      const direct = await request.get("/api/demo-controls/state", { headers });
      expect([403, 404]).toContain(direct.status());
    });
  }
});
