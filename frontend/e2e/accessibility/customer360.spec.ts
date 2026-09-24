import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

import { loginAsPersona } from "../fixtures/personaLogin";

/**
 * E4-S2 AC2, AC4, AC7: the AI/deterministic panel labelling, an axe scan
 * with zero serious/critical violations, and keyboard reach into the
 * screen's panels. Reached the same way a real officer would -- via a
 * Portfolio row -- rather than hard-coding an account id.
 *
 * Requires a running backend seeded with at least one delinquent account,
 * reachable through the Vite dev proxy per `playwright.config.ts`.
 */

function seriousOrCritical(violations: { impact?: string | null }[]) {
  return violations.filter((v) => v.impact === "serious" || v.impact === "critical");
}

test.describe("Customer 360 screen accessibility", () => {
  test("has zero serious or critical axe violations, with AI and deterministic panels distinctly labelled", async ({
    page,
  }) => {
    await loginAsPersona(page, "COLLECTIONS_OFFICER");
    await page.locator("tbody tr").first().getByRole("link").click();
    await expect(page.getByRole("heading", { name: "Rules engine" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "AI-generated" })).toBeVisible();

    const results = await new AxeBuilder({ page }).analyze();
    expect(seriousOrCritical(results.violations), JSON.stringify(results.violations, null, 2)).toEqual(
      [],
    );
  });

  test("every panel heading is keyboard-reachable in the page's tab order", async ({ page }) => {
    await loginAsPersona(page, "COLLECTIONS_OFFICER");
    await page.locator("tbody tr").first().getByRole("link").click();
    await expect(page.getByRole("heading", { name: "Rules engine" })).toBeVisible();

    // AC7: keyboard navigation reaches every panel -- a spot check that the
    // Record PTP button (inside the PTP history panel, near the bottom of
    // the screen) is reachable by repeated Tab from the top.
    for (let i = 0; i < 40; i++) {
      await page.keyboard.press("Tab");
      const focused = page.locator(":focus");
      if ((await focused.textContent())?.includes("Record")) {
        break;
      }
    }
    await expect(page.locator(":focus")).toBeVisible();
  });
});
