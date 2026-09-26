# Product KPI tree (P1)

Portfolio deliverable P1. It documents every KPI in the BRD 4.5 KPI tree (`specs/brd/brd.md`) with its definition, formula, data source, owner persona, data label and **implementation status**, and lists the three formally deferred KPIs.

North star: recovery of overdue amounts through fair, compliant, auditable customer treatment. All values on synthetic data are illustrative. Business KPIs are product hypotheses until measured in a real deployment (BRD 1.2).

This file is maintained by hand. `backend/tests/portfolio/test_kpi_tree_doc.py` enforces it: every leaf of the BRD 4.5 tree must appear in the `BRD 4.5 leaf` column, every KPI the API returns must appear here with its id, every row must fill all fields, and the three deferred KPIs must be listed and absent from the API.

## Reading the labels and statuses

**Data label** says what kind of evidence a figure is (BRD 4.5, 4.6):

- `ILLUSTRATIVE`: computed from the synthetic seed data and simulated events. It shows what the dashboard would track, not real performance.
- `MOCK`: a regression check from the scripted provider. Never evidence of real-model quality.
- `LIVE`: a measured evaluation on the labelled dataset with a real model. **No LIVE run has been stored**, so no LIVE figure exists yet; the dashboard and P2 say "No LIVE run".
- `n/a`: not measured, so it has no label.

**Status** says whether the KPI exists:

- `IMPLEMENTED`: computed and returned by `GET /api/kpis` (E10-S3) and shown on the dashboard (E10-S4). The `KPI id` column is its `kpi_id`.
- `EVAL_REPORT_ONLY`: measured by the evaluation framework and reported in P2 (or stored on the `EvalRun`), but not returned by `GET /api/kpis`.
- `NOT_YET_MEASURABLE`: the tree includes it and MVP data feeds it in principle, but no aggregation exists yet. No value is claimed.
- `DEFERRED`: needs data outside the MVP model (D-027). Listed separately below.

Nothing here is a measurement of a real deployment. A `NOT_YET_MEASURABLE` row is a documented gap, not a hidden number.

## KPI catalogue

