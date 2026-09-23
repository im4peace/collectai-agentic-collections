"""E9-S1: audit trail API (`GET /api/audit`, `GET /api/audit/chains`).

Mounts `api/routers/audit.py`'s router onto the shared `api_client` app the
same way `test_e3_s1_rbac_matrix.py`'s `probe_client` fixture does, since
`api/app.py` itself is out of this story's file ownership (the orchestrator
wires the real router in once every Group E story lands). Seed data is
written directly through `AuditService` (the same append-only write path
E1-S4's own tests exercise), never through a route this story does not own.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from collectai.api.routers.audit import router as audit_router
from collectai.audit.events import AuditEventDraft
from collectai.audit.redaction import redact_text
from collectai.audit.service import AuditService
from collectai.types.clock import SimulatedClock
from collectai.types.enums import ActorKind, AuditStage, Persona

pytestmark = pytest.mark.db

_NOW = datetime(2026, 10, 1, 9, 0, 0, tzinfo=UTC)
_COMPLIANCE_HEADERS = {"X-Persona": Persona.COMPLIANCE_RISK.value}
_STAGES_IN_CHAIN_ORDER: tuple[AuditStage, ...] = (
    AuditStage.INPUT,
    AuditStage.AI_INTERPRETATION,
    AuditStage.PROPOSAL,
    AuditStage.RULE_VALIDATION,
    AuditStage.HUMAN_DECISION,
    AuditStage.FINAL_STATE,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def audit_client(api_client: TestClient) -> TestClient:
    api_client.app.include_router(audit_router)
    return api_client


@pytest_asyncio.fixture
async def audit_service(
    engine: AsyncEngine, clock: SimulatedClock, clean_db: None
) -> AuditService:
    """`clean_db` is taken directly (not only transitively through
    `audit_client`/`api_client`) so seeding never races the truncation
    regardless of which fixture pytest resolves first -- `clean_db` is
    function-scoped and cached, so this never truncates twice.

    `clean_db` (owned by `tests/api/conftest.py`, not this story) never
    truncates `audit_event` -- it is append-only by design (E1-S4), so rows
    this module writes accumulate across every test in the whole session.
    Every id this module generates must therefore be unique per seed call
    (see `_unique_account_id`/`_unique_correlation_id` below), never a
    fixed literal reused by more than one test, or an exact-count assertion
    in one test can pick up another test's leftover rows.
    """
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    return AuditService(clock, session_factory)


def _unique_suffix() -> str:
    return uuid.uuid4().hex[:12]


def _unique_correlation_id(label: str) -> str:
    return f"corr-e9s1-{label}-{_unique_suffix()}"


def _unique_account_id() -> str:
    return f"acc_{_unique_suffix()}"


def _unique_customer_id() -> str:
    return f"cus_{_unique_suffix()}"


async def _seed(service: AuditService, clock: SimulatedClock, draft: AuditEventDraft) -> None:
    await service.record(draft)


async def _seed_chain(
    service: AuditService,
    clock: SimulatedClock,
    correlation_id: str,
    *,
    account_id: str | None = None,
    customer_id: str | None = None,
    stages: tuple[AuditStage, ...] = _STAGES_IN_CHAIN_ORDER,
) -> str:
    """Seed one full decision chain under `correlation_id`. Returns the
    account id used (freshly generated when not given), so callers that
    need to filter by it never have to guess or reuse a literal another
    test might also be using."""
    resolved_account_id = account_id or _unique_account_id()
    resolved_customer_id = customer_id or _unique_customer_id()
    for index, stage in enumerate(stages):
        clock.set(_NOW + timedelta(minutes=index))
        await _seed(
            service,
            clock,
            AuditEventDraft(
                correlation_id=correlation_id,
                stage=stage,
                event_type=f"{stage.value}_EVENT",
                actor_kind=ActorKind.SYSTEM,
                account_id=resolved_account_id,
                customer_id=resolved_customer_id,
                final_action="COMPLETED" if stage is AuditStage.FINAL_STATE else None,
            ),
        )
    return resolved_account_id


@dataclass(frozen=True, slots=True)
class SeededChain:
    correlation_id: str
    account_id: str


@pytest_asyncio.fixture
async def seeded_chain(audit_service: AuditService, clock: SimulatedClock) -> SeededChain:
    correlation_id = _unique_correlation_id("chain")
    account_id = await _seed_chain(audit_service, clock, correlation_id)
    return SeededChain(correlation_id=correlation_id, account_id=account_id)


# ---------------------------------------------------------------------------
# AC1: correlation_id returns the whole chain, ordered by stage
# ---------------------------------------------------------------------------


def test_correlation_id_filter_returns_the_full_chain_in_decision_order(
    audit_client: TestClient, seeded_chain: SeededChain
) -> None:
    response = audit_client.get(
        "/api/audit",
        params={"correlation_id": seeded_chain.correlation_id},
        headers=_COMPLIANCE_HEADERS,
    )

    assert response.status_code == 200
    body = response.json()
    assert [item["stage"] for item in body["items"]] == [
        stage.value for stage in _STAGES_IN_CHAIN_ORDER
    ]
    assert body["page"]["total"] == len(_STAGES_IN_CHAIN_ORDER)
    assert all(item["correlation_id"] == seeded_chain.correlation_id for item in body["items"])


@pytest.mark.asyncio
async def test_correlation_id_filter_ignores_events_from_other_chains(
    audit_client: TestClient, audit_service: AuditService, clock: SimulatedClock
) -> None:
    target_correlation_id = _unique_correlation_id("target")
    await _seed_chain(audit_service, clock, target_correlation_id)
    await _seed_chain(audit_service, clock, _unique_correlation_id("other"))

    response = audit_client.get(
        "/api/audit",
        params={"correlation_id": target_correlation_id},
        headers=_COMPLIANCE_HEADERS,
    )

    body = response.json()
    assert all(item["correlation_id"] == target_correlation_id for item in body["items"])
    assert len(body["items"]) == len(_STAGES_IN_CHAIN_ORDER)


# ---------------------------------------------------------------------------
# AC2: filtering by account id and date range
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_account_id_filter_returns_only_that_accounts_events(
    audit_client: TestClient, audit_service: AuditService, clock: SimulatedClock
) -> None:
    matching_account_id = _unique_account_id()
    other_account_id = _unique_account_id()
    clock.set(_NOW)
    await _seed(
        audit_service,
        clock,
        AuditEventDraft(
            correlation_id=_unique_correlation_id("acc-a"),
            stage=AuditStage.INPUT,
            event_type="MESSAGE_RECEIVED",
            actor_kind=ActorKind.CUSTOMER,
            account_id=matching_account_id,
        ),
    )
    await _seed(
        audit_service,
        clock,
        AuditEventDraft(
            correlation_id=_unique_correlation_id("acc-b"),
            stage=AuditStage.INPUT,
            event_type="MESSAGE_RECEIVED",
            actor_kind=ActorKind.CUSTOMER,
            account_id=other_account_id,
        ),
    )

    response = audit_client.get(
        "/api/audit", params={"account_id": matching_account_id}, headers=_COMPLIANCE_HEADERS
    )

    body = response.json()
    assert len(body["items"]) == 1
    assert body["items"][0]["account_id"] == matching_account_id


@pytest.mark.asyncio
async def test_date_range_filter_from_is_inclusive_and_to_is_exclusive(
    audit_client: TestClient, audit_service: AuditService, clock: SimulatedClock
) -> None:
    account_id = _unique_account_id()
    boundary_events = {
        "before_window": _NOW - timedelta(minutes=1),
        "window_start": _NOW,
        "window_end": _NOW + timedelta(minutes=10),
        "after_window": _NOW + timedelta(minutes=10, seconds=1),
    }
    correlation_ids = {
        label: _unique_correlation_id(f"date-{label}") for label in boundary_events
    }
    for label, timestamp in boundary_events.items():
        clock.set(timestamp)
        await _seed(
            audit_service,
            clock,
            AuditEventDraft(
                correlation_id=correlation_ids[label],
                stage=AuditStage.INPUT,
                event_type="MESSAGE_RECEIVED",
                actor_kind=ActorKind.SYSTEM,
                account_id=account_id,
            ),
        )

    response = audit_client.get(
        "/api/audit",
        params={
            "account_id": account_id,
            "from": boundary_events["window_start"].isoformat().replace("+00:00", "Z"),
            "to": boundary_events["window_end"].isoformat().replace("+00:00", "Z"),
        },
        headers=_COMPLIANCE_HEADERS,
    )

    returned_correlation_ids = {item["correlation_id"] for item in response.json()["items"]}
    assert returned_correlation_ids == {correlation_ids["window_start"]}


@pytest.mark.asyncio
async def test_stage_filter_narrows_to_matching_stages_only(
    audit_client: TestClient, seeded_chain: SeededChain
) -> None:
    response = audit_client.get(
        "/api/audit",
        params={
            "correlation_id": seeded_chain.correlation_id,
            "stage": [AuditStage.PROPOSAL.value],
        },
        headers=_COMPLIANCE_HEADERS,
    )

    body = response.json()
    assert [item["stage"] for item in body["items"]] == [AuditStage.PROPOSAL.value]


@pytest.mark.asyncio
async def test_event_type_filter_narrows_to_matching_event_type_only(
    audit_client: TestClient, seeded_chain: SeededChain
) -> None:
    response = audit_client.get(
        "/api/audit",
        params={"correlation_id": seeded_chain.correlation_id, "event_type": "FINAL_STATE_EVENT"},
        headers=_COMPLIANCE_HEADERS,
    )

    body = response.json()
    assert [item["event_type"] for item in body["items"]] == ["FINAL_STATE_EVENT"]


# ---------------------------------------------------------------------------
# AC3: RBAC and "no write route"
# ---------------------------------------------------------------------------


def test_compliance_risk_is_allowed_to_search_audit_events(audit_client: TestClient) -> None:
    response = audit_client.get(
        "/api/audit", params={"account_id": "acc_000123"}, headers=_COMPLIANCE_HEADERS
    )
    assert response.status_code == 200


@pytest.mark.parametrize(
    "persona", [Persona.COLLECTIONS_OFFICER, Persona.COLLECTIONS_MANAGER]
)
def test_staff_personas_other_than_compliance_risk_are_forbidden(
    audit_client: TestClient, persona: Persona
) -> None:
    response = audit_client.get(
        "/api/audit", params={"account_id": "acc_000123"}, headers={"X-Persona": persona.value}
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"


def test_customer_persona_is_forbidden(
    audit_client: TestClient, customer_session_headers: dict[str, str]
) -> None:
    response = audit_client.get(
        "/api/audit", params={"account_id": "acc_000123"}, headers=customer_session_headers
    )
    assert response.status_code == 403


def test_missing_persona_header_is_unauthenticated_not_forbidden(
    audit_client: TestClient,
) -> None:
    response = audit_client.get("/api/audit", params={"account_id": "acc_000123"})
    assert response.status_code == 401


@pytest.mark.parametrize("method", ["POST", "PUT", "PATCH", "DELETE"])
@pytest.mark.parametrize("path", ["/api/audit", "/api/audit/chains"])
def test_audit_endpoints_expose_no_write_route(
    audit_client: TestClient, method: str, path: str
) -> None:
    response = audit_client.request(method, path, headers=_COMPLIANCE_HEADERS)
    assert response.status_code in (404, 405)


# ---------------------------------------------------------------------------
# FILTER_REQUIRED (422) -- both endpoints
# ---------------------------------------------------------------------------


def test_no_filter_at_all_returns_422_filter_required(audit_client: TestClient) -> None:
    response = audit_client.get("/api/audit", headers=_COMPLIANCE_HEADERS)
    assert response.status_code == 422
    assert response.json()["error"]["reason_code"] == "FILTER_REQUIRED"


def test_stage_alone_does_not_satisfy_filter_required(audit_client: TestClient) -> None:
    response = audit_client.get(
        "/api/audit", params={"stage": AuditStage.INPUT.value}, headers=_COMPLIANCE_HEADERS
    )
    assert response.status_code == 422
    assert response.json()["error"]["reason_code"] == "FILTER_REQUIRED"


def test_event_type_and_limit_and_offset_alone_do_not_satisfy_filter_required(
    audit_client: TestClient,
) -> None:
    response = audit_client.get(
        "/api/audit",
        params={"event_type": "MESSAGE_RECEIVED", "limit": 10, "offset": 0},
        headers=_COMPLIANCE_HEADERS,
    )
    assert response.status_code == 422
    assert response.json()["error"]["reason_code"] == "FILTER_REQUIRED"


def test_chains_endpoint_also_requires_at_least_one_filter(audit_client: TestClient) -> None:
    response = audit_client.get("/api/audit/chains", headers=_COMPLIANCE_HEADERS)
    assert response.status_code == 422
    assert response.json()["error"]["reason_code"] == "FILTER_REQUIRED"


def test_correlation_id_alone_satisfies_the_filter_requirement(
    audit_client: TestClient, seeded_chain: SeededChain
) -> None:
    response = audit_client.get(
        "/api/audit",
        params={"correlation_id": seeded_chain.correlation_id},
        headers=_COMPLIANCE_HEADERS,
    )
    assert response.status_code == 200


def test_from_alone_satisfies_the_filter_requirement(audit_client: TestClient) -> None:
    response = audit_client.get(
        "/api/audit",
        params={"from": _NOW.isoformat().replace("+00:00", "Z")},
        headers=_COMPLIANCE_HEADERS,
    )
    assert response.status_code == 200


def test_to_alone_satisfies_the_filter_requirement(audit_client: TestClient) -> None:
    response = audit_client.get(
        "/api/audit",
        params={"to": _NOW.isoformat().replace("+00:00", "Z")},
        headers=_COMPLIANCE_HEADERS,
    )
    assert response.status_code == 200


# ---------------------------------------------------------------------------
# Pagination boundaries
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("limit", [0, 501])
def test_audit_limit_out_of_bounds_is_rejected(audit_client: TestClient, limit: int) -> None:
    response = audit_client.get(
        "/api/audit",
        params={"account_id": "acc_000123", "limit": limit},
        headers=_COMPLIANCE_HEADERS,
    )
    assert response.status_code == 422


@pytest.mark.parametrize("limit", [0, 201])
def test_chains_limit_out_of_bounds_is_rejected(audit_client: TestClient, limit: int) -> None:
    response = audit_client.get(
        "/api/audit/chains",
        params={"account_id": "acc_000123", "limit": limit},
        headers=_COMPLIANCE_HEADERS,
    )
    assert response.status_code == 422


def test_negative_offset_is_rejected(audit_client: TestClient) -> None:
    response = audit_client.get(
        "/api/audit", params={"account_id": "acc_000123", "offset": -1}, headers=_COMPLIANCE_HEADERS
    )
    assert response.status_code == 422


def test_offset_pagination_returns_the_next_page_without_overlap(
    audit_client: TestClient, seeded_chain: SeededChain
) -> None:
    first_page = audit_client.get(
        "/api/audit",
        params={"correlation_id": seeded_chain.correlation_id, "limit": 2, "offset": 0},
        headers=_COMPLIANCE_HEADERS,
    ).json()
    second_page = audit_client.get(
        "/api/audit",
        params={"correlation_id": seeded_chain.correlation_id, "limit": 2, "offset": 2},
        headers=_COMPLIANCE_HEADERS,
    ).json()

    first_ids = [item["audit_event_id"] for item in first_page["items"]]
    second_ids = [item["audit_event_id"] for item in second_page["items"]]
    assert len(first_ids) == 2
    assert len(second_ids) == 2
    assert set(first_ids).isdisjoint(second_ids)
    assert first_page["page"]["total"] == len(_STAGES_IN_CHAIN_ORDER)
    assert second_page["page"]["total"] == len(_STAGES_IN_CHAIN_ORDER)


def test_page_total_reflects_full_match_count_not_just_the_returned_page(
    audit_client: TestClient, seeded_chain: SeededChain
) -> None:
    response = audit_client.get(
        "/api/audit",
        params={"correlation_id": seeded_chain.correlation_id, "limit": 1, "offset": 0},
        headers=_COMPLIANCE_HEADERS,
    )
    body = response.json()
    assert len(body["items"]) == 1
    assert body["page"]["total"] == len(_STAGES_IN_CHAIN_ORDER)


# ---------------------------------------------------------------------------
# GET /api/audit/chains
# ---------------------------------------------------------------------------


def test_chains_endpoint_returns_one_summary_row_per_correlation_id(
    audit_client: TestClient, seeded_chain: SeededChain
) -> None:
    response = audit_client.get(
        "/api/audit/chains",
        params={"account_id": seeded_chain.account_id},
        headers=_COMPLIANCE_HEADERS,
    )

    assert response.status_code == 200
    body = response.json()
    assert len(body["items"]) == 1
    summary = body["items"][0]
    assert summary["correlation_id"] == seeded_chain.correlation_id
    assert summary["event_count"] == len(_STAGES_IN_CHAIN_ORDER)
    assert summary["stages_present"] == [stage.value for stage in _STAGES_IN_CHAIN_ORDER]
    assert summary["final_action"] == "COMPLETED"
    assert summary["account_id"] == seeded_chain.account_id


@pytest.mark.asyncio
async def test_chains_stages_present_deduplicates_a_repeated_stage(
    audit_client: TestClient, audit_service: AuditService, clock: SimulatedClock
) -> None:
    """LEARNED RULE: a "unique" list field needs an explicit dedup check --
    a chain that records the same stage twice (e.g. two `INPUT` events) must
    still report each stage only once in `stages_present`."""
    correlation_id = _unique_correlation_id("repeated-stage")
    account_id = await _seed_chain(
        audit_service,
        clock,
        correlation_id,
        stages=(AuditStage.INPUT, AuditStage.INPUT, AuditStage.FINAL_STATE),
    )

    response = audit_client.get(
        "/api/audit/chains", params={"account_id": account_id}, headers=_COMPLIANCE_HEADERS
    )

    body = response.json()
    summary = next(item for item in body["items"] if item["correlation_id"] == correlation_id)
    assert summary["stages_present"] == [AuditStage.INPUT.value, AuditStage.FINAL_STATE.value]
    assert summary["event_count"] == 3


@pytest.mark.asyncio
async def test_chains_newest_first_ordering_by_last_event(
    audit_client: TestClient, audit_service: AuditService, clock: SimulatedClock
) -> None:
    clock.set(_NOW)
    await _seed(
        audit_service,
        clock,
        AuditEventDraft(
            correlation_id="corr-chain-older",
            stage=AuditStage.INPUT,
            event_type="MESSAGE_RECEIVED",
            actor_kind=ActorKind.SYSTEM,
            account_id="acc_000999",
        ),
    )
    clock.set(_NOW + timedelta(hours=1))
    await _seed(
        audit_service,
        clock,
        AuditEventDraft(
            correlation_id="corr-chain-newer",
            stage=AuditStage.INPUT,
            event_type="MESSAGE_RECEIVED",
            actor_kind=ActorKind.SYSTEM,
            account_id="acc_000999",
        ),
    )

    response = audit_client.get(
        "/api/audit/chains", params={"account_id": "acc_000999"}, headers=_COMPLIANCE_HEADERS
    )

    correlation_ids = [item["correlation_id"] for item in response.json()["items"]]
    assert correlation_ids == ["corr-chain-newer", "corr-chain-older"]


@pytest.mark.asyncio
async def test_chains_account_id_and_date_range_filters_combine_with_and_semantics(
    audit_client: TestClient, audit_service: AuditService, clock: SimulatedClock
) -> None:
    clock.set(_NOW)
    await _seed(
        audit_service,
        clock,
        AuditEventDraft(
            correlation_id="corr-and-match",
            stage=AuditStage.INPUT,
            event_type="MESSAGE_RECEIVED",
            actor_kind=ActorKind.SYSTEM,
            account_id="acc_000777",
        ),
    )
    clock.set(_NOW + timedelta(days=5))
    await _seed(
        audit_service,
        clock,
        AuditEventDraft(
            correlation_id="corr-and-wrong-account",
            stage=AuditStage.INPUT,
            event_type="MESSAGE_RECEIVED",
            actor_kind=ActorKind.SYSTEM,
            account_id="acc_000888",
        ),
    )

    response = audit_client.get(
        "/api/audit/chains",
        params={
            "account_id": "acc_000777",
            "from": (_NOW - timedelta(minutes=1)).isoformat().replace("+00:00", "Z"),
            "to": (_NOW + timedelta(minutes=1)).isoformat().replace("+00:00", "Z"),
        },
        headers=_COMPLIANCE_HEADERS,
    )

    correlation_ids = [item["correlation_id"] for item in response.json()["items"]]
    assert correlation_ids == ["corr-and-match"]


# ---------------------------------------------------------------------------
# AC4: no secrets or prohibited identifiers leak through the read path
# ---------------------------------------------------------------------------

_SECRET_BEARING_TEMPLATES: tuple[dict[str, object], ...] = (
    {
        "ai_output": {
            "summary": "Customer asked about balance.",
            "note": "reviewed provider key sk-ant-api03-abcdEFGH12345678ijklMNOP inline",
        }
    },
    {
        "rule_results": {
            "eligibility": "ELIGIBLE",
            "details": "flagged card ending pattern 4111111111111111 for follow-up",
        }
    },
    {
        "human_override": {
            "overrode_ai": True,
            "reason": "manual review noted ssn reference 078-05-1120 in the case file",
        }
    },
    {
        "input_ref": (
            "raw prompt included Authorization: "
            "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.tok"
        )
    },
    {"ai_output": {"note": "agent read out CVV: 482 during the call, flagged for redaction"}},
    {
        "tool_calls": [
            {
                "tool_name": "get_account_context",
                "tool_type": "READ",
                "arguments": {"note": "card 4111111111111111 mentioned in transcript"},
                "result_status": "EXECUTED",
                "idempotency_key": None,
                "duration_ms": 42,
            }
        ]
    },
)
_ACTOR_KINDS = (ActorKind.CUSTOMER, ActorKind.STAFF, ActorKind.SYSTEM, ActorKind.AI)
_EVENT_TYPES = (
    "MESSAGE_RECEIVED",
    "NBA_GENERATED",
    "PTP_CREATED",
    "ESCALATION_OPENED",
    "RULE_REJECTED",
)
_SEEDED_EVENT_COUNT = 100


@pytest_asyncio.fixture
async def seeded_secret_bearing_events(
    audit_service: AuditService, clock: SimulatedClock
) -> None:
    for index in range(_SEEDED_EVENT_COUNT):
        clock.set(_NOW + timedelta(seconds=index))
        template = _SECRET_BEARING_TEMPLATES[index % len(_SECRET_BEARING_TEMPLATES)]
        draft_kwargs: dict[str, object] = {
            "correlation_id": f"corr-e9s1-scan-{index:04d}",
            "stage": _STAGES_IN_CHAIN_ORDER[index % len(_STAGES_IN_CHAIN_ORDER)],
            "event_type": _EVENT_TYPES[index % len(_EVENT_TYPES)],
            "actor_kind": _ACTOR_KINDS[index % len(_ACTOR_KINDS)],
            "account_id": f"acc_{200000 + index:06d}",
            "customer_id": f"cus_{200000 + index:06d}",
        }
        draft_kwargs.update(template)
        await _seed(audit_service, clock, AuditEventDraft(**draft_kwargs))


def _iter_strings(value: object) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [s for nested in value.values() for s in _iter_strings(nested)]
    if isinstance(value, list):
        return [s for nested in value for s in _iter_strings(nested)]
    return []


def _collect_all_audit_events(audit_client: TestClient) -> list[dict[str, object]]:
    events: list[dict[str, object]] = []
    offset = 0
    limit = 40
    while True:
        response = audit_client.get(
            "/api/audit",
            params={
                "from": (_NOW - timedelta(minutes=1)).isoformat().replace("+00:00", "Z"),
                "to": (_NOW + timedelta(days=1)).isoformat().replace("+00:00", "Z"),
                "limit": limit,
                "offset": offset,
            },
            headers=_COMPLIANCE_HEADERS,
        )
        assert response.status_code == 200
        body = response.json()
        events.extend(body["items"])
        if offset + limit >= body["page"]["total"]:
            break
        offset += limit
    return events


# Opaque system identifiers (`aud_`/`cus_`/`acc_`/`corr-`-prefixed, or a
# resource id) are excluded from the digit-run/SSN-shaped defense-in-depth
# regex sweep below: their format is already fixed and validated elsewhere
# (`types/ids.py`), and treating them as free-form content risks a flaky
# false positive from an incidental digit run. The `redact_text` oracle
# check (this test's primary assertion) still runs over every field,
# including these, since it only matches genuinely secret-shaped spans.
_ID_SHAPED_FIELDS = frozenset(
    {"audit_event_id", "correlation_id", "customer_id", "account_id", "resource_id"}
)


def test_no_secrets_or_prohibited_identifiers_leak_through_100_returned_events(
    audit_client: TestClient, seeded_secret_bearing_events: None
) -> None:
    events = _collect_all_audit_events(audit_client)
    scan_targets = [
        event for event in events if event["correlation_id"].startswith("corr-e9s1-scan-")
    ]
    assert len(scan_targets) >= _SEEDED_EVENT_COUNT

    for event in scan_targets:
        for field_name, field_value in event.items():
            if field_name == "timestamp":
                continue
            for string_value in _iter_strings(field_value):
                # AC4 oracle: the same redaction the write path already
                # applied must be a no-op on every string the read path
                # returns -- a match here means a secret-shaped span slipped
                # through the write-time redaction and leaked via the API.
                assert redact_text(string_value) == string_value, (
                    field_name,
                    string_value,
                )
                assert "sk-ant-" not in string_value
                assert "Bearer " not in string_value
                if field_name not in _ID_SHAPED_FIELDS:
                    assert not _looks_like_card_number(string_value)
                    assert not _looks_like_ssn(string_value)


def _looks_like_card_number(value: str) -> bool:
    return re.search(r"\b\d{13,19}\b", value) is not None


def _looks_like_ssn(value: str) -> bool:
    return re.search(r"\b\d{3}-\d{2}-\d{4}\b", value) is not None

