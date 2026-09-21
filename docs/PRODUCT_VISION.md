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
3. AI-driven account prioritization
4. AI collections conversation
5. Customer intent detection
6. Promise-to-Pay (PTP)
7. Payment-plan requests
8. Financial-hardship identification
9. Dispute identification
10. Deterministic eligibility and collections rules
11. Human approval/escalation
12. Complete AI and business audit trail
13. Collections performance dashboard

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

LLMs must NOT independently calculate financial values, approve settlements, modify balances, determine legally binding eligibility, or execute sensitive financial actions.

Financial calculations and eligibility decisions must be performed by deterministic services and approved business rules.

## Human-in-the-Loop

Human approval will be required for sensitive actions including:

- Settlement offers
- Exceptional payment arrangements
- Debt restructuring
- Policy exceptions
- Vulnerable-customer scenarios
- High-risk compliance cases

## Success Metrics

Business metrics:
- Recovery rate
- Promise-to-Pay rate
- Promise-kept rate
- Right-party contact rate
- Self-service resolution rate
- Human escalation rate
- Average handling time
- Cost per collected account

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

## MVP Safety Principle

CollectAI is a demonstration platform using synthetic customer and financial data only.

It must not contain real customer PII, bank credentials, account credentials, card information, or production banking data.
