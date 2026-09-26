import type { APIRequestContext, Locator, Page } from "@playwright/test";
import { expect } from "@playwright/test";

import { sessionHeaders } from "./apiHelpers";

/**
 * Shared setup for the Group K journeys (E11-S3, E11-S4). They run against a
 * real, long-lived dev stack, so nothing here assumes a pristine database:
 * every journey picks an account that is *currently* clean (no open case,
 * dispute, hardship, active PTP or suppression) instead of a hard-coded id,
 * and ends by driving its own cases to a terminal state through the real
 * review endpoints, so the same account is reusable on the next run.
 * `POST /api/demo-controls/reseed` is deliberately not used: it only restores
 * the core tables and, by least-privilege design (no DELETE grant), never
 * removes cases/disputes/conversations, and it would race the other specs
 * running in parallel against the same database.
 */

/** `GET /api/session/options`' customer dropdown lists only the first 25
 * customers, so a bound-CUSTOMER login can only select one of them. */
const DEMO_CUSTOMER_DROPDOWN_CEILING = 25;

/** Each journey draws its account from its own lane (customer number modulo
 * this), so parallel journeys never pick the same account. */
const LANE_COUNT = 3;

export interface FreshAccount {
  accountId: string;
  customerId: string;
  overdueAmount: string;
}

interface PortfolioItem {
  account_id: string;
  customer_id: string;
  overdue_amount: string;
  dpd: number;
}

interface Customer360Subset {
  snapshot: { freshness: string };
  account: { overdue_amount: string };
  deterministic: { status: string; treatment: { automated_treatment_suppressed: boolean } };
  escalation: { has_open_case: boolean };
  hardship_cases: { status: string }[];
  disputes: { status: string }[];
  ptp_history: { status: string }[];
}

/** Everything `isCleanAccount` can judge from Customer 360. Customer 360's own
 * `arrangements` list is always empty (E8-S1 left it out of scope), so an ACTIVE
 * arrangement is checked separately, through the customer-scoped endpoint
 * (`hasActiveArrangement`). */
export function isCleanAccount(customer360: Customer360Subset): boolean {
  return (
    customer360.snapshot.freshness === "FRESH" &&
    customer360.deterministic.status === "OK" &&
    !customer360.deterministic.treatment.automated_treatment_suppressed &&
    !customer360.escalation.has_open_case &&
    customer360.hardship_cases.every((hardship) => hardship.status === "DECIDED") &&
    customer360.disputes.every((dispute) => dispute.status === "RESOLVED") &&
    customer360.ptp_history.every((ptp) => ptp.status !== "PENDING")
  );
}

/** Whether the account has an ACTIVE payment arrangement, read as its own
 * (bound) customer -- the only persona with an arrangements listing. */
async function hasActiveArrangement(
  request: APIRequestContext,
  customerId: string,
  accountId: string,
): Promise<boolean> {
  const session = await request.post("/api/session", {
    data: { persona: "CUSTOMER", customer_id: customerId },
  });
  expect(session.ok(), await session.text()).toBe(true);
  const { session_token: token } = (await session.json()) as { session_token: string };
  const response = await request.get(`/api/me/accounts/${accountId}/arrangements`, {
    headers: { "X-Persona": "CUSTOMER", "X-Demo-Session": token },
  });
  expect(response.ok(), await response.text()).toBe(true);
  const { items } = (await response.json()) as { items: { status: string }[] };
  return items.some((item) => item.status === "ACTIVE");
}

function customerNumber(customerId: string): number {
  return Number.parseInt(customerId.replace("cus_", ""), 10);
}

/** `POST /api/demo-controls/clock/advance` with `refresh_snapshots`: marks
 * every snapshot fresh so PTP/proposal writes are not rejected as stale. The
 * current session must be COLLECTIONS_OFFICER. */
export async function refreshDemoSnapshots(page: Page, request: APIRequestContext): Promise<void> {
  const response = await request.post("/api/demo-controls/clock/advance", {
    headers: await sessionHeaders(page),
    data: { days: 1, refresh_snapshots: true },
  });
  expect(response.ok(), await response.text()).toBe(true);
}

/** The simulated clock's current instant (ISO). Audit events are stamped with
 * this clock, so it is the right lower bound for "events from this journey". */
export async function simulatedNowIso(page: Page, request: APIRequestContext): Promise<string> {
  const response = await request.get("/api/demo-controls/state", {
    headers: await sessionHeaders(page),
  });
  expect(response.ok(), await response.text()).toBe(true);
  return ((await response.json()) as { clock: { current_time: string } }).clock.current_time;
}

/** The simulated clock's current date minus the machine's real date, in whole
 * days. The default MOCK provider resolves "in N days" against the real
 * calendar (`_mock_classifier`), while the app validates against the
 * simulated clock, which every journey nudges forward -- so a PTP message's N
 * must absorb this drift to land inside the policy window. */
