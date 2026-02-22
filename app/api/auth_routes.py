"""
Authentication endpoints: register, login, MFA setup, MFA verify.

Flow:
  1. POST /register (with invite code) → creates account
  2. POST /login (username + password) → returns JWT with mfa_required=True
  3. POST /mfa/setup (first time) → returns QR code URI
  4. POST /mfa/verify (TOTP code) → returns JWT with mfa=True
"""

import uuid
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.database import User, UserConfig, AuditLog
from app.models.session import get_db
from app.models.schemas import (
    UserCreate, UserLogin, TOTPVerify, TokenResponse, 
    UserResponse, MFASetupResponse,
)
from app.auth.service import AuthService
from app.auth.dependencies import (
    get_auth_service, get_current_user, require_write, get_secrets_manager,
)
from app.core.secrets import SecretsManager

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["Authentication"])

# Hardcoded for now — move to config/db later
VALID_INVITE_CODES = {"EARLY-ACCESS-2026"}


@router.post("/register", response_model=UserResponse, status_code=201)
async def register(
    payload: UserCreate,
    db: AsyncSession = Depends(get_db),
    auth: AuthService = Depends(get_auth_service),
):
    """
    Create a new account. Requires a valid invite code.
    
    WHY invite codes: No open registration. You control exactly who
    has access. Generate codes for friends/family as needed.
    """
    # Validate invite code
    if payload.invite_code not in VALID_INVITE_CODES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid invite code",
        )

    # Check for existing user
    result = await db.execute(
        select(User).where(
            (User.username == payload.username) | (User.email == payload.email)
        )
    )
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Username or email already registered",
        )

    # Create user
    user_id = str(uuid.uuid4())
    user = User(
        id=user_id,
        username=payload.username,
        email=payload.email,
        password_hash=auth.hash_password(payload.password),
        role="viewer",  # Default role — admin upgrades later
    )
    db.add(user)

    # Create default config for the user
    config = UserConfig(user_id=user_id)
    db.add(config)

    # Audit log
    db.add(AuditLog(
        user_id=user_id,
        event_type="register",
        detail={"username": payload.username, "email": payload.email},
    ))

    await db.commit()
    await db.refresh(user)

    return UserResponse(
        id=user.id,
        username=user.username,
        email=user.email,
        role=user.role,
        mfa_enabled=user.mfa_enabled,
        trading_enabled=user.trading_enabled,
        market_data_provider=user.market_data_provider,
        account_provider=user.account_provider,
        created_at=user.created_at,
    )


@router.post("/login", response_model=TokenResponse)
async def login(
    payload: UserLogin,
    request: Request,
    db: AsyncSession = Depends(get_db),
    auth: AuthService = Depends(get_auth_service),
):
    """
    Step 1 of login: verify username + password.
    
    If MFA is enabled, returns a token with mfa_required=True.
    The user must then call /mfa/verify with their TOTP code.
    """
    result = await db.execute(
        select(User).where(User.username == payload.username)
    )
    user = result.scalar_one_or_none()

    if not user or not auth.verify_password(payload.password, user.password_hash):
        # Audit failed login
        db.add(AuditLog(
            event_type="login_failure",
            detail={"username": payload.username},
            ip_address=request.client.host if request.client else None,
        ))
        await db.commit()

        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is disabled",
        )

    # If MFA is enabled and verified (setup complete), require TOTP
    mfa_required = user.mfa_enabled and user.mfa_verified

    token, expires_in = auth.create_access_token(
        user_id=user.id,
        username=user.username,
        role=user.role,
        mfa_verified=not mfa_required,  # True if MFA not yet set up
    )

    # Audit successful login
    db.add(AuditLog(
        user_id=user.id,
        event_type="login_success",
        detail={"mfa_required": mfa_required},
        ip_address=request.client.host if request.client else None,
    ))
    await db.commit()

    return TokenResponse(
        access_token=token,
        expires_in=expires_in,
        mfa_required=mfa_required,
    )


@router.post("/mfa/setup", response_model=MFASetupResponse)
async def mfa_setup(
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    auth: AuthService = Depends(get_auth_service),
):
    """
    Generate a TOTP secret and return QR code URI for authenticator setup.
    
    Called once — when a user first enables MFA. They scan the QR code
    with Microsoft Authenticator (or any TOTP app), then call /mfa/verify
    to confirm it's working.
    """
    result = await db.execute(select(User).where(User.id == user["sub"]))
    db_user = result.scalar_one_or_none()
    if not db_user:
        raise HTTPException(status_code=404, detail="User not found")

    # Generate TOTP secret and store in Key Vault
    qr_uri = auth.generate_totp_secret(db_user.id, db_user.email)

    # Mark MFA as enabled (but not yet verified — that happens after first TOTP confirm)
    db_user.mfa_enabled = True
    db.add(AuditLog(
        user_id=db_user.id,
        event_type="mfa_setup",
        detail={"status": "secret_generated"},
    ))
    await db.commit()

    return MFASetupResponse(qr_code_uri=qr_uri)


@router.post("/mfa/verify", response_model=TokenResponse)
async def mfa_verify(
    payload: TOTPVerify,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    auth: AuthService = Depends(get_auth_service),
):
    """
    Verify a TOTP code and issue a fully-authenticated token.
    
    Used for:
      1. Completing login when MFA is required
      2. First-time MFA confirmation after setup
    """
    if not auth.verify_totp(user["sub"], payload.totp_code):
        db.add(AuditLog(
            user_id=user["sub"],
            event_type="mfa_verify_failure",
        ))
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid authenticator code",
        )

    # Mark MFA as verified (first time only)
    result = await db.execute(select(User).where(User.id == user["sub"]))
    db_user = result.scalar_one_or_none()
    if db_user and not db_user.mfa_verified:
        db_user.mfa_verified = True
        await db.commit()

    # Issue new token with mfa=True
    token, expires_in = auth.create_access_token(
        user_id=user["sub"],
        username=user["username"],
        role=user["role"],
        mfa_verified=True,
    )

    db.add(AuditLog(
        user_id=user["sub"],
        event_type="mfa_verify_success",
    ))
    await db.commit()

    return TokenResponse(
        access_token=token,
        expires_in=expires_in,
        mfa_required=False,
    )


@router.get("/me", response_model=UserResponse)
async def get_profile(
    user: dict = Depends(require_write),
    db: AsyncSession = Depends(get_db),
):
    """Get the current user's profile. Requires MFA-verified session."""
    result = await db.execute(select(User).where(User.id == user["sub"]))
    db_user = result.scalar_one_or_none()
    if not db_user:
        raise HTTPException(status_code=404, detail="User not found")

    return UserResponse(
        id=db_user.id,
        username=db_user.username,
        email=db_user.email,
        role=db_user.role,
        mfa_enabled=db_user.mfa_enabled,
        trading_enabled=db_user.trading_enabled,
        market_data_provider=db_user.market_data_provider,
        account_provider=db_user.account_provider,
        created_at=db_user.created_at,
    )
