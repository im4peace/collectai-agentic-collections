import { expect, test } from "@playwright/test";

import { sessionHeaders } from "../fixtures/apiHelpers";
import { loginAsPersona } from "../fixtures/personaLogin";

/**
 * E11-S2: Journey B1 end to end -- PAYMENT_PLAN, deterministic eligibility,
 * option selection, confirmation, arrangement creation and audit, including
 * the no-eligibility and exceptional branches. Runs against the real dev
 * stack; see `journey-a-ptp.spec.ts`'s own module docstring for the shared
 * MOCK-mode/staleness/classifier context this journey relies on identically.
 *
 * Eligibility (`policy-v1.json`: `eligible_max_dpd: 89`,
 * `min_overdue_amount: 100.00`) genuinely varies per seeded account, so
 * this spec queries `GET /api/portfolio?dpd_max=89` as the officer first to
 * find a real eligible account (AC1/AC2) and a real ineligible one
 * (`dpd_min=90`, AC3's first half) rather than assuming either exists at a
 * fixed id.
 */

interface PortfolioItem {
  account_id: string;
  customer_id: string;
  dpd: number;
  overdue_amount: string;
}

/** `GET /api/session/options`' demo-customer dropdown only lists the first
 * 25 customers by id (`CustomerRepository.list_demo_customers`'s own
 * `_DEMO_CUSTOMER_LIMIT`) -- `loginAsCustomerFor` below can only select a
 * customer within that range, so every portfolio search in this spec
 * filters to it rather than picking whichever account happens to match
 * eligibility criteria first. */
const DEMO_CUSTOMER_DROPDOWN_CEILING = "cus_000025";

function withinDemoCustomerDropdown(item: PortfolioItem): boolean {
  return item.customer_id <= DEMO_CUSTOMER_DROPDOWN_CEILING;
}

async function refreshDemoSnapshots(page: import("@playwright/test").Page, request: import("@playwright/test").APIRequestContext): Promise<void> {
  const headers = await sessionHeaders(page);
  const response = await request.post("/api/demo-controls/clock/advance", {
    headers,
    data: { days: 1, refresh_snapshots: true },
  });
  expect(response.ok()).toBe(true);
}

async function loginAsCustomerFor(
  page: import("@playwright/test").Page,
  request: import("@playwright/test").APIRequestContext,
  customerId: string,
): Promise<void> {
  await page.goto("/");
  await page.getByRole("radio", { name: /CUSTOMER/ }).click();
  const select = page.getByRole("combobox");
  await select.selectOption(customerId);
  await page.getByRole("button", { name: "Use this persona" }).click();
}

