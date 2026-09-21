# Dependency Graph

Derived from `depends_on` in each story. Groups are topological levels; stories in the same group can run in parallel. Slices come from BRD section 7; a story never depends on a story in a later slice, so each slice can pass its exit criteria on its own. No circular dependencies (validated at generation).


## Group A

| Story ID | Title | Layer | Slice | Dependencies |
|---|---|---|---|---|
| E1-S1 | Domain types, Decimal money and injectable Clock | Types | 1 | - |
| E1-S2 | Versioned PolicyRuleSet and validated application configuration | Config | 1 | - |

## Group B

| Story ID | Title | Layer | Slice | Dependencies |
|---|---|---|---|---|
| E1-S3 | PostgreSQL persistence and synthetic seed data | Repository | 1 | E1-S1, E1-S2 |
| E2-S1 | Deterministic Collections Priority service | Service | 1 | E1-S1, E1-S2 |
| E2-S2 | PTP validation, payable amounts and satisfaction rule | Service | 1 | E1-S1, E1-S2 |
| E2-S3 | Payment arrangement eligibility service | Service | 2 | E1-S1, E1-S2 |
| E2-S4 | Treatment suppression and contact-frequency policy | Service | 1 | E1-S1, E1-S2 |
| E2-S5 | Data freshness and record consistency checks | Service | 1 | E1-S1, E1-S2 |
| E2-S6 | Escalation routing service | Service | 1 | E1-S1, E1-S2 |
| E5-S1 | LLM provider abstraction with MOCK and LIVE modes | Service | 1 | E1-S1, E1-S2 |

## Group C

| Story ID | Title | Layer | Slice | Dependencies |
|---|---|---|---|---|
| E1-S4 | Transactional audit service with append-only storage | Service | 1 | E1-S3 |
| E1-S5 | Reproducible local development and CI | Config | 1 | E1-S3 |
| E5-S3 | Grounding check, prompt allow-list and redaction | Service | 1 | E5-S1 |

## Group D

| Story ID | Title | Layer | Slice | Dependencies |
|---|---|---|---|---|
| E3-S1 | Persona RBAC enforced server-side | API | 1 | E1-S4 |
| E5-S2 | Structured output validation and fail-closed write path | Service | 1 | E5-S1, E1-S4 |

## Group E

| Story ID | Title | Layer | Slice | Dependencies |
|---|---|---|---|---|
| E3-S2 | Delinquent portfolio API with filter and sort | API | 1 | E3-S1, E2-S1, E2-S4 |
| E3-S5 | Customer binding and object-level authorization | API | 1 | E3-S1 |
| E4-S1 | Customer 360 API | API | 1 | E3-S1, E2-S1, E2-S4, E2-S5 |
| E5-S4 | READ and PROPOSE tool contracts with idempotency and call cap | Service | 1 | E5-S2, E2-S2, E2-S4 |
| E6-S6 | Officer-recorded Promise-to-Pay (manual workflow) | API | 1 | E2-S2, E2-S4, E2-S5, E3-S1 |
| E9-S1 | Audit trail API | API | 1 | E3-S1 |

## Group F

| Story ID | Title | Layer | Slice | Dependencies |
|---|---|---|---|---|
| E3-S3 | Delinquent Portfolio screen | UI | 1 | E3-S2 |
| E3-S4 | Persona switcher and role-based navigation | UI | 1 | E3-S5 |
| E4-S3 | Next-Best-Action recommendation | Service | 1 | E4-S1, E5-S2, E5-S3 |
| E6-S1 | Chat API and intent classification with safety precedence | API | 1 | E5-S2, E5-S3, E3-S5 |

## Group G

| Story ID | Title | Layer | Slice | Dependencies |
|---|---|---|---|---|
| E4-S2 | Customer 360 screen | UI | 1 | E4-S1, E3-S4, E6-S6 |
| E6-S2 | Promise-to-Pay creation flow | Service | 1 | E6-S1, E5-S4, E2-S5 |
| E6-S3 | Simulated PAY_NOW and PaymentEvent | Service | 1 | E6-S1, E2-S2, E2-S5 |
| E6-S5 | AI Collections Chat screen | UI | 1 | E6-S1, E3-S4 |
| E7-S1 | Escalation case creation and safe handling of sensitive intents | Service | 1 | E6-S1, E2-S6, E5-S4 |
| E9-S2 | Audit Trail Viewer screen | UI | 1 | E9-S1, E3-S4 |

