# CollectAI - Business Requirements Document (BRD)

Status: APPROVED (rev 2, content approved by the product owner on 2026-09-21). Source documents aligned to this BRD (section 18.2).
Date: 2026-09-21
Source of truth: `docs/PRODUCT_VISION.md`, `docs/MVP_REQUIREMENTS.md` (US-001..US-010; US-011 committed at `7d7f784` on branch `docs/add-us-011-dispute-escalation`, not yet merged to `main`), `CLAUDE.md`. Alignment actions between this BRD and those documents are listed in section 18.2.

---

## 1. Executive Summary and Value Proposition

CollectAI is an AI-native Collections and Recovery platform for banks, built as a portfolio and learning project with synthetic data only. It demonstrates how conversational AI and agentic workflows can combine with deterministic financial controls, human oversight and complete auditability.

The core engineering principle is non-negotiable: LLMs understand, classify, summarize, recommend and explain; deterministic services calculate, validate eligibility, prioritize, modify financial state and execute financial actions.

The primary audience is hiring managers and senior product/technology leaders (AI Product Manager, Senior PM, AI Product Owner, Digital Banking Product roles); secondary audiences are AI engineers, solution architects and banking stakeholders. The BRD therefore covers both a working end-to-end product and four portfolio deliverables (section 15).

All targets in this document are portfolio/demo targets, not claims about production banking performance.

### 1.1 Value proposition

For collections teams in banks who work fragmented customer information with static treatment strategies, CollectAI is an AI-assisted collections workspace that prioritizes accounts deterministically, lets customers resolve routine obligations through a governed AI assistant, and routes every sensitive decision to a human, with every AI and rule decision traceable. Unlike a chatbot bolted onto a collections system, CollectAI keeps all money movement, eligibility and prioritization in deterministic services and makes the AI's contribution measurable and auditable.

### 1.2 Outcome hypotheses (product hypotheses, not results)

These are hypotheses to be tested in a real deployment. Nothing in this project measures real business improvement, because all data is synthetic. Demo dashboards only illustrate how the metrics would be computed.

| ID | Hypothesis | Metric family that would test it |
|---|---|---|
| H1 | Deterministic priority bands with AI-written explanations reduce manual triage effort and improve consistency of account handling | Recovery effectiveness; operational efficiency |
| H2 | Governed conversational self-service resolves routine Promise-to-Pay and eligible arrangements without officer time | Customer resolution (self-service resolution rate) |
| H3 | Detecting hardship, dispute and vulnerability signals in conversation, and routing them to humans, identifies these cases earlier and more consistently | AI quality and safety (sensitive-intent recall, escalation accuracy) |
| H4 | Deterministic controls plus a complete decision audit trail close the "why was this decided" visibility gap | AI quality and safety; audit coverage |

## 2. Problem Statement

Traditional collections operations rely on manual segmentation, static treatment strategies, limited agent capacity and fragmented customer information. This causes:

- High operational cost and repetitive agent work
- Inconsistent customer treatment
- Low right-party contact and poor account prioritization
- Delayed identification of financial hardship
- Compliance and audit risk, including limited visibility into why AI-assisted decisions were made

Cost of not solving it (for the portfolio): without a working product there is only limited tangible evidence of moving beyond AI product concepts into a delivered product covering problem discovery, requirements, architecture, agent/tool design, deterministic banking controls, implementation, AI evaluation, governance and measurable outcomes.

## 3. Target Users, Goals and Jobs-to-be-Done

| Persona (RBAC role) | Priority | Goals / jobs-to-be-done |
|---|---|---|
| COLLECTIONS_OFFICER | Primary | See which delinquent accounts need attention first and why; understand a customer's full collection situation quickly; get a consistent next-best-action with rationale; review and decide on escalated cases with clear context; keep every decision defensible |
| CUSTOMER | Secondary | Understand what is owed in plain language; resolve the overdue amount in a way that fits their situation (pay now, promise a date, or an arrangement); be treated respectfully; reach a human at any time; have hardship or disputes handled by a person, not argued with a bot |
| COLLECTIONS_MANAGER | Secondary | Monitor portfolio health, recovery, escalation workload and AI performance; see whether AI quality is measured (LIVE) or only regression-tested (MOCK); read-only |
| COMPLIANCE_RISK | Secondary | Reconstruct any AI-assisted decision end to end (input, AI interpretation, tool/proposal, rule validation, human decision, final state); verify controls and safety metrics; read-only, cannot mutate |

Personas are switchable in the demo (no real authentication), but permissions are enforced server-side for the active persona (D-019).

## 4. Success Metrics

### 4.1 90-day demo/portfolio success criteria

Product/demo
- At least 4 complete end-to-end journeys demonstrated (section 6): Journey A (Promise-to-Pay), Journey B1 (eligible payment arrangement), Journey B2 (financial hardship), Journey C (dispute). These cover the three portfolio journeys: PTP; arrangement/hardship; escalation/dispute.
- Working portfolio and Customer 360; AI customer conversation; deterministic rules/eligibility and priority services; human approval workflow; audit trail; collections and AI dashboard.

AI quality (claims only when measured; see 4.4 and 4.6)
- >= 90% overall intent classification accuracy on the defined labelled eval dataset, measured in LIVE mode.
- >= 95% LIVE recall for each sensitive category (section 4.4), published only under the sample-size rule there (D-008, D-025).
- Full audit coverage of material AI recommendations and tool calls within the automated and evaluation suites (definitions in 4.2).
- Zero unauthorized financial-state changes by the LLM, and zero critical policy violations, within the defined guardrail/red-team suite (definitions in 4.2).
- Financial calculations, eligibility and priority produced only by deterministic services, verified as in 4.3.
- Human escalation available in every supported journey.
- Schema validation on all business-critical structured AI outputs.

Engineering
- Automated unit, API and integration tests; E2E browser tests for the primary journeys; AI eval suite covering normal, edge, adversarial and policy scenarios; clear architecture and product docs; reproducible local setup with synthetic data.

### 4.2 Definitions used by all zero/100% claims

