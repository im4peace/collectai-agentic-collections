"""EvalCaseResult ORM table (data-models.md EvalCaseResult, E10-S1). Maps to
`eval_case_result`. One row per case in one `EvalRun`, written by
`collectai_eval.store`."""

from __future__ import annotations

from sqlalchemy import Boolean, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from collectai.persistence.orm.base import Base


class EvalCaseResultOrm(Base):
    __tablename__ = "eval_case_result"

    eval_case_result_id: Mapped[str] = mapped_column(Text, primary_key=True)
    eval_run_id: Mapped[str] = mapped_column(Text)
    case_id: Mapped[str] = mapped_column(Text)
    category: Mapped[str] = mapped_column(Text)
    expected: Mapped[dict[str, object]] = mapped_column(JSONB)
    actual: Mapped[dict[str, object]] = mapped_column(JSONB)
    passed: Mapped[bool] = mapped_column(Boolean)
    critical_policy_violation: Mapped[bool] = mapped_column(Boolean)
