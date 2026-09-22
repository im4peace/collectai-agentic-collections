# CollectAI API Contracts

Status: design. Source of truth for endpoint names, paths and JSON field names (snake_case throughout). The machine-readable equivalent is `api-contracts.schema.json` (OpenAPI 3.0.3), generated from the same definitions, so the two never disagree. Both are checked against FastAPI's generated OpenAPI in CI (contract test `tests/api/test_openapi_contract.py`).

Synthetic data only. Payments are simulated. All ids, names, emails (`example.com`) and phone numbers (fictional `+1-555-01xx`) in examples are fictional.

## 1. Conventions

### 1.1 Base, formats
- Base path `/api`. No URL version segment in the MVP; changes are additive. JSON only (`application/json; charset=utf-8`).
- Field names are snake_case. Enum values are UPPER_SNAKE_CASE strings.
- **Money** is a JSON string with exactly 2 decimal places in responses (`"1250.50"`, pattern `^\d+\.\d{2}$`). In requests money is a JSON **string** (`"1250.5"` is accepted and normalized; more than 2 decimals is rejected with reason `OVER_PRECISION`; a JSON number is rejected with 422 `FLOAT_NOT_ALLOWED`). Never a float anywhere. Currency is always `USD` (synthetic).
- Other decimals (scores, weights, ratios) are decimal strings. Score and contribution: 2 dp; normalized_value: 4 dp; ratios: 4 dp.
- Timestamps: ISO-8601 UTC with `Z` (`2026-10-01T14:30:00Z`), always from the injected Clock. Dates: `YYYY-MM-DD`, interpreted in UTC.
- Ids are opaque prefixed strings: `cus_`, `acc_`, `itm_`, `int_`, `ptp_`, `pay_`, `arr_`, `hsp_`, `dsp_`, `esc_`, `dec_`, `conv_`, `msg_`, `trn_`, `prp_`, `rec_`, `aud_`, `evr_`. Clients must not parse them.
- Lists: `{"items": [...], "page": {"limit","offset","total"}}`. Single resources are returned directly (no `data` wrapper).
- Unknown request fields are rejected (422 `UNKNOWN_FIELD`). A client-supplied `customer_id` is not part of any CUSTOMER-facing request schema and is therefore rejected (D-032).

### 1.2 Persona, session and headers
| Header | Direction | Rule |
|---|---|---|
| `X-Persona` | request | One of `CUSTOMER`, `COLLECTIONS_OFFICER`, `COLLECTIONS_MANAGER`, `COMPLIANCE_RISK`. Missing or invalid: 401 `UNAUTHENTICATED`. Public endpoints are exempt. |
| `X-Demo-Session` | request | Opaque token from `POST /api/session`. **Required when `X-Persona` is `CUSTOMER`**; the server maps it to the bound `customer_id` (table `demo_session`). Missing, unknown or persona-mismatched: 401. The client never sends a customer id. |
| `X-Correlation-Id` | request, response | Optional inbound (8-64 chars `[A-Za-z0-9_-]`, else replaced); always returned. Propagated to audit events, logs and provider calls. |
| `Idempotency-Key` | request | Required on operations marked **Idempotent: required** (8-128 chars `[A-Za-z0-9_-]`). Same key and same body returns the original result; the response carries `Idempotent-Replayed: true` (status 200 for creates that normally return 201). Same key with a different body: 409 `IDEMPOTENCY_KEY_REUSED`. Keys are scoped per persona (and per customer). Missing: 422 `IDEMPOTENCY_KEY_REQUIRED`. |
| `X-RateLimit-Limit`, `X-RateLimit-Remaining`, `Retry-After` | response | Present on rate-limited routes; 429 includes `Retry-After` seconds. |

The persona header is a demo mechanism, not authentication (D-019). It is authoritative only inside the trust model of a local demo; every endpoint still checks it server-side, audits denials, and CUSTOMER access is additionally bound to one `customer_id` (section 1.5).

### 1.3 Error envelope
Every non-2xx response has this shape (`ErrorEnvelope`):
```json
{"error": {"code": "BUSINESS_RULE_VIOLATION", "reason_code": "OVER_BALANCE",
  "message": "The promised amount is more than the undisputed overdue amount.",
  "correlation_id": "c0ffee1234abcd", "policy_version": "policy-v1",
  "details": [{"field": "promised_amount", "reason_code": "OVER_BALANCE", "message": "Maximum is 900.00"}],
  "alternatives": {"valid_amount_range": {"min": "20.00", "max": "900.00"}, "valid_date_range": {"earliest": "2026-10-01", "latest": "2026-10-31"}},
  "context": null}}
```
`code` (coarse category) to HTTP status: `UNAUTHENTICATED` 401, `FORBIDDEN` 403, `NOT_FOUND` 404, `VALIDATION_ERROR` 422 (shape, format, missing reason or note), `BUSINESS_RULE_VIOLATION` 422 (deterministic rule rejection), `CONFLICT` 409 (state, version, staleness, duplicates), `RATE_LIMITED` 429, `POLICY_UNAVAILABLE` 503, `AUDIT_UNAVAILABLE` 503, `HANDOFF_FAILED` 503, `SERVICE_UNAVAILABLE` 503, `INTERNAL_ERROR` 500. `reason_code` is the precise, stable code. Messages never contain secrets, stack traces or another customer's data. Cross-customer access returns exactly the same 404 body as a nonexistent resource (only `correlation_id` differs).

### 1.4 Reason-code catalogue (stable)
| Family | Codes |
|---|---|
| Money and dates | `ZERO_AMOUNT`, `NEGATIVE_AMOUNT`, `OVER_PRECISION`, `FLOAT_NOT_ALLOWED`, `OVER_BALANCE`, `BELOW_MIN_AMOUNT`, `PAST_DATE`, `OUTSIDE_WINDOW` |
| Records and state | `CONFLICTING_ACTIVE_ITEM`, `DISPUTED_ITEM`, `STALE_DATA`, `VERSION_CONFLICT`, `PROPOSAL_INVALID`, `INVALID_STATE_TRANSITION`, `CASE_ALREADY_DECIDED`, `WRONG_QUEUE`, `INCONSISTENT_RECORD` |
| Policy and authority | `NOT_PERMITTED_BY_POLICY`, `EXCEPTION_TYPE_NOT_PERMITTED`, `EXCEEDS_THRESHOLD`, `EXCEEDS_MAX_OVERDUE_AMOUNT`, `WRONG_REVIEWER_ROLE`, `QUEUE_NOT_PERMITTED`, `POLICY_UNAVAILABLE`, `AMBIGUOUS_VALIDATION` |
| Contact policy | `MAX_ATTEMPTS`, `MIN_INTERVAL` |
| Validation | `FIELD_INVALID`, `UNKNOWN_FIELD`, `REASON_REQUIRED`, `NOTE_REQUIRED`, `OUTCOME_REQUIRED`, `MODIFICATION_REQUIRED`, `ESCALATE_REASON_REQUIRED`, `ESCALATE_REASON_NOT_WHITELISTED`, `DESTINATION_NOT_ACCEPTED`, `FREE_FORM_AMOUNT_NOT_ALLOWED`, `IDEMPOTENCY_KEY_REQUIRED`, `IDEMPOTENCY_KEY_REUSED`, `FILTER_REQUIRED`, `CUSTOMER_ID_REQUIRED_OR_FORBIDDEN` |

Multiple violations are all listed in `details`; the envelope `reason_code` is the first by this precedence: shape/precision (`NEGATIVE_AMOUNT`, `ZERO_AMOUNT`, `OVER_PRECISION`), amount policy (`BELOW_MIN_AMOUNT`, `OVER_BALANCE`), date (`PAST_DATE`, `OUTSIDE_WINDOW`), state (`DISPUTED_ITEM`, `CONFLICTING_ACTIVE_ITEM`), freshness.

### 1.5 Authorization model
1. **Role check** (route level): each route declares one capability (`x-capability` in OpenAPI). The static role-to-capability matrix in section 1.7 decides 403 `FORBIDDEN`. A generated test walks every registered route for all four personas (E3-S1).
2. **Object-level check** (CUSTOMER): every `/api/me/*` and `/api/chat/*` handler resolves the resource through a repository call scoped by the session's bound `customer_id` (`WHERE id = :id AND customer_id = :bound`). No row means 404, identical to nonexistence. A denied cross-customer attempt is audited with persona, bound customer_id and endpoint, never the target's contents.
3. **Row-level reviewer check**: reviewer endpoints also require the case's `reviewer_role` to match the persona (403 `WRONG_REVIEWER_ROLE`); `COMPLIANCE_RISK` may act only on `COMPLIANCE_REVIEW` cases through `compliance-decision`.
4. Every 403 writes an audit event (`ACCESS_DENIED`) containing persona, method, path template and correlation id.
5. `COLLECTIONS_MANAGER` receives 403 on every POST, PUT, PATCH and DELETE. `COMPLIANCE_RISK` receives 403 on all of them except `POST /api/escalations/{case_id}/compliance-decision`.

### 1.6 Rate limits
In-process sliding window per session token (persona for staff): default `API_RATE_LIMIT_PER_MINUTE` = 300; chat messages `CHAT_RATE_LIMIT_PER_MINUTE` = 20 (contract range 1-600); recommendation generation 10/min. Exceeded: 429 `RATE_LIMITED`, `Retry-After`. Single-instance demo; a shared store would be needed for multiple instances.

### 1.7 Capability matrix
Legend: Y allowed, - denied (403). Public endpoints need no persona.

| Capability | CUSTOMER | COLLECTIONS_OFFICER | COLLECTIONS_MANAGER | COMPLIANCE_RISK |
|---|---|---|---|---|
| `audit:read` | - | - | - | Y |
| `chat:use` | Y | - | - | - |
| `compliance:decide` | - | - | - | Y |
| `conversation:read` | - | Y | - | - |
| `customer360:read` | - | Y | - | - |
| `demo_controls:use` | - | Y | - | - |
| `dispute:read` | - | Y | - | - |
| `dispute:resolve` | - | Y | - | - |
| `escalation:read` | - | Y | - | Y |
| `escalation:review` | - | Y | - | - |
| `hardship:read` | - | Y | - | - |
| `kpi:read` | - | - | Y | - |
| `portfolio:read` | - | Y | - | - |
| `ptp:read` | - | Y | - | - |
| `ptp:record` | - | Y | - | - |
| `recommendation:decide` | - | Y | - | - |
| `recommendation:generate` | - | Y | - | - |
| `recommendation:read` | - | Y | - | - |
| `self:read` | Y | - | - | - |
| `self:write` | Y | - | - | - |
| `session:read` | Y | Y | Y | Y |
| `snapshot:refresh` | - | Y | - | - |

Persona to navigation (E3-S4): CUSTOMER: Chat. COLLECTIONS_OFFICER: Portfolio, Customer 360, escalation queues, demo controls (flag). COLLECTIONS_MANAGER: Dashboard. COMPLIANCE_RISK: Audit Trail, compliance review queue.

## 2. Endpoint index

| Method | Path | Personas | Slice | Stories |
|---|---|---|---|---|
| GET | `/api/health` | any (public) | 1 | E1-S5 |
| GET | `/api/ready` | any (public) | 1 | E1-S5, E1-S2 |
| GET | `/api/meta` | any (public) | 1 | E1-S2, E9-S3 |
| GET | `/api/session/options` | any (public) | 1 | E3-S4, E3-S5 |
| POST | `/api/session` | any (public) | 1 | E3-S1, E3-S4, E3-S5 |
| GET | `/api/session/me` | CUS, OFF, MGR, CMP | 1 | E3-S1, E3-S4 |
| GET | `/api/portfolio` | OFF | 1 | E3-S2 (US-001), E2-S1, E2-S4 |
| GET | `/api/customers/{account_id}/360` | OFF | 1 | E4-S1 (US-002), E2-S5 |
| POST | `/api/customers/{account_id}/refresh` | OFF | 1 | E2-S5, E4-S2 |
| GET | `/api/accounts/{account_id}/recommendation` | OFF | 1 | E4-S3 (US-003) |
| POST | `/api/accounts/{account_id}/recommendation` | OFF | 1 | E4-S3 (US-003), E5-S2, E5-S3 |
| POST | `/api/accounts/{account_id}/recommendation/{recommendation_id}/decision` | OFF | 1 | E4-S3, E10-S3 (BRD 13.1 row 23) |
| POST | `/api/ptps/validate` | OFF | 1 | E6-S6, E2-S2 |
| POST | `/api/ptps` | OFF | 1 | E6-S6 (US-005), E2-S2, E2-S4, E2-S5 |
| GET | `/api/ptps/{ptp_id}` | OFF | 1 | E6-S6, E6-S4 |
| POST | `/api/ptps/{ptp_id}/cancel` | OFF | 1 | E6-S4, E6-S2, E8-S1 |
| GET | `/api/me/accounts` | CUS | 1 | E3-S5, E6-S1 |
| GET | `/api/me/accounts/{account_id}` | CUS | 1 | E3-S5 |
| GET | `/api/me/accounts/{account_id}/ptps` | CUS | 1 | E3-S5, E6-S2 |
| GET | `/api/me/accounts/{account_id}/payment-events` | CUS | 1 | E3-S5, E6-S3 |
| GET | `/api/me/accounts/{account_id}/arrangements` | CUS | 2 | E3-S5, E8-S1 |
| GET | `/api/me/ptps/{ptp_id}` | CUS | 1 | E3-S5 |
| POST | `/api/me/ptps/{ptp_id}/cancel` | CUS | 1 | E6-S2, E6-S4 |
| GET | `/api/me/payment-events/{payment_event_id}` | CUS | 1 | E3-S5 |
| GET | `/api/me/arrangements/{arrangement_id}` | CUS | 2 | E3-S5 |
| GET | `/api/me/hardship-cases/{hardship_case_id}` | CUS | 2 | E3-S5, E8-S2 |
| GET | `/api/me/disputes/{dispute_id}` | CUS | 3 | E3-S5, E8-S3 |
| GET | `/api/me/escalations` | CUS | 1 | E3-S5, E7-S1 |
| GET | `/api/me/escalations/{case_id}` | CUS | 1 | E3-S5 |
| POST | `/api/chat/conversations` | CUS | 1 | E6-S1 (US-004), E3-S5 |
| GET | `/api/chat/conversations` | CUS | 1 | E6-S1, E6-S5 |
| GET | `/api/chat/conversations/{conversation_id}` | CUS | 1 | E6-S1, E6-S5 |
| POST | `/api/chat/conversations/{conversation_id}/messages` | CUS | 1 | E6-S1, E6-S2, E6-S3, E7-S1, E8-S1, E8-S2, E8-S3, E5-S2..E5-S4 |
| POST | `/api/chat/conversations/{conversation_id}/proposals/{proposal_id}/confirm` | CUS | 1 | E6-S2, E6-S3, E8-S1, E7-S4, E6-S5 |
| POST | `/api/chat/conversations/{conversation_id}/proposals/{proposal_id}/cancel` | CUS | 1 | E6-S5, E6-S2 |
| POST | `/api/chat/conversations/{conversation_id}/handoff` | CUS | 1 | E6-S5, E7-S1 |
| GET | `/api/conversations/{conversation_id}` | OFF | 1 | E7-S1, E7-S3 |
| GET | `/api/escalations` | OFF, CMP | 1 | E7-S1 AC7, E7-S6, E7-S2, E7-S3, E7-S5 |
| GET | `/api/escalations/summary` | OFF, CMP | 2 | E7-S3, E7-S5 |
| GET | `/api/escalations/{case_id}` | OFF, CMP | 1 | E7-S2, E7-S3, E7-S5, E8-S2, E8-S3 |
| POST | `/api/escalations/{case_id}/start-review` | OFF | 2 | E7-S2 |
| POST | `/api/escalations/{case_id}/decisions` | OFF | 2 | E7-S2, E7-S4, E8-S2, US-008 |
| POST | `/api/escalations/{case_id}/compliance-decision` | CMP | 2 | E7-S5, E3-S1 |
| GET | `/api/hardship-cases/{hardship_case_id}` | OFF | 2 | E8-S2, E4-S1 |
| GET | `/api/disputes/{dispute_id}` | OFF | 3 | E8-S3, E8-S4 |
| POST | `/api/disputes/{dispute_id}/start-review` | OFF | 3 | E8-S4 |
| POST | `/api/disputes/{dispute_id}/resolve` | OFF | 3 | E8-S4 (US-011) |
| GET | `/api/audit` | CMP | 1 | E9-S1 (US-009) |
| GET | `/api/audit/chains` | CMP | 1 | E9-S1, E9-S2 |
| GET | `/api/kpis` | MGR | 4 | E10-S3 (US-010) |
| GET | `/api/kpis/eval-runs` | MGR | 4 | E10-S3, E10-S2 |
| GET | `/api/demo-controls/state` | OFF | 1 | E9-S3 |
| POST | `/api/demo-controls/clock/advance` | OFF | 1 | E9-S3, E6-S4 |
| POST | `/api/demo-controls/ptp-lifecycle/run` | OFF | 1 | E9-S3, E6-S4 |
| POST | `/api/demo-controls/payments/simulate` | OFF | 1 | E9-S3, E6-S3, E6-S4 |
| POST | `/api/demo-controls/reseed` | OFF | 1 | E9-S3, E1-S3 |