## Group H

| Story ID | Title | Layer | Slice | Dependencies |
|---|---|---|---|---|
| E6-S4 | PTP lifecycle: KEPT and BROKEN transitions | Service | 1 | E6-S2, E6-S3 |
| E7-S2 | Review queue API with reviewer actions | API | 2 | E7-S1 |
| E7-S6 | Minimal escalation list screen (Slice 1) | UI | 1 | E7-S1, E4-S2 |
| E8-S1 | Payment arrangement conversation flow | Service | 2 | E2-S3, E7-S1, E2-S5 |
| E8-S3 | Dispute identification and suppression | Service | 3 | E7-S1 |
| E9-S4 | Red-team, security and data-safety test suites | Service | 1 | E6-S2 |
| E10-S1 | Evaluation dataset and MOCK/LIVE runner | Service | 1 | E7-S1 |

## Group I

| Story ID | Title | Layer | Slice | Dependencies |
|---|---|---|---|---|
| E7-S4 | Exceptional arrangement handling and human decision | Service | 2 | E8-S1, E7-S2 |
| E7-S5 | Compliance review queue and decision capability | API | 2 | E7-S2 |
| E8-S2 | Financial hardship identification and handling | Service | 2 | E7-S2 |
| E8-S4 | Dispute review and resolution | Service | 3 | E8-S3, E7-S2 |
| E9-S3 | Dev and demo controls | UI | 1 | E6-S4, E3-S4 |
| E10-S2 | Evaluation metrics and reporting rules | Service | 1 | E10-S1 |
| E11-S5 | Automated accessibility verification suite | UI | 1 | E3-S3, E6-S5, E7-S6 |

## Group J

| Story ID | Title | Layer | Slice | Dependencies |
|---|---|---|---|---|
| E7-S3 | Escalation and Review Queue screen | UI | 2 | E7-S5, E7-S6 |
| E10-S3 | KPI aggregation API | API | 4 | E6-S4, E10-S2, E8-S1, E8-S2, E8-S3 |
| E11-S1 | Journey A end-to-end: Promise-to-Pay | Service | 1 | E3-S3, E4-S2, E6-S5, E9-S2, E9-S3 |
| E11-S2 | Journey B1 end-to-end: eligible payment arrangement | Service | 2 | E7-S4, E6-S5, E9-S2 |

## Group K

| Story ID | Title | Layer | Slice | Dependencies |
|---|---|---|---|---|
| E10-S4 | Collections and AI Performance Dashboard | UI | 4 | E10-S3, E3-S4 |
| E10-S5 | Portfolio deliverables P1 to P4 | Config | 4 | E10-S3 |
| E11-S3 | Journey B2 end-to-end: financial hardship | Service | 2 | E8-S2, E7-S3, E9-S2 |
| E11-S4 | Journey C end-to-end: dispute | Service | 3 | E8-S4, E7-S3, E9-S2 |

## Group L

| Story ID | Title | Layer | Slice | Dependencies |
|---|---|---|---|---|
| E11-S6 | Manual accessibility review | Config | 4 | E11-S5, E10-S4, E7-S3, E9-S2 |

## Slice summary

| Slice | Stories |
|---|---|
| 1 | E1-S1, E1-S2, E1-S3, E1-S4, E1-S5, E2-S1, E2-S2, E2-S4, E2-S5, E2-S6, E3-S1, E3-S2, E3-S3, E3-S4, E3-S5, E4-S1, E4-S2, E4-S3, E5-S1, E5-S2, E5-S3, E5-S4, E6-S1, E6-S2, E6-S3, E6-S4, E6-S5, E6-S6, E7-S1, E7-S6, E9-S1, E9-S2, E9-S3, E9-S4, E10-S1, E10-S2, E11-S1, E11-S5 |
| 2 | E2-S3, E7-S2, E7-S3, E7-S4, E7-S5, E8-S1, E8-S2, E11-S2, E11-S3 |
| 3 | E8-S3, E8-S4, E11-S4 |
| 4 | E10-S3, E10-S4, E10-S5, E11-S6 |
