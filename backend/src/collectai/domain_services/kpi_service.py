"""KPI aggregation (E10-S3; api-contracts.md 3.13). Read-only: every figure
here is a `SELECT`-only aggregate over already-written tables, never a write
path, and every KPI's `data_label`/`claim_status` makes explicit whether a
number is illustrative synthetic data, a MOCK regression figure or a LIVE
evaluation result (CLAUDE.md: "never trust free-form LLM output for
business-critical actions" -- these are deterministic aggregates, not model
output).

This module never imports `collectai_eval` (`tests/architecture/
test_e10_s1_eval_isolation.py` forbids every `collectai.*` file from doing
so -- eval is the one *upward*-only layer). The AI-quality KPIs below read
`EvalRunOrm`/`EvalCaseResultOrm` rows directly and re-derive the same
30-case/target-threshold claim logic `collectai_eval.reporting_rules`
already established for the eval report, duplicated deliberately rather than
imported.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Final

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from collectai.config.policy.provider import PolicyProvider
from collectai.persistence.orm.delinquency import DelinquencyRecordOrm
from collectai.persistence.orm.dispute import DisputeOrm
from collectai.persistence.orm.escalation_case import EscalationCaseOrm
from collectai.persistence.orm.eval_case_result import EvalCaseResultOrm
from collectai.persistence.orm.eval_run import EvalRunOrm
from collectai.persistence.orm.hardship_case import HardshipCaseOrm
from collectai.persistence.orm.payment_arrangement import PaymentArrangementOrm
from collectai.persistence.orm.payment_event import PaymentEventOrm
from collectai.persistence.orm.promise_to_pay import PromiseToPayOrm
from collectai.persistence.orm.recommendation import RecommendationOrm
from collectai.types.clock import Clock
from collectai.types.enums import ClaimStatus, DataLabel, KpiUnit, Persona
from collectai.types.money import Money
from collectai.types.results import PolicyUnavailable

_MIN_CASES_FOR_CLAIM: Final[int] = 30
"""Mirrors `collectai_eval.reporting_rules.MIN_CASES_FOR_CLAIM` -- see the
module docstring for why this is a deliberate duplication, not an import."""
_OVERALL_ACCURACY_TARGET: Final[Decimal] = Decimal("0.90")
_CATEGORY_RECALL_TARGET: Final[Decimal] = Decimal("0.95")
_SENSITIVE_CATEGORIES: Final[tuple[str, ...]] = (
    "FINANCIAL_HARDSHIP",
    "DISPUTE",
    "REQUEST_HUMAN",
)
"""MVP_REQUIREMENTS.md Epic 10: "Sensitive-category recall (hardship,
dispute, human request)" -- exactly these three intent categories."""

_OPEN_CASE_STATUSES: Final[tuple[str, ...]] = ("OPEN", "IN_REVIEW", "AWAITING_INFORMATION")
_SETTLED_PTP_STATUSES: Final[tuple[str, ...]] = ("KEPT", "BROKEN")

_SYNTHETIC_SOURCE_NOTE: Final[str] = (
    "Computed from synthetic seed data and simulated PTP/payment/escalation "
    "events; illustrative only, not evidence of real banking outcomes."
)


@dataclass(frozen=True, slots=True)
class KpiRow:
    kpi_id: str
    name: str
    definition: str
    formula: str
    data_label: DataLabel
    owner_persona: Persona
    unit: KpiUnit
    value: str | None
    numerator: str | None
    denominator: str | None
    sample_size: int | None
    claim_status: ClaimStatus
    target: str | None
    source_note: str | None


@dataclass(frozen=True, slots=True)
class AiQualityKpiRows:
    mock: list[KpiRow]
    live: list[KpiRow]
    live_run_available: bool
    note: str


@dataclass(frozen=True, slots=True)
class KpiTree:
    generated_at: datetime
    policy_version: str | None
    business: list[KpiRow]
    operational: list[KpiRow]
    ai_quality: AiQualityKpiRows


