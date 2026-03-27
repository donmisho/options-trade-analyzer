"""
Dashboard Routes — Phase 2.3
GET/PUT layout config per user, GET SAS URLs for media widget images.
"""

import json
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.database import DashboardLayout, DashboardMedia
from app.models.schemas import (
    DashboardLayoutSave, DashboardLayoutResponse,
    DashboardMediaResponse, MediaItem,
)
from app.models.session import get_db
from app.auth.dependencies import get_current_user
from app.core.config import settings

router = APIRouter(prefix="/dashboard", tags=["dashboard"])

# ── Default layout ─────────────────────────────────────────────────────────

DEFAULT_LAYOUT = [
    {"i": "market-overview-1", "x": 0, "y": 0, "w": 12, "h": 4,
     "minW": 4, "minH": 3, "isDraggable": False, "isResizable": False},
    {"i": "actions-1",         "x": 0, "y": 4, "w": 6,  "h": 4,
     "minW": 3, "minH": 3, "isDraggable": False, "isResizable": False},
    {"i": "pnl-strategy-1",   "x": 6, "y": 4, "w": 6,  "h": 4,
     "minW": 3, "minH": 3, "isDraggable": False, "isResizable": False},
    {"i": "positions-live-1",  "x": 0, "y": 8, "w": 4,  "h": 3,
     "minW": 2, "minH": 2, "isDraggable": False, "isResizable": False},
]

DEFAULT_WIDGETS = [
    {
        "id": "market-overview-1",
        "type": "market_overview",
        "title": "Market Overview",
        "settings": {
            "symbols": [
                {"ticker": ".DJI",  "apiSymbol": "$DJI", "label": "Dow Jones"},
                {"ticker": ".INX",  "apiSymbol": "$SPX", "label": "S&P 500"},
                {"ticker": "NDX",   "apiSymbol": "$NDX", "label": "Nasdaq 100"},
                {"ticker": "RUT",   "apiSymbol": "$RUT", "label": "Russell 2000"},
                {"ticker": "SPY",                        "label": "S&P 500 ETF"},
                {"ticker": "QQQ",                        "label": "Nasdaq 100 ETF"},
                {"ticker": "DIA",                        "label": "Dow Jones ETF"},
                {"ticker": "IWM",                        "label": "Russell 2000 ETF"},
                {"ticker": "VIX",   "apiSymbol": "$VIX", "label": "VIX", "noYtd": True},
            ]
        }
    },
    {
        "id": "actions-1",
        "type": "actions",
        "title": "Today's Actions",
        "settings": {
            "profit_target_pct": 0.90,
            "dte_exit_threshold": 7,
            "health_alert_grade": "D",
        }
    },
    {
        "id": "pnl-strategy-1",
        "type": "pnl_by_strategy",
        "title": "P&L by Strategy",
        "settings": {}
    },
    {
        "id": "positions-live-1",
        "type": "positions_live",
        "title": "Active Positions",
        "settings": {}
    },
]

# ── Idempotent widget injection ─────────────────────────────────────────────
# New widgets added here are automatically injected into existing saved layouts
# that don't already have them. Append entries as new widgets are introduced.
_ALWAYS_PRESENT = [
    {
        "widget": {
            "id": "positions-live-1",
            "type": "positions_live",
            "title": "Active Positions",
            "settings": {},
        },
        "layout": {"i": "positions-live-1", "x": 0, "y": 8, "w": 4, "h": 3,
                   "minW": 2, "minH": 2, "isDraggable": False, "isResizable": False},
    },
]


def _inject_missing_widgets(layout: list, widgets: list) -> tuple[list, list]:
    """Add any _ALWAYS_PRESENT widgets not yet in the saved layout (idempotent)."""
    existing_ids = {w["id"] for w in widgets}
    for entry in _ALWAYS_PRESENT:
        if entry["widget"]["id"] not in existing_ids:
            layout = layout + [entry["layout"]]
            widgets = widgets + [entry["widget"]]
    return layout, widgets


# ── Layout endpoints ───────────────────────────────────────────────────────