- **Material AI recommendation**: any AI output that (a) leads to a PROPOSE tool call, (b) is a next-best-action or priority explanation shown to an officer, (c) is an intent classification that drives routing, (d) is customer-facing text containing an account-derived figure, date or repayment option, or (e) is an escalation or non-escalation decision. Other AI outputs (greetings, generic clarifying questions) are still logged but are not subject to the full-audit claim.
- **Critical policy violation** (any one, observed in an eval or red-team case): (1) LLM-caused state change that did not pass validation and authorization; (2) a customer-facing currency figure, date or repayment option delivered that was not returned by a deterministic service; (3) the AI approves, promises or implies approval of a settlement, waiver, fee change or policy exception; (4) the AI determines dispute validity or approves hardship treatment/restructuring; (5) threatening, coercive or misleading statements; (6) disclosure of another customer's data, secrets or prohibited identifiers; (7) continued automated collection treatment after a dispute, vulnerability signal or human request without escalation.
- **Mandatory escalation**: any case in the Mandatory Human Actions list (section 5.7) that is detectable from a conversation: FINANCIAL_HARDSHIP, DISPUTE, REQUEST_HUMAN, vulnerable-customer signals, exceptional arrangement requests, policy-exception requests and settlement requests.
- **Escalation accuracy**: on the labelled eval set, the share of cases where the system's escalate / do-not-escalate decision matches the label; reported together with precision, recall and over-escalation rate (unnecessary escalations).
- **Claim scope**: every "zero" or "100%" statement in this document applies to the defined automated test and evaluation suites at the stated dataset version. It is not a claim about behaviour outside those suites.

### 4.3 Verification of deterministic-only calculation

"Financial calculations, eligibility decisions and priority scoring are performed by deterministic services, not the LLM" is verified by all of:
1. Architecture tests showing the LLM provider and AI orchestration modules contain no financial calculation, eligibility or scoring code path and cannot import the Rules Engine's calculation functions except through validated service calls.
2. Grounding tests showing every currency figure, date and repayment option in customer-facing output in the test and eval suites traces to a deterministic service result.
3. Hostile-provider tests: a MOCK provider returning arbitrary, malformed or adversarial outputs never causes a state change without passing schema validation, authorization/policy validation and a deterministic domain service.

### 4.4 Sensitive-intent evaluation rules

- Retain >= 90% overall LIVE intent classification accuracy.
- Target >= 95% LIVE recall for each of: FINANCIAL_HARDSHIP, DISPUTE, REQUEST_HUMAN, and other explicitly defined mandatory-escalation scenarios (exceptional arrangement request, policy-exception request, settlement request).
- A per-category recall claim may be published only when that category has at least 30 labelled LIVE-evaluation cases. Below 30, results are reported as observations without a pass/fail claim.
- Vulnerable-customer signals must trigger mandatory human escalation and are evaluated separately as a safety scenario set, even though they are not a standalone conversational intent. Any missed escalation in that set is a critical policy violation (4.2, item 7).
- The eval report (P2) must show for each category: dataset provenance, number of cases, true positives, false negatives, recall, model/version, prompt/template version and evaluation date.
- Dataset provenance must state how cases were authored (for example by the project author and/or an LLM), that all data is synthetic, and that LIVE results measure performance on that dataset only.

### 4.5 KPI tree (portfolio deliverable P1)

North star: recovery of overdue amounts through fair, compliant, auditable customer treatment. All values on synthetic data are illustrative and are labelled `ILLUSTRATIVE` (simulated business data), `MOCK` (regression only) or `LIVE` (measured evaluation). Business KPIs are product hypotheses until measured in a real deployment (section 1.2).

```
Business outcome: recovery with fair, auditable treatment
|- Recovery effectiveness
|   |- Total delinquent accounts
|   |- Total overdue amount
|   |- Recovered amount (from simulated PaymentEvents)
|   |- Recovery rate = recovered amount / overdue amount at start
|   |- Promise-to-Pay rate
|   |- Promise-kept rate ; PTP breakage rate
|- Customer resolution
|   |- Self-service resolution rate (resolved without human review)
|   |- Arrangement take-up rate (of eligible offers)
|   |- Hardship and dispute case counts
|   |- Human escalation rate
|- Operational efficiency
|   |- Escalation queue size and aging
|   |- Time-to-review for escalations
|   |- Human override rate
|- AI quality and safety
    |- Intent classification accuracy (LIVE)
    |- Sensitive-category recall (LIVE)
    |- Escalation accuracy, over-escalation rate (LIVE)
    |- Structured-output compliance rate (LIVE and MOCK, labelled)
    |- Grounded response rate ; hallucination rate (ungrounded figure attempts caught)
    |- Tool-call success rate ; policy violation rate
    |- Response latency ; token usage and estimated cost per AI interaction
```

Deferred, because they need data outside the MVP model (D-027): right-party contact rate, average handling time, cost per collected account. Each delivered KPI states definition, formula, data source, owner persona and data label.

### 4.6 Measurement rules

- MOCK results are for CI/regression only and are never claimed as evidence of real-model quality.
- Intent-accuracy and recall claims come only from LIVE evaluation runs on the labelled dataset.
- Only measured performance figures are reported; latency targets are observational, not SLAs.
- MOCK and LIVE results are always reported and displayed separately.

## 5. Scope

### 5.1 In scope
- User stories US-001..US-010 from `docs/MVP_REQUIREMENTS.md` plus US-011.
- Both product types: CARD and PERSONAL_LOAN via one shared delinquent-account abstraction with product-specific attributes and rules (D-014).
- Simulated in-browser web chat (customer); demo persona switching with server-side RBAC.
- Deterministic rules engine with versioned PolicyRuleSet, including a deterministic Collections Priority model (5.6) and simulated contact-frequency policy examples (13.3).
- Simulated payment flow for PAY_NOW (5.4).
- Human-in-the-loop review and escalation (5.7).
- Append-only audit trail; eval framework with MOCK and LIVE modes.

### 5.2 Out of scope (v1)
Real core-banking integrations; real payment processing/gateways; real outbound SMS/email/WhatsApp/voice; enterprise SSO; production-grade IAM; multi-tenancy; regulatory certification; production deployment; real customer or banking data; SSE/token streaming; multi-model routing; microservices/message bus.

Deferred future scope: **Settlement** (D-023). No Settlement entity, autonomous settlement workflow or settlement UI in the MVP. Settlement remains a human-controlled capability conceptually: any settlement request encountered is a mandatory human action (5.7) and is escalated. Also deferred: right-party contact rate, average handling time and cost-per-collected-account KPIs (D-027); conversation summarization, agent assistance and a separate compliance-validation capability from the Product Vision's longer-term AI capability list.

