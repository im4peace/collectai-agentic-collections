import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

import { loginAsPersona } from "../fixtures/personaLogin";

/**
 * E9-S2 AC3, AC4: no edit/delete controls, an axe scan with zero serious or
 * critical violations, and the viewer reachable only by COMPLIANCE_RISK
 * (E3-S4's own forbidden-page coverage already proves the negative case for
 * every other persona; this spec only re-confirms the positive one plus
 * this screen's own no-mutation guarantee).
 *
 * Requires a running backend reachable through the Vite dev proxy, per
 * `playwright.config.ts`.
 */

function seriousOrCritical(violations: { impact?: string | null }[]) {
  return violations.filter((v) => v.impact === "serious" || v.impact === "critical");
}

test.describe("Audit trail viewer accessibility", () => {
  test("is reachable by COMPLIANCE_RISK, has zero serious/critical axe violations and no edit/delete controls", async ({
    page,
  }) => {
    // Since E7-S3 COMPLIANCE_RISK also holds `escalation:read`, so its first
    // nav link -- and therefore its landing route -- is Escalations, not Audit
    // Trail. Reach the viewer the way a real user does: click its nav link
    // (client-side, so no full reload racing the session write).
    await loginAsPersona(page, "COMPLIANCE_RISK");
    await page.getByRole("link", { name: "Audit Trail" }).click();

    await expect(page.getByRole("heading", { name: "Audit trail" })).toBeVisible();

    const buttons = await page.getByRole("button").allTextContents();
    const hasMutatingControl = buttons.some((text) =>
      /edit|delete/i.test(text),
    );
    expect(hasMutatingControl).toBe(false);

    const results = await new AxeBuilder({ page }).analyze();
    expect(seriousOrCritical(results.violations), JSON.stringify(results.violations, null, 2)).toEqual(
      [],
    );
  });

  test("the search form is keyboard navigable from the top of the page", async ({ page }) => {
    await loginAsPersona(page, "COMPLIANCE_RISK");
    await page.getByRole("link", { name: "Audit Trail" }).click();

    await page.getByRole("heading", { name: "Audit trail" }).click();
    await page.keyboard.press("Tab");
    await expect(page.getByLabel("Correlation id")).toBeFocused();
  });
});