| BRD 4.5 leaf | KPI | KPI id | Definition | Formula | Data source | Owner persona | Data label | Status |
|---|---|---|---|---|---|---|---|---|
| Total delinquent accounts | Total delinquent accounts | `total_delinquent_accounts` | Accounts with days-past-due greater than zero. | `count(DelinquencyRecord where dpd > 0)` | `DelinquencyRecord` (synthetic seed data) | COLLECTIONS_MANAGER | ILLUSTRATIVE | IMPLEMENTED |
| Total overdue amount | Total overdue amount | `total_overdue_amount` | Sum of the overdue amount across every delinquent account. | `sum(DelinquencyRecord.overdue_amount where dpd > 0)` | `DelinquencyRecord` (synthetic seed data) | COLLECTIONS_MANAGER | ILLUSTRATIVE | IMPLEMENTED |
| Recovered amount (from simulated PaymentEvents) | Recovered amount | `recovered_amount` | Sum of every successful simulated payment. | `sum(PaymentEvent.amount where outcome = SUCCEEDED)` | Simulated `PaymentEvent` rows | COLLECTIONS_MANAGER | ILLUSTRATIVE | IMPLEMENTED |
| Recovery rate = recovered amount / overdue amount at start | Recovery rate | `recovery_rate` | Share of the ever-overdue balance that has been recovered. Overdue at start is taken as recovered plus still overdue. | `recovered_amount / (recovered_amount + total_overdue_amount)` | `PaymentEvent`, `DelinquencyRecord` | COLLECTIONS_MANAGER | ILLUSTRATIVE | IMPLEMENTED |
| Promise-to-Pay rate | Promise-to-Pay rate | `ptp_rate` | Share of delinquent accounts with at least one Promise-to-Pay. | `count(distinct delinquent accounts with a PromiseToPay) / total_delinquent_accounts` | `PromiseToPay`, `DelinquencyRecord` | COLLECTIONS_MANAGER | ILLUSTRATIVE | IMPLEMENTED |
| Promise-kept rate ; PTP breakage rate | Promise-kept rate | `promise_kept_rate` | Share of settled Promises-to-Pay that were kept, not broken. | `count(PromiseToPay where status = KEPT) / count(PromiseToPay where status in (KEPT, BROKEN))` | `PromiseToPay` | COLLECTIONS_MANAGER | ILLUSTRATIVE | IMPLEMENTED |
| Promise-kept rate ; PTP breakage rate | PTP breakage rate | `ptp_breakage_rate` | Share of settled Promises-to-Pay that broke rather than were kept. | `count(PromiseToPay where status = BROKEN) / count(PromiseToPay where status in (KEPT, BROKEN))` | `PromiseToPay` | COLLECTIONS_MANAGER | ILLUSTRATIVE | IMPLEMENTED |
| Self-service resolution rate (resolved without human review) | Self-service resolution rate | `self_service_resolution_rate` | Share of delinquent accounts resolved through a kept Promise-to-Pay or an active or completed payment arrangement without ever being escalated. | `count(distinct delinquent accounts with a KEPT PromiseToPay or an ACTIVE/COMPLETED PaymentArrangement and no EscalationCase) / total_delinquent_accounts` | `PromiseToPay`, `PaymentArrangement`, `EscalationCase` | COLLECTIONS_MANAGER | ILLUSTRATIVE | IMPLEMENTED |
| Arrangement take-up rate (of eligible offers) | Arrangement take-up rate | `arrangement_take_up_rate` | Share of delinquent accounts with at least one payment arrangement. Measured against delinquent accounts, not against eligible offers: offers are not stored. | `count(distinct delinquent accounts with a PaymentArrangement) / total_delinquent_accounts` | `PaymentArrangement`, `DelinquencyRecord` | COLLECTIONS_MANAGER | ILLUSTRATIVE | IMPLEMENTED |
| Hardship and dispute case counts | Hardship case count | `hardship_case_count` | Total financial-hardship cases identified. | `count(HardshipCase)` | `HardshipCase` | COLLECTIONS_MANAGER | ILLUSTRATIVE | IMPLEMENTED |
| Hardship and dispute case counts | Dispute case count | `dispute_case_count` | Total disputes identified. | `count(Dispute)` | `Dispute` | COLLECTIONS_MANAGER | ILLUSTRATIVE | IMPLEMENTED |
| Human escalation rate | Escalation rate | `escalation_rate` | Share of delinquent accounts with at least one escalation case. | `count(distinct delinquent accounts with an EscalationCase) / total_delinquent_accounts` | `EscalationCase`, `DelinquencyRecord` | COLLECTIONS_MANAGER | ILLUSTRATIVE | IMPLEMENTED |
| Escalation queue size and aging | Escalation queue size | `review_queue_size` | Escalation cases currently open, in review or awaiting information. | `count(EscalationCase where status in (OPEN, IN_REVIEW, AWAITING_INFORMATION))` | `EscalationCase` | COLLECTIONS_MANAGER | ILLUSTRATIVE | IMPLEMENTED |
| Escalation queue aging | Escalation queue aging | - | Age of the open escalation cases. Each case's own age and aging warning are visible in `GET /api/escalations` and the Escalations screen; no aggregate KPI (for example oldest open case) is computed or shown on the dashboard. | not defined | `EscalationCase.created_at` | COLLECTIONS_MANAGER | n/a | NOT_YET_MEASURABLE |
| Time-to-review for escalations | Average time to first review | `average_time_to_review_ms` | Average time between an escalation case being opened and first reviewed. | `avg(EscalationCase.first_reviewed_at - EscalationCase.created_at) where first_reviewed_at is not null` | `EscalationCase` | COLLECTIONS_MANAGER | ILLUSTRATIVE | IMPLEMENTED |
| Human override rate | Human override rate | `human_override_rate` | Share of officer-decided AI recommendations that were overridden rather than accepted. | `count(Recommendation.officer_decision = OVERRIDDEN) / count(Recommendation.officer_decision is not null)` | `Recommendation` | COLLECTIONS_MANAGER | ILLUSTRATIVE | IMPLEMENTED |
| Intent classification accuracy (LIVE) | Intent classification accuracy | `intent_classification_accuracy` | Share of evaluation cases where the AI's classified intent matched the expected intent. Returned separately for MOCK and LIVE. | `passed_cases / total_cases` | `EvalRun`, `EvalCaseResult` | COLLECTIONS_MANAGER | MOCK (stored run); LIVE (none yet) | IMPLEMENTED |
| Sensitive-category recall (LIVE) | Sensitive-category recall: Financial hardship | `sensitive_category_recall_financial_hardship` | Recall of the FINANCIAL_HARDSHIP category. A pass or fail claim needs at least 30 labelled LIVE cases in the category (D-025); below that it is OBSERVATION_ONLY. | `passed cases in category / total cases in category` | `EvalCaseResult` | COLLECTIONS_MANAGER | MOCK (stored run); LIVE (none yet) | IMPLEMENTED |
| Sensitive-category recall (LIVE) | Sensitive-category recall: Dispute | `sensitive_category_recall_dispute` | Recall of the DISPUTE category, same 30-case rule. | `passed cases in category / total cases in category` | `EvalCaseResult` | COLLECTIONS_MANAGER | MOCK (stored run); LIVE (none yet) | IMPLEMENTED |
| Sensitive-category recall (LIVE) | Sensitive-category recall: Request human | `sensitive_category_recall_request_human` | Recall of the REQUEST_HUMAN category, same 30-case rule. | `passed cases in category / total cases in category` | `EvalCaseResult` | COLLECTIONS_MANAGER | MOCK (stored run); LIVE (none yet) | IMPLEMENTED |
| Escalation accuracy, over-escalation rate (LIVE) | Escalation precision, recall and over-escalation rate | - | Whether the system's escalate or do-not-escalate decision matches the label, with precision, recall and the share of unnecessary escalations. Reported in P2 for each stored run and kept on the `EvalRun` metrics (including `escalation_accuracy`); not returned by `GET /api/kpis`. | see `collectai_eval.reporting_rules.compute_escalation_metrics` | `EvalCaseResult` | COLLECTIONS_MANAGER | MOCK (stored run); LIVE (none yet) | EVAL_REPORT_ONLY |
| Structured-output compliance rate (LIVE and MOCK, labelled) | Structured-output compliance rate | - | Share of model outputs that matched their schema first time. Invalid outputs are audited (`AI_OUTPUT_INVALID`) but no rate is aggregated. | not defined | Audit events | COLLECTIONS_MANAGER | n/a | NOT_YET_MEASURABLE |
| Grounded response rate ; hallucination rate (ungrounded figure attempts caught) | Grounded response rate | - | Share of customer-facing AI text whose figures all trace to a deterministic service result. The grounding check blocks ungrounded text but no rate is recorded. | not defined | Grounding check outcomes | COLLECTIONS_MANAGER | n/a | NOT_YET_MEASURABLE |
| Grounded response rate ; hallucination rate (ungrounded figure attempts caught) | Hallucination rate | - | Ungrounded figure attempts caught by the grounding check, as a share of AI responses. No rate is recorded. | not defined | Grounding check outcomes | COLLECTIONS_MANAGER | n/a | NOT_YET_MEASURABLE |
| Tool-call success rate ; policy violation rate | Tool-call success rate | - | Share of AI tool calls that executed successfully. Calls are audited but no rate is aggregated. | not defined | Audit events | COLLECTIONS_MANAGER | n/a | NOT_YET_MEASURABLE |
| Tool-call success rate ; policy violation rate | Policy violation rate | - | Critical policy violations observed in the evaluation and red-team suites (BRD 4.2). Reported in P2 as the vulnerable-customer safety-set violation count and stored on the `EvalRun` metrics (`critical_policy_violation_count`); the red-team suite asserts zero. | count of cases flagged `critical_policy_violation` | `EvalCaseResult`, red-team suite | COLLECTIONS_MANAGER | MOCK (stored run); LIVE (none yet) | EVAL_REPORT_ONLY |
| Response latency ; token usage and estimated cost per AI interaction | Response latency | - | End-to-end time to answer. Provider latency is captured on audit events but not aggregated, and latency targets are observational only (BRD 4.6). | not defined | Audit event `latency` | COLLECTIONS_MANAGER | n/a | NOT_YET_MEASURABLE |
| Response latency ; token usage and estimated cost per AI interaction | Token usage and estimated cost per evaluation run | - | Input and output tokens and estimated cost (an estimate, not a bill) for each stored evaluation run. LIVE runs only; MOCK costs nothing. Returned per run by `GET /api/kpis/eval-runs`. Per-interaction usage is not aggregated. | `EvalRun.input_tokens`, `output_tokens`, `estimated_cost_usd` | `EvalRun` | COLLECTIONS_MANAGER | LIVE (none yet) | EVAL_REPORT_ONLY |

## Deferred KPIs

These need data outside the MVP model, so they are not built and appear nowhere in the API or dashboard (D-027, BRD 4.5).

| KPI | Definition | Formula | Data source | Owner persona | Data label | Status |
|---|---|---|---|---|---|---|
| Right-party contact rate | Share of contact attempts that reach the intended customer. | not defined | Contact-centre telephony data, not in the MVP model | COLLECTIONS_MANAGER | n/a | DEFERRED |
| Average handling time | Average time an officer spends per case. | not defined | Officer work-time data, not in the MVP model | COLLECTIONS_MANAGER | n/a | DEFERRED |
| Cost per collected account | Operating cost divided by accounts collected. | not defined | Cost and finance data, not in the MVP model | COLLECTIONS_MANAGER | n/a | DEFERRED |
