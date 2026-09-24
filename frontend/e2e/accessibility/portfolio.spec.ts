import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

import { loginAsPersona } from "../fixtures/personaLogin";

/**
 * E3-S3 AC4: the Portfolio table passes an axe scan with zero serious or
 * critical violations and is operable by keyboard, including reaching
 * Customer 360 on a row without a pointer.
 *
 * Requires a running backend (`GET /api/portfolio` and friends) reachable
 * through the Vite dev proxy, per `playwright.config.ts`, seeded with at
 * least one delinquent account.
 */

function seriousOrCritical(violations: { impact?: string | null }[]) {
  return violations.filter((v) => v.impact === "serious" || v.impact === "critical");
}

// The table only appears once `GET /api/portfolio` returns -- a real
// network round trip against a real (not mocked) backend, so it can take
// longer than Playwright's 5s default `expect` timeout under load. Applied
// only to the initial-load assertion in each test, never to the fast,
// already-loaded interactions that follow it.
const TABLE_LOAD_TIMEOUT_MS = 15_000;

test.describe("Portfolio screen accessibility", () => {
  test("has zero serious or critical axe violations", async ({ page }) => {
    await loginAsPersona(page, "COLLECTIONS_OFFICER");
    await expect(page.getByRole("heading", { name: "Delinquent portfolio" })).toBeVisible();
    await expect(page.getByRole("table")).toBeVisible({ timeout: TABLE_LOAD_TIMEOUT_MS });

    const results = await new AxeBuilder({ page }).analyze();
    expect(seriousOrCritical(results.violations), JSON.stringify(results.violations, null, 2)).toEqual(
      [],
    );
  });

  test("a sortable column header is keyboard-reachable and toggles aria-sort on Enter", async ({
    page,
  }) => {
    await loginAsPersona(page, "COLLECTIONS_OFFICER");
    const overdueHeader = page.getByRole("columnheader", { name: /Overdue/ });
    await expect(overdueHeader).toHaveAttribute("aria-sort", "none", {
      timeout: TABLE_LOAD_TIMEOUT_MS,
    });

    const sortButton = page.getByRole("button", { name: /Overdue/ });
    await sortButton.focus();
    await page.keyboard.press("Enter");

    await expect(overdueHeader).toHaveAttribute("aria-sort", "descending");
  });

  test("a row's customer link is keyboard-reachable and opens Customer 360 on Enter", async ({
    page,
  }) => {
    await loginAsPersona(page, "COLLECTIONS_OFFICER");
    const firstRowLink = page.locator("tbody tr").first().getByRole("link");
    await firstRowLink.focus();
    await expect(firstRowLink).toBeFocused();

    await page.keyboard.press("Enter");

    await expect(page).toHaveURL(/\/customers\/acc_/);
  });
});
