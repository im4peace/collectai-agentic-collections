"""`python -m collectai.bootstrap.cli break-ptps` (E6-S4 AC4).

A thin wrapper: opens one transaction, runs
`domain_services.ptp_lifecycle.run_breakage_job` under a fresh, real
`SystemClock`/`AuditService`/`PolicyProvider` (via `bootstrap.main
.run_startup_validation`, the same fail-closed policy-loading path the ASGI
app itself uses), commits, and reports the counts. No breakage-rule logic
lives here.
"""

from __future__ import annotations

import uuid

from collectai.audit.service import AuditService
from collectai.bootstrap.main import run_startup_validation
from collectai.domain_services.ptp_lifecycle import BreakageJobResult, run_breakage_job
from collectai.persistence.db import build_engine, build_session_factory
from collectai.types.clock import SystemClock


async def run(database_url: str) -> BreakageJobResult:
    validation = run_startup_validation()
    clock = SystemClock()
    engine = build_engine(database_url)
    try:
        session_factory = build_session_factory(engine)
        audit_service = AuditService(clock, session_factory)
        async with session_factory() as session:
            result = await run_breakage_job(
                session,
                policy=validation.policy_provider.get_active(),
                clock=clock,
                audit_service=audit_service,
                correlation_id=uuid.uuid4().hex,
            )
            await session.commit()
        return result
    finally:
        await engine.dispose()