export async function simulatedClockDriftDays(
  page: Page,
  request: APIRequestContext,
): Promise<number> {
  const simulated = new Date(await simulatedNowIso(page, request));
  const simulatedDay = Date.UTC(
    simulated.getUTCFullYear(),
    simulated.getUTCMonth(),
    simulated.getUTCDate(),
  );
  const now = new Date();
  const realDay = Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate());
  return Math.round((simulatedDay - realDay) / 86_400_000);
}

export interface FreshAccountOptions {
  /** Draw only from this lane (customer number modulo `LANE_COUNT`), so two
   * journeys running in parallel never pick the same account. Omit for any lane. */
  lane?: number;
  /** Inclusive days-past-due bounds, e.g. `{ dpdMax: 89 }` for an account the
   * arrangement rules can serve or `{ dpdMin: 90 }` for one they cannot. */
  dpdMin?: number;
  dpdMax?: number;
  /** Search from the end of the portfolio (the Group K journeys) or from the
   * front (the older specs), so the two families rarely compete. Default: front. */
  fromEnd?: boolean;
}

/**
 * Finds a delinquent account among the demo customers that is clean right
 * now (see `isCleanAccount`) and matches `selector` (a lane number, or full
 * options). The current session must be COLLECTIONS_OFFICER.
 *
 * Repeatability note: a journey that leaves a permanent ACTIVE arrangement
 * (Journey B1's confirm test) removes its account from the clean pool -- there
 * is no cancel-arrangement endpoint and, by least-privilege design, no DELETE
 * grant -- so a long-lived database eventually runs out and this throws a
 * descriptive error. A fresh database (CI, `make down && make up`) restores it.
 */
export async function findFreshAccount(
  page: Page,
  request: APIRequestContext,
  selector: number | FreshAccountOptions,
): Promise<FreshAccount> {
  const options = typeof selector === "number" ? { lane: selector, fromEnd: true } : selector;
  const headers = await sessionHeaders(page);
  const portfolio = await request.get("/api/portfolio?limit=200", { headers });
  expect(portfolio.ok(), await portfolio.text()).toBe(true);
  const items = ((await portfolio.json()) as { items: PortfolioItem[] }).items;
  const matching = items.filter((item) => {
    const number = customerNumber(item.customer_id);
    return (
      number <= DEMO_CUSTOMER_DROPDOWN_CEILING &&
      (options.lane === undefined || number % LANE_COUNT === options.lane) &&
      (options.dpdMin === undefined || item.dpd >= options.dpdMin) &&
      (options.dpdMax === undefined || item.dpd <= options.dpdMax) &&
      Number.parseFloat(item.overdue_amount) >= 100
    );
  });
  const candidates = options.fromEnd ? matching.reverse() : matching;

  for (const candidate of candidates) {
    const response = await request.get(`/api/customers/${candidate.account_id}/360`, { headers });
    if (!response.ok()) continue;
    if (!isCleanAccount((await response.json()) as Customer360Subset)) continue;
    if (await hasActiveArrangement(request, candidate.customer_id, candidate.account_id)) continue;
    return {
      accountId: candidate.account_id,
      customerId: candidate.customer_id,
      overdueAmount: candidate.overdue_amount,
    };
  }
  throw new Error(
    `No clean delinquent demo account matches ${JSON.stringify(options)} ` +
      `(checked ${candidates.length}). Every candidate has an open case, dispute, hardship, ` +
      `active PTP or arrangement, or suppression left by earlier runs.`,
  );
}

/** Drives the real persona switcher as a bound CUSTOMER for `customerId`. */
export async function loginAsCustomerFor(page: Page, customerId: string): Promise<void> {
  await page.goto("/");
  await page.getByRole("radio", { name: /CUSTOMER/ }).click();
  await page.getByRole("combobox").selectOption(customerId);
  await page.getByRole("button", { name: "Use this persona" }).click();
  await page.waitForFunction(() => {
    const raw = window.sessionStorage.getItem("collectai.demoSession");
    return raw !== null && (JSON.parse(raw) as { persona: string }).persona === "CUSTOMER";
  });
}

export interface ChatProposal {
  proposal_id: string;
  terms_hash: string;
}

export interface ChatTurn {
  reply: Locator;
  conversationId: string;
  /** The proposal this turn produced, if any (nothing is written until the
   * customer confirms it). */
  proposal: ChatProposal | null;
  /** The turn's `correlation_id`: every audit event this message wrote
   * (AI response, escalation, hardship/dispute record) shares it. */
  correlationId: string;
}

/** Sends one chat message; returns the assistant reply it produced and the
 * turn's correlation id. The reply is located by the content the API returned
 * for this turn, so it never depends on how many messages were already shown
 * (the greeting loads asynchronously). */
