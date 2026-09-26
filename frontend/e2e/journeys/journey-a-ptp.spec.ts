import { expect, test } from "@playwright/test";

import { sessionHeaders } from "../fixtures/apiHelpers";
import {
  findFreshAccount,
  loginAsCustomerFor,
  refreshDemoSnapshots,
  simulatedClockDriftDays,
  simulatedNowIso,
} from "../fixtures/journeyHelpers";
import { loginAsPersona } from "../fixtures/personaLogin";

/**
 * E11-S1: Journey A end to end -- Portfolio, Customer 360, AI chat, PTP
 * with confirmation, simulated payment or clock, KEPT or BROKEN, and the
 * audit trail. Runs against the real dev stack (`playwright.config.ts`),
 * with `LLM_MODE=MOCK` (AC5: `docker-compose.test.yml` forces this in CI,
 * so this journey never reaches the network -- `llm_provider.MockProvider`
 * makes zero network calls by construction, already proven by `tests/unit
 * /llm_provider/test_e5_s1_mock.py::test_mock_provider_makes_zero_network
 * _calls`; this spec's own successful run against a real MOCK-mode server
 * is the integration-level half of that same guarantee).
 *
 * The demo dataset's seeded `DelinquencyRecord.as_of` is a fixed historical
 * constant (`persistence/seed/generator.py`'s `_SEED_NOW`), so every
 * account reads stale against a real clock well after that date -- this
 * spec's first step, as COLLECTIONS_OFFICER, calls `POST /api/demo-
 * controls/clock/advance` with `refresh_snapshots: true` to mark every
 * snapshot fresh before the journey begins (a realistic "officer preps the
 * demo" action, and the only way any PTP/proposal confirm can succeed).
 *
 * Repeatability: the journey no longer assumes "the first demo customer" is
 * clean. It picks a currently-clean delinquent account (`findFreshAccount`),
 * binds the CUSTOMER to that account's customer, and makes the MOCK provider's
 * real-calendar "in N days" land in the policy window whatever the simulated
 * clock has drifted to (`simulatedClockDriftDays`). It ends with both PTPs in a
 * terminal state (KEPT and BROKEN), so the account is clean for the next run.
 *
 * The AI chat surface in MOCK mode is driven by `llm_provider
 * ._mock_classifier`, a keyword-based classifier standing in for a real
 * model call -- it recognizes "I promise to pay <amount> in <N> days."
 * verbatim, which this spec's chat messages are written to match exactly.
 */

