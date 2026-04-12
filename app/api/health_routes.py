"""
Detailed Health Endpoint (OTA-441)

GET /api/v1/health/detailed — component-level status with latency.

No auth required — this is called during frontend startup before the user
is fully authenticated.
"""

import time
import logging
from typing import Optional

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import text

from app.models.session import async_session

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Health"])

# Injected at startup by init_health_routes()
_startup_time: float | None = None
_token_manager = None


def init_health_routes(startup_time: float, token_manager) -> None:
    """Called once at app startup to inject timing baseline and Schwab token manager."""
    global _startup_time, _token_manager
    _startup_time = startup_time
    _token_manager = token_manager


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class ComponentHealth(BaseModel):
    status: str  # "connected" | "disconnected" | "error"
    latency_ms: Optional[int] = None
    message: Optional[str] = None


class DetailedHealthResponse(BaseModel):
    status: str  # "healthy" | "degraded" | "unhealthy"
    uptime_seconds: float
    components: dict[str, ComponentHealth]


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------

@router.get("/health/detailed", response_model=DetailedHealthResponse)
async def health_detailed():
    """
    Component-level health check with latency measurements.

    Returns status for database and Schwab. No auth required.
    """
    components: dict[str, ComponentHealth] = {}
    overall_status = "healthy"

    # --- Database ---
    db_start = time.monotonic()
    try:
        async with async_session() as session:
            await session.execute(text("SELECT 1"))
        db_latency = int((time.monotonic() - db_start) * 1000)
        components["database"] = ComponentHealth(status="connected", latency_ms=db_latency)
    except Exception as e:
        db_latency = int((time.monotonic() - db_start) * 1000)
        components["database"] = ComponentHealth(
            status="error", latency_ms=db_latency, message=str(e)
        )
        overall_status = "unhealthy"

    # --- Schwab ---
    schwab_start = time.monotonic()
    try:
        if _token_manager is None:
            raise RuntimeError("Token manager not initialized")
        status = _token_manager.get_status()
        schwab_latency = int((time.monotonic() - schwab_start) * 1000)
        if status.get("connected"):
            components["schwab"] = ComponentHealth(status="connected", latency_ms=schwab_latency)
        else:
            components["schwab"] = ComponentHealth(
                status="disconnected", latency_ms=schwab_latency
            )
            if overall_status == "healthy":
                overall_status = "degraded"
    except Exception as e:
        schwab_latency = int((time.monotonic() - schwab_start) * 1000)
        components["schwab"] = ComponentHealth(
            status="error", latency_ms=schwab_latency, message=str(e)
        )
        if overall_status == "healthy":
            overall_status = "degraded"

    uptime = round(time.monotonic() - _startup_time, 1) if _startup_time is not None else 0.0

    return DetailedHealthResponse(
        status=overall_status,
        uptime_seconds=uptime,
        components=components,
    )