export async function sendChatMessage(page: Page, text: string): Promise<ChatTurn> {
  const composer = page.getByLabel("Message");
  await composer.fill(text);
  const [response] = await Promise.all([
    page.waitForResponse(
      (candidate) =>
        candidate.request().method() === "POST" && /\/messages$/.test(candidate.url()),
    ),
    composer.press("Enter"),
  ]);
  expect(response.ok(), await response.text()).toBe(true);
  const body = (await response.json()) as {
    correlation_id: string;
    conversation_id: string;
    proposal: ChatProposal | null;
    assistant_message: { content: string };
  };
  const reply = page
    .locator(".chat-message.assistant")
    .filter({ hasText: body.assistant_message.content })
    .last();
  await expect(reply).toBeVisible({ timeout: 15_000 });
  return {
    reply,
    conversationId: body.conversation_id,
    proposal: body.proposal,
    correlationId: body.correlation_id,
  };
}

/** Opens one decision chain in the Audit Trail viewer UI by correlation id
 * (COMPLIANCE_RISK session) and returns its timeline entries. */
export async function openChainInAuditViewer(page: Page, correlationId: string): Promise<Locator> {
  await page.goto("/audit");
  await expect(page.getByRole("heading", { name: "Audit trail" })).toBeVisible();
  await page.getByLabel("Correlation id").fill(correlationId);
  await page.getByRole("button", { name: "Search" }).click();
  const entries = page.locator("ol > li");
  await expect(entries.first()).toBeVisible({ timeout: 15_000 });
  return entries;
}

/**
 * Creates a REQUEST_HUMAN escalation case the way a customer really does: as
 * the bound CUSTOMER for `customerId`, click "Talk to a human". Returns the new
 * case id (from the handoff response), so callers can open exactly that case
 * instead of assuming which row is first. Leaves the session as that CUSTOMER.
 */
export async function createHandoffCase(page: Page, customerId: string): Promise<string> {
  await loginAsCustomerFor(page, customerId);
  const [response] = await Promise.all([
    page.waitForResponse(
      (candidate) =>
        candidate.request().method() === "POST" && /\/handoff$/.test(candidate.url()),
    ),
    page.getByRole("button", { name: "Talk to a human" }).click(),
  ]);
  expect(response.ok(), await response.text()).toBe(true);
  const body = (await response.json()) as { escalation: { case_id: string } };
  return body.escalation.case_id;
}

interface CaseListItem {
  case_id: string;
  reason: string;
  queue: string;
  priority: string;
  status: string;
  version: number;
}

/** The escalation cases for an account (officer session), newest first. */
export async function escalationsForAccount(
  page: Page,
  request: APIRequestContext,
  accountId: string,
): Promise<CaseListItem[]> {
  const response = await request.get(`/api/escalations?account_id=${accountId}&limit=50`, {
    headers: await sessionHeaders(page),
  });
  expect(response.ok(), await response.text()).toBe(true);
  return ((await response.json()) as { items: CaseListItem[] }).items;
}

/** Closes an escalation case through the real reviewer-decision endpoint
 * (REJECT with a reason), so the account is clean again for the next run.
 * The current session must be COLLECTIONS_OFFICER. */
export async function closeCase(
  page: Page,
  request: APIRequestContext,
  caseId: string,
  reason: string,
): Promise<void> {
  const headers = await sessionHeaders(page);
  const detail = await request.get(`/api/escalations/${caseId}`, { headers });
  expect(detail.ok(), await detail.text()).toBe(true);
  const { version, status } = (await detail.json()) as { version: number; status: string };
  if (status === "DECIDED") return;
  const response = await request.post(`/api/escalations/${caseId}/decisions`, {
    headers: { ...headers, "Idempotency-Key": `journey-close-${caseId}` },
    data: { action: "REJECT", expected_version: version, reason },
  });
  expect(response.ok(), await response.text()).toBe(true);
}

export interface AuditEventSubset {
  event_type: string;
  correlation_id: string;
  actor_persona: string | null;
  policy_version: string | null;
}

/** Audit events for an account (COMPLIANCE_RISK session), optionally only
 * those at or after `fromIso` (see `simulatedNowIso`): a long-lived account
 * accumulates more than one 200-event page of history across runs. */
export async function auditEventsForAccount(
  page: Page,
  request: APIRequestContext,
  accountId: string,
  fromIso?: string,
): Promise<AuditEventSubset[]> {
  const from = fromIso === undefined ? "" : `&from=${encodeURIComponent(fromIso)}`;
  const response = await request.get(`/api/audit?account_id=${accountId}${from}&limit=200`, {
    headers: await sessionHeaders(page),
  });
  expect(response.ok(), await response.text()).toBe(true);
  return ((await response.json()) as { items: AuditEventSubset[] }).items;
}
