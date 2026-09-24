import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

import { loginAsPersona } from "../fixtures/personaLogin";

/**
 * E3-S4 AC3 and AC5: axe scan, keyboard-only operability, focus
 * visibility and the assistive-technology persona announcement, for the
 * persona switcher, the resulting navigation and the forbidden page. This
 * is the one accessibility spec this story owns (nav/switcher/forbidden
 * page) — screens this story does not build are out of scope here.
 *
 * Requires a running backend (`GET /api/session/options`,
 * `POST /api/session`) reachable through the Vite dev proxy, per
 * `playwright.config.ts`.
 */

function seriousOrCritical(violations: { impact?: string | null }[]) {
  return violations.filter((v) => v.impact === "serious" || v.impact === "critical");
}

test.describe("Persona switcher accessibility", () => {
  test("has zero serious or critical axe violations", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByRole("heading", { name: "Persona switcher" })).toBeVisible();

    const results = await new AxeBuilder({ page }).analyze();

    expect(seriousOrCritical(results.violations), JSON.stringify(results.violations, null, 2)).toEqual(
      [],
    );
  });

  test("is operable by keyboard alone, with a visible focus indicator, and lands on the officer's Portfolio", async ({
    page,
  }) => {
    await page.goto("/");

    // A just-navigated page has no document focus yet in Chromium/Playwright,
    // so the very first Tab can land nowhere. A harmless click on a
    // non-interactive landmark (never a focusable control, so it selects
    // nothing itself) gives the document focus first, matching what a real
    // click-to-focus-the-window-then-Tab user does.
    await page.getByRole("heading", { name: "Persona switcher" }).click();

    // Tab from the top of the page into the persona radio group.
    await page.keyboard.press("Tab");
    const firstFocused = page.locator(":focus");
    await expect(firstFocused).toHaveAttribute("type", "radio");
    await expect(firstFocused).toHaveAttribute("value", "CUSTOMER");
    const outlineWidth = await firstFocused.evaluate((el) => getComputedStyle(el).outlineWidth);
    expect(outlineWidth).not.toBe("0px");

    // Arrow keys move within a native radio group and select as they go.
    await page.keyboard.press("ArrowDown");
    const secondFocused = page.locator(":focus");
    await expect(secondFocused).toHaveAttribute("value", "COLLECTIONS_OFFICER");
    await expect(secondFocused).toBeChecked();

    // Next Tab stop is the submit button (COLLECTIONS_OFFICER needs no
    // demo-customer select).
    await page.keyboard.press("Tab");
    const submit = page.getByRole("button", { name: "Use this persona" });
    await expect(submit).toBeFocused();

    await page.keyboard.press("Enter");

    await expect(page).toHaveURL(/\/portfolio$/);
    await expect(page.getByRole("link", { name: "Portfolio" })).toHaveAttribute("aria-current", "page");
  });

  test("announces the current persona to assistive technology after switching", async ({ page }) => {
    await loginAsPersona(page, "COLLECTIONS_MANAGER");

    const status = page.getByRole("status").filter({ hasText: "Current persona" });
    await expect(status).toHaveAttribute("aria-live", "polite");
    await expect(status).toContainText("Collections Manager");
  });
});

test.describe("Forbidden page accessibility", () => {
  test("shown with zero serious/critical violations when a persona opens a route it cannot use", async ({
    page,
  }) => {
    await loginAsPersona(page, "COLLECTIONS_MANAGER");

    // COLLECTIONS_MANAGER holds kpi:read and session:read only -- not
    // audit:read.
    await page.goto("/audit");

    const alert = page.getByRole("alert");
    await expect(alert).toContainText("403 - Forbidden");
    await expect(alert).toContainText("No restricted data was requested");

    const results = await new AxeBuilder({ page }).analyze();
    expect(seriousOrCritical(results.violations), JSON.stringify(results.violations, null, 2)).toEqual(
      [],
    );
  });
});
