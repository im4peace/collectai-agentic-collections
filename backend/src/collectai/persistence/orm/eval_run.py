"""EvalRun ORM table (data-models.md EvalRun, E10-S1). Maps to `eval_run`.

One row per evaluation run (MOCK or LIVE), written by `collectai_eval.store`
-- production code (this ORM class) that `collectai_eval` imports, never the
reverse (`tests/architecture/test_e10_s1_eval_isolation.py`)."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import Integer, Numeric, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from collectai.persistence.orm.base import Base
from collectai.persistence.orm.columns import TIMESTAMPTZ


class EvalRunOrm(Base):
    __tablename__ = "eval_run"

    eval_run_id: Mapped[str] = mapped_column(Text, primary_key=True)
    mode: Mapped[str] = mapped_column(Text)
    dataset_version: Mapped[str] = mapped_column(Text)
    dataset_provenance: Mapped[dict[str, object]] = mapped_column(JSONB)
    model_id: Mapped[str | None] = mapped_column(Text, default=None)
    prompt_version: Mapped[str] = mapped_column(Text)
    policy_version: Mapped[str] = mapped_column(Text)
    run_at: Mapped[datetime] = mapped_column(TIMESTAMPTZ)
    case_count: Mapped[int] = mapped_column(Integer)
    intent_accuracy: Mapped[Decimal | None] = mapped_column(Numeric(9, 4), default=None)
    metrics: Mapped[dict[str, object]] = mapped_column(JSONB)
    input_tokens: Mapped[int | None] = mapped_column(Integer, default=None)
    output_tokens: Mapped[int | None] = mapped_column(Integer, default=None)
    estimated_cost_usd: Mapped[Decimal | None] = mapped_column(Numeric(12, 6), default=None)
    triggered_by: Mapped[str] = mapped_column(Text)
