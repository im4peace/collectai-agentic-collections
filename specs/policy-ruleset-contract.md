# PolicyRuleSet and Application Configuration Contract

Status: specification input for `/design`. Referenced by E1-S2 and every rules-engine, routing and review story.
Scope: defines every PolicyRuleSet parameter and validated application configuration key. **Seeded numeric values are deliberately not chosen here**; they are a `/design` decision and must satisfy the constraints below. All demo rules are simulated and are not regulatory requirements of any jurisdiction.

## 1. Common rules (apply to every parameter)

- **Versioning:** a PolicyRuleSet is immutable per version (for example `policy-v1`). Changing any parameter creates a new version. Exactly one version is active. Older versions stay loadable read-only so an audit event that names a version can always be resolved to its original values.
- **Missing or invalid required parameter:** the rule set fails validation at load with a named error identifying the parameter, and the application refuses to activate it (startup failure). It is never partially applied and no default is silently substituted.
- **No valid active rule set at runtime:** every rules service returns `POLICY_UNAVAILABLE`, grants no eligibility, offers no options and produces no score (fail closed), and the case is escalated with reason `AMBIGUOUS_VALIDATION`.
- **Audit expectation:** every rules-engine decision and every routing decision records the PolicyRuleSet version used, in the audit event.
- **Money type:** `money` means a `Decimal` with at most 2 decimal places, serialized as a string.

## 2. Enumerations

| Enum | Values |
|---|---|
| EscalationReason | REQUEST_HUMAN, UNRESOLVED_UNKNOWN, AI_FAILURE_FALLBACK, EXCEPTIONAL_ARRANGEMENT, FINANCIAL_HARDSHIP, DISPUTE, SETTLEMENT_REQUEST, AMBIGUOUS_VALIDATION, VULNERABLE_CUSTOMER, POLICY_EXCEPTION, HIGH_RISK_COMPLIANCE |
| ReviewQueue | COLLECTIONS_REVIEW, COLLECTIONS_EXCEPTION_REVIEW, HARDSHIP_REVIEW, DISPUTE_REVIEW, VULNERABLE_CUSTOMER_REVIEW, COMPLIANCE_REVIEW |
| ReviewerRole (routing) | COLLECTIONS_OFFICER, COMPLIANCE_RISK (no other organization roles are introduced) |
| EscalationPriority | NORMAL, ELEVATED, URGENT |
| ContactOutcome | NO_CONTACT, CONTACT_NO_COMMITMENT, PTP_MADE, PTP_BROKEN, PAYMENT_MADE |
| ExceptionType | TERM, START_DATE, AMOUNT_STRUCTURE |
| SpecialRequest (structured AI signal, not an intent) | NONE, SETTLEMENT, POLICY_EXCEPTION |

The enumerations above are approved as specification-level contracts (D-034 and the specification review). Exact names and final membership may be refined in `/design` provided no approved behaviour changes, no BRD guardrail is weakened, and traceability back to this contract stays clear. `SETTLEMENT` only ever results in human escalation; settlement remains deferred from the MVP.

## 3. PolicyRuleSet parameters

### 3.1 Collections priority (consumer: E2-S1)

| Parameter | Purpose | Type | Unit | Valid range / constraints |
|---|---|---|---|---|
| `priority.weights.dpd` | Weight of DPD factor in the score | decimal | score points | >= 0 |
| `priority.weights.overdue_amount` | Weight of overdue amount factor | decimal | score points | >= 0 |
| `priority.weights.broken_ptp_count` | Weight of broken-PTP factor | decimal | score points | >= 0 |
| `priority.weights.recent_contact_outcome` | Weight of recent contact outcome factor | decimal | score points | >= 0; sum of all four weights > 0 |
| `priority.normalization.dpd_days` | DPD at which the DPD factor saturates at 1 | integer | days | >= 1 |
| `priority.normalization.overdue_amount` | Overdue amount at which the factor saturates | money | currency units | > 0 |
| `priority.normalization.broken_ptp_count` | Broken-PTP count at which the factor saturates | integer | count | >= 1 |
| `priority.contact_outcome_scores` | Factor value per ContactOutcome | map ContactOutcome to decimal | fraction | every ContactOutcome present; each value 0 to 1 |
| `priority.band_cutoffs` | Score cut-offs between LOW, MEDIUM and HIGH | list of 2 decimals | score points | strictly ascending; each within 0 and the sum of the weights |

### 3.2 Promise-to-Pay and payments (consumer: E2-S2)

