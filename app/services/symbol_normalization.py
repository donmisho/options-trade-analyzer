"""
Symbol normalization helpers — OTA-668 Phase 3b.2.

Three functions for consistent symbol handling:
- canonicalize(): inbound writes (strip $, uppercase, trim)
- to_api_symbol(): canonical → provider-specific form (DB lookup)
- from_api_symbol(): provider-specific → canonical form (reverse lookup)
"""

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.database import SymbolReference

logger = logging.getLogger(__name__)


def canonicalize(symbol: str) -> str:
    """Strip $ prefix, uppercase, strip whitespace. For inbound writes."""
    return symbol.strip().lstrip("$").upper()


async def to_api_symbol(db: AsyncSession, symbol: str, provider: str) -> str:
    """Canonical → provider-specific form. Looks up symbol_reference.api_symbol."""
    canonical = canonicalize(symbol)

    if provider == "schwab":
        result = await db.execute(
            select(SymbolReference.api_symbol).where(SymbolReference.symbol == canonical)
        )
        api_sym = result.scalar_one_or_none()
        if api_sym is not None:
            logger.debug("to_api_symbol: %s → %s (provider=%s)", canonical, api_sym, provider)
            return api_sym

    return canonical


async def from_api_symbol(db: AsyncSession, api_symbol: str) -> str:
    """Provider-specific → canonical form. Reverse lookup on api_symbol column."""
    result = await db.execute(
        select(SymbolReference.symbol).where(SymbolReference.api_symbol == api_symbol)
    )
    canonical = result.scalar_one_or_none()
    if canonical is not None:
        return canonical

    return canonicalize(api_symbol)