def _ratio_string(numerator: int, denominator: int) -> str | None:
    if denominator <= 0:
        return None
    value = (Decimal(numerator) / Decimal(denominator)).quantize(
        Decimal("0.0001"), rounding=ROUND_HALF_UP
    )
    return format(value, "f")


def _ms_string(total_seconds: float, count: int) -> str | None:
    if count <= 0:
        return None
    average_ms = Decimal(str(total_seconds)) / Decimal(count) * Decimal(1000)
    return format(average_ms.quantize(Decimal("1"), rounding=ROUND_HALF_UP), "f")


async def _delinquent_account_ids(session: AsyncSession) -> set[str]:
    rows = (
        (
            await session.execute(
                select(DelinquencyRecordOrm.account_id).where(DelinquencyRecordOrm.dpd > 0)
            )
        )
        .scalars()
        .all()
    )
    return set(rows)


async def _compute_business_kpis(session: AsyncSession) -> list[KpiRow]:
    delinquent_ids = await _delinquent_account_ids(session)
    total_delinquent_accounts = len(delinquent_ids)

    overdue_total = Money("0")
    if delinquent_ids:
        overdue_rows = (
            (
                await session.execute(
                    select(DelinquencyRecordOrm.overdue_amount).where(
                        DelinquencyRecordOrm.dpd > 0
                    )
                )
            )
            .scalars()
            .all()
        )
        for amount in overdue_rows:
            overdue_total = overdue_total + amount

    succeeded_amounts = (
        (
            await session.execute(
                select(PaymentEventOrm.amount).where(PaymentEventOrm.outcome == "SUCCEEDED")
            )
        )
        .scalars()
        .all()
    )
    recovered_total = Money("0")
    for amount in succeeded_amounts:
        recovered_total = recovered_total + amount

    recovery_denominator = recovered_total.amount + overdue_total.amount
    recovery_rate = (
        format(
            (recovered_total.amount / recovery_denominator).quantize(
                Decimal("0.0001"), rounding=ROUND_HALF_UP
            ),
            "f",
        )
        if recovery_denominator > 0
        else None
    )

    ptp_account_ids = set(
        (await session.execute(select(PromiseToPayOrm.account_id))).scalars().all()
    )
    ptp_rate_numerator = len(ptp_account_ids & delinquent_ids)

    ptp_statuses = (
        (
            await session.execute(
                select(PromiseToPayOrm.status).where(
                    PromiseToPayOrm.status.in_(_SETTLED_PTP_STATUSES)
                )
            )
        )
        .scalars()
        .all()
    )
    settled_count = len(ptp_statuses)
    kept_count = sum(1 for status in ptp_statuses if status == "KEPT")

    return [
        KpiRow(
            kpi_id="total_delinquent_accounts",
            name="Total delinquent accounts",
            definition="Accounts with days-past-due greater than zero.",
            formula="count(DelinquencyRecord where dpd > 0)",
            data_label=DataLabel.ILLUSTRATIVE,
            owner_persona=Persona.COLLECTIONS_MANAGER,
            unit=KpiUnit.COUNT,
            value=str(total_delinquent_accounts),
            numerator=None,
            denominator=None,
            sample_size=total_delinquent_accounts,
            claim_status=ClaimStatus.NOT_APPLICABLE,
            target=None,
            source_note=_SYNTHETIC_SOURCE_NOTE,
        ),
        KpiRow(
            kpi_id="total_overdue_amount",
            name="Total overdue amount",
            definition="Sum of the overdue amount across every delinquent account.",
            formula="sum(DelinquencyRecord.overdue_amount where dpd > 0)",
            data_label=DataLabel.ILLUSTRATIVE,
            owner_persona=Persona.COLLECTIONS_MANAGER,
            unit=KpiUnit.CURRENCY,
            value=overdue_total.to_api_string(),
            numerator=None,
            denominator=None,
            sample_size=total_delinquent_accounts,
            claim_status=ClaimStatus.NOT_APPLICABLE,
            target=None,
            source_note=_SYNTHETIC_SOURCE_NOTE,
        ),
        KpiRow(
            kpi_id="recovered_amount",
            name="Recovered amount",
            definition="Sum of every successful simulated payment.",
            formula="sum(PaymentEvent.amount where outcome = SUCCEEDED)",
            data_label=DataLabel.ILLUSTRATIVE,
            owner_persona=Persona.COLLECTIONS_MANAGER,
            unit=KpiUnit.CURRENCY,
            value=recovered_total.to_api_string(),
            numerator=None,
            denominator=None,
            sample_size=len(succeeded_amounts),
            claim_status=ClaimStatus.NOT_APPLICABLE,
            target=None,
            source_note=_SYNTHETIC_SOURCE_NOTE,
        ),
        KpiRow(
            kpi_id="recovery_rate",
            name="Recovery rate",
            definition="Share of ever-overdue balance that has been recovered.",
            formula="recovered_amount / (recovered_amount + total_overdue_amount)",
            data_label=DataLabel.ILLUSTRATIVE,
            owner_persona=Persona.COLLECTIONS_MANAGER,
            unit=KpiUnit.RATIO,
            value=recovery_rate,
            numerator=recovered_total.to_api_string(),
            denominator=(
                format(recovery_denominator.quantize(Decimal("0.01")), "f")
                if recovery_denominator > 0
                else None
            ),
            sample_size=None,
            claim_status=ClaimStatus.NOT_APPLICABLE,
            target=None,
            source_note=_SYNTHETIC_SOURCE_NOTE,
        ),
        KpiRow(
            kpi_id="ptp_rate",
            name="Promise-to-Pay rate",
            definition="Share of delinquent accounts with at least one Promise-to-Pay.",
            formula=(
                "count(distinct delinquent accounts with a PromiseToPay) / "
                "total_delinquent_accounts"
            ),
            data_label=DataLabel.ILLUSTRATIVE,
            owner_persona=Persona.COLLECTIONS_MANAGER,
            unit=KpiUnit.RATIO,
            value=_ratio_string(ptp_rate_numerator, total_delinquent_accounts),
            numerator=str(ptp_rate_numerator),
            denominator=str(total_delinquent_accounts),
            sample_size=total_delinquent_accounts,
            claim_status=ClaimStatus.NOT_APPLICABLE,
            target=None,
            source_note=_SYNTHETIC_SOURCE_NOTE,
        ),
        KpiRow(
            kpi_id="promise_kept_rate",
            name="Promise-kept rate",
            definition="Share of settled Promises-to-Pay that were kept, not broken.",
            formula=(
                "count(PromiseToPay where status = KEPT) / "
                "count(PromiseToPay where status in (KEPT, BROKEN))"
            ),
            data_label=DataLabel.ILLUSTRATIVE,
            owner_persona=Persona.COLLECTIONS_MANAGER,
            unit=KpiUnit.RATIO,
            value=_ratio_string(kept_count, settled_count),
            numerator=str(kept_count),
            denominator=str(settled_count),
            sample_size=settled_count,
            claim_status=ClaimStatus.NOT_APPLICABLE,
            target=None,
            source_note=_SYNTHETIC_SOURCE_NOTE,
        ),
    ]