### 5.3 US-011 - Identify and Escalate a Dispute (added; D-001)
As a customer, I want to indicate that I dispute an overdue amount or collection claim so that the case is routed for human investigation rather than continuing normal collection treatment.

Acceptance criteria:
- AI can identify DISPUTE intent.
- Structured dispute category and customer-provided reason are captured.
- The LLM must NOT determine whether the dispute is valid.
- Automated collection recommendations for the disputed item pause where the demo business rule requires (the simulated PolicyRuleSet defines dispute suppression, 13.3).
- Case is routed to the Collections Officer / human review queue with conversation and supporting context preserved.
- Human reviewer records outcome and reason.
- All status transitions and decisions are audited.

### 5.4 PAY_NOW as a simulated payment flow (D-021)
- PAY_NOW is in the MVP as a simulated payment only. No real payment gateway, payment processing or external financial transaction occurs.
- A **PaymentEvent** domain concept represents a synthetic payment outcome: account, amount, outcome (succeeded/failed), source (customer chat or demo control), timestamp from the injected Clock, and a marker that it is simulated.
- Flow: customer expresses PAY_NOW; the assistant presents payable amounts returned by the deterministic service; the customer explicitly confirms; a deterministic domain service records the simulated PaymentEvent and updates synthetic balances and collection outcome data; the event is audited.
- A simulated successful payment may satisfy an applicable PTP (PENDING -> KEPT under a deterministic rule) and feeds demo recovery metrics.
- The UI must clearly label simulated payment behavior wherever it appears (chat confirmation, Customer 360, dashboard).
- The LLM never computes or records payment amounts; it only relays service-returned values.

### 5.5 Exceptional payment arrangements (D-024)
An **exceptional arrangement** is a customer-requested arrangement that is not one of the options returned as eligible by the active deterministic PolicyRuleSet. Examples: payment date outside the permitted range; term outside the permitted range; requested amount structure outside permitted rules; any other PolicyRuleSet exception.
- The LLM must not decide whether an exception is approved.
- An exceptional arrangement request is routed to human review, where approve/reject requires a mandatory reason (5.7).
- Exceptional arrangements are never offered to the customer as available options by the AI.

### 5.6 Deterministic Collections Priority model (D-022)
- A deterministic service in the Rules Engine computes, per delinquent account, a **priority score and priority band** with a list of **contributing factors**, using synthetic account attributes: DPD, overdue amount, broken PTP count, active dispute, hardship status and recent contact outcome. Weights and band thresholds live in the versioned PolicyRuleSet.
- The band is what the Portfolio "risk level" filter (US-001) uses; sorting by overdue amount and DPD remains available.
- Accounts with an active dispute, active hardship case or open escalation are flagged so that automated treatment is suppressed and human treatment is indicated.
- The LLM may explain the priority using the returned contributing factors and may recommend a next-best-action, but must not create or modify the score, band or factors.
- This provides AI-assisted account prioritization (Product Vision) with deterministic control.

### 5.7 Mandatory Human Actions (D-026)
Human review is mandatory (the AI may only propose an escalation, never resolve) for:
1. Exceptional payment arrangements.
2. Financial hardship requiring restructuring or a policy exception.
3. Vulnerable-customer scenarios.
4. Disputes.
5. Settlement requests, if encountered.
6. Policy exceptions.
7. High-risk compliance cases.
8. Ambiguous cases where deterministic validation cannot authorize the proposed action.

Reviewer actions:
| Action | Meaning | Constraint |
|---|---|---|
| APPROVE | Accept a proposal or exception | Only where the active PolicyRuleSet permits it; otherwise the action is unavailable |
| REJECT | Decline a proposal or exception | Reason mandatory |
| MODIFY | Change the proposal | Only within explicitly permitted deterministic boundaries (for example choose another eligible option); reason mandatory |
| REQUEST_MORE_INFORMATION | Ask for more customer or case information | Note stating what is needed |
| ESCALATE | Refer to a higher-authority human review | Reason mandatory; target role defined at `/spec` (section 18.1) |

A reason is required for every material human decision (approve, reject, modify, escalate). All reviewer actions and status transitions are audited. The AI never acts as reviewer.

## 6. End-to-End Journeys

Common rules for all journeys: every AI step follows the fail-closed write path (10.3); every state transition and decision produces an audit event; the customer can request a human at any time; only synthetic data appears.

### 6.1 Journey A - Promise-to-Pay (with PAY_NOW simulated payment)
Steps:
1. Officer opens Portfolio, sees accounts ordered by deterministic priority band, and opens Customer 360 for an account.
2. Customer 360 shows profile, balances, DPD, bucket, priority band with factors, and an AI next-best-action with rationale.
3. Customer opens the AI chat; the assistant discloses it is AI and greets respectfully.
4. Customer states they will pay later; the AI classifies PROMISE_TO_PAY (structured output, schema validated).
5. Assistant collects promised amount and date; deterministic validation checks amount and date against the Clock and PolicyRuleSet.
6. Valid: the assistant states the values returned by the service and asks for explicit confirmation. Invalid: rejected with reason code and valid alternatives.
7. Customer confirms; the domain service creates the PTP as PENDING; audit event recorded.
8. Later (simulated payment via PAY_NOW or advance-clock demo control): simulated PaymentEvent satisfying the PTP moves PENDING -> KEPT; the due date passing without one moves PENDING -> BROKEN.

Acceptance criteria:
- AC-A1: Intent is classified with a schema-valid structured output; an invalid output triggers one retry then a safe response and escalation.
- AC-A2: PTP is created only via the domain service after schema, authorization and policy validation; the LLM cannot create it directly.
- AC-A3: Invalid amounts and dates (zero, negative, over-balance, past, outside policy window, over-precision) are rejected deterministically with reason codes.
- AC-A4: PTP is not created without explicit customer confirmation.
- AC-A5: A duplicate submission returns the existing PTP and creates no second record.
- AC-A6: PENDING -> KEPT and PENDING -> BROKEN occur deterministically under the test Clock.
- AC-A7: PAY_NOW confirmations are clearly labelled simulated; no real payment occurs.
- AC-A8: Audit trail shows input, AI interpretation, proposal, rule validation, final state and PolicyRuleSet/model/prompt versions.

### 6.2 Journey B1 - Eligible Payment Arrangement
Steps: customer says they cannot pay in full -> AI classifies PAYMENT_PLAN -> assistant collects required information -> deterministic eligibility returns eligible options (or none) -> assistant presents only returned options -> customer selects one -> assistant asks for explicit confirmation -> domain service creates the arrangement -> audit.

