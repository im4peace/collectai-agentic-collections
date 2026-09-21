# CollectAI — MVP Requirements

## Epic 1 — Collections Portfolio Management

### US-001 — View Delinquent Accounts

As a Collections Officer,
I want to view customers with delinquent accounts
so that I can prioritize collection activities.

### Acceptance Criteria

- Display synthetic delinquent accounts only.
- Show customer name, account type, outstanding balance, overdue amount and Days Past Due (DPD).
- Show delinquency bucket.
- Show collection status.
- Show the deterministic Collections Priority band (see US-003).
- Allow filtering by DPD, risk level (the deterministic priority band) and status.
- Allow sorting by overdue amount and DPD.
- Selecting an account opens Customer 360.

---

## Epic 2 — Customer 360

### US-002 — View Customer Collection Profile

As a Collections Officer,
I want a consolidated customer view
so that I can understand the customer's collection situation before taking action.

### Acceptance Criteria

Display:

- Customer profile
- Loan/card account
- Outstanding balance
- Overdue amount
- DPD
- Delinquency bucket
- Previous interactions
- Promise-to-Pay history
- Hardship indicators
- Disputes
- Escalation status
- Collections Priority band and contributing factors
- Recommended next action

No real customer PII may be used.

---

## Epic 3 — AI Collections Strategy

### US-003 — Generate Next-Best-Action

As a Collections Officer,
I want CollectAI to recommend the next collection action
so that accounts can be handled consistently.

### Example Actions

- Contact customer
- Request payment
- Offer eligible payment arrangement
- Follow up on Promise-to-Pay
- Refer to hardship workflow
- Escalate to human review

### Acceptance Criteria

- AI receives relevant account context.
- AI returns a structured recommendation.
- Recommendation includes rationale.
- AI cannot change financial records.
- AI cannot approve settlements.
- AI cannot invent eligibility.
- Recommendations are logged.

### Collections Priority

- A deterministic service computes a priority score, a priority band and its contributing factors for each delinquent account.
- Inputs are synthetic account attributes such as DPD, overdue amount, broken PTP, active dispute, hardship status and recent contact outcome.
- The LLM may explain the priority using the returned factors and recommend a next-best-action.
- The LLM must not calculate or modify the score, band or factors.
- Accounts with an active dispute, active hardship case or open escalation are flagged so that automated treatment is suppressed and human treatment is indicated.

---

## Epic 4 — AI Customer Conversation

### US-004 — Conduct Collections Conversation

As a Customer,
I want to discuss my overdue account through an AI assistant
so that I can understand and resolve my outstanding obligation.

### Acceptance Criteria

The assistant must identify intents including:

- PAY_NOW
- PROMISE_TO_PAY
- PAYMENT_PLAN
- FINANCIAL_HARDSHIP
- DISPUTE
- REQUEST_HUMAN
- UNKNOWN

The assistant must:

- communicate respectfully
- explain available options
- use approved account information
- avoid threats or misleading statements
- escalate when appropriate

PAY_NOW is a simulated payment capability only:

- No real payment gateway, payment processing or external financial transaction occurs.
- Payable amounts come from deterministic services; the customer must explicitly confirm.
- The outcome is recorded as a synthetic PaymentEvent.
- The UI clearly identifies simulated payment behavior.

Sensitive intents and scenarios (FINANCIAL_HARDSHIP, DISPUTE, REQUEST_HUMAN, vulnerable-customer signals, settlement requests, exceptional arrangement requests) are routed to human review, including before their full workflows are available.

---

## Epic 5 — Promise-to-Pay

### US-005 — Record Promise-to-Pay

As a Collections Officer,
I want to record a customer's payment commitment
so that it can be monitored.

### Acceptance Criteria

Capture:

- promised amount
- promised payment date
- account
- interaction reference
- status

Status values:

- PENDING
- KEPT
- BROKEN
- CANCELLED

Financial validation must be deterministic.

Lifecycle:

- A simulated successful payment (PaymentEvent) may satisfy an applicable PTP, moving it from PENDING to KEPT under a deterministic rule.
- A PTP whose due date passes without a satisfying PaymentEvent moves from PENDING to BROKEN.
- Time is injected so lifecycle transitions are testable deterministically.
- Simulated payment outcomes may feed demo recovery metrics.

---

## Epic 6 — Payment Arrangement

### US-006 — Request Payment Plan

As a Customer,
I want to request a payment arrangement
when I cannot pay the full overdue amount.

### Acceptance Criteria

