import { expect, test } from "@playwright/test";

import { sessionHeaders } from "../fixtures/apiHelpers";
import {
  auditEventsForAccount,
  closeCase,
  escalationsForAccount,
  findFreshAccount,
  loginAsCustomerFor,
  openChainInAuditViewer,
  refreshDemoSnapshots,
  sendChatMessage,
  simulatedClockDriftDays,
} from "../fixtures/journeyHelpers";
import { loginAsPersona } from "../fixtures/personaLogin";

/**
 * E11-S4: Journey C end to end -- dispute detection, structured capture,
 * treatment pause, escalation, human resolution and audit. Runs against the
 * real dev stack in deterministic MOCK mode (zero network); see
 * `journey-a-ptp.spec.ts` for the shared MOCK/staleness context and
 * `fixtures/journeyHelpers.ts` for why each run picks a currently-clean
 * account rather than reseeding.
 *
 * AC2's real contract (traced through the production flow, not assumed):
 * once a dispute exists, automated treatment is suppressed, so a *new* chat PTP
 * attempt is refused before any proposal exists (a templated "under review"
 * reply, no Confirm, no write). `DISPUTED_ITEM` is the PTP domain service's
 * own refusal, and it surfaces at *confirmation*: a proposal created before
 * the dispute can no longer be confirmed once the dispute is open (409
 * `DISPUTED_ITEM`, nothing written). Both are asserted below.
 */

const DISPUTE_MESSAGE = "I dispute this charge, it is not my debt.";
const JUDGING_LANGUAGE = /valid|invalid|you're right|we agree|confirmed that|upheld|rejected/i;

async function customer360(
  page: import("@playwright/test").Page,
  request: import("@playwright/test").APIRequestContext,
  accountId: string,
): Promise<{
  disputes: {
    dispute_id: string;
    status: string;
    category: string;
    customer_reason: string;
    outcome: string | null;
    resolution_reason: string | null;
  }[];
  deterministic: {
    treatment: {
      automated_treatment_suppressed: boolean;
      suppressions: { source_type: string }[];
    };
  };
}> {
  const response = await request.get(`/api/customers/${accountId}/360`, {
    headers: await sessionHeaders(page),
  });
  expect(response.ok(), await response.text()).toBe(true);
  return response.json();
}

