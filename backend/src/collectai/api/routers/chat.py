"""Customer chat endpoints this story owns (api-contracts.md 3.8):
`POST /api/chat/conversations`, `GET /api/chat/conversations`,
`GET /api/chat/conversations/{conversation_id}`,
`POST /api/chat/conversations/{conversation_id}/messages`. The confirm/
cancel/handoff endpoints under the same prefix belong to later stories
(E6-S2/E6-S3/E6-S5) and are not defined here.

This router is the HTTP-shaped translation layer only: it resolves the
bound customer (never a client-supplied id, AC7), checks object-level
ownership the same way `api/routers/me.py` does (`me_ownership.require_owned`,
including its `CROSS_CUSTOMER_ACCESS_DENIED` audit event), and calls
`application.chat_flow` for every business decision. All classification,
safety-precedence and escalation-reporting logic lives there, not here.

Not wired into `api/app.py` yet (this story does not edit that file -- a
parallel sibling story lands another router at the same time; see
`api/routers/portfolio.py` and `api/deps.py`'s own docstrings for the
established "the orchestrator wires every sibling router in once every
group's stories land" convention). `get_settings` below follows
`api/deps.py`'s `get_policy_provider` precedent for the same reason: it
degrades to a safe MOCK-mode fallback when `app.state.settings` has not
been set yet, exactly as `get_policy_provider` degrades to a
never-activated `PolicyProvider`.
"""

from __future__ import annotations

from typing import Annotated, Final, cast

from fastapi import APIRouter, Depends, Request, status

from collectai.api.deps import (
    AuditServiceDep,
    ClockDep,
    DbSession,
    PersonaContext,
    require_capability,
)
from collectai.api.middleware.errors import RateLimitedError, resolve_correlation_id
from collectai.api.middleware.rate_limit import SlidingWindowRateLimiter
from collectai.api.routers._chat_views import conversation_view, intent_summary, message_view
from collectai.api.routers.me_ownership import LimitQuery, OffsetQuery, paginate, require_owned
from collectai.api.schemas.chat import (
    ChatTurnResponse,
    ConversationCreateRequest,
    ConversationCreateResult,
    ConversationDetail,
    ConversationPage,
    MessageCreateRequest,
)
from collectai.application import chat_flow
from collectai.config.settings import Settings
from collectai.llm_provider.base import LlmProvider
from collectai.llm_provider.factory import get_provider
from collectai.persistence.orm.account import AccountOrm
from collectai.persistence.orm.conversation import ConversationOrm
from collectai.persistence.repositories.chat_message_repository import ChatMessageRepository
from collectai.persistence.repositories.conversation_repository import ConversationRepository
from collectai.types.enums import LlmMode, ProviderMode

router = APIRouter(prefix="/api/chat", tags=["Chat"])

_CHAT_USE: Final[dict[str, str]] = {"x-capability": "chat:use"}

_conversation_repo = ConversationRepository()
_chat_message_repo = ChatMessageRepository()
_rate_limiter = SlidingWindowRateLimiter()

_require_chat_use = require_capability("chat:use")

_FALLBACK_SETTINGS: Final[Settings] = Settings(
    llm_mode=LlmMode.MOCK,
    anthropic_model=None,
    anthropic_api_key=None,
    tool_call_cap_per_turn=5,
    ai_retry_bound=1,
    max_clarification_turns=2,
    chat_rate_limit_per_minute=20,
    api_rate_limit_per_minute=300,
    provider_timeout_seconds=20,
    proposal_ttl_minutes=30,
    demo_controls_enabled=False,
    database_url="",
)


def get_settings(request: Request) -> Settings:
    existing = getattr(request.app.state, "settings", None)
    return existing if isinstance(existing, Settings) else _FALLBACK_SETTINGS


SettingsDep = Annotated[Settings, Depends(get_settings)]


def get_llm_provider(request: Request, settings: SettingsDep) -> LlmProvider:
    """The `LlmProvider` for this request. Tests script deterministic
    `MockProvider` responses per call by setting `app.state.chat_llm_provider`
    directly (the same "compose `app.state` further from a test module"
    pattern this module's own docstring already uses for `app.state.settings`
    -- a real integration pass is expected to leave this attribute unset,
    falling back to `llm_provider.factory.get_provider(settings)` as it does
    today)."""
    existing = getattr(request.app.state, "chat_llm_provider", None)
    if existing is not None:
        return cast(LlmProvider, existing)
    return get_provider(settings)


ChatLlmProviderDep = Annotated[LlmProvider, Depends(get_llm_provider)]


def _extract_customer_id(persona_context: PersonaContext) -> str:
    assert persona_context.customer_id is not None  # noqa: S101 - only CUSTOMER holds chat:use
    return persona_context.customer_id


async def _bound_customer_id(
    persona_context: Annotated[PersonaContext, Depends(_require_chat_use)],
) -> str:
    return _extract_customer_id(persona_context)