- AI collects required information.
- Eligibility is evaluated by deterministic rules.
- AI cannot create financial calculations.
- Eligible arrangements are returned by a rules service.
- Customer can select an eligible option.
- An exceptional arrangement is a customer-requested arrangement that is not one of the options returned as eligible by the active deterministic rule set (for example a payment date or term outside permitted ranges).
- Exceptional arrangements require human review with approval or rejection and a mandatory reason.
- The LLM must not decide whether an exception is approved.

---

## Epic 7 — Financial Hardship

### US-007 — Identify Financial Hardship

As a Collections Officer,
I want the system to identify potential hardship
so that customers can be routed appropriately.

### Example indicators

- Job loss
- Significant income reduction
- Medical/family emergency
- Temporary financial difficulty

### Acceptance Criteria

- AI may identify potential hardship from conversation.
- AI records structured hardship indicators.
- AI does not independently approve restructuring.
- Sensitive cases are escalated for human review.

---

## Epic 8 — Human-in-the-Loop

### US-008 — Review AI Escalations

As a Collections Officer,
I want to review cases escalated by CollectAI
so that sensitive decisions remain under human control.

### Acceptance Criteria

Officer can:

- Review conversation
- Review AI recommendation
- Review supporting data
- Approve, where policy permits
- Reject
- Modify, within explicitly permitted deterministic boundaries
- Request more information
- Escalate to a higher-authority human review
- Record a reason (mandatory for material decisions)

Human review is mandatory for exceptional payment arrangements, financial hardship requiring restructuring or a policy exception, vulnerable-customer scenarios, disputes, settlement requests, policy exceptions, high-risk compliance cases, and ambiguous cases where deterministic validation cannot authorize the proposed action.

Every decision must be audited.

---

## Epic 9 — Auditability

### US-009 — AI Decision Audit Trail

As a Compliance Officer,
I want AI interactions and decisions recorded
so that CollectAI can be monitored and audited.

### Acceptance Criteria

Record:

- timestamp
- customer/account reference
- AI capability used
- model/version and prompt/template version where applicable
- rule-set version used for the decision
- input context reference
- AI output
- tool calls
- business-rule results
- human override
- final action

Sensitive secrets must never be written to logs.

---

## Epic 10 — Collections Analytics

### US-010 — Collections Dashboard

As a Collections Manager,
I want to monitor portfolio and AI performance
so that I can evaluate business outcomes.

### Business KPIs

- Total delinquent accounts
- Total overdue amount
- Recovery rate
- Promise-to-Pay rate
- Promise-kept rate
- Self-service resolution rate
- Human escalation rate

### AI KPIs

- Intent classification accuracy
- Tool-call success rate
- Human override rate
- Escalation rate
- Response latency
- Sensitive-category recall (hardship, dispute, human request)

### KPI Rules

- Business KPIs on synthetic data are illustrative and are not evidence of real banking outcomes.
- AI quality KPIs distinguish MOCK results (regression only) from LIVE evaluation results. MOCK results are never presented as evidence of real-model quality.
- A per-category recall claim of 95% or more may only be made when that category contains at least 30 labelled LIVE evaluation cases. The evaluation dataset has no fixed maximum size and may grow as needed for intent, sensitive-scenario, edge-case and adversarial coverage.
- Deferred, because the MVP lacks the required data: right-party contact rate, average handling time and cost per collected account.

---

## Epic 11 — Dispute Management

### US-011 — Identify and Escalate a Dispute

As a Customer,
I want to indicate that I dispute an overdue amount or collection claim
so that the case can be routed for human investigation rather than continuing normal collection treatment.

### Acceptance Criteria

- AI can identify DISPUTE intent.
- Capture a structured dispute category and customer-provided reason.
- The LLM must not determine whether the dispute is valid.
- Pause automated collection recommendations for the disputed item where the demo business rule requires it.
- Route the case to a Collections Officer / human review queue.
- Preserve conversation and supporting context.
- Human reviewer records the outcome and reason.
- All status transitions and decisions are audited.

---

# Product Guardrails

CollectAI must follow these principles:

1. Synthetic data only.
2. LLMs never calculate financial values.
3. LLMs never modify balances.
4. LLMs never approve settlements.
5. Deterministic services own eligibility and financial calculations.
6. Sensitive actions require explicit authorization.
7. Human escalation must always be available.
8. Every material AI recommendation must be auditable.
9. AI output must use structured schemas where appropriate.
10. Tests must validate both business logic and AI guardrails.
11. Collections priority and risk banding are deterministic; the LLM may explain them but never calculate or modify them.
12. Settlement is deferred from the MVP. Any settlement request encountered is escalated to a human.
13. Payments are simulated only; no real payment processing occurs.
