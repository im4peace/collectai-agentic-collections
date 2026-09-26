import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";
import type { Page } from "@playwright/test";

import {
  findFreshAccount,
  loginAsCustomerFor,
  refreshDemoSnapshots,
  sendChatMessage,
} from "../fixtures/journeyHelpers";
import { loginAsPersona } from "../fixtures/personaLogin";

/**
 * E11-S6 findings F-01 (page titles, WCAG 2.4.2) and F-02 (scrollable regions
 * reachable by keyboard, WCAG 2.1.1), verified against the real stack. F-03 is
 * in `escalation-case-detail.spec.ts`. These are automated checks of the
 * specific behaviours fixed; they are not screen-reader testing.
 */

const SCROLL_SELECTOR = ".tablewrap, .chat-messages";

/** For every scroll container on the page: does it overflow, and is it a tab stop? */
async function scrollContainers(
  page: Page,
): Promise<{ label: string | null; role: string | null; tabindex: string | null; overflows: boolean }[]> {
  return page.evaluate(
    (selector) =>
      Array.from(document.querySelectorAll<HTMLElement>(selector)).map((el) => ({
        label: el.getAttribute("aria-label"),
        role: el.getAttribute("role"),
        tabindex: el.getAttribute("tabindex"),
        overflows: el.scrollHeight > el.clientHeight + 1 || el.scrollWidth > el.clientWidth + 1,
      })),
    SCROLL_SELECTOR,
  );
}

async function scrollableRegionViolations(page: Page): Promise<string[]> {
  const results = await new AxeBuilder({ page }).withRules(["scrollable-region-focusable"]).analyze();
  return results.violations.map((violation) => `${violation.id}: ${violation.nodes.map((n) => n.target).join(", ")}`);
}

test.describe("F-01: every screen has its own page title", () => {
  test("titles follow navigation across officer, compliance and manager screens", async ({ page }) => {
    await page.goto("/");
    await expect(page).toHaveTitle("Persona Switcher | CollectAI");

    await loginAsPersona(page, "COLLECTIONS_OFFICER");
    await expect(page.getByRole("heading", { name: "Delinquent portfolio" })).toBeVisible();
    await expect(page).toHaveTitle("Portfolio | CollectAI");

    await page.getByRole("link", { name: "Escalations" }).click();
    await expect(page.getByRole("heading", { name: "Escalations" })).toBeVisible();
    await expect(page).toHaveTitle("Escalations | CollectAI");

    await page.getByRole("link", { name: "Customer 360" }).click();
    await expect(page.getByRole("heading", { name: "Rules engine" })).toBeVisible();
    await expect(page).toHaveTitle("Customer 360 | CollectAI");

    await page.getByRole("link", { name: "Portfolio" }).click();
    await expect(page).toHaveTitle("Portfolio | CollectAI");

    await loginAsPersona(page, "COMPLIANCE_RISK");
    await page.getByRole("link", { name: "Audit Trail" }).click();
    await expect(page.getByRole("heading", { name: "Audit trail" })).toBeVisible();
    await expect(page).toHaveTitle("Audit Trail | CollectAI");

    await loginAsPersona(page, "COLLECTIONS_MANAGER");
    await expect(page.getByRole("heading", { name: "Business" })).toBeVisible();
    await expect(page).toHaveTitle("Dashboard | CollectAI");
  });

  test("the chat and the forbidden page each have their own title", async ({ page, request }) => {
    await loginAsPersona(page, "COLLECTIONS_OFFICER");
    await refreshDemoSnapshots(page, request);
    const account = await findFreshAccount(page, request, {});

    await page.goto("/dashboard");
    await expect(page.getByRole("heading", { name: "403 - Forbidden" })).toBeVisible();
    await expect(page).toHaveTitle("Forbidden | CollectAI");

    await loginAsCustomerFor(page, account.customerId);
    await expect(page.getByLabel("Message")).toBeVisible();
    await expect(page).toHaveTitle("Chat | CollectAI");
  });
});