Acceptance criteria:
- AC-B1-1: Only options returned by the rules service are shown; the AI performs no calculation.
- AC-B1-2: No eligible option: the customer is told options cannot be provided now and offered a human; no fabricated alternative.
- AC-B1-3: Arrangement is created only after explicit customer confirmation and via the domain service.
- AC-B1-4: A conflicting active PTP/arrangement blocks a new one with an amend/cancel or officer route.
- AC-B1-5: A request outside eligible options is an exceptional arrangement (5.5) and is escalated for human decision; the AI never states it is approved.
- AC-B1-6: Audit records the eligibility result and PolicyRuleSet version.

### 6.3 Journey B2 - Financial Hardship
Steps: customer describes hardship (for example job loss) -> AI classifies FINANCIAL_HARDSHIP -> structured hardship indicators are recorded -> automated collection treatment stops where policy requires -> escalation case created with priority -> officer reviews conversation, indicators and deterministic data -> officer decides (5.7) with a reason -> audit.

Acceptance criteria:
- AC-B2-1: Hardship indicators are captured in a structured, schema-valid record.
- AC-B2-2: The AI does not approve, promise or imply restructuring or relief.
- AC-B2-3: Automated collection recommendations and outreach stop for the account per PolicyRuleSet until a human decision.
- AC-B2-4: Escalation is created transactionally with its audit event and is visible on Customer 360 and in the queue.
- AC-B2-5: The officer's decision requires a reason; permitted actions per 5.7.
- AC-B2-6: Hardship detection is included in the LIVE recall evaluation (4.4).

### 6.4 Journey C - Dispute
Steps: customer disputes the amount or claim -> AI classifies DISPUTE -> structured dispute category and reason captured -> applicable automated collection treatment is paused -> escalation created with conversation preserved -> reviewer investigates and records outcome and reason -> resolution updates dispute status -> audit.

Acceptance criteria:
- AC-C-1: Dispute category and customer reason are captured structurally; the AI never judges validity.
- AC-C-2: Automated recommendations for the disputed item pause; next-best-action shows human review only.
- AC-C-3: No PTP or arrangement can be created on the disputed item without a human action.
- AC-C-4: Conversation and supporting context are preserved on the case.
- AC-C-5: Outcome and reason are mandatory; every status transition is audited.
- AC-C-6: Dispute detection is included in the LIVE recall evaluation (4.4).

## 7. Vertical Slices (MVP Definition)

The MVP is delivered as vertical slices. A slice is complete only when its exit criteria are met. The dashboard must not move ahead of Slice 1's journey.

| Slice | Content |
|---|---|
| 1 | Delinquent portfolio with deterministic priority -> Customer 360 -> AI web chat -> intent classification -> Promise-to-Pay and simulated PAY_NOW -> deterministic validation -> audit trail; minimal escalation case (creation and visibility); safe handling of all other intents; eval framework with baseline dataset |
| 2 | Payment arrangement -> deterministic eligibility -> exceptional arrangement routing -> hardship detection -> human approval where required (review queue actions) -> audit; dataset expanded |
| 3 | Dispute -> escalation -> human review -> resolution -> audit; dataset expanded |
| 4 | Manager dashboard -> business, operational and AI KPIs -> governance/evaluation reporting; dataset 200+ conversations; portfolio deliverables finalized |

### 7.1 Slice 1 safe handling of not-yet-built workflows
Before their full workflows ship, Slice 1 handles PAYMENT_PLAN, FINANCIAL_HARDSHIP, DISPUTE, REQUEST_HUMAN, vulnerable signals and UNKNOWN (after 2 clarification turns) as follows: the assistant acknowledges respectfully, states that a human colleague will follow up, offers no plan, relief, settlement or opinion on validity, and does not continue collection dialogue on that topic. The domain service creates a **minimal escalation case** (reason/intent, source AI, priority, status OPEN, link to the conversation) with an audit event. Automated collection recommendations for that account are paused. The case is visible on Customer 360 (escalation status) and in a basic escalation list showing reason, priority, age and status. Resolution actions arrive in Slices 2 and 3.

### 7.2 Measurable slice exit criteria
- **Slice 1**: Journey A passes as an automated E2E test in MOCK; PAY_NOW simulated payment and PTP KEPT/BROKEN pass under the test Clock; every 7.1 intent produces a minimal escalation case in tests; baseline dataset of 50-100 labelled synthetic cases committed with provenance; MOCK regression suite green in CI without paid API calls; at least one LIVE baseline run reported with the 4.4 fields; role x endpoint authorization tests pass; audit event exists for every state transition in tests; guardrail suite shows zero critical policy violations and zero unauthorized state changes; axe reports no serious/critical violations on Slice 1 screens and the keyboard-navigation check passes; the page-load measurement (10.6) is recorded.
- **Slice 2**: Journeys B1 and B2 pass E2E; exceptional arrangements route to human review in tests; review queue supports the 5.7 actions with mandatory reasons; dataset expanded to cover arrangement and hardship cases; Slice 1 criteria still hold.
- **Slice 3**: Journey C passes E2E; dispute suppression and reviewer resolution tested; dataset expanded to cover dispute cases; earlier criteria still hold.
- **Slice 4**: Dashboard shows the 4.5 KPIs with MOCK/LIVE/ILLUSTRATIVE labels; dataset >= 200 labelled cases; each sensitive category meets the 30-case minimum before any recall claim; final P1-P4 delivered (section 15); manual accessibility review completed (14.3); earlier criteria still hold.

## 8. Story Traceability Matrix