Persona short names: CUS = CUSTOMER, OFF = COLLECTIONS_OFFICER, MGR = COLLECTIONS_MANAGER, CMP = COMPLIANCE_RISK.

## 3. Endpoints

Every non-public endpoint can also return 401 `UNAUTHENTICATED`, 403 `FORBIDDEN`, 429 `RATE_LIMITED` and 500 `INTERNAL_ERROR`; these are not repeated below. All responses carry `X-Correlation-Id`.

### 3.1 System

#### GET /api/health
Liveness probe.

- **Stories / slice:** E1-S5 / Slice 1
- **Personas:** any (capability `public`)
- **Success:** 200 `HealthStatus`
- **Rate limit:** none

#### GET /api/ready
Readiness: database, migrations, active valid PolicyRuleSet, audit role grants.

- **Stories / slice:** E1-S5, E1-S2 / Slice 1
- **Personas:** any (capability `public`)
- **Success:** 200 `ReadyStatus`
- **Rate limit:** none
- **Errors:**
  - 503 `SERVICE_UNAVAILABLE`: not_ready, body still ReadyStatus

#### GET /api/meta
Runtime info for badges (MOCK or LIVE, policy version, clock, demo flag).

- **Stories / slice:** E1-S2, E9-S3 / Slice 1
- **Personas:** any (capability `public`)
- **Success:** 200 `MetaInfo`
- **Rate limit:** none

### 3.2 Session

#### GET /api/session/options
List personas and seeded demo customers for the switcher.

- **Stories / slice:** E3-S4, E3-S5 / Slice 1
- **Personas:** any (capability `public`)
- **Success:** 200 `SessionOptionsResponse`
- **Rate limit:** none

#### POST /api/session
Select a persona; for CUSTOMER binds one seeded customer_id server-side and returns an opaque session token.

- **Stories / slice:** E3-S1, E3-S4, E3-S5 / Slice 1
- **Personas:** any (capability `public`)
- **Body:** `SessionCreateRequest` (section 4)
- **Success:** 201 `SessionInfo`
- **Rate limit:** none
- **Errors:**
  - 422 `VALIDATION_ERROR` / `FIELD_INVALID`: Schema violation, unknown field, float money, missing Idempotency-Key (IDEMPOTENCY_KEY_REQUIRED)
  - 404 `NOT_FOUND`: customer_id is not a seeded customer
  - 422 `VALIDATION_ERROR` / `CUSTOMER_ID_REQUIRED_OR_FORBIDDEN`: customer_id missing for CUSTOMER or supplied for another persona
- **Behaviour:** Staff personas get a token too but it is optional for them; CUSTOMER requests without a valid X-Demo-Session are rejected 401. Sessions are rows in demo_session and are not authentication.

#### GET /api/session/me
Current persona, bound customer and capability list.

- **Stories / slice:** E3-S1, E3-S4 / Slice 1
- **Personas:** CUSTOMER, COLLECTIONS_OFFICER, COLLECTIONS_MANAGER, COMPLIANCE_RISK (capability `session:read`)
- **Headers:** `X-Persona`
- **Success:** 200 `SessionInfo`
- **Rate limit:** default: API_RATE_LIMIT_PER_MINUTE (300) per session

### 3.3 Portfolio

#### GET /api/portfolio
List delinquent accounts with deterministic priority, filter and sort.

- **Stories / slice:** E3-S2 (US-001), E2-S1, E2-S4 / Slice 1
- **Personas:** COLLECTIONS_OFFICER (capability `portfolio:read`)
- **Query:** `dpd_min` (integer) Inclusive minimum DPD, >= 0; `dpd_max` (integer) Inclusive maximum DPD, >= dpd_min; `priority_band` (enum PriorityBand[]) Repeatable; OR within the parameter; `status` (enum CollectionStatus[]) Repeatable; OR within the parameter; `sort_by` (string) overdue_amount, dpd or priority_score (default priority_score); `sort_dir` (string) asc or desc (default desc); `limit` (integer) 1-200, default 50; `offset` (integer) Default 0
- **Headers:** `X-Persona`
- **Success:** 200 `PortfolioPage`
- **Rate limit:** default: API_RATE_LIMIT_PER_MINUTE (300) per session
- **Errors:**
  - 422 `VALIDATION_ERROR` / `FIELD_INVALID`: Schema violation, unknown field, float money, missing Idempotency-Key (IDEMPOTENCY_KEY_REQUIRED)
  - 503 `POLICY_UNAVAILABLE`: No valid active PolicyRuleSet: fail closed
- **Behaviour:** Filters intersect (AND across parameters). Only accounts with overdue_amount > 0 are listed. Money sorts use Decimal comparison (NUMERIC in SQL). Ties break by account_id asc. Accounts with INCONSISTENT_RECORD are excluded and counted in the audit log, never scored.

### 3.4 Customer 360

#### GET /api/customers/{account_id}/360
Consolidated Customer 360 read model (path segment is the account id).

- **Stories / slice:** E4-S1 (US-002), E2-S5 / Slice 1
- **Personas:** COLLECTIONS_OFFICER (capability `customer360:read`)
- **Path params:** `account_id` (id) acc_ id
- **Headers:** `X-Persona`
- **Success:** 200 `Customer360`
- **Rate limit:** default: API_RATE_LIMIT_PER_MINUTE (300) per session
- **Errors:**
  - 404 `NOT_FOUND`: Unknown account or ownership failure (identical body for both)
- **Behaviour:** Priority and factors are under deterministic; the recommendation under ai. Read-only: never triggers AI, never mutates. When POLICY_UNAVAILABLE the deterministic block has status POLICY_UNAVAILABLE and priority null (still 200) so manual work continues. CUSTOMER receives 403.

#### POST /api/customers/{account_id}/refresh
Simulated core-banking sync: sets as_of to Clock now, rolls DPD forward by whole days elapsed, increments record_version.

- **Stories / slice:** E2-S5, E4-S2 / Slice 1
- **Personas:** COLLECTIONS_OFFICER (capability `snapshot:refresh`)
- **Path params:** `account_id` (id) acc_ id
- **Headers:** `X-Persona`
- **Success:** 200 `SnapshotInfo`
- **Rate limit:** default: API_RATE_LIMIT_PER_MINUTE (300) per session
- **Errors:**
  - 404 `NOT_FOUND`: Unknown account or ownership failure (identical body for both)
  - 503 `AUDIT_UNAVAILABLE`: Audit write failed; transition rolled back
- **Behaviour:** Backs the stale-data banner refresh action. Audited (event SNAPSHOT_REFRESHED). Pending customer proposals for the account become INVALIDATED because record_version changed.

### 3.5 Recommendation

#### GET /api/accounts/{account_id}/recommendation
Latest stored next-best-action.

- **Stories / slice:** E4-S3 (US-003) / Slice 1
- **Personas:** COLLECTIONS_OFFICER (capability `recommendation:read`)
- **Path params:** `account_id` (id) acc_ id
- **Headers:** `X-Persona`
- **Success:** 200 `RecommendationResult`
- **Rate limit:** default: API_RATE_LIMIT_PER_MINUTE (300) per session
- **Errors:**
  - 404 `NOT_FOUND`: Unknown account or ownership failure (identical body for both)
- **Behaviour:** status NOT_GENERATED with recommendation null when none exists.

#### POST /api/accounts/{account_id}/recommendation
Generate a next-best-action with rationale through AI orchestration.

- **Stories / slice:** E4-S3 (US-003), E5-S2, E5-S3 / Slice 1
- **Personas:** COLLECTIONS_OFFICER (capability `recommendation:generate`)
- **Path params:** `account_id` (id) acc_ id
- **Headers:** `X-Persona`
- **Success:** 200 `RecommendationResult`
- **Rate limit:** 10/min per session
- **Errors:**
  - 404 `NOT_FOUND`: Unknown account or ownership failure (identical body for both)
  - 503 `AUDIT_UNAVAILABLE`: Audit write failed; transition rolled back
  - 503 `POLICY_UNAVAILABLE`: No valid active PolicyRuleSet: fail closed
- **Behaviour:** Never changes financial state. AI failure returns 200 with status AI_UNAVAILABLE and recommendation null (no fabricated content). Schema-invalid output after one retry returns SAFE_FALLBACK (ESCALATE_TO_HUMAN_REVIEW, TEMPLATE). Accounts under dispute, hardship, vulnerable flag or open escalation always return HUMAN_REVIEW_ONLY with action ESCALATE_TO_HUMAN_REVIEW regardless of model output. An ungrounded rationale is replaced by templated text (content_source TEMPLATE). If the audit write fails the response is 503 AUDIT_UNAVAILABLE with no recommendation body.

#### POST /api/accounts/{account_id}/recommendation/{recommendation_id}/decision
Officer accepts or overrides an AI recommendation (override reason mandatory; feeds human override rate).

- **Stories / slice:** E4-S3, E10-S3 (BRD 13.1 row 23) / Slice 1
- **Personas:** COLLECTIONS_OFFICER (capability `recommendation:decide`)
- **Path params:** `account_id` (id) acc_ id; `recommendation_id` (id) rec_ id
- **Headers:** `X-Persona`, `Idempotency-Key` (**Idempotent: required**)
- **Body:** `RecommendationDecisionRequest` (section 4)
- **Success:** 200 `Recommendation`
- **Rate limit:** default: API_RATE_LIMIT_PER_MINUTE (300) per session
- **Errors:**
  - 404 `NOT_FOUND`: Unknown account or ownership failure (identical body for both)
  - 422 `VALIDATION_ERROR` / `FIELD_INVALID`: Schema violation, unknown field, float money, missing Idempotency-Key (IDEMPOTENCY_KEY_REQUIRED)
  - 409 `CONFLICT` / `IDEMPOTENCY_KEY_REUSED`: Same key sent with a different request body
  - 503 `AUDIT_UNAVAILABLE`: Audit write failed; transition rolled back
- **Behaviour:** reason is required when decision is OVERRIDDEN (422 REASON_REQUIRED).

### 3.6 Promise-to-Pay

#### POST /api/ptps/validate
Dry-run deterministic validation of amount and date; always 200.

- **Stories / slice:** E6-S6, E2-S2 / Slice 1
- **Personas:** COLLECTIONS_OFFICER (capability `ptp:record`)
- **Headers:** `X-Persona`
- **Body:** `PtpValidateRequest` (section 4)
- **Success:** 200 `PtpValidationResult`
- **Rate limit:** default: API_RATE_LIMIT_PER_MINUTE (300) per session
- **Errors:**
  - 422 `VALIDATION_ERROR` / `FIELD_INVALID`: Schema violation, unknown field, float money, missing Idempotency-Key (IDEMPOTENCY_KEY_REQUIRED)
  - 404 `NOT_FOUND`: Unknown account or ownership failure (identical body for both)
  - 503 `POLICY_UNAVAILABLE`: No valid active PolicyRuleSet: fail closed
- **Behaviour:** Uses the same validator as creation. Same-day dates are valid; the last permitted day (Clock today + ptp.window_days) is valid.

#### POST /api/ptps
Officer manually records a PTP (status PENDING) with the same guardrails as the chat flow.

- **Stories / slice:** E6-S6 (US-005), E2-S2, E2-S4, E2-S5 / Slice 1
- **Personas:** COLLECTIONS_OFFICER (capability `ptp:record`)
- **Headers:** `X-Persona`, `Idempotency-Key` (**Idempotent: required**)
- **Body:** `PtpCreateRequest` (section 4)
- **Success:** 201 `PromiseToPay` (200 with `Idempotent-Replayed: true` on replay)
- **Rate limit:** default: API_RATE_LIMIT_PER_MINUTE (300) per session
- **Errors:**
  - 422 `BUSINESS_RULE_VIOLATION` / `ZERO_AMOUNT|NEGATIVE_AMOUNT|OVER_BALANCE|OVER_PRECISION|BELOW_MIN_AMOUNT|PAST_DATE|OUTSIDE_WINDOW`: Deterministic rejection; alternatives populated
  - 409 `CONFLICT` / `CONFLICTING_ACTIVE_ITEM`: Active PENDING PTP (or active arrangement if policy forbids) exists; context.permitted_paths lists cancel or amend
  - 409 `CONFLICT` / `DISPUTED_ITEM`: PTP on an item under active dispute, or all overdue items disputed
  - 409 `CONFLICT` / `STALE_DATA`: Snapshot stale or version mismatch; context.refreshed_context returned
  - 409 `CONFLICT` / `AMBIGUOUS_VALIDATION`: Freshness UNKNOWN or rules cannot authorize; no state change; escalation reported
  - 422 `VALIDATION_ERROR` / `FIELD_INVALID`: Schema violation, unknown field, float money, missing Idempotency-Key (IDEMPOTENCY_KEY_REQUIRED)
  - 409 `CONFLICT` / `IDEMPOTENCY_KEY_REUSED`: Same key sent with a different request body
  - 404 `NOT_FOUND`: Unknown account or ownership failure (identical body for both)
  - 503 `POLICY_UNAVAILABLE`: No valid active PolicyRuleSet: fail closed
  - 503 `AUDIT_UNAVAILABLE`: Audit write failed; transition rolled back
- **Behaviour:** A duplicate submission with the same Idempotency-Key returns 200 with the original PTP and header Idempotent-Replayed: true. Does not depend on AI orchestration and works when the provider is down. Suppression governs automated treatment only, so an officer (human treatment) may record a PTP on a suppressed account, but never on a disputed item.

#### GET /api/ptps/{ptp_id}
Read one PTP.

- **Stories / slice:** E6-S6, E6-S4 / Slice 1
- **Personas:** COLLECTIONS_OFFICER (capability `ptp:read`)
- **Path params:** `ptp_id` (id) ptp_ id
- **Headers:** `X-Persona`
- **Success:** 200 `PromiseToPay`
- **Rate limit:** default: API_RATE_LIMIT_PER_MINUTE (300) per session
- **Errors:**
  - 404 `NOT_FOUND`: Unknown id

#### POST /api/ptps/{ptp_id}/cancel
Cancel a PENDING PTP (PENDING to CANCELLED only).

- **Stories / slice:** E6-S4, E6-S2, E8-S1 / Slice 1
- **Personas:** COLLECTIONS_OFFICER (capability `ptp:record`)
- **Path params:** `ptp_id` (id) ptp_ id
- **Headers:** `X-Persona`, `Idempotency-Key` (**Idempotent: required**)
- **Body:** `CancelRequest` (section 4)
- **Success:** 200 `PromiseToPay`
- **Rate limit:** default: API_RATE_LIMIT_PER_MINUTE (300) per session
- **Errors:**
  - 409 `CONFLICT` / `INVALID_STATE_TRANSITION`: PTP is KEPT, BROKEN or CANCELLED
  - 422 `VALIDATION_ERROR` / `FIELD_INVALID`: Schema violation, unknown field, float money, missing Idempotency-Key (IDEMPOTENCY_KEY_REQUIRED)
  - 409 `CONFLICT` / `IDEMPOTENCY_KEY_REUSED`: Same key sent with a different request body
  - 404 `NOT_FOUND`: Unknown id
  - 503 `AUDIT_UNAVAILABLE`: Audit write failed; transition rolled back
- **Behaviour:** Amend = cancel then create.

### 3.7 Customer

#### GET /api/me/accounts
Own accounts (customer-safe summary).

- **Stories / slice:** E3-S5, E6-S1 / Slice 1
- **Personas:** CUSTOMER (capability `self:read`)
- **Query:** `limit` (integer) 1-50; `offset` (integer)
- **Headers:** `X-Persona` + `X-Demo-Session`
- **Success:** 200 `CustomerAccountPage`
- **Rate limit:** default: API_RATE_LIMIT_PER_MINUTE (300) per session

#### GET /api/me/accounts/{account_id}
Own account summary.

- **Stories / slice:** E3-S5 / Slice 1
- **Personas:** CUSTOMER (capability `self:read`)
- **Path params:** `account_id` (id) acc_ id
- **Headers:** `X-Persona` + `X-Demo-Session`
- **Success:** 200 `CustomerAccountSummary`
- **Rate limit:** default: API_RATE_LIMIT_PER_MINUTE (300) per session
- **Errors:**
  - 404 `NOT_FOUND`: Unknown account or ownership failure (identical body for both)

#### GET /api/me/accounts/{account_id}/ptps
Own PTPs for an owned account.

- **Stories / slice:** E3-S5, E6-S2 / Slice 1
- **Personas:** CUSTOMER (capability `self:read`)
- **Path params:** `account_id` (id) acc_ id
- **Query:** `limit` (integer); `offset` (integer)
- **Headers:** `X-Persona` + `X-Demo-Session`
- **Success:** 200 `PtpPage`
- **Rate limit:** default: API_RATE_LIMIT_PER_MINUTE (300) per session
- **Errors:**
  - 404 `NOT_FOUND`: Unknown account or ownership failure (identical body for both)

