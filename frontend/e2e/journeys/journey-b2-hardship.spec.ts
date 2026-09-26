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
} from "../fixtures/journeyHelpers";
import { loginAsPersona } from "../fixtures/personaLogin";

/**
 * E11-S3: Journey B2 end to end -- hardship detection, structured capture,
 * treatment suppression, escalation, human review and audit, including the
 * vulnerable-customer variant. Runs against the real dev stack in
 * deterministic MOCK mode (`llm_provider._mock_classifier`, zero network); see
 * `journey-a-ptp.spec.ts` for the shared MOCK/staleness context and
 * `fixtures/journeyHelpers.ts` for why each run picks a currently-clean
 * account rather than reseeding.
 *
 * MOCK recognises exactly one hardship wording ("lost my job" -> JOB_LOSS) and
 * one vulnerability wording (bereavement); the messages below are written to
 * match, so this journey proves the orchestration, rules, escalation and audit
 * around the model -- not model quality.
 */

const HARDSHIP_MESSAGE = "I lost my job and I can't afford my payments.";
const VULNERABLE_MESSAGE = "My husband passed away last week and I don't know how to manage this.";
/** Language that would promise or imply relief; the customer reply must have none (AC-B2-2). */
const RELIEF_LANGUAGE = /relief|waive|restructur|reduc|forgiv|approved|you qualify/i;

interface OutboundCounter {
  interactions: { direction: string }[];
}

async function outboundInteractionCount(
  page: import("@playwright/test").Page,
  request: import("@playwright/test").APIRequestContext,
  accountId: string,
): Promise<number> {
  const response = await request.get(`/api/customers/${accountId}/360`, {
    headers: await sessionHeaders(page),
  });
  expect(response.ok(), await response.text()).toBe(true);
  const body = (await response.json()) as OutboundCounter;
  return body.interactions.filter((interaction) => interaction.direction === "OUTBOUND").length;
}

