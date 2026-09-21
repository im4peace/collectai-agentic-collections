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
- Allow filtering by DPD, risk level and status.
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
- Exceptional arrangements require human approval.

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
- Approve allowed actions
- Reject recommendation
- Modify permitted actions
- Record reason

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
- model/version where applicable
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