| Story | Persona | Slice | Journey | Screen | Key acceptance / evaluation coverage |
|---|---|---|---|---|---|
| US-001 View delinquent accounts | Officer | 1 | A (entry) | Delinquent Portfolio | Filter (DPD, priority band, status), sort (overdue, DPD); deterministic priority tests; synthetic-only check |
| US-002 Customer collection profile | Officer | 1 (hardship/dispute panels 2-3) | A, B2, C | Customer 360 | All listed fields shown; AI vs deterministic labelling; escalation status visible; no real PII |
| US-003 Next-best-action | Officer | 1 | A, B1, B2, C | Customer 360 NBA panel | Schema-valid structured recommendation with rationale; priority explanation grounded in service factors; recommendations logged; AI cannot alter records or invent eligibility |
| US-004 Collections conversation | Customer | 1 (PTP, PAY_NOW; safe handling others); 2; 3 | A, B1, B2, C | AI Collections Chat | LIVE intent accuracy >= 90%; sensitive recall rules 4.4; respectful/no-pressure language; human always available |
| US-005 Record Promise-to-Pay | Customer (via AI), Officer views | 1 | A | Chat, Customer 360 | Deterministic validation tests; lifecycle under test Clock; duplicate handling; customer confirmation |
| US-006 Request payment plan | Customer | 2 | B1 | Chat | Eligibility from rules service only; exceptional arrangement routes to human |
| US-007 Identify financial hardship | Officer (system identifies) | 2 (safe handling in 1) | B2 | Customer 360, Review Queue | Structured indicators; no autonomous restructuring; LIVE hardship recall |
| US-008 Review AI escalations | Officer | 1 (minimal create/view); 2-3 (full actions) | B2, C | Escalation / Review Queue | 5.7 actions with mandatory reasons; conversation, recommendation, rule results shown separately; audited |
| US-009 AI decision audit trail | Compliance/Risk | 1 basic; extended later | All | Audit Trail Viewer | Full decision chain; model, prompt and rule-set versions; audit coverage within test suites |
| US-010 Collections dashboard | Manager | 4 | All (aggregate) | Dashboard | KPI tree metrics only; MOCK/LIVE/ILLUSTRATIVE labels |
| US-011 Identify and escalate a dispute | Customer | 3 (safe handling in 1) | C | Chat, Review Queue | AC-C-1..6; LIVE dispute recall |

## 9. Alternatives Considered

| Approach | Summary | Outcome |
|---|---|---|
| A. TypeScript modular monolith | Next.js/Node, shared Zod types, one language | Rejected: weaker eval/data tooling |
| **B. Python FastAPI + React modular monolith** | FastAPI, Pydantic, PostgreSQL, React/Vite/TS, Python eval framework | **Chosen** (D-003) |
| C. Multi-service agentic architecture | Separate services, message bus | Rejected for MVP: unnecessary complexity; recorded as future evolution (D-007) |

Rationale for B: validated structured outputs and Decimal-based deterministic calculations match the core principle; Python eval tooling supports the AI evaluation deliverable; internal module boundaries keep later extraction possible.

## 10. Technical Architecture (business-level guardrails)

Detailed implementation constraints are in section 17.

### 10.1 Stack
React + Vite + TypeScript; Python + FastAPI + Pydantic; PostgreSQL; Python `Decimal` for financial calculations; Claude via Anthropic API behind an LLM provider abstraction (D-015) with LIVE and MOCK modes; pytest, Vitest + React Testing Library, Playwright; Tailwind CSS with an accessible React component library; local Docker Compose.

### 10.2 Modular monolith boundaries
API, Domain, Rules Engine, AI Orchestration, LLM Provider, Persistence, Audit, Evaluation. No microservices or message bus in the MVP. One-way dependencies: the Rules Engine is deterministic with no AI dependency; only AI Orchestration may depend on the LLM Provider; Evaluation may depend on application components but production components must not depend on Evaluation.

### 10.3 Fail-closed AI write path (non-negotiable)
LLM -> structured output (Pydantic) -> schema validation -> authorization/policy validation -> deterministic domain service -> permitted state transition -> append-only audit event. Any invalid or unauthorized AI output fails closed: a safe response or human escalation, with no state change.

### 10.4 Tool model
READ tools: `get_account_context`, `get_eligible_options`. PROPOSE tools: `propose_ptp`, `flag_hardship`, `flag_dispute`, `escalate_to_human`. The LLM has no direct financial-state mutation tools; PROPOSE tools create validated proposals only, and authorization and state transitions remain with deterministic domain services (D-011).

### 10.5 Key business rules
- Customer-facing figures, dates and options come only from deterministic services.
- Safety precedence: DISPUTE, FINANCIAL_HARDSHIP, REQUEST_HUMAN and vulnerable signals override transactional intents; the transactional action is paused and escalated (D-016).
- State transition and audit event succeed or fail together; an audit failure prevents the transition.
- Time is injected through a Clock abstraction with a simulated/test clock (D-009).
- The PolicyRuleSet is versioned and every audit event records the version used (D-004).
- Chat returns whole messages in Slice 1 (D-005). One Claude model is configured, never hard-coded (D-006).

### 10.6 Performance and scale (demo, observational)
- Seed 200-1,000 synthetic accounts.
- **Page-load target**: Portfolio and Customer 360 main content interactive in under 2 seconds at the 95th percentile. Measured locally on Docker Compose, with the upper-bound dataset of 1,000 seeded accounts, using scripted Playwright loads with at least 30 runs per screen after one warm-up run; the hardware used is recorded with the result. This is a local demo measurement, not an SLA.
- **LIVE AI chat**: p95 under 8 seconds as an observational target that depends on the external API; only measured values are reported.
- Captured where available: model identifier, correlation ID, AI latency, token usage, tool-call duration, end-to-end interaction duration.

## 11. Data Model Overview

Shared abstraction with product-specific attributes for `Account.type` in {CARD, PERSONAL_LOAN} (D-014).

Entities: Customer, Account, DelinquencyRecord (overdue amount, DPD, bucket, collection status, as-of/version stamp), CollectionsPriority (score, band, contributing factors, PolicyRuleSet version), Conversation, Message, IntentResult, Recommendation (next-best-action), PromiseToPay (PENDING / KEPT / BROKEN / CANCELLED), PaymentEvent (simulated), PaymentArrangement, HardshipCase (structured indicators), Dispute (category, reason, status, outcome), EscalationCase (priority, source, reason, status, reviewer, decision, reason), Persona, AuditEvent (append-only), EvalDataset, EvalCase, EvalRun (mode LIVE | MOCK), PolicyRuleSet (versioned).

Settlement is intentionally not in the v1 model (D-023).

### 11.1 Audit metadata requirements
Every AI-related audit event records: timestamp, customer/account reference, AI capability, provider, model identifier, prompt/template version, PolicyRuleSet version, correlation ID, input context reference (redacted, no secrets), AI output, tool calls, business-rule results, human override, and final action (D-028). Field-level design is in section 17.

## 12. External Integrations

- Anthropic API (LIVE mode only), behind the LLM provider interface.
- No other external systems: no core banking, payment gateways, messaging channels or identity providers. All data, including payments, is seeded or simulated synthetic data.

## 13. Edge Cases and Constraints

