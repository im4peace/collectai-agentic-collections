"""Persists one `EvalRunResult` as `eval_run` + `eval_case_result` rows
(E10-S1 AC2, AC4). Both tables are ordinary business tables (full INSERT/
SELECT/UPDATE for `collectai_app`, `deploy/db/init-roles.sql`) -- but this
module still never issues an UPDATE: the run's final, already-aggregated
metrics are known before either table is touched, so one INSERT per row is
sufficient and this avoids the class of bug migration 0008/0009 fixed for
two other insert-order assumptions in Group G/H.
"""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from collectai.persistence.orm.eval_case_result import EvalCaseResultOrm
from collectai.persistence.orm.eval_run import EvalRunOrm
from collectai.types.ids import EntityPrefix, generate_id
from collectai_eval.schemas import EvalRunResult


async def store_eval_run(session: AsyncSession, result: EvalRunResult) -> str:
    """Insert the `eval_run` row and every `eval_case_result` row in one
    transaction, then commit. Returns the new `eval_run_id`."""
    eval_run_id = generate_id(EntityPrefix.EVAL_RUN)
    run_row = EvalRunOrm(
        eval_run_id=eval_run_id,
        mode=result.mode,
        dataset_version=result.dataset_version,
        dataset_provenance=result.dataset_provenance,
        model_id=result.model_id,
        prompt_version=result.prompt_version,
        policy_version=result.policy_version,
        run_at=result.run_at,
        case_count=result.case_count,
        intent_accuracy=Decimal(str(result.metrics["accuracy"])),
        metrics=result.metrics,
        input_tokens=result.token_usage.input_tokens if result.token_usage else None,
        output_tokens=result.token_usage.output_tokens if result.token_usage else None,
        estimated_cost_usd=(
            Decimal(str(result.estimated_cost_usd))
            if result.estimated_cost_usd is not None
            else None
        ),
        triggered_by=result.triggered_by,
    )
    session.add(run_row)
    await session.flush()

    for case_result in result.case_results:
        session.add(
            EvalCaseResultOrm(
                eval_case_result_id=generate_id(EntityPrefix.EVAL_CASE_RESULT),
                eval_run_id=eval_run_id,
                case_id=case_result.case_id,
                category=case_result.category,
                expected=case_result.expected,
                actual=case_result.actual,
                passed=case_result.passed,
                critical_policy_violation=case_result.critical_policy_violation,
            )
        )
    await session.commit()
    return eval_run_id