ChatBoundCustomerId = Annotated[str, Depends(_bound_customer_id)]


async def _rate_limited_customer_id(
    clock: ClockDep,
    settings: SettingsDep,
    persona_context: Annotated[PersonaContext, Depends(_require_chat_use)],
) -> str:
    """AC6: the messages endpoint alone carries the `CHAT_RATE_LIMIT_PER_MINUTE`
    sliding window (the other three chat endpoints use the generic
    API-wide limit, which is not this story's concern)."""
    customer_id = _extract_customer_id(persona_context)
    key = persona_context.session_token_hash or customer_id
    decision = _rate_limiter.check(key, clock.now(), settings.chat_rate_limit_per_minute)
    if not decision.allowed:
        raise RateLimitedError(retry_after_seconds=decision.retry_after_seconds)
    return customer_id


RateLimitedCustomerId = Annotated[str, Depends(_rate_limited_customer_id)]


@router.post(
    "/conversations",
    response_model=ConversationCreateResult,
    status_code=status.HTTP_201_CREATED,
    openapi_extra=_CHAT_USE,
)
async def create_conversation_endpoint(
    body: ConversationCreateRequest,
    request: Request,
    db: DbSession,
    clock: ClockDep,
    audit_service: AuditServiceDep,
    customer_id: ChatBoundCustomerId,
) -> ConversationCreateResult:
    account = await require_owned(
        db, request, audit_service, customer_id, AccountOrm, AccountOrm.account_id, body.account_id
    )
    outcome = await chat_flow.create_conversation(
        db, customer_id=customer_id, account_id=account.account_id, clock=clock
    )
    await db.commit()
    return ConversationCreateResult(
        conversation=conversation_view(outcome.conversation),
        greeting=message_view(outcome.greeting),
        talk_to_human_available=True,
    )


@router.get("/conversations", response_model=ConversationPage, openapi_extra=_CHAT_USE)
async def list_conversations_endpoint(
    db: DbSession,
    customer_id: ChatBoundCustomerId,
    limit: LimitQuery = 20,
    offset: OffsetQuery = 0,
) -> ConversationPage:
    rows = sorted(
        await _conversation_repo.list_by_customer(db, customer_id),
        key=lambda row: row.created_at,
        reverse=True,
    )
    page_rows, page_info = paginate(rows, limit, offset)
    return ConversationPage(items=[conversation_view(row) for row in page_rows], page=page_info)


@router.get(
    "/conversations/{conversation_id}", response_model=ConversationDetail, openapi_extra=_CHAT_USE
)
async def get_conversation_endpoint(
    conversation_id: str,
    request: Request,
    db: DbSession,
    audit_service: AuditServiceDep,
    customer_id: ChatBoundCustomerId,
) -> ConversationDetail:
    conversation = await require_owned(
        db,
        request,
        audit_service,
        customer_id,
        ConversationOrm,
        ConversationOrm.conversation_id,
        conversation_id,
    )
    messages = await _chat_message_repo.list_by_conversation_for_customer(
        db, conversation_id, customer_id
    )
    return ConversationDetail(
        conversation=conversation_view(conversation),
        messages=[message_view(row) for row in messages],
    )


@router.post(
    "/conversations/{conversation_id}/messages",
    response_model=ChatTurnResponse,
    openapi_extra=_CHAT_USE,
)
async def send_message_endpoint(
    conversation_id: str,
    body: MessageCreateRequest,
    request: Request,
    db: DbSession,
    clock: ClockDep,
    audit_service: AuditServiceDep,
    settings: SettingsDep,
    provider: ChatLlmProviderDep,
    customer_id: RateLimitedCustomerId,
) -> ChatTurnResponse:
    conversation = await require_owned(
        db,
        request,
        audit_service,
        customer_id,
        ConversationOrm,
        ConversationOrm.conversation_id,
        conversation_id,
    )
    provider_mode = ProviderMode(settings.llm_mode.value)
    outcome = await chat_flow.process_customer_message(
        db,
        conversation=conversation,
        customer_id=customer_id,
        content=body.content,
        clock=clock,
        correlation_id=resolve_correlation_id(request),
        provider=provider,
        provider_mode=provider_mode,
        audit_service=audit_service,
        ai_retry_bound=settings.ai_retry_bound,
        max_clarification_turns=settings.max_clarification_turns,
    )
    await db.commit()
    return ChatTurnResponse(
        conversation_id=conversation.conversation_id,
        turn_id=outcome.turn.turn_id,
        customer_message=message_view(outcome.customer_message),
        assistant_message=message_view(outcome.assistant_message),
        intent=intent_summary(outcome.intent),
        safe_state=outcome.safe_state,
        talk_to_human_available=True,
        correlation_id=outcome.turn.correlation_id,
        escalation_reported=outcome.escalation_reported,
        escalation_reason=outcome.escalation_reason,
    )