| Parameter | Purpose | Type | Unit | Valid range / constraints |
|---|---|---|---|---|
| `ptp.window_days` | Latest allowed promised date relative to Clock now | integer | days | 1 to 365 |
| `ptp.min_amount` | Smallest promised amount | money | currency units | > 0 |
| `ptp.qualifying_payment_min_amount` | Smallest simulated payment that counts toward satisfying a PTP | money | currency units | > 0 and <= `ptp.min_amount` |
| `payment.payable_options` | Amounts PAY_NOW may offer | list of enum | none | non-empty subset of OVERDUE_AMOUNT, FULL_BALANCE |

### 3.3 Arrangement eligibility (consumer: E2-S3)

| Parameter | Purpose | Type | Unit | Valid range / constraints |
|---|---|---|---|---|
| `arrangement.eligible_max_dpd` | Highest DPD still eligible for a standard arrangement | integer | days | >= 0 |
| `arrangement.min_overdue_amount` | Smallest overdue amount eligible for an arrangement | money | currency units | > 0 |
| `arrangement.installment_counts` | Permitted numbers of installments | list of integers | count | non-empty, unique, ascending, each 2 to 60 |
| `arrangement.min_installment_amount` | Smallest installment | money | currency units | > 0 |
| `arrangement.max_start_delay_days` | Latest first-installment date relative to Clock now | integer | days | 0 to 90 |
| `arrangement.allow_with_active_ptp` | Whether an arrangement may coexist with an active PTP | boolean | none | required |

### 3.4 Arrangement exception thresholds and authority (consumers: E2-S3 classification, E7-S2 and E7-S4 approval)

| Parameter | Purpose | Type | Unit | Valid range / constraints |
|---|---|---|---|---|
| `exception.thresholds.max_installment_count` | Largest term a reviewer may consider as an exception | integer | count | > max(`arrangement.installment_counts`) and <= 120 |
| `exception.thresholds.max_start_delay_days` | Latest first-installment date a reviewer may consider | integer | days | >= `arrangement.max_start_delay_days` and <= 180 |
| `exception.thresholds.min_installment_amount` | Smallest installment a reviewer may consider | money | currency units | > 0 and <= `arrangement.min_installment_amount` |
| `exception.authority.collections_officer.types` | ExceptionTypes a COLLECTIONS_OFFICER may approve | list of ExceptionType | none | subset of ExceptionType (may be empty) |
| `exception.authority.collections_officer.max_overdue_amount` | Highest overdue amount for which an officer may approve an exception | money | currency units | >= 0 |

A requested arrangement outside `arrangement.*` limits is EXCEPTIONAL. An exception outside `exception.thresholds.*`, of a type not in `types`, or above `max_overdue_amount` cannot be APPROVED by a COLLECTIONS_OFFICER (APPROVE unavailable; REJECT, REQUEST_MORE_INFORMATION and ESCALATE remain).

### 3.5 Contact-frequency controls (consumer: E2-S4)

| Parameter | Purpose | Type | Unit | Valid range / constraints |
|---|---|---|---|---|
| `contact.max_attempts` | Maximum contact attempts within the period | integer | count | >= 1 |
| `contact.period_days` | Length of the period for `max_attempts` | integer | days | >= 1 |
| `contact.min_interval_hours` | Minimum interval between attempts | integer | hours | >= 0 (0 disables) |

### 3.6 Data freshness (consumer: E2-S5)

| Parameter | Purpose | Type | Unit | Valid range / constraints |
|---|---|---|---|---|
| `freshness.max_snapshot_age_minutes` | Oldest account snapshot accepted before a consequential transition | integer | minutes | 1 to 10080 |

A snapshot whose `as_of` is missing, or whose version differs from the current record version, is never treated as fresh (fail closed, escalation reason `AMBIGUOUS_VALIDATION`).

### 3.7 Treatment suppression (consumers: E2-S1 flags, E2-S4)

| Parameter | Purpose | Type | Unit | Valid range / constraints |
|---|---|---|---|---|
| `suppression.dispute.scope` | What an active dispute suppresses | enum | none | ITEM or ACCOUNT (approved demo rule: ITEM) |
| `suppression.hardship.scope` | What active hardship suppresses | enum | none | ACCOUNT |
| `suppression.vulnerable.scope` | What a vulnerable-customer flag suppresses | enum | none | ACCOUNT |
| `suppression.release` | Who may lift a suppression | enum | none | HUMAN_DECISION (only allowed value) |

### 3.8 Vulnerability signals (consumer: E6-S1 schema, E7-S1)

| Parameter | Purpose | Type | Unit | Valid range / constraints |
|---|---|---|---|---|
| `vulnerability.categories` | Allowed values of `vulnerability_category` | list of strings | none | non-empty, unique |

Vulnerability routing and priority are defined by `routing.table` and `routing.priority_by_reason` for reason `VULNERABLE_CUSTOMER`.