test.describe("F-02: scrollable regions are keyboard reachable", () => {
  test("a chat transcript that overflows is a named, focusable region that scrolls from the keyboard", async ({
    page,
    request,
  }) => {
    await loginAsPersona(page, "COLLECTIONS_OFFICER");
    await refreshDemoSnapshots(page, request);
    const account = await findFreshAccount(page, request, {});
    await loginAsCustomerFor(page, account.customerId);
    await page.setViewportSize({ width: 1280, height: 360 });

    // A short conversation: nothing to scroll, so the transcript is not a tab stop.
    await expect(page.getByLabel("Message")).toBeVisible();
    const transcript = page.getByRole("region", { name: "Conversation" });
    await expect(transcript).toBeVisible();
    expect(await transcript.getAttribute("tabindex")).toBeNull();

    // A longer one: the transcript now overflows its 60vh box.
    for (let i = 0; i < 3; i += 1) {
      await sendChatMessage(page, "Can I set up a payment plan?");
    }
    await expect
      .poll(async () => (await scrollContainers(page)).find((c) => c.label === "Conversation")?.overflows)
      .toBe(true);
    await expect(transcript).toHaveAttribute("tabindex", "0");

    // axe's scrollable-region-focusable rule no longer fires.
    expect(await scrollableRegionViolations(page)).toEqual([]);

    // Tab reaches it, with a visible focus indicator...
    await page.evaluate(() => {
      (document.activeElement as HTMLElement | null)?.blur();
      document.body.setAttribute("tabindex", "-1");
      document.body.focus();
      document.body.removeAttribute("tabindex");
    });
    let reached = false;
    for (let i = 0; i < 12 && !reached; i += 1) {
      await page.keyboard.press("Tab");
      reached = await transcript.evaluate((el) => el === document.activeElement);
    }
    expect(reached, "Tab must reach the transcript").toBe(true);
    const outline = await transcript.evaluate((el) => {
      const style = getComputedStyle(el);
      return { style: style.outlineStyle, width: Number.parseFloat(style.outlineWidth) };
    });
    expect(outline.style).not.toBe("none");
    expect(outline.width).toBeGreaterThan(0);

    // ...and the keyboard scrolls it.
    await transcript.evaluate((el) => {
      el.scrollTop = 0;
    });
    await page.keyboard.press("PageDown");
    await expect.poll(async () => transcript.evaluate((el) => el.scrollTop)).toBeGreaterThan(0);
    const afterPageDown = await transcript.evaluate((el) => el.scrollTop);
    await page.keyboard.press("ArrowDown");
    await expect.poll(async () => transcript.evaluate((el) => el.scrollTop)).toBeGreaterThan(afterPageDown);
  });

  test("a table wrapper is a focusable named region only while it overflows, and never an extra tab stop when it fits", async ({
    page,
    request,
  }) => {
    await loginAsPersona(page, "COLLECTIONS_OFFICER");
    await refreshDemoSnapshots(page, request);
    const account = await findFreshAccount(page, request, {});

    // Wide window: every table fits, so no wrapper is a tab stop.
    await page.goto(`/customers/${account.accountId}`);
    await expect(page.getByRole("heading", { name: "Rules engine" })).toBeVisible();
    for (const container of await scrollContainers(page)) {
      expect(container.overflows, "no table overflows at 1280px").toBe(false);
      expect(container.tabindex).toBeNull();
    }

    // 200% zoom (a 640 CSS px viewport): the factors table overflows its panel.
    await page.setViewportSize({ width: 640, height: 720 });
    await expect
      .poll(async () => (await scrollContainers(page)).some((c) => c.overflows))
      .toBe(true);
    // The invariant, once the page has re-measured: a wrapper is focusable
    // exactly while it scrolls, and then it is a named region.
    await expect
      .poll(async () => {
        const containers = await scrollContainers(page);
        return containers.every(
          (c) => (c.tabindex !== null) === c.overflows && (!c.overflows || (c.role === "region" && !!c.label)),
        );
      })
      .toBe(true);
    expect(await scrollableRegionViolations(page)).toEqual([]);

    // Tab reaches the overflowing region.
    const region = page.locator(`${SCROLL_SELECTOR}[tabindex="0"]`).first();
    await page.evaluate(() => {
      (document.activeElement as HTMLElement | null)?.blur();
      document.body.setAttribute("tabindex", "-1");
      document.body.focus();
      document.body.removeAttribute("tabindex");
    });
    let reached = false;
    for (let i = 0; i < 25 && !reached; i += 1) {
      await page.keyboard.press("Tab");
      reached = await region.evaluate((el) => el === document.activeElement);
    }
    expect(reached, "Tab must reach the overflowing table region").toBe(true);
  });
});