async def _compute_operational_kpis(session: AsyncSession) -> list[KpiRow]:
    delinquent_ids = await _delinquent_account_ids(session)
    total_delinquent_accounts = len(delinquent_ids)

    escalation_account_ids = set(
        (await session.execute(select(EscalationCaseOrm.account_id))).scalars().all()
    )
    escalation_rate_numerator = len(escalation_account_ids & delinquent_ids)

    open_cases = (
        (
            await session.execute(
                select(EscalationCaseOrm.created_at).where(
                    EscalationCaseOrm.status.in_(_OPEN_CASE_STATUSES)
                )
            )
        )
        .scalars()
        .all()
    )
    queue_size = len(open_cases)

    reviewed_cases = (
        (
            await session.execute(
                select(EscalationCaseOrm.created_at, EscalationCaseOrm.first_reviewed_at).where(
                    EscalationCaseOrm.first_reviewed_at.is_not(None)
                )
            )
        ).all()
    )
    time_to_review_total_seconds = sum(
        (first_reviewed_at - created_at).total_seconds()
        for created_at, first_reviewed_at in reviewed_cases
        if first_reviewed_at is not None
    )

    officer_decisions = (
        (await session.execute(select(RecommendationOrm.officer_decision).where(
            RecommendationOrm.officer_decision.is_not(None)
        )))
        .scalars()
        .all()
    )
    decided_count = len(officer_decisions)
    overridden_count = sum(1 for decision in officer_decisions if decision == "OVERRIDDEN")

    ptp_statuses = (
        (
            await session.execute(
                select(PromiseToPayOrm.status).where(
                    PromiseToPayOrm.status.in_(_SETTLED_PTP_STATUSES)
                )
            )
        )
        .scalars()
        .all()
    )
    settled_count = len(ptp_statuses)
    broken_count = sum(1 for status in ptp_statuses if status == "BROKEN")

    arrangement_account_ids = set(
        (await session.execute(select(PaymentArrangementOrm.account_id))).scalars().all()
    )
    arrangement_numerator = len(arrangement_account_ids & delinquent_ids)

    kept_ptp_account_ids = set(
        (
            await session.execute(
                select(PromiseToPayOrm.account_id).where(PromiseToPayOrm.status == "KEPT")
            )
        )
        .scalars()
        .all()
    )
    active_arrangement_account_ids = set(
        (
            await session.execute(
                select(PaymentArrangementOrm.account_id).where(
                    PaymentArrangementOrm.status.in_(("ACTIVE", "COMPLETED"))
                )
            )
        )
        .scalars()
        .all()
    )
    resolved_without_escalation = (
        (kept_ptp_account_ids | active_arrangement_account_ids) - escalation_account_ids
    ) & delinquent_ids

    hardship_case_count = (
        await session.execute(select(HardshipCaseOrm.hardship_case_id))
    ).scalars().all()
    dispute_case_count = (await session.execute(select(DisputeOrm.dispute_id))).scalars().all()

    return [
        KpiRow(
            kpi_id="escalation_rate",
            name="Escalation rate",
            definition="Share of delinquent accounts with at least one escalation case.",
            formula=(
                "count(distinct delinquent accounts with an EscalationCase) / "
                "total_delinquent_accounts"
            ),
            data_label=DataLabel.ILLUSTRATIVE,
            owner_persona=Persona.COLLECTIONS_MANAGER,
            unit=KpiUnit.RATIO,
            value=_ratio_string(escalation_rate_numerator, total_delinquent_accounts),
            numerator=str(escalation_rate_numerator),
            denominator=str(total_delinquent_accounts),
            sample_size=total_delinquent_accounts,
            claim_status=ClaimStatus.NOT_APPLICABLE,
            target=None,
            source_note=_SYNTHETIC_SOURCE_NOTE,
        ),
        KpiRow(
            kpi_id="review_queue_size",
            name="Review queue size",
            definition="Escalation cases currently open, in review or awaiting information.",
            formula="count(EscalationCase where status in (OPEN, IN_REVIEW, AWAITING_INFORMATION))",
            data_label=DataLabel.ILLUSTRATIVE,
            owner_persona=Persona.COLLECTIONS_MANAGER,
            unit=KpiUnit.COUNT,
            value=str(queue_size),
            numerator=None,
            denominator=None,
            sample_size=queue_size,
            claim_status=ClaimStatus.NOT_APPLICABLE,
            target=None,
            source_note=_SYNTHETIC_SOURCE_NOTE,
        ),
        KpiRow(
            kpi_id="average_time_to_review_ms",
            name="Average time to first review",
            definition="Average time between an escalation case being opened and first reviewed.",
            formula=(
                "avg(EscalationCase.first_reviewed_at - EscalationCase.created_at) "
                "where first_reviewed_at is not null"
            ),
            data_label=DataLabel.ILLUSTRATIVE,
            owner_persona=Persona.COLLECTIONS_MANAGER,
            unit=KpiUnit.MILLISECONDS,
            value=_ms_string(time_to_review_total_seconds, len(reviewed_cases)),
            numerator=None,
            denominator=None,
            sample_size=len(reviewed_cases),
            claim_status=ClaimStatus.NOT_APPLICABLE,
            target=None,
            source_note=_SYNTHETIC_SOURCE_NOTE,
        ),
        KpiRow(
            kpi_id="human_override_rate",
            name="Human override rate",
            definition=(
                "Share of officer-decided AI recommendations that were overridden rather "
                "than accepted."
            ),
            formula=(
                "count(Recommendation.officer_decision = OVERRIDDEN) / "
                "count(Recommendation.officer_decision is not null)"
            ),
            data_label=DataLabel.ILLUSTRATIVE,
            owner_persona=Persona.COLLECTIONS_MANAGER,
            unit=KpiUnit.RATIO,
            value=_ratio_string(overridden_count, decided_count),
            numerator=str(overridden_count),
            denominator=str(decided_count),
            sample_size=decided_count,
            claim_status=ClaimStatus.NOT_APPLICABLE,
            target=None,
            source_note=_SYNTHETIC_SOURCE_NOTE,
        ),
        KpiRow(
            kpi_id="ptp_breakage_rate",
            name="PTP breakage rate",
            definition="Share of settled Promises-to-Pay that broke rather than were kept.",
            formula=(
                "count(PromiseToPay where status = BROKEN) / "
                "count(PromiseToPay where status in (KEPT, BROKEN))"
            ),
            data_label=DataLabel.ILLUSTRATIVE,
            owner_persona=Persona.COLLECTIONS_MANAGER,
            unit=KpiUnit.RATIO,
            value=_ratio_string(broken_count, settled_count),
            numerator=str(broken_count),
            denominator=str(settled_count),
            sample_size=settled_count,
            claim_status=ClaimStatus.NOT_APPLICABLE,
            target=None,
            source_note=_SYNTHETIC_SOURCE_NOTE,
        ),
        KpiRow(
            kpi_id="self_service_resolution_rate",
            name="Self-service resolution rate",
            definition=(
                "Share of delinquent accounts resolved through a kept Promise-to-Pay or an "
                "active/completed payment arrangement without ever being escalated."
            ),
            formula=(
                "count(distinct delinquent accounts with a KEPT PromiseToPay or an "
                "ACTIVE/COMPLETED PaymentArrangement and no EscalationCase) / "
                "total_delinquent_accounts"
            ),
            data_label=DataLabel.ILLUSTRATIVE,
            owner_persona=Persona.COLLECTIONS_MANAGER,
            unit=KpiUnit.RATIO,
            value=_ratio_string(len(resolved_without_escalation), total_delinquent_accounts),
            numerator=str(len(resolved_without_escalation)),
            denominator=str(total_delinquent_accounts),
            sample_size=total_delinquent_accounts,
            claim_status=ClaimStatus.NOT_APPLICABLE,
            target=None,
            source_note=_SYNTHETIC_SOURCE_NOTE,
        ),
        KpiRow(
            kpi_id="arrangement_take_up_rate",
            name="Arrangement take-up rate",
            definition="Share of delinquent accounts with at least one payment arrangement.",
            formula=(
                "count(distinct delinquent accounts with a PaymentArrangement) / "
                "total_delinquent_accounts"
            ),
            data_label=DataLabel.ILLUSTRATIVE,
            owner_persona=Persona.COLLECTIONS_MANAGER,
            unit=KpiUnit.RATIO,
            value=_ratio_string(arrangement_numerator, total_delinquent_accounts),
            numerator=str(arrangement_numerator),
            denominator=str(total_delinquent_accounts),
            sample_size=total_delinquent_accounts,
            claim_status=ClaimStatus.NOT_APPLICABLE,
            target=None,
            source_note=_SYNTHETIC_SOURCE_NOTE,
        ),
        KpiRow(
            kpi_id="hardship_case_count",
            name="Hardship case count",
            definition="Total financial-hardship cases identified.",
            formula="count(HardshipCase)",
            data_label=DataLabel.ILLUSTRATIVE,
            owner_persona=Persona.COLLECTIONS_MANAGER,
            unit=KpiUnit.COUNT,
            value=str(len(hardship_case_count)),
            numerator=None,
            denominator=None,
            sample_size=len(hardship_case_count),
            claim_status=ClaimStatus.NOT_APPLICABLE,
            target=None,
            source_note=_SYNTHETIC_SOURCE_NOTE,
        ),
        KpiRow(
            kpi_id="dispute_case_count",
            name="Dispute case count",
            definition="Total disputes identified.",
            formula="count(Dispute)",
            data_label=DataLabel.ILLUSTRATIVE,
            owner_persona=Persona.COLLECTIONS_MANAGER,
            unit=KpiUnit.COUNT,
            value=str(len(dispute_case_count)),
            numerator=None,
            denominator=None,
            sample_size=len(dispute_case_count),
            claim_status=ClaimStatus.NOT_APPLICABLE,
            target=None,
            source_note=_SYNTHETIC_SOURCE_NOTE,
        ),
    ]


