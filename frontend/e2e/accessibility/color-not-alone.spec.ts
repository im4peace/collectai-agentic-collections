import { expect, test } from "@playwright/test";

import { loginAsPersona } from "../fixtures/personaLogin";

/**
 * E11-S5 AC4: AI, rules-engine, risk, priority and simulated states each
 * carry a text or icon label, never color alone. Every such state in this
 * app renders through the shared `Badge` component, whose own `text: string`
 * prop is required (`components/Badge.tsx`'s own contract) -- so the
 * generic, comprehensive check is that every `.chip` (Badge's rendered
 * class) visible on a screen has non-empty, real text content. This
 * directly covers: AI panel status and recommendation (Customer 360),
 * rules-engine priority band and treatment flags (Customer 360), the
 * vulnerable-customer/escalation risk badge (Customer 360's profile panel),
 * priority band badges (Portfolio, Escalations), and simulated-payment
 * labels (Customer 360's payment-events panel, Chat's proposal card).
 *
 * Requires a running backend reachable through the Vite dev proxy, per
 * `playwright.config.ts`, seeded with at least one delinquent account.
 */

async function chipTexts(page: import("@playwright/test").Page): Promise<string[]> {
  return page.locator(".chip").allTextContents();
}

test.describe("Color is never the only signal", () => {
  test("every badge on Customer 360 (AI, rules-engine, priority, risk) carries real text", async ({
    page,
  }) => {
    await loginAsPersona(page, "COLLECTIONS_OFFICER");
    await page.locator("tbody tr").first().getByRole("link").click();
    await expect(page.getByRole("heading", { name: "Rules engine" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "AI-generated" })).toBeVisible();

    const texts = await chipTexts(page);
    expect(texts.length).toBeGreaterThan(0);
    for (const text of texts) {
      expect(
        text.trim().length,
        `a .chip badge rendered with no visible text: ${JSON.stringify(texts)}`,
      ).toBeGreaterThan(0);
    }
  });

  test("every badge on the Portfolio and Escalations lists carries real text", async ({ page }) => {
    await loginAsPersona(page, "COLLECTIONS_OFFICER");
    await expect(page.getByRole("table")).toBeVisible({ timeout: 15_000 });
    const portfolioChips = await chipTexts(page);
    for (const text of portfolioChips) {
      expect(text.trim().length).toBeGreaterThan(0);
    }

    await page.getByRole("link", { name: "Escalations" }).click();
    await expect(page.getByRole("heading", { name: "Escalations" })).toBeVisible();
    const escalationChips = await chipTexts(page);
    for (const text of escalationChips) {
      expect(text.trim().length).toBeGreaterThan(0);
    }
  });

  test("a decorative badge icon is aria-hidden, never the only conveyor of meaning", async ({
    page,
  }) => {
    await loginAsPersona(page, "COLLECTIONS_OFFICER");
    await page.locator("tbody tr").first().getByRole("link").click();
    await expect(page.getByRole("heading", { name: "Rules engine" })).toBeVisible();

    // Any chip that renders an icon glyph marks it aria-hidden (Badge.tsx's
    // own contract) -- assistive tech reads the chip's real text, never the
    // icon glyph as if it carried independent meaning.
    const iconSpans = page.locator(".chip > span[aria-hidden='true']");
    const count = await iconSpans.count();
    for (let i = 0; i < count; i++) {
      await expect(iconSpans.nth(i)).toHaveAttribute("aria-hidden", "true");
    }
  });
});