### 3.9 Escalation routing (consumers: E2-S6, E7-S2, E7-S3, E7-S6)

| Parameter | Purpose | Type | Unit | Valid range / constraints |
|---|---|---|---|---|
| `routing.table` | Maps every EscalationReason to a queue and reviewer role | map EscalationReason to {queue, reviewer_role} | none | exactly the 11 EscalationReason keys; queue in ReviewQueue; role in ReviewerRole |
| `routing.fallback` | Destination for an unknown or missing reason | {queue, reviewer_role} | none | must equal COLLECTIONS_REVIEW and COLLECTIONS_OFFICER |
| `routing.priority_by_reason` | Deterministic priority per reason | map EscalationReason to EscalationPriority | none | all 11 keys; FINANCIAL_HARDSHIP and VULNERABLE_CUSTOMER at least ELEVATED |
| `routing.reviewer_escalation_reasons` | Reasons a reviewer may choose for the ESCALATE action | list of EscalationReason | none | non-empty; excludes REQUEST_HUMAN and UNRESOLVED_UNKNOWN |
| `routing.aging_warning_hours` | Simulated aging warning per priority | map EscalationPriority to integer | hours | all 3 keys; each >= 1 |

Required default `routing.table`:

| Reason | Queue | Reviewer role |
|---|---|---|
| REQUEST_HUMAN | COLLECTIONS_REVIEW | COLLECTIONS_OFFICER |
| UNRESOLVED_UNKNOWN | COLLECTIONS_REVIEW | COLLECTIONS_OFFICER |
| AI_FAILURE_FALLBACK | COLLECTIONS_REVIEW | COLLECTIONS_OFFICER |
| EXCEPTIONAL_ARRANGEMENT | COLLECTIONS_EXCEPTION_REVIEW | COLLECTIONS_OFFICER |
| FINANCIAL_HARDSHIP | HARDSHIP_REVIEW | COLLECTIONS_OFFICER |
| DISPUTE | DISPUTE_REVIEW | COLLECTIONS_OFFICER |
| SETTLEMENT_REQUEST | COLLECTIONS_REVIEW | COLLECTIONS_OFFICER |
| AMBIGUOUS_VALIDATION | COLLECTIONS_REVIEW | COLLECTIONS_OFFICER |
| VULNERABLE_CUSTOMER | VULNERABLE_CUSTOMER_REVIEW (elevated priority) | COLLECTIONS_OFFICER |
| POLICY_EXCEPTION | COMPLIANCE_REVIEW | COMPLIANCE_RISK |
| HIGH_RISK_COMPLIANCE | COMPLIANCE_REVIEW | COMPLIANCE_RISK |

The LLM may propose only an EscalationReason. It never supplies a queue or reviewer role. A reviewer ESCALATE action supplies a whitelisted reason and the routing service determines the destination. Slice 1 maps a PAYMENT_PLAN request, before the arrangement workflow ships, to `AMBIGUOUS_VALIDATION` because deterministic eligibility does not yet exist.

### 3.10 Compliance review (consumer: E7-S5)

| Parameter | Purpose | Type | Unit | Valid range / constraints |
|---|---|---|---|---|
| `compliance.review_outcomes` | Allowed outcomes for a compliance review decision | list of strings | none | non-empty, unique (names finalized in `/design`) |

## 4. Validated application configuration (not versioned with the rule set)

Validated at startup. An invalid value fails startup with a named error. No secret or model id is hard-coded.

| Key | Purpose | Type | Constraints / default |
|---|---|---|---|
| `ANTHROPIC_MODEL` | Claude model identifier for LIVE mode | string | required when `LLM_MODE=LIVE`; never hard-coded |
| `LLM_MODE` | Provider mode | enum | MOCK or LIVE; default MOCK |
| `TOOL_CALL_CAP_PER_TURN` | Maximum AI tool calls per conversation turn | integer | 1 to 20; default 5 |
| `AI_RETRY_BOUND` | Retries after schema-invalid output or provider timeout | integer | 0 to 2; default 1 |
| `MAX_CLARIFICATION_TURNS` | Clarification questions before UNRESOLVED_UNKNOWN escalation | integer | 0 to 5; default 2 |
| `CHAT_RATE_LIMIT_PER_MINUTE` | Chat requests allowed per minute | integer | 1 to 600 |
| `DEMO_CONTROLS_ENABLED` | Enables demo controls | boolean | default false |
| `DATABASE_URL` | PostgreSQL connection | string | required |

## 5. Explicitly not decided here

Seeded numeric values for every parameter above, final compliance outcome names, and the concrete `vulnerability.categories` list are `/design` decisions constrained by this contract.