#### GET /api/me/accounts/{account_id}/payment-events
Own simulated payment events.

- **Stories / slice:** E3-S5, E6-S3 / Slice 1
- **Personas:** CUSTOMER (capability `self:read`)
- **Path params:** `account_id` (id) acc_ id
- **Query:** `limit` (integer); `offset` (integer)
- **Headers:** `X-Persona` + `X-Demo-Session`
- **Success:** 200 `PaymentEventPage`
- **Rate limit:** default: API_RATE_LIMIT_PER_MINUTE (300) per session
- **Errors:**
  - 404 `NOT_FOUND`: Unknown account or ownership failure (identical body for both)

#### GET /api/me/accounts/{account_id}/arrangements
Own arrangements.

- **Stories / slice:** E3-S5, E8-S1 / Slice 2
- **Personas:** CUSTOMER (capability `self:read`)
- **Path params:** `account_id` (id) acc_ id
- **Query:** `limit` (integer); `offset` (integer)
- **Headers:** `X-Persona` + `X-Demo-Session`
- **Success:** 200 `ArrangementPage`
- **Rate limit:** default: API_RATE_LIMIT_PER_MINUTE (300) per session
- **Errors:**
  - 404 `NOT_FOUND`: Unknown account or ownership failure (identical body for both)

#### GET /api/me/ptps/{ptp_id}
Own PTP by id.

- **Stories / slice:** E3-S5 / Slice 1
- **Personas:** CUSTOMER (capability `self:read`)
- **Path params:** `ptp_id` (id) ptp_ id
- **Headers:** `X-Persona` + `X-Demo-Session`
- **Success:** 200 `PromiseToPay`
- **Rate limit:** default: API_RATE_LIMIT_PER_MINUTE (300) per session
- **Errors:**
  - 404 `NOT_FOUND`: Unknown account or ownership failure (identical body for both)

#### POST /api/me/ptps/{ptp_id}/cancel
Customer cancels an own PENDING PTP.

- **Stories / slice:** E6-S2, E6-S4 / Slice 1
- **Personas:** CUSTOMER (capability `self:write`)
- **Path params:** `ptp_id` (id) ptp_ id
- **Headers:** `X-Persona` + `X-Demo-Session`, `Idempotency-Key` (**Idempotent: required**)
- **Body:** `CancelRequest` (section 4)
- **Success:** 200 `PromiseToPay`
- **Rate limit:** default: API_RATE_LIMIT_PER_MINUTE (300) per session
- **Errors:**
  - 404 `NOT_FOUND`: Unknown account or ownership failure (identical body for both)
  - 409 `CONFLICT` / `INVALID_STATE_TRANSITION`: Not PENDING
  - 422 `VALIDATION_ERROR` / `FIELD_INVALID`: Schema violation, unknown field, float money, missing Idempotency-Key (IDEMPOTENCY_KEY_REQUIRED)
  - 409 `CONFLICT` / `IDEMPOTENCY_KEY_REUSED`: Same key sent with a different request body
  - 503 `AUDIT_UNAVAILABLE`: Audit write failed; transition rolled back

#### GET /api/me/payment-events/{payment_event_id}
Own payment event by id.

- **Stories / slice:** E3-S5 / Slice 1
- **Personas:** CUSTOMER (capability `self:read`)
- **Path params:** `payment_event_id` (id) pay_ id
- **Headers:** `X-Persona` + `X-Demo-Session`
- **Success:** 200 `PaymentEvent`
- **Rate limit:** default: API_RATE_LIMIT_PER_MINUTE (300) per session
- **Errors:**
  - 404 `NOT_FOUND`: Unknown account or ownership failure (identical body for both)

#### GET /api/me/arrangements/{arrangement_id}
Own arrangement by id.

- **Stories / slice:** E3-S5 / Slice 2
- **Personas:** CUSTOMER (capability `self:read`)
- **Path params:** `arrangement_id` (id) arr_ id
- **Headers:** `X-Persona` + `X-Demo-Session`
- **Success:** 200 `PaymentArrangement`
- **Rate limit:** default: API_RATE_LIMIT_PER_MINUTE (300) per session
- **Errors:**
  - 404 `NOT_FOUND`: Unknown account or ownership failure (identical body for both)

#### GET /api/me/hardship-cases/{hardship_case_id}
Own hardship record (customer-safe view).

- **Stories / slice:** E3-S5, E8-S2 / Slice 2
- **Personas:** CUSTOMER (capability `self:read`)
- **Path params:** `hardship_case_id` (id) hsp_ id
- **Headers:** `X-Persona` + `X-Demo-Session`
- **Success:** 200 `HardshipCustomerView`
- **Rate limit:** default: API_RATE_LIMIT_PER_MINUTE (300) per session
- **Errors:**
  - 404 `NOT_FOUND`: Unknown account or ownership failure (identical body for both)

#### GET /api/me/disputes/{dispute_id}
Own dispute (customer-safe view).

- **Stories / slice:** E3-S5, E8-S3 / Slice 3
- **Personas:** CUSTOMER (capability `self:read`)
- **Path params:** `dispute_id` (id) dsp_ id
- **Headers:** `X-Persona` + `X-Demo-Session`
- **Success:** 200 `DisputeCustomerView`
- **Rate limit:** default: API_RATE_LIMIT_PER_MINUTE (300) per session
- **Errors:**
  - 404 `NOT_FOUND`: Unknown account or ownership failure (identical body for both)

#### GET /api/me/escalations
Own escalation cases (customer-safe view).

- **Stories / slice:** E3-S5, E7-S1 / Slice 1
- **Personas:** CUSTOMER (capability `self:read`)
- **Query:** `limit` (integer); `offset` (integer)
- **Headers:** `X-Persona` + `X-Demo-Session`
- **Success:** 200 `EscalationCustomerPage`
- **Rate limit:** default: API_RATE_LIMIT_PER_MINUTE (300) per session

#### GET /api/me/escalations/{case_id}
Own escalation by id (customer-safe view).

- **Stories / slice:** E3-S5 / Slice 1
- **Personas:** CUSTOMER (capability `self:read`)
- **Path params:** `case_id` (id) esc_ id
- **Headers:** `X-Persona` + `X-Demo-Session`
- **Success:** 200 `EscalationCustomerView`
- **Rate limit:** default: API_RATE_LIMIT_PER_MINUTE (300) per session
- **Errors:**
  - 404 `NOT_FOUND`: Unknown account or ownership failure (identical body for both)

### 3.8 Chat

#### POST /api/chat/conversations
Start a conversation; returns the AI disclosure greeting.

- **Stories / slice:** E6-S1 (US-004), E3-S5 / Slice 1
- **Personas:** CUSTOMER (capability `chat:use`)
- **Headers:** `X-Persona` + `X-Demo-Session`
- **Body:** `ConversationCreateRequest` (section 4)
- **Success:** 201 `ConversationCreateResult`
- **Rate limit:** default: API_RATE_LIMIT_PER_MINUTE (300) per session
- **Errors:**
  - 404 `NOT_FOUND`: Unknown account or ownership failure (identical body for both)
  - 422 `VALIDATION_ERROR` / `FIELD_INVALID`: Schema violation, unknown field, float money, missing Idempotency-Key (IDEMPOTENCY_KEY_REQUIRED)
- **Behaviour:** account_id must belong to the bound customer; another customer's account gives the same 404 as a nonexistent one. The greeting is a template (no provider call) and always states that the assistant is an AI.

#### GET /api/chat/conversations
Own conversations, newest first.

- **Stories / slice:** E6-S1, E6-S5 / Slice 1
- **Personas:** CUSTOMER (capability `chat:use`)
- **Query:** `account_id` (id) Filter to one owned account; `limit` (integer); `offset` (integer)
- **Headers:** `X-Persona` + `X-Demo-Session`
- **Success:** 200 `ConversationPage`
- **Rate limit:** default: API_RATE_LIMIT_PER_MINUTE (300) per session

#### GET /api/chat/conversations/{conversation_id}
Own conversation with messages, pending proposal and handoff.

- **Stories / slice:** E6-S1, E6-S5 / Slice 1
- **Personas:** CUSTOMER (capability `chat:use`)
- **Path params:** `conversation_id` (id) conv_ id
- **Headers:** `X-Persona` + `X-Demo-Session`
- **Success:** 200 `ConversationDetail`
- **Rate limit:** default: API_RATE_LIMIT_PER_MINUTE (300) per session
- **Errors:**
  - 404 `NOT_FOUND`: Unknown account or ownership failure (identical body for both)

#### POST /api/chat/conversations/{conversation_id}/messages
Send a customer message; synchronous whole-message reply (no streaming).

- **Stories / slice:** E6-S1, E6-S2, E6-S3, E7-S1, E8-S1, E8-S2, E8-S3, E5-S2..E5-S4 / Slice 1
- **Personas:** CUSTOMER (capability `chat:use`)
- **Path params:** `conversation_id` (id) conv_ id
- **Headers:** `X-Persona` + `X-Demo-Session`, `Idempotency-Key` (optional)
- **Body:** `MessageCreateRequest` (section 4)
- **Success:** 200 `ChatTurnResponse`
- **Rate limit:** CHAT_RATE_LIMIT_PER_MINUTE (default 20) per session; 429 RATE_LIMITED with Retry-After
- **Errors:**
  - 404 `NOT_FOUND`: Unknown account or ownership failure (identical body for both)
  - 422 `VALIDATION_ERROR` / `FIELD_INVALID`: Schema violation, unknown field, float money, missing Idempotency-Key (IDEMPOTENCY_KEY_REQUIRED)
  - 503 `SERVICE_UNAVAILABLE`: Only for infrastructure faults (database down). AI, policy, audit and handoff failures are 200 with safe_state
- **Behaviour:** Optional Idempotency-Key: a replay returns the stored turn response. Processing order: refresh-if-stale, classify (schema validated, one retry), safety precedence, bounded tool loop (TOOL_CALL_CAP_PER_TURN), grounding check, persist, audit. Whole-message HTTP response; latency depends on provider (observational p95 target 8 s in LIVE). Provider failure after the retry returns 200 with safe_state AI_UNAVAILABLE, a safe message with the Talk to a human option, and an AI_FAILURE_FALLBACK escalation. If the audit write fails for a material output the response is 200 with safe_state AUDIT_UNAVAILABLE and no proposal. Tool cap reached: safe_state TOOL_CAP_REACHED and an AI_FAILURE_FALLBACK escalation. Sensitive intents (FINANCIAL_HARDSHIP, DISPUTE, REQUEST_HUMAN, vulnerability_detected, special_request != NONE, PAYMENT_PLAN before Slice 2, UNKNOWN after clarifications) return a respectful holding message, handoff populated, no proposal. In a HANDED_OFF conversation replies are templated holding messages without a provider call for that topic.

#### POST /api/chat/conversations/{conversation_id}/proposals/{proposal_id}/confirm
Explicit customer confirmation; the domain service revalidates and creates the PTP, simulated PaymentEvent, arrangement or exception-review case.

- **Stories / slice:** E6-S2, E6-S3, E8-S1, E7-S4, E6-S5 / Slice 1
- **Personas:** CUSTOMER (capability `chat:use`)
- **Path params:** `conversation_id` (id) conv_ id; `proposal_id` (id) prp_ id
- **Headers:** `X-Persona` + `X-Demo-Session`, `Idempotency-Key` (**Idempotent: required**)
- **Body:** `ConfirmRequest` (section 4)
- **Success:** 201 `ConfirmResult` (200 with `Idempotent-Replayed: true` on replay)
- **Rate limit:** default: API_RATE_LIMIT_PER_MINUTE (300) per session
- **Errors:**
  - 404 `NOT_FOUND`: Unknown account or ownership failure (identical body for both)
  - 422 `VALIDATION_ERROR` / `FIELD_INVALID`: Schema violation, unknown field, float money, missing Idempotency-Key (IDEMPOTENCY_KEY_REQUIRED)
  - 409 `CONFLICT` / `IDEMPOTENCY_KEY_REUSED`: Same key sent with a different request body
  - 409 `CONFLICT` / `PROPOSAL_INVALID`: Stale record_version, altered terms_hash, expired, already cancelled or no longer permitted; nothing created
  - 409 `CONFLICT` / `CONFLICTING_ACTIVE_ITEM`: Active PTP or arrangement blocks creation; context.permitted_paths lists amend, cancel, officer
  - 409 `CONFLICT` / `DISPUTED_ITEM`: Disputed item
  - 409 `CONFLICT` / `AMBIGUOUS_VALIDATION`: Freshness UNKNOWN or rules cannot authorize; no state change; escalation reported
  - 503 `POLICY_UNAVAILABLE`: No valid active PolicyRuleSet: fail closed
  - 503 `AUDIT_UNAVAILABLE`: Audit write failed; transition rolled back
- **Behaviour:** First success 201; an idempotent replay returns 200 with replayed true and header Idempotent-Replayed: true. PAYMENT confirmation is simulated only: a PaymentEvent with simulated=true is recorded and no external call occurs. STALE_DATA in this flow is reported as PROPOSAL_INVALID. AMBIGUOUS_VALIDATION also creates an AMBIGUOUS_VALIDATION escalation (context.escalation_case_id). A proposal can be confirmed only by the owning customer.

#### POST /api/chat/conversations/{conversation_id}/proposals/{proposal_id}/cancel
Customer declines a pending proposal; nothing is created.

- **Stories / slice:** E6-S5, E6-S2 / Slice 1
- **Personas:** CUSTOMER (capability `chat:use`)
- **Path params:** `conversation_id` (id) conv_ id; `proposal_id` (id) prp_ id
- **Headers:** `X-Persona` + `X-Demo-Session`
- **Success:** 200 `CancelProposalResult`
- **Rate limit:** default: API_RATE_LIMIT_PER_MINUTE (300) per session
- **Errors:**
  - 404 `NOT_FOUND`: Unknown account or ownership failure (identical body for both)
  - 409 `CONFLICT` / `PROPOSAL_INVALID`: Proposal is no longer PENDING_CONFIRMATION
- **Behaviour:** Naturally idempotent on an already CANCELLED proposal (returns 200).

#### POST /api/chat/conversations/{conversation_id}/handoff
Talk to a human: creates a REQUEST_HUMAN escalation immediately, never discouraged.

- **Stories / slice:** E6-S5, E7-S1 / Slice 1
- **Personas:** CUSTOMER (capability `chat:use`)
- **Path params:** `conversation_id` (id) conv_ id
- **Headers:** `X-Persona` + `X-Demo-Session`, `Idempotency-Key` (**Idempotent: required**)
- **Body:** `HandoffRequest` (section 4)
- **Success:** 201 `HandoffResult` (200 with `Idempotent-Replayed: true` on replay)
- **Rate limit:** default: API_RATE_LIMIT_PER_MINUTE (300) per session
- **Errors:**
  - 404 `NOT_FOUND`: Unknown account or ownership failure (identical body for both)
  - 422 `VALIDATION_ERROR` / `FIELD_INVALID`: Schema violation, unknown field, float money, missing Idempotency-Key (IDEMPOTENCY_KEY_REQUIRED)
  - 409 `CONFLICT` / `IDEMPOTENCY_KEY_REUSED`: Same key sent with a different request body
  - 503 `HANDOFF_FAILED`: Case could not be created; customer is told the handoff was not completed and given a safe next step; automated treatment for the account stays paused
- **Behaviour:** Works without the AI provider. Returns 200 replayed true when an OPEN REQUEST_HUMAN case already exists for the conversation.

#### GET /api/conversations/{conversation_id}
Staff read of a transcript.

- **Stories / slice:** E7-S1, E7-S3 / Slice 1
- **Personas:** COLLECTIONS_OFFICER (capability `conversation:read`)
- **Path params:** `conversation_id` (id) conv_ id
- **Headers:** `X-Persona`
- **Success:** 200 `ConversationDetail`
- **Rate limit:** default: API_RATE_LIMIT_PER_MINUTE (300) per session
- **Errors:**
  - 404 `NOT_FOUND`: Unknown id

### 3.9 Escalation

#### GET /api/escalations
Escalation list (Slice 1) and review queue (Slice 2+).

- **Stories / slice:** E7-S1 AC7, E7-S6, E7-S2, E7-S3, E7-S5 / Slice 1
- **Personas:** COLLECTIONS_OFFICER, COMPLIANCE_RISK (capability `escalation:read`)
- **Query:** `queue` (enum ReviewQueue[]) Repeatable filter; `status` (enum CaseStatus[]) Repeatable; default OPEN, IN_REVIEW, AWAITING_INFORMATION; `priority` (enum EscalationPriority[]) Repeatable; `reason` (enum EscalationReason[]) Repeatable; `account_id` (id); `limit` (integer) 1-200, default 50; `offset` (integer)
- **Headers:** `X-Persona`
- **Success:** 200 `EscalationPage`
- **Rate limit:** default: API_RATE_LIMIT_PER_MINUTE (300) per session
- **Errors:**
  - 403 `FORBIDDEN` / `QUEUE_NOT_PERMITTED`: COMPLIANCE_RISK requesting a queue other than COMPLIANCE_REVIEW
