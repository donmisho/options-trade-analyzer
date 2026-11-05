"""
Schwab refresh-token expiry alerting (OTA-857).

The Schwab refresh token expires 7 days after the interactive browser login, is
pinned to that login, and cannot be renewed programmatically — every silent
access-token refresh preserves the original expiry. When it lapses the
account-activity poller fails silently: `get_trade_fills` just keeps returning
the fills already stored, so a dead feed looks like "no recent trades." This
module is the early warning so stale data is never the first signal.

Two paths, both best-effort (an alert failure never blocks a poll or a request):

  * Proactive — a daily pre-open check (wired into the APScheduler fleet in
    main.py) calls `check_expiry_and_alert()`. While the token is still valid but
    within `settings.schwab_expiry_warn_seconds` of the cliff, it fires.
  * Reactive — `AccountActivitySync._finish` calls `notify_auth_error()` the
    first time a poll fails on an expired/again-reconnect refresh token (the
    caller owns the dedupe), so the very first dead poll alerts immediately.

Each path emits a loud `logger.error` with a stable, greppable prefix AND an
Application Insights span via the shared OTel tracer. An Azure Monitor alert rule
on either the log prefix or the span name turns these into email/SMS without this
app owning a mail channel (Task 3 design, OTA-857).
"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)

# The interactive re-login entry point (prod). Named in every alert so the signal
# is actionable without a lookup.
RELOGIN_URL = "https://oa.tmtctech.ai/api/v1/auth/schwab/login"

# Stable, greppable prefixes so an Azure Monitor log-query alert can match on them
# regardless of the surrounding text.
WARN_PREFIX = "SCHWAB_TOKEN_EXPIRY_WARNING"
AUTH_ERROR_PREFIX = "SCHWAB_AUTH_ERROR"


def _emit_span(name: str, attributes: dict) -> None:
    """Best-effort Application Insights custom event via the shared OTel tracer.

    No-op when telemetry is not wired (local dev without App Insights). Never
    raises — alerting must not break the caller.
    """
    try:
        from app.agents.telemetry import _tracer
        if _tracer is None:
            return
        from opentelemetry.trace import SpanKind
        with _tracer.start_as_current_span(name, kind=SpanKind.INTERNAL) as span:
            for key, value in attributes.items():
                if value is not None:
                    span.set_attribute(key, value)
    except Exception as e:  # pragma: no cover - telemetry is best-effort
        logger.debug(f"schwab expiry alert: span emit failed (non-blocking): {e}")


def check_expiry_and_alert(token_manager, warn_seconds: int) -> dict:
    """Warn when the Schwab refresh token is valid but near its 7-day cliff.

    Reads `token_manager.get_status()`. When the token is still connected and
    `refresh_token_expires_in_seconds <= warn_seconds`, emits a loud log and an
    App Insights span. Returns the status dict so a caller can reuse it. Safe to
    call on any schedule — it only alerts inside the window.
    """
    status = token_manager.get_status()
    expires_in = status.get("refresh_token_expires_in_seconds")
    connected = bool(status.get("connected"))

    if connected and expires_in is not None and expires_in <= warn_seconds:
        hours = round(expires_in / 3600, 1)
        logger.error(
            f"{WARN_PREFIX}: Schwab refresh token expires in {hours}h "
            f"({expires_in}s). Re-login at {RELOGIN_URL} to avoid a silent "
            f"account-activity feed outage."
        )
        _emit_span("schwab.expiry_warning", {
            "ota.alert": WARN_PREFIX,
            "ota.schwab.expires_in_seconds": expires_in,
            "ota.schwab.relogin_url": RELOGIN_URL,
        })

    return status


def notify_auth_error(message: Optional[str]) -> None:
    """Alert that a poll just failed on the expired Schwab refresh token.

    Called by the poller on the FIRST failing run of an outage — the caller owns
    the dedupe so the 15-minute cadence does not spam. Loud log + App Insights
    span; never raises.
    """
    logger.error(
        f"{AUTH_ERROR_PREFIX}: account-activity poll failed on the Schwab refresh "
        f"token — the feed is now stale until re-login at {RELOGIN_URL}. "
        f"({message or 'refresh token expired'})"
    )
    _emit_span("schwab.auth_error", {
        "ota.alert": AUTH_ERROR_PREFIX,
        "ota.schwab.relogin_url": RELOGIN_URL,
        "ota.schwab.message": (message or "")[:200],
    })


def is_auth_error(message: Optional[str]) -> bool:
    """True when an error message indicates the refresh token needs re-login.

    Mirrors the classification `get_schwab_status` uses to map a run to
    `auth_error`, so the reactive alert and the status pill agree.
    """
    if not message:
        return False
    low = message.lower()
    return (
        "refresh token" in low
        or "reconnect" in low
        or "re-authenticate" in low
        or "reauth" in low
    )