test.describe("Journey B1: eligible payment arrangement", () => {
  test("eligible options -> select -> Confirm (double-clicked) creates exactly one ACTIVE arrangement, with audit", async ({
    page,
    request,
  }) => {
    // --- Setup: officer refreshes snapshots and finds a real eligible account ---
    await loginAsPersona(page, "COLLECTIONS_OFFICER");
    await refreshDemoSnapshots(page, request);
    const officerHeaders = await sessionHeaders(page);

    const eligibleResponse = await request.get("/api/portfolio?limit=200&dpd_max=89", {
      headers: officerHeaders,
    });
    const eligibleBody = (await eligibleResponse.json()) as { items: PortfolioItem[] };
    const eligibleCandidate = eligibleBody.items.find(
      (item) => Number.parseFloat(item.overdue_amount) >= 100 && withinDemoCustomerDropdown(item),
    );
    expect(eligibleCandidate, "no eligible-for-arrangement account found in seed data").toBeTruthy();
    const eligible = eligibleCandidate!;

    // --- AC1: as the bound CUSTOMER, request a payment plan; only the
    // options the eligibility service actually returned are shown ---
    await loginAsCustomerFor(page, request, eligible.customer_id);
    const composer = page.getByLabel("Message");
    await composer.fill("Can I set up a payment plan?");
    await composer.press("Enter");
    const firstReply = page.locator(".chat-message.assistant").last();
    await expect(firstReply).toContainText(/payments of/i, { timeout: 15_000 });

    // --- AC2: selecting an option and confirming creates exactly one ACTIVE
    // arrangement, even if Confirm is clicked twice ---
    const composer2 = page.getByLabel("Message");
    await composer2.fill("I'll take the payment plan with 3 installments.");
    await composer2.press("Enter");
    await expect(page.getByRole("button", { name: "Confirm" })).toBeVisible({ timeout: 15_000 });

    await page.getByRole("button", { name: "Confirm" }).click();
    const confirmDialog = page.getByRole("dialog", { name: "Confirm this proposal?" });
    await expect(confirmDialog).toBeVisible();
    const dialogConfirm = confirmDialog.getByRole("button", { name: "Confirm" });
    // A genuine double click: both clicks issued concurrently (each waits
    // on Playwright's own actionability check, not on the other), so both
    // can pass the "is this button enabled" check before either network
    // request lands and React disables the button -- the same race a real
    // impatient double-click can trigger. The second click may legitimately
    // no-op once the button becomes disabled; either outcome is fine, only
    // the resulting arrangement count below is asserted.
    await Promise.all([
      dialogConfirm.click(),
      dialogConfirm.click().catch(() => undefined),
    ]);
    await expect(page.getByText(/confirmed|set up/i)).toBeVisible({ timeout: 15_000 });

    const customerHeaders = await sessionHeaders(page);
    const arrangementsResponse = await request.get(
      `/api/me/accounts/${eligible.account_id}/arrangements`,
      { headers: customerHeaders },
    );
    expect(arrangementsResponse.ok(), await arrangementsResponse.text()).toBe(true);
    const arrangements = (await arrangementsResponse.json()) as {
      items: { arrangement_id: string; status: string; option: { installment_count: number } }[];
    };
    const active = arrangements.items.filter((item) => item.status === "ACTIVE");
    expect(active, JSON.stringify(arrangements.items)).toHaveLength(1);
    expect(active[0].option.installment_count).toBe(3);

    // --- AC4: audit viewer shows the eligibility result, chosen option,
    // confirmation and PolicyRuleSet version for the journey ---
    await loginAsPersona(page, "COMPLIANCE_RISK");
    const complianceHeaders = await sessionHeaders(page);
    const auditResponse = await request.get(
      `/api/audit?account_id=${eligible.account_id}&limit=200`,
      { headers: complianceHeaders },
    );
    expect(auditResponse.ok()).toBe(true);
    const auditBody = (await auditResponse.json()) as {
      items: { event_type: string; policy_version: string | null }[];
    };
    expect(auditBody.items.map((event) => event.event_type)).toEqual(
      expect.arrayContaining(["ARRANGEMENT_CREATED"]),
    );
    const withPolicy = auditBody.items.find((event) => event.policy_version !== null);
    expect(withPolicy, JSON.stringify(auditBody.items)).toBeTruthy();
  });

  test("a no-eligible-option scenario offers a human (AC3)", async ({ page, request }) => {
    await loginAsPersona(page, "COLLECTIONS_OFFICER");
    await refreshDemoSnapshots(page, request);
    const officerHeaders = await sessionHeaders(page);

    const ineligibleResponse = await request.get("/api/portfolio?limit=200&dpd_min=90", {
      headers: officerHeaders,
    });
    const ineligibleBody = (await ineligibleResponse.json()) as { items: PortfolioItem[] };
    const ineligible = ineligibleBody.items.find(withinDemoCustomerDropdown);
    expect(ineligible, "no ineligible (dpd >= 90) account found in seed data").toBeTruthy();

    await loginAsCustomerFor(page, request, ineligible!.customer_id);
    const composer = page.getByLabel("Message");
    await composer.fill("Can I set up a payment plan?");
    await composer.press("Enter");

    const reply = page.locator(".chat-message.assistant").last();
    await expect(reply).toContainText(/can't offer a payment plan/i, { timeout: 15_000 });
    await expect(reply).toContainText(/talk to a human/i);
    await expect(page.getByRole("button", { name: "Confirm" })).toHaveCount(0);
  });

  test("an exceptional request creates an escalation in COLLECTIONS_EXCEPTION_REVIEW with no approval language (AC3)", async ({
    page,
    request,
  }) => {
    await loginAsPersona(page, "COLLECTIONS_OFFICER");
    await refreshDemoSnapshots(page, request);
    const officerHeaders = await sessionHeaders(page);

    const eligibleResponse = await request.get("/api/portfolio?limit=200&dpd_max=89", {
      headers: officerHeaders,
    });
    const eligibleBody = (await eligibleResponse.json()) as { items: PortfolioItem[] };
    const eligibleCandidate = eligibleBody.items.find(
      (item) => Number.parseFloat(item.overdue_amount) >= 100 && withinDemoCustomerDropdown(item),
    );
    expect(eligibleCandidate).toBeTruthy();
    const eligible = eligibleCandidate!;

    await loginAsCustomerFor(page, request, eligible.customer_id);
    const composer = page.getByLabel("Message");
    await composer.fill("Can I set up a payment plan?");
    await composer.press("Enter");
    await expect(page.locator(".chat-message.assistant").last()).toContainText(/payments of/i, {
      timeout: 15_000,
    });

    // policy-v1.json: exception.thresholds.max_installment_count = 24, and
    // the standard offered set is {3, 6, 12} -- 24 installments is outside
    // the standard set but within the officer's exception authority, so
    // this classifies EXCEPTIONAL rather than being rejected outright.
    const composer2 = page.getByLabel("Message");
    await composer2.fill("I'll take the payment plan with 24 installments.");
    await composer2.press("Enter");

    const assistantText = page.locator(".chat-message.assistant").last();
    await expect(assistantText).toContainText(/specialist/i, { timeout: 15_000 });
    await expect(assistantText).not.toContainText(/approved|congratulations|you're all set/i);
    await expect(page.getByRole("button", { name: "Confirm" })).toHaveCount(0);

    await loginAsPersona(page, "COLLECTIONS_OFFICER");
    const escalationsResponse = await request.get(
      `/api/escalations?queue=COLLECTIONS_EXCEPTION_REVIEW&account_id=${eligible.account_id}`,
      { headers: officerHeaders },
    );
    expect(escalationsResponse.ok(), await escalationsResponse.text()).toBe(true);
    const escalations = (await escalationsResponse.json()) as {
      items: { queue: string; reason: string }[];
    };
    expect(escalations.items.length, JSON.stringify(escalations.items)).toBeGreaterThan(0);
    expect(escalations.items[0].queue).toBe("COLLECTIONS_EXCEPTION_REVIEW");
  });
});