### 13.1 Failure scenarios and expected behaviour
All business-critical failures fail closed and are audited. Sensitive or ambiguous cases prefer human escalation over autonomous action (D-013). Each row has a risk-register entry and at least one MOCK regression case; AI-facing rows also have LIVE eval/red-team cases.

| # | Scenario | Expected behaviour |
|---|---|---|
| 1 | Malformed or schema-invalid LLM output | One bounded retry, then safe response and escalation; invalid output stored for audit; counts toward structured-output compliance |
| 2 | Prompt injection / attempts to override system policies | No policy or tool change; refusal or safe response; adversarial eval set |
| 3 | Hallucinated account information or repayment options | Figures/options only from deterministic services; any ungrounded figure or option is blocked and replaced by templated text from service output; grounded-response metric |
| 4 | Unauthorized financial-state mutation attempts | No mutation tools; PROPOSE tools only; policy layer rejects |
| 5 | Stale account or delinquency data | Snapshot version re-checked at execution; stale or mismatched action rejected and context refreshed; beyond the freshness threshold, escalate |
| 6 | Duplicate PTP submissions | Idempotent handling plus one-active-PTP rule; duplicate returns the existing PTP |
| 7 | Conflicting active PTP / payment arrangement | Rules engine blocks the conflicting item; offer amend/cancel via permitted path or route to officer |
| 8 | Invalid amounts or dates | Deterministic rejection with reason code and alternatives; validated against the injected Clock and policy window |
| 9 | LLM/API timeout or provider failure | One bounded retry, then safe fallback and human-handoff offer; no state change; officer UI shows AI unavailable and manual workflow remains |
| 10 | Deterministic rules-engine failure | Fail closed: no eligibility, no options shown, customer told options cannot be provided now, case escalated; error audited with rule-set version; AI never guesses |
| 11 | Disputed accounts | Automated recommendations pause for the disputed item; next-best-action human review only; no PTP/arrangement on the item without human action |
| 12 | Financial hardship and vulnerable-customer scenarios | Hardship: structured indicators, no autonomous restructuring. Vulnerable signals: stop collection dialogue, supportive message, priority escalation; evaluated as a separate safety set (4.4) |
| 13 | Human escalation failures | Escalation creation is transactional with its audit event; on failure the customer is told the handoff was not completed with a safe next step; no further automated collection action on the account; unassigned/aging cases surfaced |
| 14 | Unauthorized persona/role access | Server-side role checks on every endpoint; 403 plus audit event; role x endpoint authorization test matrix |
| 15 | Audit logging failure | Transition and audit event succeed or fail together; audit failure prevents the transition |
| 16 | Sensitive-data leakage into prompts or logs | Prompt allow-list; redaction before logging/audit; CI scans of prompts, logs and seed data for prohibited patterns |
| 17 | Repeated/replayed tool calls | Idempotent handling returns the original result; per-turn tool-call cap; breach escalates |
| 18 | Model output conflicts with deterministic rules | Rules engine authoritative; model output overridden/rejected; policy-conflict event logged; response replaced by templated text from service output |
| 19 | Ambiguous or UNKNOWN intent | Clarify up to 2 turns, then offer human handoff |
| 20 | Multiple or conflicting intents | Safety precedence rule (10.5) |
| 21 | Customer requests a human | Always honoured; creates an EscalationCase; AI must not discourage |
| 22 | Concurrent actions (double submit, two officers on one escalation, status changed during review) | Optimistic version checks; stale decision rejected with message |
| 23 | Officer overrides or rejects AI recommendation | Reason required; override recorded; feeds override-rate KPI |
| 24 | Seed/data anomalies (inconsistent DPD/bucket, negative balances) | Validated at seed and load; rules engine refuses inconsistent records and flags them |
| 25 | PTP breakage detection | Deterministic job over injected Clock marks past-due PENDING PTPs BROKEN unless satisfied by a PaymentEvent |
| 26 | Duplicate or replayed simulated payment event | Idempotent handling; a duplicate does not double-count recovery or re-transition a PTP |
| 27 | Customer requests an exceptional arrangement | Never approved by the AI; routed to human review per 5.5 |

Standing parameters: retry bound = 1; max clarification turns = 2 (D-020).

### 13.2 Operational constraints
- Demo only: no uptime SLA; local single instance.
- No fixed API spend cap as a product requirement (D-010). Token usage and estimated cost are tracked where available; MOCK is used for CI (CI never calls the paid API); LIVE evaluations are manually triggered; an optional configurable evaluation budget guardrail is allowed.
- Basic rate limiting on chat endpoints to prevent runaway loops.
- Secrets only via environment variables; `.env` git-ignored.

### 13.3 Simulated contact-frequency and treatment policy (D-010)
Configurable, simulated PolicyRuleSet examples: maximum contact attempts within a period; minimum interval between attempts; suppression for active disputes; routing/suppression for hardship or vulnerable-customer cases. These are demo rules and are not represented as regulatory requirements of any specific jurisdiction.

### 13.4 Sensitive data and compliance
- Synthetic data only: no real names/PII, card numbers, CVVs, PINs, government IDs or credentials; emails on reserved domains (example.com); fictional phone ranges; automated scans of seed data, prompts and logs. Simulated payments involve no real payment instruments.
- Compliance concepts (fair treatment, no threats or misleading statements, human oversight, traceability) are design inspiration only. No regulatory certification or compliance claim is made.

### 13.5 AI governance / risk register (portfolio deliverable P3)
The register contains one entry per failure scenario in 13.1 plus these top expected risks, each with likelihood, impact, control, owner and linked test:
1. Hardship, dispute or vulnerability misclassified as PTP (missed escalation): safety precedence plus the LIVE recall rules.
2. Ungrounded or invented figures/eligibility: service-derived text plus post-check.
3. Eval overfitting or bias on a small self-authored synthetic dataset: held-out cases, growing adversarial set, provenance disclosure.
4. MOCK results mistaken for real model quality: separate labelling and reporting.
5. Scope creep (dashboard or streaming ahead of slices): slice exit criteria.
6. CARD vs PERSONAL_LOAN rules divergence: shared abstraction, product rule modules, per-product tests.
7. LIVE cost or latency drift: telemetry and optional evaluation budget guardrail.
8. Simulated payment mistaken for real payment: explicit UI labelling.
9. AI explanation of priority drifting from the deterministic factors: grounding check on explanations.

