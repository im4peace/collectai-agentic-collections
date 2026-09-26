import { expect, test } from "@playwright/test";

import { sessionHeaders } from "../fixtures/apiHelpers";
import {
  auditEventsForAccount,
  closeCase,
  escalationsForAccount,
  findFreshAccount,
  loginAsCustomerFor,
  refreshDemoSnapshots,
  sendChatMessage,
  simulatedNowIso,
} from "../fixtures/journeyHelpers";
import { loginAsPersona } from "../fixtures/personaLogin";

/**
 * E11-S2: Journey B1 end to end -- PAYMENT_PLAN, deterministic eligibility,
 * option selection, confirmation, arrangement creation and audit, including
 * the no-eligibility and exceptional branches. Runs against the real dev
 * stack; see `journey-a-ptp.spec.ts`'s own module docstring for the shared
 * MOCK-mode/staleness/classifier context this journey relies on identically.
 *
 * Eligibility (`policy-v1.json`: `eligible_max_dpd: 89`,
 * `min_overdue_amount: 100.00`) genuinely varies per seeded account, so each
 * test asks for a *currently clean* eligible account (`dpdMax: 89`) or a clean
 * ineligible one (`dpdMin: 90`) via `findFreshAccount` instead of assuming one
 * exists at a fixed id, or that an earlier test left a customer untouched.
 *
 * Repeatability: the exceptional test closes its escalation case through the
 * real review endpoint. The confirm test necessarily leaves an ACTIVE
 * arrangement -- there is no cancel endpoint -- which takes that account out of
 * the clean pool, so a long-lived database eventually runs out of eligible
 * accounts and `findFreshAccount` says so; a fresh database restores them.
 */

test.describe("Journey B1: eligible payment arrangement", () => {
  // Each test consumes/holds an account from the shared pool and the journeys
  // drive several logins, so run them in order and give slower hardware headroom.
  test.describe.configure({ mode: "serial", timeout: 90_000 });

  test("eligible options -> select -> Confirm (double-clicked) creates exactly one ACTIVE arrangement, with audit", async ({
    page,
    request,
  }) => {
    // --- Setup: officer refreshes snapshots and finds a clean eligible account ---
    await loginAsPersona(page, "COLLECTIONS_OFFICER");
    await refreshDemoSnapshots(page, request);
    const eligible = await findFreshAccount(page, request, { dpdMax: 89 });
    const journeyStart = await simulatedNowIso(page, request);

    // --- AC1: as the bound CUSTOMER, request a payment plan; only the
    // options the eligibility service actually returned are shown ---
    await loginAsCustomerFor(page, eligible.customerId);
    const first = await sendChatMessage(page, "Can I set up a payment plan?");
    await expect(first.reply).toContainText(/payments of/i);

    // --- AC2: selecting an option and confirming creates exactly one ACTIVE
    // arrangement, even if Confirm is clicked twice ---
    await sendChatMessage(page, "I'll take the payment plan with 3 installments.");
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
    // the resulting arrangement count below is asserted. The second click is
    // bounded: if the dialog is already tearing down it can never become
    // actionable, and an unbounded wait would silently eat the whole test timeout.
    await Promise.all([
      dialogConfirm.click(),
      dialogConfirm.click({ timeout: 2_000 }).catch(() => undefined),
    ]);
    // The confirmation message, asserted inside the transcript (the same
    // sentence is also in a screen-reader live region, so a page-wide text
    // match would be ambiguous).
    await expect(page.getByLabel("Conversation").getByText(/has been set up/i)).toBeVisible({
      timeout: 15_000,
    });

    const customerHeaders = await sessionHeaders(page);
    const arrangementsResponse = await request.get(
      `/api/me/accounts/${eligible.accountId}/arrangements`,
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
    const events = await auditEventsForAccount(page, request, eligible.accountId, journeyStart);
    expect(events.map((event) => event.event_type)).toEqual(
      expect.arrayContaining(["ARRANGEMENT_CREATED"]),
    );
    const withPolicy = events.find((event) => event.policy_version !== null);
    expect(withPolicy, JSON.stringify(events)).toBeTruthy();
  });

  test("a no-eligible-option scenario offers a human (AC3)", async ({ page, request }) => {
    await loginAsPersona(page, "COLLECTIONS_OFFICER");
    await refreshDemoSnapshots(page, request);
    // dpd >= 90 is past `eligible_max_dpd`, so the eligibility service returns no options.
    const ineligible = await findFreshAccount(page, request, { dpdMin: 90 });

    await loginAsCustomerFor(page, ineligible.customerId);
    const { reply } = await sendChatMessage(page, "Can I set up a payment plan?");

    await expect(reply).toContainText(/can't offer a payment plan/i);
    await expect(reply).toContainText(/talk to a human/i);
    await expect(page.getByRole("button", { name: "Confirm" })).toHaveCount(0);
  });

  test("an exceptional request creates an escalation in COLLECTIONS_EXCEPTION_REVIEW with no approval language (AC3)", async ({
    page,
    request,
  }) => {
    await loginAsPersona(page, "COLLECTIONS_OFFICER");
    await refreshDemoSnapshots(page, request);
    const eligible = await findFreshAccount(page, request, { dpdMax: 89 });

    await loginAsCustomerFor(page, eligible.customerId);
    const plan = await sendChatMessage(page, "Can I set up a payment plan?");
    await expect(plan.reply).toContainText(/payments of/i);

    // policy-v1.json: exception.thresholds.max_installment_count = 24, and
    // the standard offered set is {3, 6, 12} -- 24 installments is outside
    // the standard set but within the officer's exception authority, so
    // this classifies EXCEPTIONAL rather than being rejected outright.
    const exceptional = await sendChatMessage(
      page,
      "I'll take the payment plan with 24 installments.",
    );

    await expect(exceptional.reply).toContainText(/specialist/i);
    await expect(exceptional.reply).not.toContainText(/approved|congratulations|you're all set/i);
    await expect(page.getByRole("button", { name: "Confirm" })).toHaveCount(0);

    await loginAsPersona(page, "COLLECTIONS_OFFICER");
    const cases = await escalationsForAccount(page, request, eligible.accountId);
    const exceptionCase = cases.find((item) => item.queue === "COLLECTIONS_EXCEPTION_REVIEW");
    expect(exceptionCase, JSON.stringify(cases)).toBeTruthy();
    expect(exceptionCase?.queue).toBe("COLLECTIONS_EXCEPTION_REVIEW");

    // Tidy up through the real review endpoint so the account is reusable.
    await closeCase(page, request, exceptionCase!.case_id, "Reviewed; no exception granted.");
  });
});
