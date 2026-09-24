import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

import { loginAsPersona } from "../fixtures/personaLogin";

/**
 * E7-S6 AC1, AC3, AC4: the minimal escalation list is reachable only by
 * COLLECTIONS_OFFICER, zero serious/critical axe violations, and keyboard
 * operability. Reached via the real "Escalations" nav link (COLLECTIONS_
 * OFFICER's default landing route is Portfolio, not Escalations --
 * `lib/navLinks.ts`'s ordering -- so a nav click is the real path, not a
 * `page.goto`), matching `customer360.spec.ts`'s "reach it the way a real
 * officer would" convention.
 *
 * Requires a running backend reachable through the Vite dev proxy, per
 * `playwright.config.ts`.
 */

function seriousOrCritical(violations: { impact?: string | null }[]) {
  return violations.filter((v) => v.impact === "serious" || v.impact === "critical");
}

test.describe("Escalations screen accessibility", () => {
  test("is reachable by COLLECTIONS_OFFICER and has zero serious/critical axe violations (AC1, AC3)", async ({
    page,
  }) => {
    await loginAsPersona(page, "COLLECTIONS_OFFICER");
    await page.getByRole("link", { name: "Escalations" }).click();
    await expect(page.getByRole("heading", { name: "Escalations" })).toBeVisible();

    const results = await new AxeBuilder({ page }).analyze();
    expect(seriousOrCritical(results.violations), JSON.stringify(results.violations, null, 2)).toEqual(
      [],
    );
  });

  test("shows the forbidden page with no escalation data for a persona without escalation:review (AC3)", async ({
    page,
  }) => {
    await loginAsPersona(page, "COMPLIANCE_RISK");
    await expect(page.getByRole("link", { name: "Escalations" })).toHaveCount(0);

    await page.goto("/escalations");
    await expect(page.getByRole("heading", { name: /403|forbidden/i })).toBeVisible();
    await expect(page.getByRole("table")).toHaveCount(0);
  });

  test("the list is keyboard operable: Tab reaches a row's customer link", async ({ page }) => {
    await loginAsPersona(page, "COLLECTIONS_OFFICER");
    await page.getByRole("link", { name: "Escalations" }).click();
    await expect(page.getByRole("heading", { name: "Escalations" })).toBeVisible();

    // A just-navigated page has no document focus yet in Chromium/Playwright
    // (nav-and-switcher.spec.ts's own precedent): the preceding nav-link
    // click triggered a client-side route change, so the very first Tab can
    // land nowhere without this harmless click on a non-interactive
    // landmark first, matching customer360.spec.ts's own keyboard test.
    await page.getByRole("heading", { name: "Escalations" }).click();

    for (let i = 0; i < 20; i++) {
      await page.keyboard.press("Tab");
      const focused = page.locator(":focus");
      if ((await focused.getAttribute("href"))?.startsWith("/customers/")) {
        break;
      }
    }
    await expect(page.locator(":focus")).toHaveAttribute("href", /^\/customers\//);
  });
});