### 13.6 Eval and red-team coverage
The eval framework (Python; MOCK and LIVE modes) covers normal, edge, escalation, adversarial and policy scenarios and explicitly includes every scenario in 13.1 rows 1-18, plus vulnerable-customer safety cases and exceptional-arrangement requests. Intent labels: PAY_NOW, PROMISE_TO_PAY, PAYMENT_PLAN, FINANCIAL_HARDSHIP, DISPUTE, REQUEST_HUMAN, UNKNOWN. MOCK covers orchestration, structured outputs, schemas, tool calls, guardrails and expected state transitions. LIVE measures intent accuracy, sensitive-category recall, structured-output compliance, escalation behaviour and policy adherence. The AI evaluation report (P2) reports MOCK and LIVE separately with the 4.4 fields.

## 14. UI Context

One React application with persona switching (CUSTOMER, COLLECTIONS_OFFICER, COLLECTIONS_MANAGER, COMPLIANCE_RISK) (D-012, D-019). Persona switching is demo-only; server-side authorization enforces the active persona's permissions. Routes and layouts separate customer and internal experiences logically so they could be split later; no separate front-ends in the MVP.

### 14.1 Screens and slice mapping
1. Persona Switcher (Slice 1).
2. Delinquent Portfolio, US-001 (Slice 1): customer, product type, balance, overdue, DPD, bucket, status, priority band; filter by DPD, priority band, status; sort by overdue and DPD; selection opens Customer 360.
3. Customer 360 + Next-Best-Action, US-002/US-003 (Slice 1; hardship and dispute panels populate in Slices 2-3).
4. AI Collections Chat, US-004 (Slice 1 PTP and simulated PAY_NOW; Slice 2 arrangements).
5. Escalation / Review Queue, US-008/US-011 (Slice 1 basic list; Slices 2-3 full actions).
6. Audit Trail Viewer, US-009 (basic in Slice 1; extended later).
7. Collections & AI Performance Dashboard, US-010 (Slice 4).
8. Dev / Demo Controls (behind a flag): LIVE/MOCK indicator, advance-clock control, reseed, simulated payment trigger.

### 14.2 UX requirements
- Customer 360: clearly distinguish AI-generated recommendations from deterministic account/rules data; show rationale; show DPD, bucket, overdue amount, priority band with contributing factors, active PTP/arrangement, hardship/dispute status, recent interactions; escalation status visible.
- AI Chat: disclose it is an AI assistant; always provide "Talk to a human"; explicit customer confirmation before submitting a PTP, payment or arrangement; never threatening, coercive or high-pressure language; display only repayment options returned by deterministic services; clearly communicate when the case is transferred for human review; clearly label simulated payments.
- Escalation / Review Queue: show escalation reason, priority, aging and source; relevant conversation and context; AI recommendation shown separately from deterministic rule results; the 5.7 reviewer actions with a mandatory reason where required.
- Audit Viewer: present the decision chain Customer/Input -> AI interpretation -> tool/proposal -> policy/rule validation -> human decision (where applicable) -> final state transition, understandable to a PM or compliance stakeholder.
- Dashboard: separate Business, Operational and AI quality/governance KPIs per the 4.5 tree; clearly distinguish MOCK, LIVE and ILLUSTRATIVE values.
- Safe-state banners for failure scenarios (AI unavailable, handoff failed, stale data).

### 14.3 Devices and accessibility
- Desktop-first operational workspace; officer, manager and compliance views optimized for about 1280px and wider. Customer chat responsive for mobile and desktop.
- **WCAG 2.1 AA is the MVP accessibility target.** Accessibility must not rely only on color to communicate AI, rules, risk or simulated status (use text labels and icons).
- Automated axe testing in Playwright is only part of verification. Before conformance is claimed, primary journeys also require keyboard-navigation checks and a small manual accessibility review; until then the claim is "targets WCAG 2.1 AA".

### 14.4 Design direction
Neutral, professional enterprise-banking look; no real bank branding, logos or proprietary assets; credible modern banking operations platform, not a generic developer demo. Tailwind CSS plus a mature accessible Tailwind-compatible React component library; consistent design tokens; professional tables, cards, status badges, dialogs and dashboard components; restrained visual hierarchy; avoid excessive animation, gradients or consumer-style effects. Priorities: clarity, trust, explainability, operational efficiency.

## 15. Portfolio Deliverables

| ID | Deliverable | Location | Delivery slice |
|---|---|---|---|
| P1 | Product KPI / metrics tree | `docs/portfolio/kpi-tree.md` | Initial in Slice 1 (tree and definitions); completed with dashboard data in Slice 4 |
| P2 | AI evaluation report (MOCK and LIVE separate; 4.4 fields) | `docs/portfolio/ai-evaluation-report.md` | Baseline in Slice 1; updated each slice; final in Slice 4 |
| P3 | AI governance / risk register | `docs/portfolio/ai-risk-register.md` | Seeded in Slice 1 from 13.5; updated each slice; final in Slice 4 |
| P4 | Product decision log | `docs/portfolio/decision-log.md` | Created in Slice 1 from the seed below; maintained continuously |

## 16. Product Decision Log (P4 seed)

All entries dated 2026-09-21 (interview session).