@router.get("", response_model=DashboardLayoutResponse)
async def get_layout(
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    result = await db.execute(
        select(DashboardLayout).where(DashboardLayout.user_id == current_user["sub"])
    )
    record = result.scalar_one_or_none()

    if not record:
        return DashboardLayoutResponse(
            layout=DEFAULT_LAYOUT,
            widgets=DEFAULT_WIDGETS,
            updated_at=None,
        )

    layout  = json.loads(record.layout_json)
    widgets = json.loads(record.widgets_json)
    layout, widgets = _inject_missing_widgets(layout, widgets)

    return DashboardLayoutResponse(
        layout=layout,
        widgets=widgets,
        updated_at=record.updated_at,
    )


@router.put("", response_model=DashboardLayoutResponse)
async def save_layout(
    payload: DashboardLayoutSave,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    result = await db.execute(
        select(DashboardLayout).where(DashboardLayout.user_id == current_user["sub"])
    )
    record = result.scalar_one_or_none()

    layout_json = json.dumps([item.model_dump() for item in payload.layout])
    widgets_json = json.dumps([w.model_dump() for w in payload.widgets])

    if record:
        record.layout_json = layout_json
        record.widgets_json = widgets_json
        record.updated_at = datetime.utcnow()
    else:
        record = DashboardLayout(
            user_id=current_user["sub"],
            layout_json=layout_json,
            widgets_json=widgets_json,
        )
        db.add(record)

    await db.commit()
    await db.refresh(record)

    return DashboardLayoutResponse(
        layout=json.loads(record.layout_json),
        widgets=json.loads(record.widgets_json),
        updated_at=record.updated_at,
    )


# ── Media endpoints ────────────────────────────────────────────────────────

def _generate_sas_url(blob_name: str) -> str:
    """
    Generate a short-lived SAS URL for a blob using DefaultAzureCredential
    (Managed Identity in Azure, local credential chain in dev).

    Requires Storage Blob Delegator role on the storage account.
    Falls back to a placeholder if Azure credentials are not available (local dev).
    """
    try:
        from azure.storage.blob import BlobServiceClient, generate_blob_sas, BlobSasPermissions
        from azure.identity import DefaultAzureCredential

        account_name = settings.azure_storage_account_name
        container = settings.azure_storage_dashboard_container
        expiry = datetime.now(timezone.utc) + timedelta(
            minutes=settings.azure_storage_sas_expiry_minutes
        )

        credential = DefaultAzureCredential()
        blob_service = BlobServiceClient(
            account_url=f"https://{account_name}.blob.core.windows.net",
            credential=credential,
        )

        udk = blob_service.get_user_delegation_key(
            key_start_time=datetime.now(timezone.utc),
            key_expiry_time=expiry,
        )

        sas_token = generate_blob_sas(
            account_name=account_name,
            container_name=container,
            blob_name=blob_name,
            user_delegation_key=udk,
            permission=BlobSasPermissions(read=True),
            expiry=expiry,
        )

        return f"https://{account_name}.blob.core.windows.net/{container}/{blob_name}?{sas_token}"

    except Exception as e:
        # In dev without Azure Blob credentials, return a placeholder so the
        # widget renders gracefully rather than crashing the endpoint.
        return f"/api/v1/dashboard/media-placeholder?blob={blob_name}&err={str(e)[:60]}"


@router.get("/media/{widget_id}", response_model=DashboardMediaResponse)
async def get_media(
    widget_id: str,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Return media items for a widget with short-lived SAS URLs.
    Called by MediaWidget on mount and on its 14-minute refresh timer.
    """
    result = await db.execute(
        select(DashboardMedia)
        .where(DashboardMedia.widget_id == widget_id)
        .order_by(DashboardMedia.sort_order)
    )
    rows = result.scalars().all()

    items = [
        MediaItem(
            id=row.id,
            blob_name=row.blob_name,
            caption=row.caption,
            sort_order=row.sort_order,
            sas_url=_generate_sas_url(row.blob_name),
        )
        for row in rows
    ]

    return DashboardMediaResponse(widget_id=widget_id, items=items)
