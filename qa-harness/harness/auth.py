"""
Authentication for the QA harness.

Phase 1 finding: dev server uses SKIP_AUTH=True (set via App Settings).
No auth headers needed when SKIP_AUTH is active.
When running against a server that requires auth, set QA_HARNESS_SESSION_COOKIE
environment variable to the ota_session cookie value.
"""

import os
from typing import Dict


def get_auth_headers() -> Dict[str, str]:
    """Return auth headers for API calls. Empty dict when SKIP_AUTH is active."""
    cookie = os.environ.get("QA_HARNESS_SESSION_COOKIE")
    if cookie:
        return {"Cookie": f"ota_session={cookie}"}
    return {}