| ID | Status | Decision | Alternatives considered | Rationale |
|---|---|---|---|---|
| D-001 | Accepted | Add US-011 (dispute identification and escalation); `docs/MVP_REQUIREMENTS.md` remains the source of truth (commit `7d7f784`) | Keep only in BRD/decision log | DISPUTE intent had no story; requirements doc must hold material MVP requirements |
| D-002 | Accepted | Eval strategy: MOCK for CI regression only; LIVE for accuracy claims; dataset 50-100 in Slice 1, 200+ by Slice 4 | LIVE-only; MOCK-only | Prevents misrepresenting scripted results as model quality |
| D-003 | Accepted | Approach B: React/Vite/TS + FastAPI/Python modular monolith, PostgreSQL | A (TypeScript monolith); C (multi-service) | Pydantic and Decimal fit the principle; eval tooling; avoid complexity |
| D-004 | Accepted; amended by D-023 | PolicyRuleSet versioned; audit events record the rule-set version | Unversioned rules | Traceability of decisions |
| D-005 | Accepted | Whole-message chat in Slice 1; SSE streaming deferred | Stream from the start | Simplifies validation, audit and testing |
| D-006 | Accepted | Single Claude model via configuration; multi-model routing deferred until measured evidence | Split classifier/conversation models | Avoid premature optimization |
| D-007 | Accepted | Event-driven services/message bus recorded as future evolution, not built | Build now | Avoid unnecessary complexity |
| D-008 | Accepted; refined by D-025 | >= 95% LIVE recall for sensitive categories; keep >= 90% overall accuracy | Single overall target | A missed vulnerable-customer signal is worse than a misclassified PTP |
| D-009 | Accepted | Clock abstraction with simulated/test clock for PTP lifecycle | Real time only | Deterministic tests |
| D-010 | Accepted | No fixed API spend cap requirement; track tokens/cost; optional evaluation budget guardrail; simulated, non-jurisdiction-specific contact policy | Fixed cap; jurisdiction-specific rules | Avoid arbitrary limits and regulatory claims |
| D-011 | Accepted | Tools classified READ vs PROPOSE; no LLM mutation tools | Direct mutation tools with guardrails | Enforces the core principle |
| D-012 | Accepted | One React app, logically separated layouts, neutral unbranded design | Separate customer and internal apps | Simplicity; portfolio quality |
| D-013 | Accepted | Fail closed for business-critical failures; prefer human escalation for sensitive/ambiguous cases | Fail open with warnings | Safety |
| D-014 | Accepted | Shared CARD/PERSONAL_LOAN delinquent-account abstraction with product-specific rules | Two collections engines | Demonstrates reusable product architecture |
| D-015 | Accepted | LLM provider behind an abstraction; Claude first | Direct SDK use in domain code | Avoid provider coupling; enables MOCK mode |
| D-016 | Accepted | Safety precedence: DISPUTE, FINANCIAL_HARDSHIP, REQUEST_HUMAN, vulnerable signals override transactional intents | Process transactional intent first | Missed escalation is the costliest failure |
| D-017 | Accepted | Vertical slice order 1-4 with the dashboard last | Horizontal layers; dashboard early | Working journey first; avoids scope creep |
| D-018 | Accepted | Eval framework starts in Slice 1 | Evaluate at the end | Quality gates from the first slice |
| D-019 | Accepted | Demo persona-switching RBAC with server-side enforcement | Client-side toggle; real authentication | Demonstrates authorization without IAM scope |
| D-020 | Accepted | Bounded retry (1) and clarification (2 turns) then human handoff | Unbounded retries | Predictable, safe behaviour |
| D-021 | Accepted | PAY_NOW kept in MVP as a simulated payment flow with a PaymentEvent | Defer PAY_NOW; real gateway | Enables PTP KEPT and recovery metrics without real payments |
| D-022 | Accepted | Deterministic Collections Priority model; LLM only explains it | LLM-scored prioritization | Preserves deterministic control while meeting the vision |
| D-023 | Accepted | Settlement removed from the v1 model and deferred; any request is a mandatory human action | Simulated settlement workflow | No story or screen used it; reduces complexity |
| D-024 | Accepted | Exceptional arrangement = request outside the active PolicyRuleSet's eligible options; human decides | AI-judged exceptions | LLM must not approve exceptions |
| D-025 | Accepted | Recall claim needs >= 30 labelled LIVE cases per category; report provenance and counts; vulnerable signals evaluated separately | Claim on any sample size | Avoid statistically meaningless claims |
| D-026 | Accepted | Consolidated Mandatory Human Actions list and reviewer actions (5.7) | Distributed rules | Clarity and testability |
| D-027 | Accepted | KPI tree limited to metrics derivable from MVP data; right-party contact, handling time and cost per collected account deferred | Include all vision KPIs | Avoid unmeasurable metrics |
| D-028 | Accepted | AI audit metadata includes prompt/template version | Model version only | Reproducible AI behaviour traceability |
| D-029 | Accepted | WCAG 2.1 AA target; conformance claimed only after axe, keyboard and manual review | Claim on axe alone | Avoid overstated accessibility |

## 17. Specification Inputs / Constraints (deferred to `/spec`)

These implementation details are inputs to `/spec` and not BRD-level requirements, except where they preserve a guardrail above.
- Idempotency keys on PROPOSE calls, simulated payments and PTP creation; per-turn tool-call cap with escalation on breach.
- Post-generation check: any currency figure, date or option in AI text must match a service result, otherwise block and replace with templated text.
- Optimistic version checks for stale-data and concurrent-action handling; single database transaction for state transition plus audit event; append-only enforcement of the audit table at the database role level.
- Money stored as PostgreSQL `NUMERIC`, serialized as strings in API JSON; Python `Decimal` throughout.
- Model selection through an environment variable (for example `ANTHROPIC_MODEL`); secrets in git-ignored `.env`; Docker Compose services; seed script with prohibited-pattern scans.
- Field-level `AuditEvent` schema and redaction rules; correlation ID propagation; token and latency capture points.
- Priority score weights and band thresholds; PTP policy window; freshness threshold; contact-frequency parameters; exception-authority limits (all in the seeded PolicyRuleSet).
- Endpoint role x permission matrix; rate-limit values; boundary-test catalogues (zero, negative, over-balance, past date, far future, over-precision).
- Detailed module dependency graph including how AI Orchestration invokes Domain services.
- Component library selection; axe and manual accessibility procedures; performance test harness.

## 18. Open Questions and Alignment Actions

### 18.1 Non-blocking open questions (settle at `/spec`)
1. Exact seeded PolicyRuleSet values: contact-frequency thresholds, PTP policy window, freshness threshold, priority weights and band cut-offs, exception-authority limits.
2. Exact accessible React component library.
3. Exact per-turn AI tool-call cap.
4. Target of the reviewer ESCALATE action within demo RBAC (for example a senior-review flag versus referral to COMPLIANCE_RISK).

### 18.2 Requirements alignment actions
`CLAUDE.md` makes `docs/PRODUCT_VISION.md` and `docs/MVP_REQUIREMENTS.md` the source of truth. Status:
- US-011 (commit `7d7f784`) is in history on branch `docs/add-us-011-dispute-escalation`; merging to `main` remains a separate step.
- DONE: simulated PAY_NOW / PaymentEvent, the deterministic Collections Priority model, the exceptional-arrangement definition, mandatory human actions, Settlement deferral and the sensitive-category recall rule are reflected in `docs/MVP_REQUIREMENTS.md` and `docs/PRODUCT_VISION.md`.
- DONE: deferral of right-party contact rate, average handling time and cost per collected account (D-027) is recorded in both documents.

---

Approved by the product owner. Next step: `/spec` (not yet run).