test.describe("Journey C: dispute", () => {
  // Multi-persona journeys drive several logins and a chat; give slower CI hardware headroom.
  test.describe.configure({ mode: "serial", timeout: 90_000 });

  test("dispute -> structured record, pause, DISPUTE_REVIEW, PTP refused, officer resolves with outcome and reason, full audit", async ({
    page,
    request,
  }) => {
    // --- Setup: a currently-clean account, and a PTP wording that lands in
    // the policy window despite the simulated-clock drift ---
    await loginAsPersona(page, "COLLECTIONS_OFFICER");
    await refreshDemoSnapshots(page, request);
    const account = await findFreshAccount(page, request, 2);
    const drift = await simulatedClockDriftDays(page, request);
    const promisedAmount = (Number.parseFloat(account.overdueAmount) * 0.3).toFixed(2);

    // --- A PTP proposal exists *before* the dispute (nothing is written until
    // the customer confirms it) ---
    await loginAsCustomerFor(page, account.customerId);
    const preDispute = await sendChatMessage(
      page,
      `I promise to pay ${promisedAmount} in ${drift + 7} days.`,
    );
    expect(preDispute.proposal, "a PTP proposal must exist before the dispute").toBeTruthy();
    await expect(page.getByRole("button", { name: "Confirm" })).toBeVisible();
    const proposal = preDispute.proposal!;

    // --- AC1: as the bound CUSTOMER, raise a dispute ---
    const dispute = await sendChatMessage(page, DISPUTE_MESSAGE);
    await expect(dispute.reply).toContainText(/recorded your dispute/i);
    await expect(dispute.reply).toContainText(/specialist/i);
    await expect(dispute.reply, "the AI never judges validity").not.toContainText(JUDGING_LANGUAGE);
    // The superseded proposal is no longer offered for confirmation.
    await expect(page.getByRole("button", { name: "Confirm" })).toHaveCount(0);

    // Structured category and reason stored, the item paused, and a
    // DISPUTE_REVIEW escalation created.
    await loginAsPersona(page, "COLLECTIONS_OFFICER");
    const after = await customer360(page, request, account.accountId);
    const openDispute = after.disputes.find((item) => item.status === "OPEN");
    expect(openDispute, JSON.stringify(after.disputes)).toBeTruthy();
    expect(openDispute?.category).toBe("NOT_MY_DEBT");
    expect(openDispute?.customer_reason).toBe(DISPUTE_MESSAGE);
    expect(after.deterministic.treatment.automated_treatment_suppressed).toBe(true);
    expect(after.deterministic.treatment.suppressions.map((entry) => entry.source_type)).toContain(
      "DISPUTE",
    );

    const cases = await escalationsForAccount(page, request, account.accountId);
    const disputeCase = cases.find((item) => item.reason === "DISPUTE");
    expect(disputeCase, JSON.stringify(cases)).toBeTruthy();
    expect(disputeCase?.queue).toBe("DISPUTE_REVIEW");
    expect(disputeCase?.status).toBe("OPEN");
    const caseId = disputeCase!.case_id;
    const disputeId = openDispute!.dispute_id;

    // --- AC2: a PTP on the disputed account is refused until a human acts ---
    await loginAsCustomerFor(page, account.customerId);
    const customerHeaders = await sessionHeaders(page);
    // (a) A new chat attempt is refused before any proposal exists.
    const retry = await sendChatMessage(
      page,
      `I promise to pay ${promisedAmount} in ${drift + 7} days.`,
    );
    await expect(retry.reply).toContainText(/being reviewed by a specialist/i);
    expect(retry.proposal).toBeNull();
    await expect(page.getByRole("button", { name: "Confirm" })).toHaveCount(0);
    // (b) The proposal made before the dispute cannot be confirmed: the PTP
    // domain service refuses it as DISPUTED_ITEM and writes nothing.
    const confirmResponse = await request.post(
      `/api/chat/conversations/${preDispute.conversationId}/proposals/${proposal.proposal_id}/confirm`,
      {
        headers: { ...customerHeaders, "Idempotency-Key": `journey-c-confirm-${disputeId}` },
        data: { terms_hash: proposal.terms_hash },
      },
    );
    expect(confirmResponse.status()).toBe(409);
    const refusal = (await confirmResponse.json()) as { error: { reason_code: string } };
    expect(refusal.error.reason_code).toBe("DISPUTED_ITEM");
    const ptps = await request.get(`/api/me/accounts/${account.accountId}/ptps`, {
      headers: customerHeaders,
    });
    const ptpList = (await ptps.json()) as { items: { status: string }[] };
    expect(ptpList.items.filter((ptp) => ptp.status === "PENDING")).toHaveLength(0);

    // --- AC3: the officer reviews and resolves with an outcome and a reason;
    // the UI requires both ---
    await loginAsPersona(page, "COLLECTIONS_OFFICER");
    await page.goto("/escalations");
    await expect(page.locator(`a[href="/escalations/${caseId}"]`)).toBeVisible();
    await page.locator(`a[href="/escalations/${caseId}"]`).click();
    const panel = page.getByRole("region", { name: "Dispute resolution" });
    await expect(panel).toBeVisible();
    await expect(panel).toContainText(DISPUTE_MESSAGE);
    await expect(panel).toContainText(/open/i);

    await panel.getByRole("button", { name: "Start review" }).click();
    await expect(panel).toContainText(/under review/i, { timeout: 15_000 });

    const resolve = panel.getByRole("button", { name: "Resolve dispute" });
    await expect(resolve, "blocked with neither outcome nor reason").toBeDisabled();
    await panel.getByLabel("Outcome").selectOption("REJECTED");
    await expect(resolve, "blocked with an outcome but no reason").toBeDisabled();
    await panel.getByLabel("Outcome").selectOption("");
    await panel.getByLabel("Reason").fill("Ledger confirms the debt belongs to this customer.");
    await expect(resolve, "blocked with a reason but no outcome").toBeDisabled();
    await panel.getByLabel("Outcome").selectOption("REJECTED");
    await expect(resolve).toBeEnabled();
    await resolve.click();

    await expect(panel).toContainText("Dispute resolved.", { timeout: 15_000 });
    await expect(panel.getByText("Resolved", { exact: true })).toBeVisible();
    await expect(panel).toContainText("Rejected");
    await expect(panel).toContainText("Ledger confirms the debt belongs to this customer.");
    await expect(panel.getByRole("button", { name: "Resolve dispute" })).toHaveCount(0);

    const resolved = await customer360(page, request, account.accountId);
    const resolvedDispute = resolved.disputes.find((item) => item.dispute_id === disputeId);
    expect(resolvedDispute?.status).toBe("RESOLVED");
    expect(resolvedDispute?.outcome).toBe("REJECTED");
    expect(resolvedDispute?.resolution_reason).toBe(
      "Ledger confirms the debt belongs to this customer.",
    );
    // The human resolution lifted the dispute's own suppression.
    expect(resolved.deterministic.treatment.suppressions.map((entry) => entry.source_type)).not.toContain(
      "DISPUTE",
    );

    // Tidy up through the real review endpoint so the account is reusable.
    await closeCase(page, request, caseId, "Dispute resolved; closing the case.");

    // --- AC4: the audit viewer shows every dispute status transition and the
    // reviewer decision ---
    await loginAsPersona(page, "COMPLIANCE_RISK");
    const events = await auditEventsForAccount(page, request, account.accountId);
    const opened = events.find(
      (event) => event.event_type === "DISPUTE_OPENED" && event.correlation_id === dispute.correlationId,
    );
    const underReview = events.find((event) => event.event_type === "DISPUTE_UNDER_REVIEW");
    const resolvedEvent = events.find((event) => event.event_type === "DISPUTE_RESOLVED");
    expect(opened, JSON.stringify(events.map((event) => event.event_type))).toBeTruthy();
    expect(underReview).toBeTruthy();
    expect(resolvedEvent).toBeTruthy();
    expect(underReview?.actor_persona).toBe("COLLECTIONS_OFFICER");
    expect(resolvedEvent?.actor_persona).toBe("COLLECTIONS_OFFICER");
    expect(events.map((event) => event.event_type)).toContain("REVIEW_DECISION_RECORDED");
    // In order: opened, then under review, then resolved.
    const order = events.map((event) => event.event_type);
    expect(order.indexOf("DISPUTE_OPENED")).toBeLessThan(order.indexOf("DISPUTE_UNDER_REVIEW"));
    expect(order.indexOf("DISPUTE_UNDER_REVIEW")).toBeLessThan(order.indexOf("DISPUTE_RESOLVED"));

    for (const [eventType, correlationId] of [
      ["DISPUTE_OPENED", opened!.correlation_id],
      ["DISPUTE_UNDER_REVIEW", underReview!.correlation_id],
      ["DISPUTE_RESOLVED", resolvedEvent!.correlation_id],
    ] as const) {
      const timeline = await openChainInAuditViewer(page, correlationId);
      await expect(timeline.filter({ hasText: eventType }).first()).toBeVisible();
    }
  });
});
