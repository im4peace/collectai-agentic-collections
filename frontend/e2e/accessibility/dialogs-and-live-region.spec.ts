import { expect, test } from "@playwright/test";

import { loginAsPersona } from "../fixtures/personaLogin";

/**
 * E11-S5 AC3: focus-management tests for `ConfirmDialog` (the shared modal
 * behind Customer 360's "Record Promise-to-Pay" form and the Chat screen's
 * proposal Confirm/Cancel UI) and `LiveRegion` (new assistant chat
 * messages). Exercised here against the real "Record Promise-to-Pay"
 * dialog on Customer 360 -- a reliable, AI-free trigger for the shared
 * `ConfirmDialog` component every other confirmation dialog in the app
 * reuses, so this one spec's coverage of open/trap/close-returns-focus
 * applies to all of them.
 *
 * Requires a running backend reachable through the Vite dev proxy, per
 * `playwright.config.ts`, seeded with at least one delinquent account.
 */

test.describe("Dialog focus management", () => {
  test("focus moves into the dialog on open, is trapped while open, and returns to the trigger on close", async ({
    page,
  }) => {
    await loginAsPersona(page, "COLLECTIONS_OFFICER");
    await page.locator("tbody tr").first().getByRole("link").click();
    await expect(page.getByRole("heading", { name: "Promise-to-Pay history" })).toBeVisible();

    const trigger = page.getByRole("button", { name: "Record Promise-to-Pay" });
    await trigger.focus();
    await trigger.press("Enter");

    const dialog = page.getByRole("dialog", { name: "Record Promise-to-Pay" });
    await expect(dialog).toBeVisible();

    // Focus moved into the dialog on open (its first focusable control).
    const amountInput = page.getByLabel("Promised amount (AED)");
    await expect(amountInput).toBeFocused();

    // Trap: Shift+Tab from the first focusable control wraps to the last
    // one inside the dialog, never escaping to something behind it (e.g.
    // the trigger button, or the page's own nav links).
    await page.keyboard.press("Shift+Tab");
    const wrapped = page.locator(":focus");
    await expect(wrapped).toBeVisible();
    const isInsideDialog = await dialog.locator(":focus").count();
    expect(isInsideDialog).toBe(1);

    // Escape closes the dialog and returns focus to the trigger.
    await page.keyboard.press("Escape");
    await expect(dialog).toBeHidden();
    await expect(trigger).toBeFocused();
  });

  test("Cancel also closes the dialog and returns focus to the trigger", async ({ page }) => {
    await loginAsPersona(page, "COLLECTIONS_OFFICER");
    await page.locator("tbody tr").first().getByRole("link").click();
    await expect(page.getByRole("heading", { name: "Promise-to-Pay history" })).toBeVisible();

    const trigger = page.getByRole("button", { name: "Record Promise-to-Pay" });
    await trigger.click();
    const dialog = page.getByRole("dialog", { name: "Record Promise-to-Pay" });
    await expect(dialog).toBeVisible();

    await dialog.getByRole("button", { name: "Cancel" }).click();
    await expect(dialog).toBeHidden();
    await expect(trigger).toBeFocused();
  });
});

test.describe("Chat live region", () => {
  test("a new assistant message is announced through a polite live region", async ({ page }) => {
    await loginAsPersona(page, "CUSTOMER");

    const liveRegion = page.locator('[aria-live="polite"].sr');
    await expect(liveRegion).toBeAttached();

    const composer = page.getByLabel("Message");
    await composer.click();
    await composer.fill("Hello, I have a question about my account.");
    await composer.press("Enter");

    // The customer's own message appears in the visible message list once
    // the turn completes; `LiveRegion` renders the assistant's reply to
    // that turn (`latestAssistantText`, `ChatScreen.tsx`), so a non-empty
    // live region afterward confirms the announcement path actually fired,
    // not just that the message list updated.
    await expect(page.locator(".chat-layout")).toContainText("Hello, I have a question", {
      timeout: 15_000,
    });
    await expect(liveRegion).not.toBeEmpty({ timeout: 15_000 });
  });
});