- **Behaviour:** OFFICER sees all queues (COMPLIANCE_REVIEW cases read-only). COMPLIANCE_RISK is automatically scoped to COMPLIANCE_REVIEW. Sorted by priority (URGENT, ELEVATED, NORMAL) then created_at ascending. COLLECTIONS_MANAGER and CUSTOMER receive 403.

#### GET /api/escalations/summary
Per-queue counts and aging warnings.

- **Stories / slice:** E7-S3, E7-S5 / Slice 2
- **Personas:** COLLECTIONS_OFFICER, COMPLIANCE_RISK (capability `escalation:read`)
- **Headers:** `X-Persona`
- **Success:** 200 `EscalationSummaryResponse`
- **Rate limit:** default: API_RATE_LIMIT_PER_MINUTE (300) per session

#### GET /api/escalations/{case_id}
Case detail: conversation, AI recommendation and deterministic rule results as separate sections.

- **Stories / slice:** E7-S2, E7-S3, E7-S5, E8-S2, E8-S3 / Slice 1
- **Personas:** COLLECTIONS_OFFICER, COMPLIANCE_RISK (capability `escalation:read`)
- **Path params:** `case_id` (id) esc_ id
- **Headers:** `X-Persona`
- **Success:** 200 `EscalationDetail`
- **Rate limit:** default: API_RATE_LIMIT_PER_MINUTE (300) per session
- **Errors:**
  - 404 `NOT_FOUND`: Unknown id
  - 403 `FORBIDDEN` / `QUEUE_NOT_PERMITTED`: COMPLIANCE_RISK on a case outside COMPLIANCE_REVIEW
- **Behaviour:** available_actions is computed server-side; APPROVE is reported permitted=false with denied_reason_code NOT_PERMITTED_BY_POLICY when the active PolicyRuleSet does not permit it.

#### POST /api/escalations/{case_id}/start-review
OPEN to IN_REVIEW, or AWAITING_INFORMATION back to IN_REVIEW.

- **Stories / slice:** E7-S2 / Slice 2
- **Personas:** COLLECTIONS_OFFICER (capability `escalation:review`)
- **Path params:** `case_id` (id) esc_ id
- **Headers:** `X-Persona`, `Idempotency-Key` (**Idempotent: required**)
- **Body:** `StartReviewRequest` (section 4)
- **Success:** 200 `EscalationDetail`
- **Rate limit:** default: API_RATE_LIMIT_PER_MINUTE (300) per session
- **Errors:**
  - 404 `NOT_FOUND`: Unknown id
  - 409 `CONFLICT` / `VERSION_CONFLICT`: expected_version does not match; context.current_version returned; nothing changed
  - 409 `CONFLICT` / `INVALID_STATE_TRANSITION`: Transition outside the state machine
  - 403 `FORBIDDEN` / `WRONG_REVIEWER_ROLE`: Case reviewer_role is not COLLECTIONS_OFFICER
  - 422 `VALIDATION_ERROR` / `FIELD_INVALID`: Schema violation, unknown field, float money, missing Idempotency-Key (IDEMPOTENCY_KEY_REQUIRED)
  - 409 `CONFLICT` / `IDEMPOTENCY_KEY_REUSED`: Same key sent with a different request body
  - 503 `AUDIT_UNAVAILABLE`: Audit write failed; transition rolled back

#### POST /api/escalations/{case_id}/decisions
Reviewer action: APPROVE, REJECT, MODIFY, REQUEST_MORE_INFORMATION or ESCALATE.

- **Stories / slice:** E7-S2, E7-S4, E8-S2, US-008 / Slice 2
- **Personas:** COLLECTIONS_OFFICER (capability `escalation:review`)
- **Path params:** `case_id` (id) esc_ id
- **Headers:** `X-Persona`, `Idempotency-Key` (**Idempotent: required**)
- **Body:** `DecisionRequest` (section 4)
- **Success:** 200 `DecisionResult`
- **Rate limit:** default: API_RATE_LIMIT_PER_MINUTE (300) per session
- **Errors:**
  - 404 `NOT_FOUND`: Unknown id
  - 422 `VALIDATION_ERROR` / `REASON_REQUIRED|NOTE_REQUIRED|MODIFICATION_REQUIRED|ESCALATE_REASON_REQUIRED|ESCALATE_REASON_NOT_WHITELISTED|DESTINATION_NOT_ACCEPTED|FREE_FORM_AMOUNT_NOT_ALLOWED`: Missing reason or note, free-form destination (queue or reviewer_role fields are unknown fields), option not in the eligible set
  - 409 `CONFLICT` / `NOT_PERMITTED_BY_POLICY`: APPROVE or MODIFY not permitted for this case type or authority (EXCEPTION_TYPE_NOT_PERMITTED, EXCEEDS_THRESHOLD, EXCEEDS_MAX_OVERDUE_AMOUNT in details)
  - 409 `CONFLICT` / `VERSION_CONFLICT`: expected_version does not match; context.current_version returned; nothing changed
  - 409 `CONFLICT` / `CASE_ALREADY_DECIDED`: A different decision on a DECIDED or RE_ROUTED case
  - 409 `CONFLICT` / `INVALID_STATE_TRANSITION`: Transition outside the state machine
  - 409 `CONFLICT` / `STALE_DATA`: Snapshot stale or version mismatch; context.refreshed_context returned
  - 403 `FORBIDDEN` / `WRONG_REVIEWER_ROLE`: Case reviewer_role is COMPLIANCE_RISK
  - 409 `CONFLICT` / `IDEMPOTENCY_KEY_REUSED`: Same key sent with a different request body
  - 503 `AUDIT_UNAVAILABLE`: Audit write failed; transition rolled back
- **Behaviour:** OPEN cases pass through IN_REVIEW implicitly (two audit events). APPROVE of EXCEPTIONAL_ARRANGEMENT re-validates authority and freshness then creates the arrangement through the arrangement domain service with exactly the customer's requested terms. MODIFY (exceptional arrangements only) creates a pending ARRANGEMENT proposal the customer must confirm (D-041). ESCALATE takes only a whitelisted escalate_reason; the routing service picks the destination, the case becomes RE_ROUTED and a new OPEN case is created (parent_case_id set). release_suppression true releases hardship or vulnerable suppression and clears the vulnerability flag. Replays with the same Idempotency-Key return the original DecisionResult (replayed true).

#### POST /api/escalations/{case_id}/compliance-decision
record_compliance_review_decision: outcome, mandatory reason on a COMPLIANCE_REVIEW case.

- **Stories / slice:** E7-S5, E3-S1 / Slice 2
- **Personas:** COMPLIANCE_RISK (capability `compliance:decide`)
- **Path params:** `case_id` (id) esc_ id
- **Headers:** `X-Persona`, `Idempotency-Key` (**Idempotent: required**)
- **Body:** `ComplianceDecisionRequest` (section 4)
- **Success:** 200 `DecisionResult`
- **Rate limit:** default: API_RATE_LIMIT_PER_MINUTE (300) per session
- **Errors:**
  - 404 `NOT_FOUND`: Unknown id
  - 409 `CONFLICT` / `WRONG_QUEUE`: Case is not in COMPLIANCE_REVIEW
  - 409 `CONFLICT` / `INVALID_STATE_TRANSITION`: Case already DECIDED or RE_ROUTED
  - 409 `CONFLICT` / `VERSION_CONFLICT`: expected_version does not match; context.current_version returned; nothing changed
  - 422 `VALIDATION_ERROR` / `FIELD_INVALID`: Schema violation, unknown field, float money, missing Idempotency-Key (IDEMPOTENCY_KEY_REQUIRED)
  - 409 `CONFLICT` / `IDEMPOTENCY_KEY_REUSED`: Same key sent with a different request body
  - 503 `AUDIT_UNAVAILABLE`: Audit write failed; transition rolled back
- **Behaviour:** The only mutating endpoint COMPLIANCE_RISK may call. Touches only the case, its decision row, its suppression release and audit; no balance, payment, PTP, arrangement, hardship or dispute writes (verified by table-snapshot test).

### 3.10 Hardship

#### GET /api/hardship-cases/{hardship_case_id}
Read a hardship record.

- **Stories / slice:** E8-S2, E4-S1 / Slice 2
- **Personas:** COLLECTIONS_OFFICER (capability `hardship:read`)
- **Path params:** `hardship_case_id` (id) hsp_ id
- **Headers:** `X-Persona`
- **Success:** 200 `HardshipCase`
- **Rate limit:** default: API_RATE_LIMIT_PER_MINUTE (300) per session
- **Errors:**
  - 404 `NOT_FOUND`: Unknown id
- **Behaviour:** Hardship records are created only by the chat flow after a validated flag_hardship proposal (idempotent per account while open); there is no create endpoint. Reviewer hardship decisions use the decisions endpoint on the linked case.

### 3.11 Dispute

#### GET /api/disputes/{dispute_id}
Read a dispute.

- **Stories / slice:** E8-S3, E8-S4 / Slice 3
- **Personas:** COLLECTIONS_OFFICER (capability `dispute:read`)
- **Path params:** `dispute_id` (id) dsp_ id
- **Headers:** `X-Persona`
- **Success:** 200 `Dispute`
- **Rate limit:** default: API_RATE_LIMIT_PER_MINUTE (300) per session
- **Errors:**
  - 404 `NOT_FOUND`: Unknown id
- **Behaviour:** Disputes are created only by the chat flow after a validated flag_dispute proposal.

#### POST /api/disputes/{dispute_id}/start-review
OPEN to UNDER_REVIEW.

- **Stories / slice:** E8-S4 / Slice 3
- **Personas:** COLLECTIONS_OFFICER (capability `dispute:resolve`)
- **Path params:** `dispute_id` (id) dsp_ id
- **Headers:** `X-Persona`, `Idempotency-Key` (**Idempotent: required**)
- **Body:** `DisputeStartReviewRequest` (section 4)
- **Success:** 200 `DisputeTransitionResult`
- **Rate limit:** default: API_RATE_LIMIT_PER_MINUTE (300) per session
- **Errors:**
  - 404 `NOT_FOUND`: Unknown id
  - 409 `CONFLICT` / `VERSION_CONFLICT`: expected_version does not match; context.current_version returned; nothing changed
  - 409 `CONFLICT` / `INVALID_STATE_TRANSITION`: Not OPEN
  - 422 `VALIDATION_ERROR` / `FIELD_INVALID`: Schema violation, unknown field, float money, missing Idempotency-Key (IDEMPOTENCY_KEY_REQUIRED)
  - 409 `CONFLICT` / `IDEMPOTENCY_KEY_REUSED`: Same key sent with a different request body
  - 503 `AUDIT_UNAVAILABLE`: Audit write failed; transition rolled back

#### POST /api/disputes/{dispute_id}/resolve
UNDER_REVIEW to RESOLVED with outcome and reason; lifts item suppression only once the outcome is recorded.

- **Stories / slice:** E8-S4 (US-011) / Slice 3
- **Personas:** COLLECTIONS_OFFICER (capability `dispute:resolve`)
- **Path params:** `dispute_id` (id) dsp_ id
- **Headers:** `X-Persona`, `Idempotency-Key` (**Idempotent: required**)
- **Body:** `DisputeResolveRequest` (section 4)
- **Success:** 200 `DisputeTransitionResult`
- **Rate limit:** default: API_RATE_LIMIT_PER_MINUTE (300) per session
- **Errors:**
  - 404 `NOT_FOUND`: Unknown id
  - 422 `VALIDATION_ERROR` / `OUTCOME_REQUIRED|REASON_REQUIRED`: Missing outcome or empty reason
  - 409 `CONFLICT` / `VERSION_CONFLICT`: expected_version does not match; context.current_version returned; nothing changed
  - 409 `CONFLICT` / `INVALID_STATE_TRANSITION`: Status must be UNDER_REVIEW (OPEN cannot skip to RESOLVED)
  - 409 `CONFLICT` / `IDEMPOTENCY_KEY_REUSED`: Same key sent with a different request body
  - 503 `AUDIT_UNAVAILABLE`: Audit write failed; transition rolled back

### 3.12 Audit

#### GET /api/audit
Read-only audit events; decision chain ordered by timestamp.

- **Stories / slice:** E9-S1 (US-009) / Slice 1
- **Personas:** COMPLIANCE_RISK (capability `audit:read`)
- **Query:** `correlation_id` (string) Exact match; returns the whole chain; `account_id` (id) Filter by account; `from` (timestamp) Inclusive lower bound; `to` (timestamp) Exclusive upper bound; `stage` (enum AuditStage[]) Repeatable; `event_type` (string); `limit` (integer) 1-500, default 100; `offset` (integer)
- **Headers:** `X-Persona`
- **Success:** 200 `AuditPage`
- **Rate limit:** default: API_RATE_LIMIT_PER_MINUTE (300) per session
- **Errors:**
  - 422 `VALIDATION_ERROR` / `FILTER_REQUIRED`: At least one of correlation_id, account_id or from/to is required
- **Behaviour:** No write route exists for audit. Responses contain only redacted values; a test scans 100 events for secrets and prohibited identifiers. Reads are not themselves audited.

#### GET /api/audit/chains
Chain summaries (one per correlation_id) for the viewer's search.

- **Stories / slice:** E9-S1, E9-S2 / Slice 1
- **Personas:** COMPLIANCE_RISK (capability `audit:read`)
- **Query:** `account_id` (id); `from` (timestamp); `to` (timestamp); `limit` (integer) 1-200, default 50; `offset` (integer)
- **Headers:** `X-Persona`
- **Success:** 200 `AuditChainPage`
- **Rate limit:** default: API_RATE_LIMIT_PER_MINUTE (300) per session
- **Errors:**
  - 422 `VALIDATION_ERROR` / `FILTER_REQUIRED`: At least one filter is required

### 3.13 KPI

#### GET /api/kpis
KPI tree: Business, Operational, AI quality (MOCK and LIVE separate); deferred KPIs absent.

- **Stories / slice:** E10-S3 (US-010) / Slice 4
- **Personas:** COLLECTIONS_MANAGER (capability `kpi:read`)
- **Headers:** `X-Persona`
- **Success:** 200 `KpiResponse`
- **Rate limit:** default: API_RATE_LIMIT_PER_MINUTE (300) per session
- **Behaviour:** Business KPIs carry data_label ILLUSTRATIVE. A LIVE category recall with fewer than 30 labelled LIVE cases has claim_status OBSERVATION_ONLY and no pass/fail. MOCK results never appear in ai_quality.live and are never compared to targets.

#### GET /api/kpis/eval-runs
Stored EvalRuns behind the AI KPIs.

- **Stories / slice:** E10-S3, E10-S2 / Slice 4
- **Personas:** COLLECTIONS_MANAGER (capability `kpi:read`)
- **Query:** `mode` (enum ProviderMode) Filter; `limit` (integer); `offset` (integer)
- **Headers:** `X-Persona`
- **Success:** 200 `EvalRunPage`
- **Rate limit:** default: API_RATE_LIMIT_PER_MINUTE (300) per session

### 3.14 Demo controls

#### GET /api/demo-controls/state
LIVE or MOCK mode text, clock, flag.

- **Stories / slice:** E9-S3 / Slice 1
- **Personas:** COLLECTIONS_OFFICER (capability `demo_controls:use`)
- **Headers:** `X-Persona`
- **Success:** 200 `DemoState`
- **Rate limit:** default: API_RATE_LIMIT_PER_MINUTE (300) per session
- **Errors:**
  - 404 `NOT_FOUND`: DEMO_CONTROLS_ENABLED=false: every /api/demo-controls route answers 404 before persona checks

#### POST /api/demo-controls/clock/advance
Advance the simulated Clock.

- **Stories / slice:** E9-S3, E6-S4 / Slice 1
- **Personas:** COLLECTIONS_OFFICER (capability `demo_controls:use`)
- **Headers:** `X-Persona`
- **Body:** `ClockAdvanceRequest` (section 4)
- **Success:** 200 `ClockAdvanceResult`
- **Rate limit:** default: API_RATE_LIMIT_PER_MINUTE (300) per session
- **Errors:**
  - 404 `NOT_FOUND`: DEMO_CONTROLS_ENABLED=false: every /api/demo-controls route answers 404 before persona checks
  - 422 `VALIDATION_ERROR` / `FIELD_INVALID`: Schema violation, unknown field, float money, missing Idempotency-Key (IDEMPOTENCY_KEY_REQUIRED)
  - 503 `AUDIT_UNAVAILABLE`: Audit write failed; transition rolled back
- **Behaviour:** Requires the SIMULATED clock, which is only installed when DEMO_CONTROLS_ENABLED=true. Audited (DEMO_CLOCK_ADVANCED).

#### POST /api/demo-controls/ptp-lifecycle/run
Run the PTP breakage job now under the current Clock.

