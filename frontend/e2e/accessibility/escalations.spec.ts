import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

import {
  closeCase,
  createHandoffCase,
  findFreshAccount,
  refreshDemoSnapshots,
} from "../fixtures/journeyHelpers";
import { loginAsPersona } from "../fixtures/personaLogin";

/**
 * E7-S6 AC1, AC3, AC4 / E7-S3 AC6: the escalation list, zero serious/
 * critical axe violations, and keyboard operability. Reached via the real
 * "Escalations" nav link (COLLECTIONS_OFFICER's default landing route is
 * Portfolio, not Escalations -- `lib/navLinks.ts`'s ordering -- so a nav
 * click is the real path, not a `page.goto`), matching `customer360.spec
 * .ts`'s "reach it the way a real officer would" convention.
 *
 * E7-S3 AC6 widened `/escalations` from COLLECTIONS_OFFICER-only
 * (`escalation:review`) to shared with COMPLIANCE_RISK (`escalation:read`)
 * -- COMPLIANCE_RISK now sees the same nav link and reaches the same
 * screen, auto-scoped server-side to the COMPLIANCE_REVIEW queue, so the
 * "COMPLIANCE_RISK is forbidden here" test this file had under E7-S6 no
 * longer describes real behaviour and is replaced below.
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

  test("COMPLIANCE_RISK sees the Escalations link and only the compliance review queue (E7-S3 AC6)", async ({
    page,
  }) => {
    await loginAsPersona(page, "COMPLIANCE_RISK");
    await page.getByRole("link", { name: "Escalations" }).click();
    await expect(page.getByRole("heading", { name: "Escalations" })).toBeVisible();

    // AC5: the officer-only queue filter checkboxes never render for
    // COMPLIANCE_RISK -- its queue is fixed server-side, nothing to filter.
    await expect(page.getByRole("checkbox")).toHaveCount(0);

    const queueCells = page.locator("tbody td:nth-child(2)");
    const count = await queueCells.count();
    for (let i = 0; i < count; i++) {
      await expect(queueCells.nth(i)).toHaveText("Compliance review");
    }
  });

  test("a persona without escalation:read (CUSTOMER) is forbidden", async ({ page }) => {
    await loginAsPersona(page, "CUSTOMER");
    await page.goto("/escalations");
    await expect(page.getByRole("heading", { name: /403|forbidden/i })).toBeVisible();
    await expect(page.getByRole("table")).toHaveCount(0);
  });

  test("the list is keyboard operable: Tab reaches a row's customer link", async ({
    page,
    request,
  }) => {
    // The list needs at least one row, and a fresh database has none (cases are
    // created by the real app flow, never seeded): create exactly the one this
    // test needs as a real customer handoff, and close it afterwards through the
    // real review endpoint, so no other spec's data is assumed or left behind.
    await loginAsPersona(page, "COLLECTIONS_OFFICER");
    await refreshDemoSnapshots(page, request);
    const account = await findFreshAccount(page, request, {});
    const caseId = await createHandoffCase(page, account.customerId);

    try {
      await loginAsPersona(page, "COLLECTIONS_OFFICER");
      await page.getByRole("link", { name: "Escalations" }).click();
      await expect(page.getByRole("heading", { name: "Escalations" })).toBeVisible();
      await expect(page.locator(`a[href="/escalations/${caseId}"]`)).toBeVisible();
      await expectTabReachesCustomerLink(page);
    } finally {
      await loginAsPersona(page, "COLLECTIONS_OFFICER");
      await closeCase(page, request, caseId, "Test cleanup.");
    }
  });
});

async function expectTabReachesCustomerLink(page: import("@playwright/test").Page): Promise<void> {
  // A just-navigated page has no document focus yet in Chromium/Playwright
  // (nav-and-switcher.spec.ts's own precedent): the preceding nav-link
  // click triggered a client-side route change, so the very first Tab can
  // land nowhere without this harmless click on a non-interactive
  // landmark first, matching customer360.spec.ts's own keyboard test.
  await page.getByRole("heading", { name: "Escalations" }).click();

  for (let i = 0; i < 40; i++) {
    await page.keyboard.press("Tab");
    const focused = page.locator(":focus");
    if ((await focused.getAttribute("href"))?.startsWith("/customers/")) {
      break;
    }
  }
  await expect(page.locator(":focus")).toHaveAttribute("href", /^\/customers\//);
}
