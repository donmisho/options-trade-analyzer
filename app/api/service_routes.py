"""
External Services Status Route.

Returns the registry of external service providers and their connection state.
Used by the frontend's startup "Connect External Services" step.

The service list is a static registry — adding a new provider means adding
one entry here. No scattered conditionals.
"""

import logging

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from app.auth.dependencies import get_session_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/services", tags=["Services"])

# Injected at startup via init_service_routes()
_schwab_token_manager = None


def init_service_routes(token_manager):
    """Called once at app startup to inject the Schwab token manager."""
    global _schwab_token_manager
    _schwab_token_manager = token_manager


# Static registry of external service definitions.
# Fields: id, name, description, active, auth_type, login_url
# 'active' = whether this provider is enabled in this deployment.
_SERVICE_REGISTRY = [
    {
        "id": "schwab",
        "name": "Charles Schwab",
        "description": "Market Data & Trading",
        "active": True,
        "auth_type": "oauth",
        "login_url": "/api/v1/auth/schwab/login",
    },
    {
        "id": "tradier",
        "name": "Tradier",
        "description": "Market Data (Deprecated)",
        "active": False,
        "auth_type": "api_key",
        "login_url": None,
    },
]


@router.get("/status")
async def services_status(user: dict = Depends(get_session_user)):
    """
    Return the list of external services and their live connection state.

    Each service includes:
      id, name, description, active, connected, auth_type, login_url
    """
    services = []
    for svc in _SERVICE_REGISTRY:
        connected = False

        if svc["id"] == "schwab" and _schwab_token_manager is not None:
            status = _schwab_token_manager.get_status()
            connected = status.get("connected", False)

        services.append({**svc, "connected": connected})

    return JSONResponse(content={"services": services})
