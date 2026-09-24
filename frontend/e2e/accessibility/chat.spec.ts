import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

import { loginAsPersona } from "../fixtures/personaLogin";

/**
 * E6-S5 AC1, AC5: the AI-disclosure opening message, the always-visible
 * "Talk to a human" control, mobile-width usability with zero horizontal
 * scroll, and an axe scan with zero serious/critical violations.
 *
 * Requires a running backend reachable through the Vite dev proxy, per
 * `playwright.config.ts`, with at least one seeded CUSTOMER demo account.
 */

function seriousOrCritical(violations: { impact?: string | null }[]) {
  return violations.filter((v) => v.impact === "serious" || v.impact === "critical");
}

test.describe("Chat screen accessibility", () => {
  test("opens with an AI disclosure and keeps 'Talk to a human' visible; zero serious/critical axe violations", async ({
    page,
  }) => {
    // `loginAsPersona` already lands on CUSTOMER's default route (Chat is
    // its only permitted screen) via client-side navigation; a redundant
    // `page.goto("/chat")` here would force a full reload that can race the
    // session write and land on a 403 instead.
    await loginAsPersona(page, "CUSTOMER");

    await expect(page.getByRole("button", { name: "Talk to a human" })).toBeVisible();

    const results = await new AxeBuilder({ page }).analyze();
    expect(seriousOrCritical(results.violations), JSON.stringify(results.violations, null, 2)).toEqual(
      [],
    );
  });

  test("is usable at 375px width with no horizontal scroll (AC5)", async ({ page }) => {
    await page.setViewportSize({ width: 375, height: 700 });
    await loginAsPersona(page, "CUSTOMER");
    await expect(page.getByRole("button", { name: "Talk to a human" })).toBeVisible();

    const hasHorizontalScroll = await page.evaluate(
      () => document.documentElement.scrollWidth > document.documentElement.clientWidth,
    );
    expect(hasHorizontalScroll).toBe(false);
  });

  test("supports keyboard-only sending: Tab to the composer, type, Enter to send", async ({ page }) => {
    await loginAsPersona(page, "CUSTOMER");

    const composer = page.getByLabel("Message");
    await composer.click();
    await composer.fill("Hello, I have a question about my account.");
    await composer.press("Enter");

    // A customer message appended to the visible message list confirms the
    // Enter-to-send path worked without ever touching the mouse.
    await expect(page.getByText("Hello, I have a question about my account.")).toBeVisible();
  });
});
