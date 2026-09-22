"""Shared FastAPI dependencies. Kept separate from `app.py` so routers can
import `DbSession` without an import cycle back through `app.py`.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession


async def get_db(request: Request) -> AsyncIterator[AsyncSession]:
    """Per-request session, built from the session factory `lifespan`
    stores on `app.state` (see `api/app.py`). Never construct a session
    manually per request."""
    session_factory = request.app.state.session_factory
    async with session_factory() as session:
        yield session


DbSession = Annotated[AsyncSession, Depends(get_db)]
