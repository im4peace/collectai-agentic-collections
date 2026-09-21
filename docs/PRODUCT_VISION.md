# CollectAI — Product Vision

## Product
CollectAI — Agentic Collections & Recovery Platform

## Vision
Build an AI-native collections platform for banks that helps collections teams engage delinquent customers intelligently, improve recovery outcomes, and provide appropriate repayment options while maintaining human oversight, regulatory compliance, and a complete audit trail.

## Problem Statement
Traditional collections operations rely heavily on manual segmentation, static call strategies, agent capacity, and fragmented customer information.

This creates:
- High operational cost
- Inconsistent customer treatment
- Low right-party contact rates
- Poor prioritization of accounts
- Repetitive work for collection agents
- Limited personalization
- Slow identification of financial hardship
- Compliance and audit risks

## Target Users

### Collections Officer
Manages delinquent accounts and customer interactions.

### Collections Manager
Monitors portfolio performance, agent productivity, recovery rates, and operational risk.

### Customer
Needs a simple and appropriate way to resolve overdue obligations.

### Compliance / Risk Officer
Ensures AI recommendations and customer interactions comply with approved policies.

## MVP Scope

The MVP will support:

1. Delinquent account portfolio
2. Customer 360 view
3. AI-assisted account prioritization (deterministic priority score and band; AI explains the factors and recommends a next-best-action)
4. AI collections conversation
5. Customer intent detection
6. Promise-to-Pay (PTP) and simulated pay-now (PAY_NOW)
7. Payment-plan requests
8. Financial-hardship identification
9. Dispute identification and human escalation
10. Deterministic eligibility and collections rules
11. Human approval/escalation
12. Complete AI and business audit trail
13. Collections performance dashboard

### Deferred from the MVP

- Settlement offers and settlement workflows. Any settlement request encountered is escalated to a human.
- Right-party contact rate, average handling time and cost per collected account, because the MVP lacks the data they require.
- Real payment processing. Payments in the MVP are simulated only (PaymentEvent).

## AI Capabilities

CollectAI will eventually contain specialized AI capabilities for:

- Collections strategy
- Customer conversation
- Intent classification
- Hardship handling
- Agent assistance
- Compliance validation
- Conversation summarization
- Next-best-action recommendation

## Core Design Principle

LLMs may understand, classify, summarize, recommend and explain.

LLMs must NOT independently calculate financial values, calculate or modify collections priority scores, approve settlements, modify balances, determine legally binding eligibility, or execute sensitive financial actions.

Financial calculations, eligibility decisions and collections priority scoring must be performed by deterministic services and approved business rules. The LLM may explain a priority score and its contributing factors.

## Human-in-the-Loop

Human approval will be required for sensitive actions including:

- Settlement requests (settlement itself is deferred from the MVP)
- Exceptional payment arrangements (any arrangement outside the options the deterministic rules return as eligible)
- Debt restructuring
- Disputes
- Policy exceptions
- Vulnerable-customer scenarios
- High-risk compliance cases

## Success Metrics

Business metrics:
- Recovery rate
- Promise-to-Pay rate
- Promise-kept rate
- Self-service resolution rate
- Human escalation rate

Deferred until the required data exists: right-party contact rate, average handling time, cost per collected account.

Business metrics measured on synthetic data are illustrative and are not evidence of real banking outcomes.

AI metrics:
- Intent classification accuracy
- Grounded response rate
- Hallucination rate
- Tool-call success rate
- Policy violation rate
- Human override rate
- Escalation accuracy
- Response latency
- Cost per AI interaction

AI quality claims come only from LIVE evaluation against labelled data. MOCK results are regression checks and are never presented as evidence of real-model quality. A per-category recall claim of 95% or more for sensitive scenarios (hardship, dispute, human request) requires at least 30 labelled LIVE evaluation cases in that category.

## MVP Safety Principle

CollectAI is a demonstration platform using synthetic customer and financial data only.

It must not contain real customer PII, bank credentials, account credentials, card information, or production banking data.