test.describe("Journey A: Promise-to-Pay", () => {
  // Several persona logins, a chat and two PTP lifecycles: headroom for slower hardware.
  test.describe.configure({ timeout: 90_000 });

  test("Portfolio -> Customer 360 -> AI chat PTP -> Confirm -> PENDING -> KEPT/BROKEN -> audit trail", async ({
    page,
    request,
  }) => {
    // --- AC1: officer opens Portfolio, selects an account, reaches Customer 360 ---
    await loginAsPersona(page, "COLLECTIONS_OFFICER");
    await refreshDemoSnapshots(page, request);
    const fresh = await findFreshAccount(page, request, {});
    const drift = await simulatedClockDriftDays(page, request);
    const journeyStart = await simulatedNowIso(page, request);
    const account = { account_id: fresh.accountId, overdue_amount: fresh.overdueAmount };

    await page.goto("/portfolio");
    await expect(page.getByRole("heading", { name: "Delinquent portfolio" })).toBeVisible();
    await page.locator("tbody tr").first().getByRole("link").click();

    await expect(page.getByRole("heading", { name: "Rules engine" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "AI-generated" })).toBeVisible();
    const priorityBadge = page.getByText(/(HIGH|MEDIUM|LOW) priority/);
    await expect(priorityBadge).toBeVisible();
    await expect(page.getByText("score", { exact: false })).toBeVisible();
    await expect(page.getByRole("table", { name: "Contributing factors" })).toBeVisible();

    // --- AC2: as the bound CUSTOMER, complete the PTP conversation ---
    await loginAsCustomerFor(page, fresh.customerId);
    const customerHeaders = await sessionHeaders(page);
    const ptpsUrl = `/api/me/accounts/${account.account_id}/ptps`;
    type PtpRow = { ptp_id: string; status: string; source: string; promised_amount: string };
    const listPtps = async (): Promise<PtpRow[]> => {
      const listResponse = await request.get(ptpsUrl, { headers: customerHeaders });
      return ((await listResponse.json()) as { items: PtpRow[] }).items;
    };
    // Earlier runs may have left terminal PTPs on this account: only ever look
    // at the ones this run creates, and key its payments to this run.
    const priorPtpIds = new Set((await listPtps()).map((item) => item.ptp_id));
    const runId = Date.now();
    const promisedAmount = (Number.parseFloat(account.overdue_amount) * 0.3).toFixed(2);

    await expect(page.getByRole("button", { name: "Talk to a human" })).toBeVisible();
    const composer = page.getByLabel("Message");
    await composer.fill(`I promise to pay ${promisedAmount} in ${drift + 5} days.`);
    await composer.press("Enter");

    // The AI's service-returned values (never the customer's raw text) are
    // shown before any write happens.
    // Scoped to the proposal card: the same sentence is also in the chat
    // transcript and a screen-reader live region.
    await expect(
      page
        .getByRole("group", { name: "Proposal awaiting confirmation" })
        .getByText(new RegExp(`promise ${promisedAmount.replace(".", "\\.")}`)),
    ).toBeVisible({ timeout: 15_000 });
    await expect(page.getByRole("button", { name: "Confirm" })).toBeVisible();

    // An explicit Confirm click is required -- nothing was written yet.
    await page.getByRole("button", { name: "Confirm" }).click();
    const confirmDialog = page.getByRole("dialog", { name: "Confirm this proposal?" });
    await expect(confirmDialog).toBeVisible();
    await confirmDialog.getByRole("button", { name: "Confirm" }).click();
    await expect(page.getByLabel("Conversation").getByText("has been recorded")).toBeVisible({ timeout: 15_000 });

    const ptpItems = await listPtps();
    const createdPtp = ptpItems.find(
      (item) =>
        !priorPtpIds.has(item.ptp_id) &&
        item.source === "CUSTOMER_CHAT" &&
        item.promised_amount === promisedAmount,
    );
    expect(createdPtp, JSON.stringify(ptpItems)).toBeTruthy();
    expect(createdPtp?.status).toBe("PENDING");

    // --- AC3: KEPT via two partial simulated payments ---
    await loginAsPersona(page, "COLLECTIONS_OFFICER");
    const officerHeaders = await sessionHeaders(page);
    // Two partial payments that sum to the promised amount *exactly*, in integer
    // cents (two independently rounded halves can fall a cent short, which
    // would leave the PTP PENDING instead of KEPT).
    const promisedCents = Math.round(Number.parseFloat(promisedAmount) * 100);
    const firstCents = Math.floor(promisedCents / 2);
    const payments = [firstCents, promisedCents - firstCents].map((cents) => (cents / 100).toFixed(2));
    for (const [index, amount] of payments.entries()) {
      const paymentResponse = await request.post("/api/demo-controls/payments/simulate", {
        headers: { ...officerHeaders, "Idempotency-Key": `journey-a-kept-${runId}-${index}` },
        data: { account_id: account.account_id, amount },
      });
      expect(paymentResponse.ok(), await paymentResponse.text()).toBe(true);
      const paymentBody = (await paymentResponse.json()) as {
        payment_event: { simulated: boolean };
      };
      expect(paymentBody.payment_event.simulated).toBe(true);
    }
    const afterKeptResponse = await request.get(`/api/me/accounts/${account.account_id}/ptps`, {
      headers: customerHeaders,
    });
    const afterKept = (await afterKeptResponse.json()) as {
      items: { ptp_id: string; status: string }[];
    };
    const keptPtp = afterKept.items.find((item) => item.ptp_id === createdPtp?.ptp_id);
    expect(keptPtp?.status).toBe("KEPT");

    // --- AC3: BROKEN via a second PTP, advancing the clock past its due date ---
    await loginAsCustomerFor(page, fresh.customerId);
    const composer2 = page.getByLabel("Message");
    await composer2.fill(`I promise to pay 10 in ${drift + 1} days.`);
    await composer2.press("Enter");
    await expect(page.getByRole("button", { name: "Confirm" })).toBeVisible({ timeout: 15_000 });
    await page.getByRole("button", { name: "Confirm" }).click();
    await page.getByRole("dialog", { name: "Confirm this proposal?" }).getByRole("button", { name: "Confirm" }).click();
    await expect(page.getByLabel("Conversation").getByText("has been recorded")).toBeVisible({ timeout: 15_000 });

    await loginAsPersona(page, "COLLECTIONS_OFFICER");
    const advanceResponse = await request.post("/api/demo-controls/clock/advance", {
      headers: officerHeaders,
      data: { days: 5, refresh_snapshots: false },
    });
    expect(advanceResponse.ok()).toBe(true);
    const lifecycleResponse = await request.post("/api/demo-controls/ptp-lifecycle/run", {
      headers: officerHeaders,
    });
    expect(lifecycleResponse.ok()).toBe(true);

    const afterBrokenResponse = await request.get(`/api/me/accounts/${account.account_id}/ptps`, {
      headers: customerHeaders,
    });
    const afterBroken = (await afterBrokenResponse.json()) as {
      items: { ptp_id: string; status: string; promised_amount: string }[];
    };
    const brokenPtp = afterBroken.items.find(
      (item) =>
        !priorPtpIds.has(item.ptp_id) &&
        item.promised_amount === "10.00" &&
        item.ptp_id !== createdPtp?.ptp_id,
    );
    expect(brokenPtp?.status).toBe("BROKEN");

    // --- AC4: compliance sees the full decision chain, with model id, prompt
    // version and PolicyRuleSet version, for every state transition ---
    await loginAsPersona(page, "COMPLIANCE_RISK");
    await page.getByRole("link", { name: "Audit Trail" }).click();
    await expect(page.getByRole("heading", { name: "Audit trail" })).toBeVisible();
    await page.getByLabel("Account id").fill(account.account_id);
    await page.getByRole("button", { name: "Search" }).click();

    const complianceHeaders = await sessionHeaders(page);
    const auditResponse = await request.get(
      `/api/audit?account_id=${account.account_id}&from=${encodeURIComponent(journeyStart)}&limit=200`,
      { headers: complianceHeaders },
    );
    expect(auditResponse.ok(), await auditResponse.text()).toBe(true);
    const auditBody = (await auditResponse.json()) as {
      items: { event_type: string; model_id: string | null; prompt_version: string | null; policy_version: string | null }[];
    };
    const eventTypes = auditBody.items.map((event) => event.event_type);
    // One audit event per state transition (AC4): the AI's own intent
    // classification and proposal extraction (each `AI_RESPONSE_RECORDED`,
    // carrying model id + prompt version), the PTP write itself
    // (`PTP_RECORDED`, carrying the PolicyRuleSet version) and each lifecycle
    // transition, all on this account.
    expect(eventTypes).toEqual(
      expect.arrayContaining(["AI_RESPONSE_RECORDED", "PTP_RECORDED", "PTP_KEPT", "PTP_BROKEN"]),
    );
    // This journey's own clock/lifecycle demo-control actions are system-wide
    // (they carry no account), so they are read from the journey's time window.
    const windowResponse = await request.get(
      `/api/audit?from=${encodeURIComponent(journeyStart)}&limit=200`,
      { headers: complianceHeaders },
    );
    expect(windowResponse.ok(), await windowResponse.text()).toBe(true);
    const windowTypes = ((await windowResponse.json()) as { items: { event_type: string }[] }).items.map(
      (event) => event.event_type,
    );
    expect(windowTypes).toEqual(
      expect.arrayContaining(["DEMO_CLOCK_ADVANCED", "DEMO_PTP_LIFECYCLE_RUN"]),
    );
    const aiEvent = auditBody.items.find((event) => event.model_id !== null);
    expect(aiEvent, JSON.stringify(auditBody.items)).toBeTruthy();
    expect(aiEvent?.prompt_version).toBeTruthy();
    const policyEvent = auditBody.items.find((event) => event.policy_version !== null);
    expect(policyEvent, JSON.stringify(auditBody.items)).toBeTruthy();
  });
});
