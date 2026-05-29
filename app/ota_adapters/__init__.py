"""
OTA consumer adapters for the Insight Engine.

Each subdirectory is one adapter boundary — its own input adapter with
its own strategies and its own candidate type. Cross-adapter shared
providers (Schwab client, Black-Scholes) live in ``_shared/``.

Adapter inventory:
    options_chain  — screening (OTA-712)
    (position_health — Wave 3.2, OTA-734)
    (directional     — Wave 3.2, OTA-752)
"""