- **Stories / slice:** E9-S3, E6-S4 / Slice 1
- **Personas:** COLLECTIONS_OFFICER (capability `demo_controls:use`)
- **Headers:** `X-Persona`
- **Success:** 200 `LifecycleRunResult`
- **Rate limit:** default: API_RATE_LIMIT_PER_MINUTE (300) per session
- **Errors:**
  - 404 `NOT_FOUND`: DEMO_CONTROLS_ENABLED=false: every /api/demo-controls route answers 404 before persona checks
  - 503 `AUDIT_UNAVAILABLE`: Audit write failed; transition rolled back
- **Behaviour:** Same job the scheduler runs. Safe to rerun: KEPT and BROKEN PTPs are never re-transitioned and no duplicate audit events are written.

#### POST /api/demo-controls/payments/simulate
Record a simulated PaymentEvent with source DEMO_CONTROL.

- **Stories / slice:** E9-S3, E6-S3, E6-S4 / Slice 1
- **Personas:** COLLECTIONS_OFFICER (capability `demo_controls:use`)
- **Headers:** `X-Persona`, `Idempotency-Key` (**Idempotent: required**)
- **Body:** `SimulatePaymentRequest` (section 4)
- **Success:** 201 `SimulatePaymentResult` (200 with `Idempotent-Replayed: true` on replay)
- **Rate limit:** default: API_RATE_LIMIT_PER_MINUTE (300) per session
- **Errors:**
  - 404 `NOT_FOUND`: DEMO_CONTROLS_ENABLED=false: every /api/demo-controls route answers 404 before persona checks
  - 422 `VALIDATION_ERROR` / `FIELD_INVALID`: Schema violation, unknown field, float money, missing Idempotency-Key (IDEMPOTENCY_KEY_REQUIRED)
  - 409 `CONFLICT` / `IDEMPOTENCY_KEY_REUSED`: Same key sent with a different request body
  - 404 `NOT_FOUND`: Unknown account or ownership failure (identical body for both)
  - 422 `BUSINESS_RULE_VIOLATION` / `ZERO_AMOUNT|NEGATIVE_AMOUNT|OVER_PRECISION|OVER_BALANCE`: Amount validation
  - 503 `AUDIT_UNAVAILABLE`: Audit write failed; transition rolled back
- **Behaviour:** Uses the same PaymentService as chat confirmation. simulated is always true.

#### POST /api/demo-controls/reseed
Restore the seeded dataset (audit rows are never deleted).

- **Stories / slice:** E9-S3, E1-S3 / Slice 1
- **Personas:** COLLECTIONS_OFFICER (capability `demo_controls:use`)
- **Headers:** `X-Persona`
- **Body:** `ReseedRequest` (section 4)
- **Success:** 200 `ReseedResult`
- **Rate limit:** default: API_RATE_LIMIT_PER_MINUTE (300) per session
- **Errors:**
  - 404 `NOT_FOUND`: DEMO_CONTROLS_ENABLED=false: every /api/demo-controls route answers 404 before persona checks
  - 422 `VALIDATION_ERROR` / `FIELD_INVALID`: Schema violation, unknown field, float money, missing Idempotency-Key (IDEMPOTENCY_KEY_REQUIRED)
  - 503 `AUDIT_UNAVAILABLE`: Audit write failed; transition rolled back
- **Behaviour:** Deletes and reloads business tables inside one transaction; writes DEMO_RESEED. Seed ids are deterministic so earlier audit events still resolve.

## 4. Schemas

Type notation: `?` after the type means the key is always present but may be null; `optional` means the key may be omitted. Enumerations are in section 5.

### ErrorDetail
One field-level or rule-level problem.

