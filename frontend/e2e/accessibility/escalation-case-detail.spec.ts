import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

import { loginAsPersona } from "../fixtures/personaLogin";

/**
 * E7-S3 AC2, AC3, AC4, AC7: the case-detail screen -- three separately
 * labelled sections, reason-gated action dialogs, zero serious/critical axe
 * violations, and focus management identical to `dialogs-and-live-region
 * .spec.ts`'s own established pattern for `ConfirmDialog`.
 *
 * The demo dataset seeds no escalation cases (they are created by the real
 * app flow, never static seed data), so each test here first creates one
 * as CUSTOMER via the chat screen's "Talk to a human" handoff (E6-S1),
 * which routes a REQUEST_HUMAN case to the COLLECTIONS_REVIEW queue --
 * mirroring how a real officer would encounter a case, not a fixture.
 *
 * Requires a running backend reachable through the Vite dev proxy, per
 * `playwright.config.ts`.
 */

function seriousOrCritical(violations: { impact?: string | null }[]) {
  return violations.filter((v) => v.impact === "serious" || v.impact === "critical");
}

async function createHandoffCase(page: import("@playwright/test").Page): Promise<void> {
  await loginAsPersona(page, "CUSTOMER");
  await page.getByRole("button", { name: "Talk to a human" }).click();
  await expect(page.getByText(/talk to a human|specialist|human/i)).toBeVisible({ timeout: 15_000 });
}

test.describe("Escalation case detail", () => {
  test("is reachable by an officer, shows three labelled sections and has zero serious/critical axe violations (AC2, AC4)", async ({
    page,
  }) => {
    await createHandoffCase(page);

    await loginAsPersona(page, "COLLECTIONS_OFFICER");
    await page.getByRole("link", { name: "Escalations" }).click();
    await expect(page.getByRole("heading", { name: "Escalations" })).toBeVisible();
    await page.locator("tbody tr").first().getByRole("link").first().click();

    await expect(page.getByRole("heading", { name: "Conversation" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "AI recommendation" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Deterministic rule results" })).toBeVisible();

    const results = await new AxeBuilder({ page }).analyze();
    expect(seriousOrCritical(results.violations), JSON.stringify(results.violations, null, 2)).toEqual(
      [],
    );
  });

  test("the Reject dialog moves focus into the reason field, traps it, stays disabled until a reason is entered, and returns focus on close (AC3, AC7)", async ({
    page,
  }) => {
    await createHandoffCase(page);

    await loginAsPersona(page, "COLLECTIONS_OFFICER");
    await page.getByRole("link", { name: "Escalations" }).click();
    await page.locator("tbody tr").first().getByRole("link").first().click();
    await expect(page.getByRole("heading", { name: "Reviewer decision" })).toBeVisible();

    const trigger = page.getByRole("button", { name: "Reject" });
    await trigger.focus();
    await trigger.press("Enter");

    const dialog = page.getByRole("dialog", { name: "Reject this case?" });
    await expect(dialog).toBeVisible();

    const reasonField = page.getByLabel("Reason");
    await expect(reasonField).toBeFocused();

    const confirmButton = dialog.getByRole("button", { name: "Reject" });
    await expect(confirmButton).toBeDisabled();
    await reasonField.fill("Not eligible for this exception.");
    await expect(confirmButton).toBeEnabled();

    // Trap: Shift+Tab from the first focusable control wraps to the last.
    await reasonField.press("Shift+Tab");
    const isInsideDialog = await dialog.locator(":focus").count();
    expect(isInsideDialog).toBe(1);

    await page.keyboard.press("Escape");
    await expect(dialog).toBeHidden();
    await expect(trigger).toBeFocused();
  });

  test("a stale-version conflict shows a message and reloads the case (AC4)", async ({ page }) => {
    await createHandoffCase(page);

    await loginAsPersona(page, "COLLECTIONS_OFFICER");
    await page.getByRole("link", { name: "Escalations" }).click();
    await page.locator("tbody tr").first().getByRole("link").first().click();
    await expect(page.getByRole("heading", { name: "Reviewer decision" })).toBeVisible();

    // A second tab acts on the same case first, bumping its version behind
    // this tab's back -- the case-detail screen still holds the stale
    // `expected_version` it loaded with.
    const secondTab = await page.context().newPage();
    await secondTab.goto(page.url());
    await secondTab.getByRole("button", { name: "Reject" }).click();
    await secondTab
      .getByRole("dialog", { name: "Reject this case?" })
      .getByLabel("Reason")
      .fill("Handled from another tab.");
    await secondTab.getByRole("dialog", { name: "Reject this case?" }).getByRole("button", { name: "Reject" }).click();
    await expect(secondTab.getByRole("dialog", { name: "Reject this case?" })).toBeHidden();
    await secondTab.close();

    await page.getByRole("button", { name: "Reject" }).click();
    await page.getByRole("dialog", { name: "Reject this case?" }).getByLabel("Reason").fill("Stale attempt.");
    await page
      .getByRole("dialog", { name: "Reject this case?" })
      .getByRole("button", { name: "Reject" })
      .click();

    await expect(page.getByRole("alert").filter({ hasText: "This case changed" })).toBeVisible();
  });
});
