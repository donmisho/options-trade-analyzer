# All endpoints in this file must filter by user_id.
# See architecture-plan.md § 2 (Data Isolation Invariant).
# Cross-user attempts return 404 (not 403) to avoid leaking existence.

"""
User configuration endpoints: get and update analysis preferences.

These are Tier 2 (write) — requires MFA-verified session.
Each user has their own config (scoring weights, filters, risk settings).
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.database import UserConfig, AuditLog
from app.models.session import get_db
from app.models.schemas import UserConfigUpdate, UserConfigResponse
from app.auth.dependencies import require_read, require_write

router = APIRouter(prefix="/config", tags=["Configuration"])


@router.get("", response_model=UserConfigResponse)
async def get_config(
    user: dict = Depends(require_read),
    db: AsyncSession = Depends(get_db),
):
    """
    Get the current user's analysis configuration.
    
    Returns all scoring weights, filter settings, and risk parameters.
    This is the equivalent of the Setup sheet's B28-B80 cells.
    """
    result = await db.execute(
        select(UserConfig).where(UserConfig.user_id == user["sub"])
    )
    config = result.scalar_one_or_none()
    if not config:
        raise HTTPException(status_code=404, detail="Config not found")

    return UserConfigResponse(
        default_symbol=config.default_symbol,
        min_dte=config.min_dte,
        max_dte=config.max_dte,
        strike_range_pct=config.strike_range_pct,
        min_open_interest=config.min_open_interest,
        min_volume=config.min_volume,
        min_spread_width=config.min_spread_width,
        max_spread_width=config.max_spread_width,
        weight_expected_value=config.weight_expected_value,
        weight_reward_risk=config.weight_reward_risk,
        weight_probability=config.weight_probability,
        weight_liquidity=config.weight_liquidity,
        max_risk_per_trade=config.max_risk_per_trade,
        profit_target_pct=config.profit_target_pct,
        stop_loss_pct=config.stop_loss_pct,
        extra_settings=config.extra_settings or {},
        updated_at=config.updated_at,
    )


@router.put("", response_model=UserConfigResponse)
async def update_config(
    payload: UserConfigUpdate,
    user: dict = Depends(require_write),
    db: AsyncSession = Depends(get_db),
):
    """
    Update analysis configuration. Only provided fields are changed.
    
    WHY partial updates: You might want to change just your scoring weights
    without touching your DTE filters. Sending only the fields you want to
    change keeps it simple.
    
    Validates that scoring weights sum to 1.0 if any weight is changed.
    """
    result = await db.execute(
        select(UserConfig).where(UserConfig.user_id == user["sub"])
    )
    config = result.scalar_one_or_none()
    if not config:
        raise HTTPException(status_code=404, detail="Config not found")

    # Track what changed for audit log
    changes = {}
    update_data = payload.model_dump(exclude_unset=True)

    for field, new_value in update_data.items():
        old_value = getattr(config, field, None)
        if old_value != new_value:
            changes[field] = {"old": old_value, "new": new_value}
            setattr(config, field, new_value)

    # Validate scoring weights sum to 1.0 if any weight was changed
    weight_fields = [
        "weight_expected_value", "weight_reward_risk",
        "weight_probability", "weight_liquidity",
    ]
    if any(f in changes for f in weight_fields):
        total = (
            config.weight_expected_value
            + config.weight_reward_risk
            + config.weight_probability
            + config.weight_liquidity
        )
        if abs(total - 1.0) > 0.001:
            raise HTTPException(
                status_code=400,
                detail=f"Scoring weights must sum to 1.0 (current sum: {total:.3f})",
            )

    if changes:
        # Audit log with before/after values
        db.add(AuditLog(
            user_id=user["sub"],
            event_type="config_change",
            detail=changes,
        ))
        await db.commit()
        await db.refresh(config)

    return UserConfigResponse(
        default_symbol=config.default_symbol,
        min_dte=config.min_dte,
        max_dte=config.max_dte,
        strike_range_pct=config.strike_range_pct,
        min_open_interest=config.min_open_interest,
        min_volume=config.min_volume,
        min_spread_width=config.min_spread_width,
        max_spread_width=config.max_spread_width,
        weight_expected_value=config.weight_expected_value,
        weight_reward_risk=config.weight_reward_risk,
        weight_probability=config.weight_probability,
        weight_liquidity=config.weight_liquidity,
        max_risk_per_trade=config.max_risk_per_trade,
        profit_target_pct=config.profit_target_pct,
        stop_loss_pct=config.stop_loss_pct,
        extra_settings=config.extra_settings or {},
        updated_at=config.updated_at,
    )
