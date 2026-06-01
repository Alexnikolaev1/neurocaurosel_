"""HTTP helpers — fresh AsyncClient per Vercel invocation (no cross-loop cache)."""

from __future__ import annotations

from contextlib import asynccontextmanager
from collections.abc import AsyncIterator

import httpx

from bot.config import Settings


@asynccontextmanager
async def http_session(settings: Settings) -> AsyncIterator[httpx.AsyncClient]:
    """One client per carousel job; closed when the context exits."""
    async with httpx.AsyncClient(timeout=settings.request_timeout) as client:
        yield client
