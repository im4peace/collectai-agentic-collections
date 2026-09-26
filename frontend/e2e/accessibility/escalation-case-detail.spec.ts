import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

import { sessionHeaders } from "../fixtures/apiHelpers";
import {
  closeCase,
  createHandoffCase,
  findFreshAccount,
  refreshDemoSnapshots,
} from "../fixtures/journeyHelpers";
import { loginAsPersona } from "../fixtures/personaLogin";

/**
 * E7-S3 AC2, AC3, AC4, AC7: the case-detail screen -- three separately
 * labelled sections, reason-gated action dialogs, zero serious/critical axe
 * violations, and focus management identical to `dialogs-and-live-region
 * .spec.ts`'s own established pattern for `ConfirmDialog`.
 *
 * The demo dataset seeds no escalation cases (they are created by the real
 * app flow, never static seed data), so each test here first creates its own
 * as CUSTOMER via the chat screen's "Talk to a human" handoff (E6-S1), which
 * routes a REQUEST_HUMAN case to the COLLECTIONS_REVIEW queue -- mirroring how
 * a real officer would encounter a case, not a fixture. The customer is a
 * currently-clean account (not "the first demo customer"), the test opens
 * exactly the case it created (never "the first row"), and `afterEach` closes
 * it through the real review endpoint, so the spec depends on no other spec's
 * data and leaves none behind (see `fixtures/journeyHelpers.ts`).
 *
 * Requires a running backend reachable through the Vite dev proxy, per
 * `playwright.config.ts`.
 */

function seriousOrCritical(violations: { impact?: string | null }[]) {
  return violations.filter((v) => v.impact === "serious" || v.impact === "critical");
}

test.describe("Escalation case detail", () => {
  let caseId = "";

  test.beforeEach(async ({ page, request }) => {
    await loginAsPersona(page, "COLLECTIONS_OFFICER");
    await refreshDemoSnapshots(page, request);
    const account = await findFreshAccount(page, request, {});
    caseId = await createHandoffCase(page, account.customerId);
    await loginAsPersona(page, "COLLECTIONS_OFFICER");
  });

  test.afterEach(async ({ page, request }) => {
    // The session may be any persona if a test failed midway; closing needs the officer.
    await loginAsPersona(page, "COLLECTIONS_OFFICER");
    await closeCase(page, request, caseId, "Test cleanup.");
  });

  async function openCase(page: import("@playwright/test").Page): Promise<void> {
    await page.getByRole("link", { name: "Escalations" }).click();
    await expect(page.getByRole("heading", { name: "Escalations" })).toBeVisible();
    await page.locator(`a[href="/escalations/${caseId}"]`).click();
  }

  test("is reachable by an officer, shows three labelled sections and has zero serious/critical axe violations (AC2, AC4)", async ({
    page,
  }) => {
    await openCase(page);

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
    await openCase(page);
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

  test("a recorded decision is announced and focus moves to the case status, not <body> (E11-S6 F-03)", async ({
    page,
  }) => {
    await openCase(page);
    await expect(page.getByRole("heading", { name: "Reviewer decision" })).toBeVisible();
    await expect(page).toHaveTitle("Escalation Case | CollectAI"); // F-01, on the case screen

    await page.getByRole("button", { name: "Reject" }).click();
    const dialog = page.getByRole("dialog", { name: "Reject this case?" });
    await dialog.getByLabel("Reason").fill("Reviewed; no action needed.");
    await dialog.getByRole("button", { name: "Reject" }).click();

    // The outcome is announced through a polite status region...
    const announcement = page.getByText("Reject decision recorded. Case status: DECIDED.");
    await expect(announcement).toBeAttached({ timeout: 15_000 });
    await expect(page.locator('[role="status"][aria-live="polite"]').filter({ has: announcement })).toHaveCount(1);
    // ...the dialog is gone, the decision controls left with the new status...
    await expect(dialog).toBeHidden();
    await expect(page.getByRole("button", { name: "Reject" })).toHaveCount(0);
    // ...and focus is on the case status, not dropped on <body>.
    const status = page.getByRole("group", { name: "Case status" });
    await expect(status).toBeFocused();
    await expect(status).toContainText("DECIDED");
    expect(await page.evaluate(() => document.activeElement === document.body)).toBe(false);
  });

  test("a stale-version conflict shows a message and reloads the case (AC4)", async ({
    page,
    request,
  }) => {
    await openCase(page);
    await expect(page.getByRole("heading", { name: "Reviewer decision" })).toBeVisible();

    // Another reviewer acts on the same case first, bumping its version behind
    // this tab's back (REQUEST_MORE_INFORMATION changes the version but leaves
    // the case actionable) -- the screen still holds the `expected_version` it
    // loaded with. Done through the real endpoint: `sessionStorage` is per-tab,
    // so a second browser tab would not share this officer session.
    const headers = await sessionHeaders(page);
    const detail = await request.get(`/api/escalations/${caseId}`, { headers });
    const { version } = (await detail.json()) as { version: number };
    const other = await request.post(`/api/escalations/${caseId}/decisions`, {
      headers: { ...headers, "Idempotency-Key": `stale-version-${caseId}` },
      data: {
        action: "REQUEST_MORE_INFORMATION",
        expected_version: version,
        note: "Handled by another reviewer.",
      },
    });
    expect(other.ok(), await other.text()).toBe(true);

    // The screen still shows the case as it loaded it: OPEN, at the old version.
    await expect(page.getByText("OPEN", { exact: true }).first()).toBeVisible();

    await page.getByRole("button", { name: "Reject" }).click();
    const dialog = page.getByRole("dialog", { name: "Reject this case?" });
    await dialog.getByLabel("Reason").fill("Stale attempt.");
    await dialog.getByRole("button", { name: "Reject" }).click();

    // E7-S3 AC4, in full: the stale-version message appears...
    await expect(page.getByRole("alert").filter({ hasText: "This case changed" })).toBeVisible();
    // ...the decision dialog closes...
    await expect(dialog).toBeHidden();
    // ...and the case is refetched, so the server's current state is shown.
    await expect(page.getByText("AWAITING INFORMATION", { exact: true }).first()).toBeVisible();
    await expect(page.getByText("OPEN", { exact: true })).toHaveCount(0);

    // The rejected Reject was not retried or applied behind the reviewer's back:
    // the case is exactly where the other reviewer left it, one version on.
    const after = await request.get(`/api/escalations/${caseId}`, { headers });
    const current = (await after.json()) as { status: string; version: number };
    expect(current.status).toBe("AWAITING_INFORMATION");
    expect(current.version).toBe(version + 1);
  });
});