test.describe("Journey B2: financial hardship", () => {
  // Multi-persona journeys drive several logins and a chat; give slower CI hardware headroom.
  test.describe.configure({ mode: "serial", timeout: 90_000 });

  test("job loss -> structured case, suppression, HARDSHIP_REVIEW escalation, officer decision with a reason, Customer 360 and audit", async ({
    page,
    request,
  }) => {
    // --- Setup: a currently-clean account, and the outbound-contact baseline ---
    await loginAsPersona(page, "COLLECTIONS_OFFICER");
    await refreshDemoSnapshots(page, request);
    const account = await findFreshAccount(page, request, 0);
    const outboundBefore = await outboundInteractionCount(page, request, account.accountId);

    // --- AC1: as the bound CUSTOMER, describe job loss in the chat ---
    await loginAsCustomerFor(page, account.customerId);
    const { reply, correlationId } = await sendChatMessage(page, HARDSHIP_MESSAGE);
    await expect(reply).toContainText(/specialist will review/i);
    await expect(reply).not.toContainText(RELIEF_LANGUAGE);
    // Nothing transactional is offered on a hardship message.
    await expect(page.getByRole("button", { name: "Confirm" })).toHaveCount(0);

    // The system recorded a structured hardship case, stopped automated
    // treatment and opened an elevated-priority HARDSHIP_REVIEW escalation.
    await loginAsPersona(page, "COLLECTIONS_OFFICER");
    const officerHeaders = await sessionHeaders(page);
    const customer360Response = await request.get(`/api/customers/${account.accountId}/360`, {
      headers: officerHeaders,
    });
    expect(customer360Response.ok(), await customer360Response.text()).toBe(true);
    const customer360 = (await customer360Response.json()) as {
      hardship_cases: {
        status: string;
        indicators: { indicator_type: string; customer_statement: string }[];
      }[];
      deterministic: { treatment: { automated_treatment_suppressed: boolean } };
    };
    const openHardship = customer360.hardship_cases.find((hardship) => hardship.status === "OPEN");
    expect(openHardship, JSON.stringify(customer360.hardship_cases)).toBeTruthy();
    expect(openHardship?.indicators.map((indicator) => indicator.indicator_type)).toEqual([
      "JOB_LOSS",
    ]);
    expect(openHardship?.indicators[0].customer_statement).toBe(HARDSHIP_MESSAGE);
    expect(customer360.deterministic.treatment.automated_treatment_suppressed).toBe(true);

    const cases = await escalationsForAccount(page, request, account.accountId);
    const hardshipCase = cases.find((item) => item.reason === "FINANCIAL_HARDSHIP");
    expect(hardshipCase, JSON.stringify(cases)).toBeTruthy();
    expect(hardshipCase?.queue).toBe("HARDSHIP_REVIEW");
    expect(hardshipCase?.status).toBe("OPEN");
    expect(hardshipCase?.priority, "hardship must be escalated above NORMAL").not.toBe("NORMAL");
    const caseId = hardshipCase!.case_id;

    // --- AC2 (first half): the case appears in the officer's review queue ---
    await page.goto("/escalations");
    await expect(page.getByRole("heading", { name: "Escalations" })).toBeVisible();
    const queueLink = page.locator(`a[href="/escalations/${caseId}"]`);
    await expect(queueLink).toBeVisible();
    await expect(queueLink).toHaveText("Financial hardship");

    // --- AC3: Customer 360 shows the hardship state and a human-review-only
    // next-best-action, and no automated outreach was produced ---
    const recommendationResponse = await request.post(
      `/api/accounts/${account.accountId}/recommendation`,
      { headers: officerHeaders },
    );
    expect(recommendationResponse.ok(), await recommendationResponse.text()).toBe(true);
    const recommendation = (await recommendationResponse.json()) as {
      status: string;
      recommendation: { action: string; content_source: string } | null;
    };
    expect(recommendation.status).toBe("HUMAN_REVIEW_ONLY");
    expect(recommendation.recommendation?.action).toBe("ESCALATE_TO_HUMAN_REVIEW");
    expect(recommendation.recommendation?.content_source, "no model output may drive it").not.toBe(
      "MODEL",
    );

    await page.goto(`/customers/${account.accountId}`);
    const hardshipPanel = page.getByRole("region", { name: "Hardship and disputes" });
    await expect(hardshipPanel).toBeVisible();
    await expect(hardshipPanel).toContainText(/open/i);
    await expect(hardshipPanel).toContainText(/job loss/i);
    await expect(page.getByText("Escalate to human review")).toBeVisible();
    expect(
      await outboundInteractionCount(page, request, account.accountId),
      "no automated outreach may be produced for a hardship account",
    ).toBe(outboundBefore);

    // --- AC2 (second half): the officer decides with a reason; the UI blocks
    // submission without one ---
    await page.goto(`/escalations/${caseId}`);
    await expect(page.getByRole("heading", { name: "Financial hardship" })).toBeVisible();
    await page.getByRole("button", { name: "Reject" }).click();
    const dialog = page.getByRole("dialog", { name: "Reject this case?" });
    await expect(dialog).toBeVisible();
    const submit = dialog.getByRole("button", { name: "Reject" });
    await expect(submit, "blocked with no reason").toBeDisabled();
    await dialog.getByLabel("Reason").fill("   ");
    await expect(submit, "blocked with a blank reason").toBeDisabled();
    await dialog.getByLabel("Reason").fill("Reviewed; no relief is available in the MVP.");
    await expect(submit).toBeEnabled();
    await submit.click();
    await expect(dialog).toBeHidden();
    await expect(page.getByText("DECIDED", { exact: true }).first()).toBeVisible({
      timeout: 15_000,
    });

    // The decision closes the hardship case and releases the account.
    const afterResponse = await request.get(`/api/customers/${account.accountId}/360`, {
      headers: officerHeaders,
    });
    const after = (await afterResponse.json()) as {
      hardship_cases: { status: string }[];
      escalation: { has_open_case: boolean };
    };
    expect(after.hardship_cases.every((hardship) => hardship.status === "DECIDED")).toBe(true);
    expect(after.escalation.has_open_case).toBe(false);

    // --- Audit: the full chain, with the hardship record, the escalation and
    // the reviewer decision, visible to COMPLIANCE_RISK ---
    await loginAsPersona(page, "COMPLIANCE_RISK");
    const events = await auditEventsForAccount(page, request, account.accountId);
    const chainTypes = events
      .filter((event) => event.correlation_id === correlationId)
      .map((event) => event.event_type);
    expect(chainTypes).toEqual(
      expect.arrayContaining([
        "AI_RESPONSE_RECORDED",
        "HARDSHIP_CASE_OPENED",
        "ESCALATION_CASE_CREATED",
      ]),
    );
    expect(events.map((event) => event.event_type)).toContain("REVIEW_DECISION_RECORDED");

    const timeline = await openChainInAuditViewer(page, correlationId);
    await expect(timeline.filter({ hasText: "HARDSHIP_CASE_OPENED" })).toHaveCount(1);
    await expect(timeline.filter({ hasText: "ESCALATION_CASE_CREATED" })).toHaveCount(1);
  });

  test("vulnerable-customer variant -> VULNERABLE_CUSTOMER_REVIEW escalation and a full audit chain", async ({
    page,
    request,
  }) => {
    await loginAsPersona(page, "COLLECTIONS_OFFICER");
    await refreshDemoSnapshots(page, request);
    const account = await findFreshAccount(page, request, 1);

    // --- AC4: the vulnerability signal (vulnerability_detected true) routes
    // to a mandatory human escalation and stops collection dialogue ---
    await loginAsCustomerFor(page, account.customerId);
    const { reply, correlationId } = await sendChatMessage(page, VULNERABLE_MESSAGE);
    await expect(reply).toContainText(/specialist/i);
    await expect(reply).not.toContainText(RELIEF_LANGUAGE);
    await expect(page.getByRole("button", { name: "Confirm" })).toHaveCount(0);

    await loginAsPersona(page, "COLLECTIONS_OFFICER");
    const cases = await escalationsForAccount(page, request, account.accountId);
    const vulnerableCase = cases.find((item) => item.reason === "VULNERABLE_CUSTOMER");
    expect(vulnerableCase, JSON.stringify(cases)).toBeTruthy();
    expect(vulnerableCase?.queue).toBe("VULNERABLE_CUSTOMER_REVIEW");
    expect(vulnerableCase?.status).toBe("OPEN");
    expect(vulnerableCase?.priority).not.toBe("NORMAL");

    // Tidy up through the real review endpoint so the account is reusable.
    await closeCase(page, request, vulnerableCase!.case_id, "Reviewed; supportive follow-up made.");

    // --- AC4: the audit viewer shows the full chain ---
    await loginAsPersona(page, "COMPLIANCE_RISK");
    const events = await auditEventsForAccount(page, request, account.accountId);
    const chainTypes = events
      .filter((event) => event.correlation_id === correlationId)
      .map((event) => event.event_type);
    expect(chainTypes).toEqual(
      expect.arrayContaining([
        "AI_RESPONSE_RECORDED",
        "ESCALATION_REQUIRED",
        "ESCALATION_CASE_CREATED",
      ]),
    );
    expect(events.map((event) => event.event_type)).toContain("REVIEW_DECISION_RECORDED");

    const timeline = await openChainInAuditViewer(page, correlationId);
    await expect(timeline.filter({ hasText: "ESCALATION_REQUIRED" })).toHaveCount(1);
    await expect(timeline.filter({ hasText: "ESCALATION_CASE_CREATED" })).toHaveCount(1);
    await expect(timeline.filter({ hasText: /mock-model/ }).first()).toBeVisible();
  });
});