async def _latest_run(session: AsyncSession, mode: str) -> EvalRunOrm | None:
    stmt = (
        select(EvalRunOrm)
        .where(EvalRunOrm.mode == mode)
        .order_by(EvalRunOrm.run_at.desc())
        .limit(1)
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def _ai_quality_kpis_for_run(session: AsyncSession, run: EvalRunOrm) -> list[KpiRow]:
    case_rows = (
        (
            await session.execute(
                select(EvalCaseResultOrm.category, EvalCaseResultOrm.passed).where(
                    EvalCaseResultOrm.eval_run_id == run.eval_run_id
                )
            )
        ).all()
    )
    source_note = f"eval_run_id={run.eval_run_id}, dataset_version={run.dataset_version}"

    rows: list[KpiRow] = []

    if run.intent_accuracy is None:
        accuracy_status = ClaimStatus.NOT_APPLICABLE
    elif run.mode != "LIVE":
        accuracy_status = ClaimStatus.OBSERVATION_ONLY
    elif run.intent_accuracy >= _OVERALL_ACCURACY_TARGET:
        accuracy_status = ClaimStatus.PASS
    else:
        accuracy_status = ClaimStatus.FAIL
    rows.append(
        KpiRow(
            kpi_id="intent_classification_accuracy",
            name="Intent classification accuracy",
            definition=(
                "Share of evaluation cases where the AI's classified intent matched the "
                "expected intent."
            ),
            formula="passed_cases / total_cases (collectai_eval.metrics.compute_metrics)",
            data_label=DataLabel(run.mode),
            owner_persona=Persona.COLLECTIONS_MANAGER,
            unit=KpiUnit.RATIO,
            value=(format(run.intent_accuracy, "f") if run.intent_accuracy is not None else None),
            numerator=None,
            denominator=None,
            sample_size=run.case_count,
            claim_status=accuracy_status,
            target=(format(_OVERALL_ACCURACY_TARGET, "f") if run.mode == "LIVE" else None),
            source_note=source_note,
        )
    )

    by_category: dict[str, list[bool]] = {}
    for category, passed in case_rows:
        by_category.setdefault(category, []).append(passed)

    for category in _SENSITIVE_CATEGORIES:
        passed_flags = by_category.get(category)
        if passed_flags is None:
            continue
        case_count = len(passed_flags)
        recall = sum(1 for flag in passed_flags if flag) / case_count if case_count else 0.0
        recall_decimal = Decimal(str(recall)).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
        if run.mode == "LIVE" and case_count >= _MIN_CASES_FOR_CLAIM:
            status = (
                ClaimStatus.PASS if recall_decimal >= _CATEGORY_RECALL_TARGET else ClaimStatus.FAIL
            )
        else:
            status = ClaimStatus.OBSERVATION_ONLY
        rows.append(
            KpiRow(
                kpi_id=f"sensitive_category_recall_{category.lower()}",
                name=f"Sensitive-category recall: {category.replace('_', ' ').title()}",
                definition=(
                    f"Recall of the {category} intent category "
                    "(MVP Epic 10 sensitive-category recall)."
                ),
                formula="passed cases in category / total cases in category",
                data_label=DataLabel(run.mode),
                owner_persona=Persona.COLLECTIONS_MANAGER,
                unit=KpiUnit.RATIO,
                value=format(recall_decimal, "f"),
                numerator=str(sum(1 for flag in passed_flags if flag)),
                denominator=str(case_count),
                sample_size=case_count,
                claim_status=status,
                target=(format(_CATEGORY_RECALL_TARGET, "f") if run.mode == "LIVE" else None),
                source_note=source_note,
            )
        )

    return rows


async def _compute_ai_quality_kpis(session: AsyncSession) -> AiQualityKpiRows:
    mock_run = await _latest_run(session, "MOCK")
    live_run = await _latest_run(session, "LIVE")

    mock_rows = await _ai_quality_kpis_for_run(session, mock_run) if mock_run is not None else []
    live_rows = await _ai_quality_kpis_for_run(session, live_run) if live_run is not None else []

    return AiQualityKpiRows(
        mock=mock_rows,
        live=live_rows,
        live_run_available=live_run is not None,
        note=(
            "MOCK results exercise the evaluation harness against scripted responses and are "
            "never evidence of real-model quality. Only a LIVE run with at least "
            f"{_MIN_CASES_FOR_CLAIM} labelled cases in a category may claim PASS or FAIL against "
            "its target; every other figure is OBSERVATION_ONLY."
        ),
    )


async def compute_kpi_tree(
    session: AsyncSession, *, clock: Clock, policy_provider: PolicyProvider
) -> KpiTree:
    """AC1-AC6: the full `GET /api/kpis` tree. Every branch is computed
    independently so a gap in one (e.g. no eval runs yet) never prevents the
    others from returning."""
    policy_version: str | None
    try:
        policy_version = policy_provider.get_active().policy_version
    except PolicyUnavailable:
        policy_version = None

    business = await _compute_business_kpis(session)
    operational = await _compute_operational_kpis(session)
    ai_quality = await _compute_ai_quality_kpis(session)

    return KpiTree(
        generated_at=clock.now(),
        policy_version=policy_version,
        business=business,
        operational=operational,
        ai_quality=ai_quality,
    )


@dataclass(frozen=True, slots=True)
class EvalRunRow:
    eval_run_id: str
    mode: str
    dataset_version: str
    model_id: str | None
    prompt_version: str
    policy_version: str
    run_at: datetime
    case_count: int
    intent_accuracy: str | None
    estimated_cost_usd: str | None


async def list_eval_runs(
    session: AsyncSession, *, mode: str | None, limit: int, offset: int
) -> tuple[list[EvalRunRow], int]:
    """`GET /api/kpis/eval-runs`: stored `EvalRun`s, newest first."""
    stmt = select(EvalRunOrm).order_by(EvalRunOrm.run_at.desc())
    if mode is not None:
        stmt = stmt.where(EvalRunOrm.mode == mode)
    rows = (await session.execute(stmt)).scalars().all()
    total = len(rows)
    page_rows = rows[offset : offset + limit]
    return [
        EvalRunRow(
            eval_run_id=row.eval_run_id,
            mode=row.mode,
            dataset_version=row.dataset_version,
            model_id=row.model_id,
            prompt_version=row.prompt_version,
            policy_version=row.policy_version,
            run_at=row.run_at,
            case_count=row.case_count,
            intent_accuracy=(
                format(row.intent_accuracy, "f") if row.intent_accuracy is not None else None
            ),
            estimated_cost_usd=(
                format(row.estimated_cost_usd, "f")
                if row.estimated_cost_usd is not None
                else None
            ),
        )
        for row in page_rows
    ], total


__all__ = [
    "AiQualityKpiRows",
    "EvalRunRow",
    "KpiRow",
    "KpiTree",
    "compute_kpi_tree",
    "list_eval_runs",
]