| Field | Type | Required | Description |
|---|---|---|---|
| `field` | string or null | yes | Dotted request field path, null for non-field problems |
| `reason_code` | string | yes | Stable machine reason code |
| `message` | string | yes | Human-readable, safe (no secrets, no other customer's data) |

### ErrorBody
Error content. code is the coarse category, reason_code the precise deterministic reason.

| Field | Type | Required | Description |
|---|---|---|---|
| `code` | enum ErrorCode | yes | Category, one of the ErrorCode values |
| `reason_code` | string or null | yes | Precise reason (for example OVER_BALANCE, STALE_DATA); null when the category is sufficient |
| `message` | string | yes | Human-readable, safe message |
| `correlation_id` | string | yes | Same value as the X-Correlation-Id response header |
| `details` | ErrorDetail[] | yes | Zero or more details; multiple violations are all listed, primary reason_code is the first by fixed precedence |
| `alternatives` | object or null | yes | Deterministic valid alternatives (for example valid amount and date ranges) when a rule rejects input |
| `context` | object or null | yes | Error-specific context: refreshed_context, current_version, escalation_case_id, permitted_paths, retry_after_seconds |
| `policy_version` | string or null | yes | PolicyRuleSet version used, when a rule decision was involved |

### ErrorEnvelope
Every non-2xx response body.

| Field | Type | Required | Description |
|---|---|---|---|
| `error` | ErrorBody | yes | Error content |

### PageInfo
Offset pagination block.

| Field | Type | Required | Description |
|---|---|---|---|
| `limit` | integer | yes | Page size used |
| `offset` | integer | yes | Offset used |
| `total` | integer | yes | Total matching rows |

### HealthStatus
Liveness.

| Field | Type | Required | Description |
|---|---|---|---|
| `status` | string | yes | Always ok when the process is up |

### ReadyCheck
One readiness check.

| Field | Type | Required | Description |
|---|---|---|---|
| `name` | string | yes | database, migrations, policy_ruleset, audit_role_grants |
| `ok` | boolean | yes | Check result |
| `detail` | string or null | yes | Safe detail |

### ReadyStatus
Readiness (503 with same body when not ready).

| Field | Type | Required | Description |
|---|---|---|---|
| `status` | string | yes | ready or not_ready |
| `checks` | ReadyCheck[] | yes | Individual checks |

### ClockInfo
Injected Clock reading.

| Field | Type | Required | Description |
|---|---|---|---|
| `now` | timestamp | yes | Clock.now() in UTC |
| `mode` | enum ClockMode | yes | SYSTEM, or SIMULATED when demo controls have set the clock |

### MetaInfo
Non-sensitive runtime info for badges and banners.

| Field | Type | Required | Description |
|---|---|---|---|
| `app_version` | string | yes | Application version |
| `llm_mode` | enum LlmMode | yes | MOCK or LIVE |
| `policy_version` | string or null | yes | Active PolicyRuleSet version, null if none valid |
| `demo_controls_enabled` | boolean | yes | DEMO_CONTROLS_ENABLED |
| `clock` | ClockInfo | yes | Current clock |
| `simulated_payments_notice` | string | yes | Fixed text: payments are simulated, no real payment occurs |

### PersonaOption
A persona offered by the switcher.

| Field | Type | Required | Description |
|---|---|---|---|
| `persona` | enum Persona | yes | Persona |
| `display_name` | string | yes | Label |
| `description` | string | yes | One-line description |
| `requires_customer_binding` | boolean | yes | True for CUSTOMER |

### DemoCustomer
A seeded synthetic customer selectable for the CUSTOMER persona.

| Field | Type | Required | Description |
|---|---|---|---|
| `customer_id` | id | yes | cus_ id |
| `display_name` | string | yes | Synthetic name |
| `account_count` | integer | yes | Number of accounts |

### SessionOptionsResponse
Switcher content.

| Field | Type | Required | Description |
|---|---|---|---|
| `personas` | PersonaOption[] | yes | Exactly the four personas |
| `demo_customers` | DemoCustomer[] | yes | First 25 seeded customers with delinquent accounts |

### SessionCreateRequest
Select a persona (demo, not authentication). Unknown fields are rejected.

| Field | Type | Required | Description |
|---|---|---|---|
| `persona` | enum Persona | yes | Persona to act as |
| `customer_id` | id | optional | Required iff persona is CUSTOMER; must be a seeded customer; forbidden otherwise |

### SessionInfo
Current persona session.

| Field | Type | Required | Description |
|---|---|---|---|
| `persona` | enum Persona | yes | Active persona |
| `customer_id` | id or null | yes | Bound customer (CUSTOMER only) |
| `display_name` | string | yes | Persona or customer display name |
| `capabilities` | string[] | yes | Capability strings granted to this persona, drives navigation |
| `demo_label` | string | yes | Fixed: Demo persona - not real authentication |
| `session_token` | string | optional | Opaque token, returned only by POST /api/session; send as X-Demo-Session |
| `issued_at` | timestamp | yes | Issue time from Clock |

### Factor
One contributing factor of the deterministic priority score.

| Field | Type | Required | Description |
|---|---|---|---|
| `factor_id` | string | yes | dpd, overdue_amount, broken_ptp_count or recent_contact_outcome |
| `attribute` | string | yes | Input attribute name |
| `value` | string | yes | Input value as string (Decimal, integer or enum name) |
| `normalized_value` | decimal string | yes | Value after normalization, 0 to 1, 4 decimal places |
| `weight` | decimal string | yes | Policy weight |
| `contribution` | decimal string | yes | Weighted contribution, 2 decimal places; contributions sum exactly to the score |

### PriorityResult
Deterministic Collections Priority.

| Field | Type | Required | Description |
|---|---|---|---|
| `score` | decimal string | yes | Sum of contributions, 2 decimal places |
| `band` | enum PriorityBand | yes | LOW, MEDIUM or HIGH |
| `factors` | Factor[] | yes | Ordered by contribution descending then factor_id |
| `policy_version` | string | yes | PolicyRuleSet version |

### PortfolioItem
One delinquent account row.

| Field | Type | Required | Description |
|---|---|---|---|
| `account_id` | id | yes | acc_ id |
| `customer_id` | id | yes | cus_ id |
| `customer_name` | string | yes | Synthetic name |
| `account_type` | enum AccountType | yes | CARD or PERSONAL_LOAN |
| `outstanding_balance` | money string | yes | Total balance |
| `overdue_amount` | money string | yes | Overdue amount |
| `dpd` | integer | yes | Days past due |
| `bucket` | enum Bucket | yes | Delinquency bucket |
| `collection_status` | enum CollectionStatus | yes | Collection status |
| `priority_band` | enum PriorityBand | yes | Deterministic band |
| `priority_score` | decimal string | yes | Deterministic score |
| `human_treatment` | boolean | yes | True when dispute, hardship, vulnerable flag or open escalation applies |
| `automated_treatment_suppressed` | boolean | yes | True when automated treatment is suppressed |
| `record_version` | integer | yes | DelinquencyRecord version |

### PortfolioPage
Portfolio list.

| Field | Type | Required | Description |
|---|---|---|---|
| `items` | PortfolioItem[] | yes | Rows |
| `page` | PageInfo | yes | Pagination |
| `policy_version` | string | yes | PolicyRuleSet version used for priority |

### SnapshotInfo
Snapshot stamp and freshness.

| Field | Type | Required | Description |
|---|---|---|---|
| `as_of` | timestamp or null | yes | Snapshot as-of time (null means freshness UNKNOWN) |
| `record_version` | integer | yes | Current DelinquencyRecord version |
| `freshness` | enum Freshness | yes | FRESH, STALE or UNKNOWN |
| `freshness_reason_code` | string or null | yes | STALE_DATA, VERSION_MISMATCH, MISSING_AS_OF or null |
| `max_age_minutes` | integer | yes | freshness.max_snapshot_age_minutes |

### ProfileBlock
Synthetic customer profile.

| Field | Type | Required | Description |
|---|---|---|---|
| `customer_id` | id | yes | cus_ id |
| `display_name` | string | yes | Synthetic name |
| `email` | string | yes | Reserved domain example.com only |
| `phone` | string | yes | Fictional range +1-555-01xx only |
| `vulnerability_flag` | boolean | yes | Set by a VULNERABLE_CUSTOMER case until a human decision releases it |
| `vulnerability_category` | enum VulnerabilityCategory or null | yes | Category when flagged |

### AccountBlock
Account and delinquency facts (deterministic data).

| Field | Type | Required | Description |
|---|---|---|---|
| `account_id` | id | yes | acc_ id |
| `account_type` | enum AccountType | yes | CARD or PERSONAL_LOAN |
| `product_name` | string | yes | Synthetic product name |
| `currency` | string | yes | Always USD |
| `opened_on` | date | yes | Open date |
| `outstanding_balance` | money string | yes | Total balance |
| `overdue_amount` | money string | yes | Overdue amount |
| `undisputed_overdue_amount` | money string | yes | Overdue amount excluding items under active dispute |
| `dpd` | integer | yes | Days past due |
| `bucket` | enum Bucket | yes | Delinquency bucket |
| `collection_status` | enum CollectionStatus | yes | Status |
| `product_attributes` | object | yes | CARD: credit_limit, minimum_payment_due. PERSONAL_LOAN: original_principal, term_months, monthly_installment (money strings) |

### DelinquentItem
An overdue component that can be disputed.

| Field | Type | Required | Description |
|---|---|---|---|
| `item_id` | id | yes | itm_ id |
| `kind` | enum ItemKind | yes | INSTALLMENT, STATEMENT_CYCLE or FEE_OR_CHARGE |
| `label` | string | yes | Synthetic label |
| `amount_outstanding` | money string | yes | Outstanding amount |
| `due_date` | date | yes | Original due date |
| `status` | enum ItemStatus | yes | OPEN or PAID |
| `disputed` | boolean | yes | True while an unresolved dispute references it |

### SuppressionEntry
Why treatment is suppressed.

| Field | Type | Required | Description |
|---|---|---|---|
| `source_type` | enum SuppressionSource | yes | ESCALATION, HARDSHIP, DISPUTE or VULNERABLE |
| `source_id` | id | yes | Case, hardship, dispute id or customer id |
| `scope` | enum SuppressionScope | yes | ITEM or ACCOUNT |
| `item_id` | id or null | yes | Item when scope is ITEM |

### TreatmentBlock
Treatment suppression state.

| Field | Type | Required | Description |
|---|---|---|---|
| `human_treatment` | boolean | yes | Human treatment indicated |
| `automated_treatment_suppressed` | boolean | yes | Automated treatment suppressed (account level or item level) |
| `suppressions` | SuppressionEntry[] | yes | Active suppressions |

### ContactPolicyResult
Contact-frequency policy result.

| Field | Type | Required | Description |
|---|---|---|---|
| `contact_allowed` | boolean | yes | Whether another contact attempt is allowed now |
| `reason_code` | string or null | yes | MAX_ATTEMPTS, MIN_INTERVAL or null |
| `next_allowed_at` | timestamp or null | yes | Earliest allowed time when known |
| `attempts_in_period` | integer | yes | Attempts in contact.period_days |

### PayableOption
A payable amount returned by the deterministic service.

| Field | Type | Required | Description |
|---|---|---|---|
| `option` | enum PayableOptionType | yes | OVERDUE_AMOUNT or FULL_BALANCE |
| `amount` | money string | yes | Payable amount |

### RecordCheck
Internal-consistency check result.

| Field | Type | Required | Description |
|---|---|---|---|
| `consistent` | boolean | yes | False when the record is inconsistent |
| `reason_code` | string or null | yes | INCONSISTENT_RECORD or null |

### DeterministicBlock
All rules-engine output, labelled Rules engine in the UI.

| Field | Type | Required | Description |
|---|---|---|---|
| `source` | string | yes | Constant deterministic |
| `label` | string | yes | Constant Rules engine |
| `policy_version` | string or null | yes | Policy version, null when POLICY_UNAVAILABLE |
| `status` | string | yes | OK or POLICY_UNAVAILABLE (priority is then null, no eligibility granted) |
| `priority` | PriorityResult or null | yes | Score, band, factors |
| `treatment` | TreatmentBlock | yes | Suppression state |
| `contact_policy` | ContactPolicyResult or null | yes | Contact policy |
| `payable_options` | PayableOption[] | yes | Empty when suppressed |
| `record_check` | RecordCheck | yes | Consistency |

### Recommendation
AI next-best-action, labelled AI-generated in the UI.

| Field | Type | Required | Description |
|---|---|---|---|
| `recommendation_id` | id | yes | rec_ id |
| `account_id` | id | yes | acc_ id |
| `source` | string | yes | Constant ai |
| `action` | enum NbaAction | yes | Allowed action |
| `rationale` | string | yes | Rationale text, grounded (figures only from services) |
| `referenced_factor_ids` | string[] | yes | Factor ids the rationale relies on |
| `status` | enum RecommendationStatus | yes | GENERATED, SAFE_FALLBACK, HUMAN_REVIEW_ONLY, AI_UNAVAILABLE or NOT_GENERATED |
| `content_source` | enum ContentSource | yes | MODEL or TEMPLATE |
| `model_id` | string or null | yes | Model identifier (null for TEMPLATE-only) |
| `prompt_version` | string or null | yes | Prompt template version |
| `policy_version` | string | yes | PolicyRuleSet version |
| `record_version` | integer | yes | Record version the recommendation was generated against |
| `created_at` | timestamp | yes | Clock time |
| `audit_event_id` | id | yes | Audit event id |
| `officer_decision` | enum RecommendationDecision or null | yes | ACCEPTED or OVERRIDDEN once an officer decided |

### AiBlock
AI-generated content.

| Field | Type | Required | Description |
|---|---|---|---|
| `source` | string | yes | Constant ai |
| `label` | string | yes | Constant AI-generated |
| `status` | enum RecommendationStatus | yes | Latest status; AI_UNAVAILABLE shows the manual-workflow banner |
| `recommendation` | Recommendation or null | yes | Latest stored recommendation or null |

### Interaction
A previous interaction (synthetic).

| Field | Type | Required | Description |
|---|---|---|---|
| `interaction_id` | id | yes | int_ id |
| `channel` | enum InteractionChannel | yes | Channel |
| `direction` | enum InteractionDirection | yes | Direction |
| `outcome` | enum ContactOutcome or null | yes | Contact outcome |
| `occurred_at` | timestamp | yes | Time |
| `summary` | string | yes | Synthetic summary |
| `counts_as_attempt` | boolean | yes | Counts toward contact frequency |
| `conversation_id` | id or null | yes | Linked conversation |

### PromiseToPay
Promise-to-Pay record.

| Field | Type | Required | Description |
|---|---|---|---|
| `ptp_id` | id | yes | ptp_ id |
| `account_id` | id | yes | acc_ id |
| `promised_amount` | money string | yes | Promised amount |
| `promised_date` | date | yes | Promised payment date |
| `status` | enum PtpStatus | yes | PENDING, KEPT, BROKEN, CANCELLED |
| `cumulative_paid` | money string | yes | Qualifying successful simulated payments counted so far |
| `remaining_amount` | money string | yes | promised_amount minus cumulative_paid, min 0.00 |
| `interaction_reference` | id or null | yes | int_ or conv_ reference |
| `source` | enum PtpSource | yes | OFFICER_MANUAL or CUSTOMER_CHAT |
| `created_by_persona` | enum Persona | yes | Persona that recorded it |
| `created_at` | timestamp | yes | Creation time |
| `updated_at` | timestamp | yes | Last update |
| `kept_at` | timestamp or null | yes | When KEPT |
| `broken_at` | timestamp or null | yes | When BROKEN |
| `cancelled_at` | timestamp or null | yes | When CANCELLED |
| `cancel_reason` | string or null | yes | Reason for cancellation |
| `policy_version` | string | yes | PolicyRuleSet version at creation |
| `version` | integer | yes | Row version |

### PaymentEvent
Simulated payment outcome. No real payment ever occurs.

| Field | Type | Required | Description |
|---|---|---|---|
| `payment_event_id` | id | yes | pay_ id |
| `account_id` | id | yes | acc_ id |
| `amount` | money string | yes | Amount |
| `outcome` | enum PaymentOutcome | yes | SUCCEEDED or FAILED |
| `source` | enum PaymentSource | yes | CUSTOMER_CHAT or DEMO_CONTROL |
| `simulated` | boolean | yes | Always true |
| `simulated_label` | string | yes | Constant Simulated payment |
| `occurred_at` | timestamp | yes | Clock time |
| `balance_after` | money string | yes | Outstanding balance after event |
| `applied_to_ptp_id` | id or null | yes | PTP counted toward, if any |

### ScheduleEntry
One installment.

| Field | Type | Required | Description |
|---|---|---|---|
| `sequence` | integer | yes | 1-based |
| `due_date` | date | yes | Due date |
| `amount` | money string | yes | Installment amount |

### ArrangementOption
An eligible arrangement option computed by the rules engine.

| Field | Type | Required | Description |
|---|---|---|---|
| `option_id` | string | yes | Deterministic id opt-{installment_count}-{first_installment_date} |
| `installment_count` | integer | yes | Number of installments |
| `installment_amount` | money string | yes | Regular installment |
| `final_installment_amount` | money string | yes | Last installment absorbing remainder; schedule sums exactly to total_amount |
| `total_amount` | money string | yes | Arranged amount |
| `first_installment_date` | date | yes | First due date |
| `frequency` | string | yes | Constant MONTHLY |
| `schedule` | ScheduleEntry[] | yes | Full schedule |

### PaymentArrangement
Payment arrangement.

| Field | Type | Required | Description |
|---|---|---|---|
| `arrangement_id` | id | yes | arr_ id |
| `account_id` | id | yes | acc_ id |
| `status` | enum ArrangementStatus | yes | ACTIVE, COMPLETED or CANCELLED |
| `option` | ArrangementOption | yes | Terms |
| `created_via` | enum ArrangementCreatedVia | yes | CUSTOMER_CONFIRMATION or EXCEPTION_APPROVAL |
| `exception_case_id` | id or null | yes | Case that approved the exception |
| `policy_version` | string | yes | Policy version |
| `created_at` | timestamp | yes | Creation time |

### HardshipIndicator
One structured indicator.

| Field | Type | Required | Description |
|---|---|---|---|
| `indicator_type` | enum HardshipIndicatorType | yes | Type |
| `customer_statement` | string | yes | Redacted customer statement excerpt, max 500 chars |

### HardshipCase
Hardship record (officer view).

| Field | Type | Required | Description |
|---|---|---|---|
| `hardship_case_id` | id | yes | hsp_ id |
| `account_id` | id | yes | acc_ id |
| `customer_id` | id | yes | cus_ id |
| `conversation_id` | id or null | yes | Source conversation |
| `status` | enum HardshipStatus | yes | OPEN, UNDER_REVIEW, DECIDED |
| `indicators` | HardshipIndicator[] | yes | Structured indicators |
| `escalation_case_id` | id or null | yes | Linked case |
| `created_at` | timestamp | yes | Creation |
| `decided_at` | timestamp or null | yes | Decision time |

### Dispute
Dispute record (officer view).

| Field | Type | Required | Description |
|---|---|---|---|
| `dispute_id` | id | yes | dsp_ id |
| `account_id` | id | yes | acc_ id |
| `customer_id` | id | yes | cus_ id |
| `item_id` | id or null | yes | Disputed item; null means whole overdue amount |
| `category` | enum DisputeCategory | yes | Category |
| `customer_reason` | string | yes | Redacted customer-provided reason, max 1000 chars |
| `status` | enum DisputeStatus | yes | OPEN, UNDER_REVIEW, RESOLVED |
| `outcome` | enum DisputeOutcome or null | yes | Set when RESOLVED |
| `resolution_reason` | string or null | yes | Reviewer reason |
| `conversation_id` | id or null | yes | Source conversation |
| `escalation_case_id` | id or null | yes | Linked case |
| `created_at` | timestamp | yes | Creation |
| `resolved_at` | timestamp or null | yes | Resolution time |
| `version` | integer | yes | Row version |

### EscalationSummary
Escalation reference for Customer 360.

| Field | Type | Required | Description |
|---|---|---|---|
| `case_id` | id | yes | esc_ id |
| `reason` | enum EscalationReason | yes | Reason |
| `status` | enum CaseStatus | yes | Status |
| `priority` | enum EscalationPriority | yes | Priority |
| `queue` | enum ReviewQueue | yes | Queue |
| `created_at` | timestamp | yes | Creation |

### EscalationBlock
Escalation status on Customer 360.

| Field | Type | Required | Description |
|---|---|---|---|
| `badge` | string or null | yes | Escalated - human review when any case is OPEN, IN_REVIEW or AWAITING_INFORMATION, else null |
| `has_open_case` | boolean | yes | Open case exists |
| `cases` | EscalationSummary[] | yes | Cases, newest first, max 10 |

### Customer360
Consolidated read model.

| Field | Type | Required | Description |
|---|---|---|---|
| `account_id` | id | yes | acc_ id |
| `generated_at` | timestamp | yes | Clock time |
| `snapshot` | SnapshotInfo | yes | Freshness |
| `profile` | ProfileBlock | yes | Profile |
| `account` | AccountBlock | yes | Account |
| `items` | DelinquentItem[] | yes | Delinquent items |
| `deterministic` | DeterministicBlock | yes | Rules-engine data |
| `ai` | AiBlock | yes | AI-generated data |
| `interactions` | Interaction[] | yes | Latest 20 |
| `ptp_history` | PromiseToPay[] | yes | All PTPs, newest first |
| `payment_events` | PaymentEvent[] | yes | Latest 20 simulated payments |
| `arrangements` | PaymentArrangement[] | yes | Arrangements (Slice 2) |
| `hardship_cases` | HardshipCase[] | yes | Hardship (Slice 2) |
| `disputes` | Dispute[] | yes | Disputes (Slice 3) |
| `escalation` | EscalationBlock | yes | Escalation status |

### RecommendationResult
Result of generating a recommendation.

| Field | Type | Required | Description |
|---|---|---|---|
| `status` | enum RecommendationStatus | yes | Outcome status |
| `recommendation` | Recommendation or null | yes | Null when AI_UNAVAILABLE |

### RecommendationDecisionRequest
Officer accepts or overrides an AI recommendation. Unknown fields are rejected.

| Field | Type | Required | Description |
|---|---|---|---|
| `decision` | enum RecommendationDecision | yes | ACCEPTED or OVERRIDDEN |
| `reason` | string | optional | Mandatory (1-1000 chars) when OVERRIDDEN |
| `chosen_action` | enum NbaAction | optional | Officer's own action when OVERRIDDEN |

### PtpValidateRequest
Dry-run PTP validation. Unknown fields are rejected.

| Field | Type | Required | Description |
|---|---|---|---|
| `account_id` | id | yes | acc_ id |
| `promised_amount` | decimal string (input) | yes | Decimal string |
| `promised_date` | date | yes | YYYY-MM-DD |

### PtpValidationResult
Deterministic validation result.

| Field | Type | Required | Description |
|---|---|---|---|
| `valid` | boolean | yes | True when creation would pass validation |
| `reason_codes` | string[] | yes | ZERO_AMOUNT, NEGATIVE_AMOUNT, OVER_BALANCE, OVER_PRECISION, BELOW_MIN_AMOUNT, PAST_DATE, OUTSIDE_WINDOW, CONFLICTING_ACTIVE_ITEM, DISPUTED_ITEM |
| `alternatives` | object or null | yes | valid_amount_range {min,max}, valid_date_range {earliest,latest} |
| `policy_version` | string | yes | Policy version |

### PtpCreateRequest
Officer manual PTP (D-040). Unknown fields are rejected.

| Field | Type | Required | Description |
|---|---|---|---|
| `account_id` | id | yes | acc_ id |
| `promised_amount` | decimal string (input) | yes | Decimal string, at most 2 dp, positive |
| `promised_date` | date | yes | Between today and today plus ptp.window_days |
| `interaction_reference` | id | optional | int_ or conv_ id belonging to the account |
| `item_id` | id | optional | Optional disputed-item check |
| `record_version` | integer | yes | record_version from the Customer 360 snapshot the officer saw |
| `snapshot_as_of` | timestamp | yes | as_of from that snapshot |

### CancelRequest
Cancel with reason. Unknown fields are rejected.

| Field | Type | Required | Description |
|---|---|---|---|
| `reason` | string | yes | 1-500 chars |

### ConversationCreateRequest
Start a conversation on one of the customer's own accounts. Unknown fields are rejected.

| Field | Type | Required | Description |
|---|---|---|---|
| `account_id` | id | yes | Must belong to the bound customer, else 404 |

### ChatMessage
One message.

| Field | Type | Required | Description |
|---|---|---|---|
| `message_id` | id | yes | msg_ id |
| `conversation_id` | id | yes | conv_ id |
| `role` | enum MessageRole | yes | CUSTOMER, ASSISTANT or SYSTEM |
| `content` | string | yes | Text; assistant text is grounded or templated |
| `content_source` | enum ContentSource | yes | CUSTOMER_INPUT, MODEL or TEMPLATE |
| `labels` | enum MessageLabel[] | yes | AI_DISCLOSURE, SIMULATED, HUMAN_HANDOFF, SAFE_FALLBACK |
| `created_at` | timestamp | yes | Clock time |

### PtpTerms
Terms of a PTP proposal (service-validated).

| Field | Type | Required | Description |
|---|---|---|---|
| `kind` | string | yes | Constant PTP |
| `promised_amount` | money string | yes | Validated amount |
| `promised_date` | date | yes | Validated date |

### PaymentTerms
Terms of a simulated payment proposal.

| Field | Type | Required | Description |
|---|---|---|---|
| `kind` | string | yes | Constant PAYMENT |
| `payment_option` | enum PayableOptionType | yes | Option |
| `payment_amount` | money string | yes | Amount from payable-amounts service |
| `simulated` | boolean | yes | Always true |
| `simulated_label` | string | yes | Constant Simulated payment - no real money moves |

### ArrangementTerms
Terms of an arrangement proposal.

| Field | Type | Required | Description |
|---|---|---|---|
| `kind` | string | yes | Constant ARRANGEMENT |
| `option` | ArrangementOption | yes | Eligible option |

### RequestedTerms
Customer-requested arrangement terms.

| Field | Type | Required | Description |
|---|---|---|---|
| `installment_count` | integer | yes | Requested count |
| `first_installment_date` | date | yes | Requested first date |
| `installment_amount` | money string or null | yes | Requested amount if stated |

### ExceptionRequestTerms
Terms of an exceptional-arrangement request submission.

| Field | Type | Required | Description |
|---|---|---|---|
| `kind` | string | yes | Constant EXCEPTION_REQUEST |
| `requested_terms` | RequestedTerms | yes | Terms exactly as requested |
| `exception_types` | enum ExceptionType[] | yes | Deterministic classification |
| `notice` | string | yes | Constant: This request needs human review and is not approved |

### Proposal
A deterministic, customer-visible proposal awaiting explicit confirmation (D-041).

| Field | Type | Required | Description |
|---|---|---|---|
| `proposal_id` | id | yes | prp_ id |
| `conversation_id` | id | yes | conv_ id |
| `kind` | enum ProposalKind | yes | PTP, PAYMENT, ARRANGEMENT or EXCEPTION_REQUEST |
| `status` | enum ProposalStatus | yes | Lifecycle status |
| `terms` | object | yes | One of PtpTerms, PaymentTerms, ArrangementTerms, ExceptionRequestTerms discriminated by kind |
| `terms_hash` | string | yes | sha256 hex of canonical terms; echoed in the confirm request |
| `summary` | string | yes | Templated summary built from service output |
| `simulated` | boolean | yes | True for PAYMENT |
| `record_version` | integer | yes | Record version the proposal is valid for |
| `created_at` | timestamp | yes | Creation |
| `expires_at` | timestamp | yes | Clock time after which it is EXPIRED |

### EscalationCustomerView
Customer-safe escalation view.

| Field | Type | Required | Description |
|---|---|---|---|
| `case_id` | id | yes | esc_ id |
| `account_id` | id | yes | acc_ id |
| `status` | enum CaseStatus | yes | Status |
| `customer_message` | string | yes | Templated respectful message |
| `created_at` | timestamp | yes | Creation |
| `decided_at` | timestamp or null | yes | Decision time |

### IntentSummary
Advisory interpretation summary (never authoritative).

| Field | Type | Required | Description |
|---|---|---|---|
| `label` | enum Intent | yes | Seven-value intent |
| `confidence` | decimal string | yes | 0 to 1 |
| `vulnerability_detected` | boolean | yes | Advisory safety signal |
| `special_request` | enum SpecialRequest | yes | NONE, SETTLEMENT or POLICY_EXCEPTION |

### MessageCreateRequest
Customer message. Unknown fields are rejected.

| Field | Type | Required | Description |
|---|---|---|---|
| `content` | string | yes | 1-2000 chars, plain text |

### ChatTurnResponse
Whole-message response for one turn (no streaming).

| Field | Type | Required | Description |
|---|---|---|---|
| `conversation_id` | id | yes | conv_ id |
| `turn_id` | id | yes | trn_ id |
| `customer_message` | ChatMessage | yes | Stored customer message |
| `assistant_message` | ChatMessage | yes | Assistant reply |
| `intent` | IntentSummary or null | yes | Null when the provider failed |
| `proposal` | Proposal or null | yes | Pending proposal needing Confirm/Cancel |
| `handoff` | EscalationCustomerView or null | yes | Present when a human handoff exists |
| `safe_state` | enum SafeState | yes | NONE unless a fail-closed state applies |
| `talk_to_human_available` | boolean | yes | Always true |
| `correlation_id` | string | yes | Turn correlation id |

### Conversation
Conversation header.

| Field | Type | Required | Description |
|---|---|---|---|
| `conversation_id` | id | yes | conv_ id |
| `account_id` | id | yes | acc_ id |
| `status` | enum ConversationStatus | yes | Status |
| `created_at` | timestamp | yes | Creation |
| `last_message_at` | timestamp or null | yes | Last message |

### ConversationDetail
Conversation with messages.

| Field | Type | Required | Description |
|---|---|---|---|
| `conversation` | Conversation | yes | Header |
| `messages` | ChatMessage[] | yes | Chronological |
| `pending_proposal` | Proposal or null | yes | Current PENDING_CONFIRMATION proposal |
| `handoff` | EscalationCustomerView or null | yes | Open handoff |

### ConversationCreateResult
New conversation with AI disclosure greeting.

| Field | Type | Required | Description |
|---|---|---|---|
| `conversation` | Conversation | yes | Header |
| `greeting` | ChatMessage | yes | First assistant message, labels include AI_DISCLOSURE |
| `talk_to_human_available` | boolean | yes | Always true |

### ConversationPage
Own conversations.

| Field | Type | Required | Description |
|---|---|---|---|
| `items` | Conversation[] | yes | Rows |
| `page` | PageInfo | yes | Pagination |

### ConfirmRequest
Explicit customer confirmation of a displayed proposal. Unknown fields are rejected.

| Field | Type | Required | Description |
|---|---|---|---|
| `terms_hash` | string | yes | terms_hash of the proposal as displayed; mismatch gives PROPOSAL_INVALID |

### ConfirmOutcome
What the domain service created (exactly one non-null).

| Field | Type | Required | Description |
|---|---|---|---|
| `kind` | enum ProposalKind | yes | Proposal kind |
| `ptp` | PromiseToPay or null | yes | Created PTP |
| `payment_event` | PaymentEvent or null | yes | Recorded simulated payment |
| `arrangement` | PaymentArrangement or null | yes | Created arrangement |
| `escalation` | EscalationCustomerView or null | yes | Created review case |

### ConfirmResult
Result of confirm.

| Field | Type | Required | Description |
|---|---|---|---|
| `proposal` | Proposal or null | yes | Proposal after confirmation |
| `outcome` | ConfirmOutcome | yes | Created record |
| `assistant_message` | ChatMessage | yes | Templated confirmation; contains the word simulated for payments |
| `replayed` | boolean | yes | True when an idempotent replay |

### CancelProposalResult
Result of cancelling a proposal.

| Field | Type | Required | Description |
|---|---|---|---|
| `proposal` | Proposal | yes | Proposal, status CANCELLED |
| `assistant_message` | ChatMessage | yes | Acknowledgement |

### HandoffRequest
Talk to a human. Unknown fields are rejected.

| Field | Type | Required | Description |
|---|---|---|---|
| `note` | string | optional | Optional customer note, max 500 chars |

### HandoffResult
Handoff created (or existing case returned).

| Field | Type | Required | Description |
|---|---|---|---|
| `escalation` | EscalationCustomerView | yes | Case |
| `assistant_message` | ChatMessage | yes | Message that a human colleague will follow up |
| `replayed` | boolean | yes | True when an existing OPEN case was returned |

### CustomerAccountSummary
Customer-safe account summary.

| Field | Type | Required | Description |
|---|---|---|---|
| `account_id` | id | yes | acc_ id |
| `account_type` | enum AccountType | yes | Type |
| `product_name` | string | yes | Synthetic product |
| `currency` | string | yes | USD |
| `outstanding_balance` | money string | yes | Balance |
| `overdue_amount` | money string | yes | Overdue |
| `collection_status` | enum CollectionStatus | yes | Status |

### CustomerAccountPage
Own accounts.

| Field | Type | Required | Description |
|---|---|---|---|
| `items` | CustomerAccountSummary[] | yes | Rows |
| `page` | PageInfo | yes | Pagination |

### PtpPage
PTP list.

| Field | Type | Required | Description |
|---|---|---|---|
| `items` | PromiseToPay[] | yes | Rows |
| `page` | PageInfo | yes | Pagination |

### PaymentEventPage
Payment event list.

| Field | Type | Required | Description |
|---|---|---|---|
| `items` | PaymentEvent[] | yes | Rows |
| `page` | PageInfo | yes | Pagination |

### ArrangementPage
Arrangement list.

| Field | Type | Required | Description |
|---|---|---|---|
| `items` | PaymentArrangement[] | yes | Rows |
| `page` | PageInfo | yes | Pagination |

### EscalationCustomerPage
Own escalation cases.

| Field | Type | Required | Description |
|---|---|---|---|
| `items` | EscalationCustomerView[] | yes | Rows |
| `page` | PageInfo | yes | Pagination |

### HardshipCustomerView
Customer-safe hardship record.

| Field | Type | Required | Description |
|---|---|---|---|
| `hardship_case_id` | id | yes | hsp_ id |
| `status` | enum HardshipStatus | yes | Status |
| `indicator_types` | enum HardshipIndicatorType[] | yes | Recorded indicators |
| `created_at` | timestamp | yes | Creation |

### DisputeCustomerView
Customer-safe dispute record.

| Field | Type | Required | Description |
|---|---|---|---|
| `dispute_id` | id | yes | dsp_ id |
| `item_id` | id or null | yes | Item |
| `category` | enum DisputeCategory | yes | Category |
| `status` | enum DisputeStatus | yes | Status |
| `outcome` | enum DisputeOutcome or null | yes | Outcome when resolved |
| `created_at` | timestamp | yes | Creation |
| `resolved_at` | timestamp or null | yes | Resolution time |

### EscalationListItem
Row of the escalation list / review queue.

| Field | Type | Required | Description |
|---|---|---|---|
| `case_id` | id | yes | esc_ id |
| `reason` | enum EscalationReason | yes | Reason |
| `queue` | enum ReviewQueue | yes | Queue |
| `reviewer_role` | enum ReviewerRole | yes | Reviewer role |
| `priority` | enum EscalationPriority | yes | Priority |
| `status` | enum CaseStatus | yes | Status |
| `source` | enum CaseSource | yes | AI, CUSTOMER, SYSTEM or REVIEWER |
| `created_at` | timestamp | yes | Creation |
| `age_hours` | integer | yes | Whole hours since creation by Clock |
| `aging_warning` | boolean | yes | age_hours >= routing.aging_warning_hours[priority] |
| `customer_id` | id | yes | cus_ id |
| `customer_name` | string | yes | Synthetic name |
| `account_id` | id | yes | acc_ id |
| `customer_360_path` | string | yes | /customers/{account_id} |
| `version` | integer | yes | Case version for optimistic checks |

### EscalationPage
Escalation list.

| Field | Type | Required | Description |
|---|---|---|---|
| `items` | EscalationListItem[] | yes | Sorted by priority (URGENT first) then age (oldest first) |
| `page` | PageInfo | yes | Pagination |
| `policy_version` | string or null | yes | Policy version used for aging thresholds |

### QueueSummary
Per-queue counts.

| Field | Type | Required | Description |
|---|---|---|---|
| `queue` | enum ReviewQueue | yes | Queue |
| `open_count` | integer | yes | OPEN |
| `in_review_count` | integer | yes | IN_REVIEW |
| `awaiting_information_count` | integer | yes | AWAITING_INFORMATION |
| `oldest_age_hours` | integer or null | yes | Oldest active case |
| `aging_warning_count` | integer | yes | Cases past aging warning |

### EscalationSummaryResponse
Queue summary.

| Field | Type | Required | Description |
|---|---|---|---|
| `queues` | QueueSummary[] | yes | One entry per queue visible to the persona |
| `policy_version` | string or null | yes | Policy version |

### ExceptionAuthority
Whether the officer may approve an exception.

| Field | Type | Required | Description |
|---|---|---|---|
| `approve_permitted` | boolean | yes | APPROVE available |
| `denied_reason_code` | string or null | yes | NOT_PERMITTED_BY_POLICY, EXCEPTION_TYPE_NOT_PERMITTED, EXCEEDS_THRESHOLD, EXCEEDS_MAX_OVERDUE_AMOUNT |
| `permitted_types` | enum ExceptionType[] | yes | Types the officer may approve |
| `max_overdue_amount` | money string | yes | Authority ceiling |

### EligibilityResult
Deterministic arrangement eligibility for the case's account.

| Field | Type | Required | Description |
|---|---|---|---|
| `classification` | enum EligibilityClass | yes | ELIGIBLE, EXCEPTIONAL or NOT_ELIGIBLE |
| `reason_code` | string or null | yes | Eligibility failure reason, for example CONFLICTING_ACTIVE_ITEM |
| `options` | ArrangementOption[] | yes | Eligible options (the only set MODIFY may choose from) |
| `requested_terms` | RequestedTerms or null | yes | Customer's request when present |
| `exception_types` | enum ExceptionType[] | yes | Exception types of the request |
| `within_reviewer_thresholds` | boolean or null | yes | Request within exception.thresholds.* |

### RuleResults
Deterministic rule results shown separately from AI content.

| Field | Type | Required | Description |
|---|---|---|---|
| `policy_version` | string or null | yes | Policy version |
| `priority` | PriorityResult or null | yes | Priority |
| `treatment` | TreatmentBlock | yes | Suppression |
| `eligibility` | EligibilityResult or null | yes | Arrangement eligibility (Slice 2) |
| `exception_authority` | ExceptionAuthority or null | yes | Approval authority (EXCEPTIONAL_ARRANGEMENT cases) |

### AvailableAction
Action availability computed server-side.

| Field | Type | Required | Description |
|---|---|---|---|
| `action` | string | yes | ReviewAction value or COMPLIANCE_DECISION or START_REVIEW |
| `permitted` | boolean | yes | False means the UI hides or disables it |
| `denied_reason_code` | string or null | yes | NOT_PERMITTED_BY_POLICY, WRONG_REVIEWER_ROLE, INVALID_STATE_TRANSITION |
| `requires_reason` | boolean | yes | Reason mandatory |
| `requires_note` | boolean | yes | Note mandatory (REQUEST_MORE_INFORMATION) |

### ReviewDecision
A recorded human decision or transition.

| Field | Type | Required | Description |
|---|---|---|---|
| `decision_id` | id | yes | dec_ id |
| `case_id` | id | yes | esc_ id |
| `kind` | enum DecisionKind | yes | REVIEWER_ACTION, COMPLIANCE_DECISION or START_REVIEW |
| `action` | enum ReviewAction or null | yes | Reviewer action |
| `compliance_outcome` | enum ComplianceOutcome or null | yes | Compliance outcome |
| `reason` | string or null | yes | Reason |
| `note` | string or null | yes | Note |
| `modification_option_id` | string or null | yes | Chosen eligible option id |
| `escalate_reason` | enum EscalationReason or null | yes | Whitelisted reason |
| `rerouted_case_id` | id or null | yes | New case created by ESCALATE |
| `release_suppression` | boolean | yes | Whether this decision released hardship or vulnerable suppression |
| `overrode_ai` | boolean | yes | REJECT or MODIFY on a case whose source is AI |
| `reviewer_persona` | enum Persona | yes | Persona that decided |
| `decided_at` | timestamp | yes | Clock time |
| `case_version_after` | integer | yes | Case version after the decision |
| `policy_version` | string | yes | Policy version |

### EscalationDetail
Full case for review (conversation, AI recommendation and rule results separated).

| Field | Type | Required | Description |
|---|---|---|---|
| `case` | EscalationListItem | yes | Header |
| `summary` | string | yes | Templated one-line case summary |
| `parent_case_id` | id or null | yes | Case this was re-routed from |
| `rerouted_to_case_id` | id or null | yes | Case this was re-routed to |
| `conversation` | ConversationDetail or null | yes | Transcript (source: customer and assistant text) |
| `ai_recommendation` | Recommendation or null | yes | Latest AI recommendation (source: AI) |
| `rule_results` | RuleResults | yes | Deterministic results (source: rules engine) |
| `hardship_case` | HardshipCase or null | yes | Linked hardship record |
| `dispute` | Dispute or null | yes | Linked dispute |
| `decisions` | ReviewDecision[] | yes | History, oldest first |
| `available_actions` | AvailableAction[] | yes | Permitted actions for this persona now |
| `allowed_escalate_reasons` | enum EscalationReason[] | yes | routing.reviewer_escalation_reasons |
| `compliance_outcomes` | enum ComplianceOutcome[] | yes | Non-empty only for COMPLIANCE_REVIEW cases viewed by COMPLIANCE_RISK |

### StartReviewRequest
Claim a case (OPEN to IN_REVIEW) or resume (AWAITING_INFORMATION to IN_REVIEW). Unknown fields are rejected.

| Field | Type | Required | Description |
|---|---|---|---|
| `expected_version` | integer | yes | Case version the reviewer saw |

### ModificationRequest
Change the proposal within deterministic boundaries. Unknown fields are rejected.

| Field | Type | Required | Description |
|---|---|---|---|
| `option_id` | string | yes | Must be in EligibilityResult.options; free-form amounts are rejected |

### DecisionRequest
Reviewer action on a case. Unknown fields are rejected.

| Field | Type | Required | Description |
|---|---|---|---|
| `action` | enum ReviewAction | yes | APPROVE, REJECT, MODIFY, REQUEST_MORE_INFORMATION or ESCALATE |
| `expected_version` | integer | yes | Case version the reviewer saw; mismatch gives 409 VERSION_CONFLICT |
| `reason` | string | optional | Mandatory (1-1000 chars) for REJECT, MODIFY, ESCALATE and APPROVE |
| `note` | string | optional | Mandatory (1-1000 chars) for REQUEST_MORE_INFORMATION |
| `modification` | ModificationRequest | optional | Required for MODIFY |
| `escalate_reason` | enum EscalationReason | optional | Required for ESCALATE; must be in routing.reviewer_escalation_reasons |
| `release_suppression` | boolean | optional | Default false; only meaningful for HARDSHIP and VULNERABLE cases |

### DecisionResult
Outcome of a decision.

| Field | Type | Required | Description |
|---|---|---|---|
| `case` | EscalationDetail | yes | Case after the decision |
| `decision` | ReviewDecision | yes | Recorded decision |
| `rerouted_case` | EscalationListItem or null | yes | New case for ESCALATE |
| `arrangement` | PaymentArrangement or null | yes | Created by APPROVE of an exceptional arrangement |
| `customer_proposal` | Proposal or null | yes | Pending customer proposal created by MODIFY |
| `replayed` | boolean | yes | True on idempotent replay |

### ComplianceDecisionRequest
record_compliance_review_decision. Unknown fields are rejected.

| Field | Type | Required | Description |
|---|---|---|---|
| `outcome` | enum ComplianceOutcome | yes | CLEARED, NOT_CLEARED or REMEDIATION_REQUIRED (compliance.review_outcomes) |
| `reason` | string | yes | Mandatory, 1-1000 chars |
| `expected_version` | integer | yes | Case version |

### DisputeStartReviewRequest
OPEN to UNDER_REVIEW. Unknown fields are rejected.

| Field | Type | Required | Description |
|---|---|---|---|
| `expected_version` | integer | yes | Dispute version |

### DisputeResolveRequest
UNDER_REVIEW to RESOLVED. Unknown fields are rejected.

| Field | Type | Required | Description |
|---|---|---|---|
| `outcome` | enum DisputeOutcome | yes | UPHELD, REJECTED or WITHDRAWN |
| `reason` | string | yes | Mandatory, 1-1000 chars |
| `expected_version` | integer | yes | Dispute version |

### DisputeTransitionResult
Dispute after a transition.

| Field | Type | Required | Description |
|---|---|---|---|
| `dispute` | Dispute | yes | Dispute |
| `suppression_lifted` | boolean | yes | True only when RESOLVED with an outcome |
| `replayed` | boolean | yes | Idempotent replay |

### ToolCallRecord
One AI tool call.

| Field | Type | Required | Description |
|---|---|---|---|
| `tool_name` | string | yes | One of the six tools |
| `tool_type` | string | yes | READ or PROPOSE |
| `arguments` | object | yes | Redacted arguments |
| `result_status` | string | yes | EXECUTED, REJECTED_INVALID_ARGS, REJECTED_UNKNOWN_TOOL, NOT_EXECUTED_CAP_REACHED, REPLAYED |
| `idempotency_key` | string or null | yes | Derived key for PROPOSE tools |
| `duration_ms` | integer | yes | Duration |

### LatencyInfo
Timing capture points.

| Field | Type | Required | Description |
|---|---|---|---|
| `provider_latency_ms` | integer or null | yes | Provider round trip |
| `tool_call_duration_ms` | integer or null | yes | Total tool time |
| `interaction_duration_ms` | integer or null | yes | End to end |

### TokenUsage
Token usage where available.

| Field | Type | Required | Description |
|---|---|---|---|
| `input_tokens` | integer | yes | Input tokens |
| `output_tokens` | integer | yes | Output tokens |
| `estimated_cost_usd` | decimal string or null | yes | Estimated cost, 6 dp |

### AuditEvent
Immutable audit record (read-only).

| Field | Type | Required | Description |
|---|---|---|---|
| `audit_event_id` | id | yes | aud_ id |
| `sequence` | integer | yes | Monotonic sequence for stable ordering |
| `timestamp` | timestamp | yes | Clock time |
| `correlation_id` | string | yes | Correlation id |
| `stage` | enum AuditStage | yes | Decision-chain stage |
| `event_type` | string | yes | Catalogued event type |
| `actor_kind` | enum ActorKind | yes | CUSTOMER, STAFF, SYSTEM or AI |
| `actor_persona` | enum Persona or null | yes | Persona when applicable |
| `customer_id` | id or null | yes | Customer reference |
| `account_id` | id or null | yes | Account reference |
| `capability` | string or null | yes | AI capability: INTENT_CLASSIFICATION, CHAT_RESPONSE, NEXT_BEST_ACTION |
| `provider` | string or null | yes | mock or anthropic |
| `provider_mode` | enum ProviderMode or null | yes | MOCK or LIVE |
| `model_id` | string or null | yes | Model identifier |
| `prompt_version` | string or null | yes | Prompt template version |
| `policy_version` | string or null | yes | PolicyRuleSet version used |
| `input_ref` | string or null | yes | Redacted input reference |
| `ai_output` | object or null | yes | Redacted AI output (invalid output stored here too) |
| `tool_calls` | ToolCallRecord[] | yes | Tool calls |
| `rule_results` | object or null | yes | Business-rule results |
| `human_override` | object or null | yes | Override details {overrode_ai, reason} |
| `final_action` | string or null | yes | Final action or state |
| `reason_code` | string or null | yes | Reason code |
| `resource_type` | string or null | yes | Affected resource type |
| `resource_id` | id or null | yes | Affected resource id |
| `latency` | LatencyInfo or null | yes | Timing |
| `token_usage` | TokenUsage or null | yes | Tokens |

### AuditPage
Audit events.

| Field | Type | Required | Description |
|---|---|---|---|
| `items` | AuditEvent[] | yes | Ordered by timestamp then sequence ascending |
| `page` | PageInfo | yes | Pagination |

### AuditChainSummary
One decision chain.

| Field | Type | Required | Description |
|---|---|---|---|
| `correlation_id` | string | yes | Correlation id |
| `account_id` | id or null | yes | Account |
| `started_at` | timestamp | yes | First event |
| `last_event_at` | timestamp | yes | Last event |
| `event_count` | integer | yes | Events |
| `stages_present` | enum AuditStage[] | yes | Stages present |
| `final_action` | string or null | yes | Final action |
| `policy_version` | string or null | yes | Policy version |
| `model_id` | string or null | yes | Model id |
| `prompt_version` | string or null | yes | Prompt version |

### AuditChainPage
Chain summaries.

| Field | Type | Required | Description |
|---|---|---|---|
| `items` | AuditChainSummary[] | yes | Newest first |
| `page` | PageInfo | yes | Pagination |

### Kpi
One KPI with definition and label.

| Field | Type | Required | Description |
|---|---|---|---|
| `kpi_id` | string | yes | Stable id |
| `name` | string | yes | Display name |
| `definition` | string | yes | Definition |
| `formula` | string | yes | Formula |
| `data_label` | enum DataLabel | yes | ILLUSTRATIVE, MOCK or LIVE |
| `owner_persona` | enum Persona | yes | Owner persona |
| `unit` | enum KpiUnit | yes | Unit |
| `value` | string or null | yes | Decimal string, integer string or null when not computable |
| `numerator` | string or null | yes | Numerator when a ratio |
| `denominator` | string or null | yes | Denominator when a ratio |
| `sample_size` | integer or null | yes | Cases behind the value |
| `claim_status` | enum ClaimStatus | yes | NOT_APPLICABLE, OBSERVATION_ONLY (fewer than 30 LIVE cases), PASS or FAIL |
| `target` | string or null | yes | Target when defined |
| `source_note` | string or null | yes | Dataset version, run id or synthetic-data note |

### AiQualityKpis
AI KPIs, MOCK and LIVE never mixed.

| Field | Type | Required | Description |
|---|---|---|---|
| `mock` | Kpi[] | yes | MOCK regression results, never evidence of model quality |
| `live` | Kpi[] | yes | LIVE evaluation results; empty when no LIVE run exists |
| `live_run_available` | boolean | yes | Whether at least one LIVE EvalRun exists |
| `note` | string | yes | Fixed disclaimer text |

### KpiResponse
KPI tree (BRD 4.5). Deferred KPIs are absent.

| Field | Type | Required | Description |
|---|---|---|---|
| `generated_at` | timestamp | yes | Clock time |
| `policy_version` | string or null | yes | Policy version |
| `business` | Kpi[] | yes | Business KPIs (ILLUSTRATIVE) |
| `operational` | Kpi[] | yes | Operational KPIs |
| `ai_quality` | AiQualityKpis | yes | AI quality and governance |

### EvalRunSummary
Stored EvalRun.

| Field | Type | Required | Description |
|---|---|---|---|
| `eval_run_id` | id | yes | evr_ id |
| `mode` | enum ProviderMode | yes | MOCK or LIVE |
| `dataset_version` | string | yes | Dataset version |
| `model_id` | string or null | yes | Model id |
| `prompt_version` | string | yes | Prompt version |
| `policy_version` | string | yes | Policy version |
| `run_at` | timestamp | yes | Run time |
| `case_count` | integer | yes | Cases |
| `intent_accuracy` | decimal string or null | yes | Overall accuracy |
| `estimated_cost_usd` | decimal string or null | yes | Estimated cost |

### EvalRunPage
Eval runs.

| Field | Type | Required | Description |
|---|---|---|---|
| `items` | EvalRunSummary[] | yes | Newest first |
| `page` | PageInfo | yes | Pagination |

### DemoState
Demo control state.

| Field | Type | Required | Description |
|---|---|---|---|
| `llm_mode` | enum LlmMode | yes | MOCK or LIVE, shown as text |
| `clock` | ClockInfo | yes | Clock |
| `demo_controls_enabled` | boolean | yes | Always true when reachable |
| `policy_version` | string or null | yes | Active policy version |

### ClockAdvanceRequest
Advance the simulated Clock. Unknown fields are rejected.

| Field | Type | Required | Description |
|---|---|---|---|
| `days` | integer | yes | 1 to 365 |
| `refresh_snapshots` | boolean | optional | Default true: run the simulated core sync (as_of, DPD, version) after advancing |

### ClockAdvanceResult
Result of advancing the clock.

| Field | Type | Required | Description |
|---|---|---|---|
| `clock` | ClockInfo | yes | New clock |
| `snapshots_refreshed` | integer | yes | Records refreshed |

### LifecycleRunResult
PTP lifecycle job result.

| Field | Type | Required | Description |
|---|---|---|---|
| `evaluated` | integer | yes | PENDING PTPs evaluated |
| `kept` | integer | yes | Moved to KEPT |
| `broken` | integer | yes | Moved to BROKEN |
| `unchanged` | integer | yes | Left PENDING |

### SimulatePaymentRequest
Demo-control simulated payment. Unknown fields are rejected.

| Field | Type | Required | Description |
|---|---|---|---|
| `account_id` | id | yes | acc_ id |
| `amount` | decimal string (input) | yes | Decimal string |
| `outcome` | enum PaymentOutcome | optional | Default SUCCEEDED |

### SimulatePaymentResult
Recorded event.

| Field | Type | Required | Description |
|---|---|---|---|
| `payment_event` | PaymentEvent | yes | Event with simulated=true and source DEMO_CONTROL |
| `ptp` | PromiseToPay or null | yes | PTP affected, if any |
| `replayed` | boolean | yes | Idempotent replay |

### ReseedRequest
Restore the seeded dataset. Unknown fields are rejected.

| Field | Type | Required | Description |
|---|---|---|---|
| `confirm` | boolean | yes | Must be true |

### ReseedResult
Reseed summary.

| Field | Type | Required | Description |
|---|---|---|---|
| `customers` | integer | yes | Customers seeded |
| `accounts` | integer | yes | Accounts seeded |
| `policy_version` | string | yes | Active policy version |

### ProposalTerms
`Proposal.terms` is one of `PtpTerms`, `PaymentTerms`, `ArrangementTerms`, `ExceptionRequestTerms`, discriminated by `kind`.

## 5. Enumerations

| Enum | Values |
|---|---|
| Persona | CUSTOMER, COLLECTIONS_OFFICER, COLLECTIONS_MANAGER, COMPLIANCE_RISK |
| AccountType | CARD, PERSONAL_LOAN |
| Bucket | CURRENT, DPD_1_29, DPD_30_59, DPD_60_89, DPD_90_PLUS |
| CollectionStatus | NEW, IN_PROGRESS, PTP_PENDING, ARRANGEMENT_ACTIVE, ESCALATED, RESOLVED |
| PriorityBand | LOW, MEDIUM, HIGH |
| Intent | PAY_NOW, PROMISE_TO_PAY, PAYMENT_PLAN, FINANCIAL_HARDSHIP, DISPUTE, REQUEST_HUMAN, UNKNOWN |
| SpecialRequest | NONE, SETTLEMENT, POLICY_EXCEPTION |
| VulnerabilityCategory | BEREAVEMENT, SERIOUS_ILLNESS_OR_DISABILITY, MENTAL_HEALTH_CONCERN, DOMESTIC_ABUSE_OR_COERCION, LIMITED_CAPACITY_TO_UNDERSTAND, LANGUAGE_OR_COMMUNICATION_BARRIER, OTHER |
| PtpStatus | PENDING, KEPT, BROKEN, CANCELLED |
| PtpSource | OFFICER_MANUAL, CUSTOMER_CHAT |
| PaymentOutcome | SUCCEEDED, FAILED |
| PaymentSource | CUSTOMER_CHAT, DEMO_CONTROL |
| PayableOptionType | OVERDUE_AMOUNT, FULL_BALANCE |
| ArrangementStatus | ACTIVE, COMPLETED, CANCELLED |
| ArrangementCreatedVia | CUSTOMER_CONFIRMATION, EXCEPTION_APPROVAL |
| EscalationReason | REQUEST_HUMAN, UNRESOLVED_UNKNOWN, AI_FAILURE_FALLBACK, EXCEPTIONAL_ARRANGEMENT, FINANCIAL_HARDSHIP, DISPUTE, SETTLEMENT_REQUEST, AMBIGUOUS_VALIDATION, VULNERABLE_CUSTOMER, POLICY_EXCEPTION, HIGH_RISK_COMPLIANCE |
| ReviewQueue | COLLECTIONS_REVIEW, COLLECTIONS_EXCEPTION_REVIEW, HARDSHIP_REVIEW, DISPUTE_REVIEW, VULNERABLE_CUSTOMER_REVIEW, COMPLIANCE_REVIEW |
| ReviewerRole | COLLECTIONS_OFFICER, COMPLIANCE_RISK |
| EscalationPriority | NORMAL, ELEVATED, URGENT |
| CaseStatus | OPEN, IN_REVIEW, AWAITING_INFORMATION, DECIDED, RE_ROUTED |
| CaseSource | AI, CUSTOMER, SYSTEM, REVIEWER |
| ReviewAction | APPROVE, REJECT, MODIFY, REQUEST_MORE_INFORMATION, ESCALATE |
| DecisionKind | REVIEWER_ACTION, COMPLIANCE_DECISION, START_REVIEW |
| ComplianceOutcome | CLEARED, NOT_CLEARED, REMEDIATION_REQUIRED |
| ExceptionType | TERM, START_DATE, AMOUNT_STRUCTURE |
| EligibilityClass | ELIGIBLE, EXCEPTIONAL, NOT_ELIGIBLE |
| HardshipIndicatorType | JOB_LOSS, INCOME_REDUCTION, MEDICAL_OR_FAMILY_EMERGENCY, TEMPORARY_FINANCIAL_DIFFICULTY, OTHER |
| HardshipStatus | OPEN, UNDER_REVIEW, DECIDED |
| DisputeCategory | AMOUNT_INCORRECT, NOT_MY_DEBT, ALREADY_PAID, FRAUD_OR_UNAUTHORIZED, FEE_OR_INTEREST_DISPUTE, OTHER |
| DisputeStatus | OPEN, UNDER_REVIEW, RESOLVED |
| DisputeOutcome | UPHELD, REJECTED, WITHDRAWN |
| NbaAction | CONTACT_CUSTOMER, REQUEST_PAYMENT, OFFER_ELIGIBLE_ARRANGEMENT, FOLLOW_UP_PTP, REFER_TO_HARDSHIP_WORKFLOW, ESCALATE_TO_HUMAN_REVIEW |
| RecommendationStatus | GENERATED, SAFE_FALLBACK, HUMAN_REVIEW_ONLY, AI_UNAVAILABLE, NOT_GENERATED |
| RecommendationDecision | ACCEPTED, OVERRIDDEN |
| ContentSource | MODEL, TEMPLATE, CUSTOMER_INPUT |
| ProposalKind | PTP, PAYMENT, ARRANGEMENT, EXCEPTION_REQUEST |
| ProposalStatus | PENDING_CONFIRMATION, CONFIRMED, CANCELLED, EXPIRED, INVALIDATED |
| MessageRole | CUSTOMER, ASSISTANT, SYSTEM |
| ConversationStatus | ACTIVE, HANDED_OFF, CLOSED |
| SafeState | NONE, AI_UNAVAILABLE, HANDOFF_CREATED, HANDOFF_FAILED, POLICY_UNAVAILABLE, AUDIT_UNAVAILABLE, TOOL_CAP_REACHED, STALE_DATA_REFRESHED |
| MessageLabel | AI_DISCLOSURE, SIMULATED, HUMAN_HANDOFF, SAFE_FALLBACK |
| Freshness | FRESH, STALE, UNKNOWN |
| ItemKind | INSTALLMENT, STATEMENT_CYCLE, FEE_OR_CHARGE |
| ItemStatus | OPEN, PAID |
| ContactOutcome | NO_CONTACT, CONTACT_NO_COMMITMENT, PTP_MADE, PTP_BROKEN, PAYMENT_MADE |
| InteractionChannel | SIMULATED_CHAT, SIMULATED_OUTBOUND_CALL, SIMULATED_OUTBOUND_MESSAGE, SYSTEM_EVENT |
| InteractionDirection | INBOUND, OUTBOUND, INTERNAL |
| SuppressionSource | ESCALATION, HARDSHIP, DISPUTE, VULNERABLE |
| SuppressionScope | ITEM, ACCOUNT |
| AuditStage | INPUT, AI_INTERPRETATION, PROPOSAL, RULE_VALIDATION, HUMAN_DECISION, FINAL_STATE |
| ActorKind | CUSTOMER, STAFF, SYSTEM, AI |
| ProviderMode | MOCK, LIVE |
| LlmMode | MOCK, LIVE |
| ClockMode | SYSTEM, SIMULATED |
| DataLabel | ILLUSTRATIVE, MOCK, LIVE |
| ClaimStatus | NOT_APPLICABLE, OBSERVATION_ONLY, PASS, FAIL |
| KpiUnit | COUNT, CURRENCY, RATIO, MILLISECONDS, USD_ESTIMATE |
| CaseSummaryKind | NONE, OPEN, CLOSED |
| ErrorCode | UNAUTHENTICATED, FORBIDDEN, NOT_FOUND, VALIDATION_ERROR, BUSINESS_RULE_VIOLATION, CONFLICT, RATE_LIMITED, POLICY_UNAVAILABLE, AUDIT_UNAVAILABLE, HANDOFF_FAILED, SERVICE_UNAVAILABLE, INTERNAL_ERROR |

## 6. Worked examples (synthetic)

**Create a PTP as an officer**
```
POST /api/ptps
X-Persona: COLLECTIONS_OFFICER
Idempotency-Key: ptp-acc000123-20261001-01
{"account_id":"acc_000123","promised_amount":"250.00","promised_date":"2026-10-15","record_version":7,"snapshot_as_of":"2026-10-01T09:00:00Z"}
-> 201 {"ptp_id":"ptp_01J8ZK3M2Q","account_id":"acc_000123","promised_amount":"250.00","promised_date":"2026-10-15","status":"PENDING","cumulative_paid":"0.00","remaining_amount":"250.00","source":"OFFICER_MANUAL", ...}
```
**Customer chat turn producing a proposal**
```
POST /api/chat/conversations/conv_01J8ZK4A9B/messages
X-Persona: CUSTOMER
X-Demo-Session: 5b0c...e1
{"content":"I can pay 250 by the 15th"}
-> 200 {"assistant_message":{"content":"You can promise 250.00 by 2026-10-15. Please confirm below.","content_source":"TEMPLATE","labels":[]},
        "intent":{"label":"PROMISE_TO_PAY","confidence":"0.93","vulnerability_detected":false,"special_request":"NONE"},
        "proposal":{"proposal_id":"prp_01J8ZK4C7D","kind":"PTP","status":"PENDING_CONFIRMATION","terms":{"kind":"PTP","promised_amount":"250.00","promised_date":"2026-10-15"},"terms_hash":"9f2c...","record_version":7},
        "handoff":null,"safe_state":"NONE","talk_to_human_available":true}
POST /api/chat/conversations/conv_01J8ZK4A9B/proposals/prp_01J8ZK4C7D/confirm   (Idempotency-Key: required)
{"terms_hash":"9f2c..."}   -> 201 {"outcome":{"kind":"PTP","ptp":{...,"status":"PENDING"}}, "replayed":false, ...}
```
**Stale confirm**: `409 {"error":{"code":"CONFLICT","reason_code":"PROPOSAL_INVALID", ...}}` and no PTP is created.
