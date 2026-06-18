"""Shared pytest fixtures for the insight-engine cross-consumer suite (OTA-795).

Session-scoped so the full seed is hydrated once and reused across the system
suite (OTA-795) and the trace/bronze suite (OTA-798) — no re-seeding per test.
The building-block functions live in ``cross_consumer_harness``; these fixtures
are thin wrappers so tests can request them by name.
"""

from __future__ import annotations

import pytest

from tests.insight_engine import cross_consumer_harness as harness

# Skip the whole package's seeded-config fixtures when the build-time seed
# workbook is absent (mirrors test_full_seed_boot's module-level skip).
_skip_no_workbook = pytest.mark.skipif(
    not harness.SEED_WORKBOOK_AVAILABLE,
    reason="seed workbook not available; cross-consumer system suite needs it",
)


@pytest.fixture(scope="session")
def seeded_engine_config():
    """The hydrated mixed-surface EngineConfig (all three surfaces), built once."""
    if not harness.SEED_WORKBOOK_AVAILABLE:
        pytest.skip("seed workbook not available")
    return harness.build_seeded_config()


@pytest.fixture(scope="session")
def combined_registry():
    """The real screening ∪ directional ∪ position-health formula registry."""
    return harness.get_combined_registry()


@pytest.fixture(scope="session")
def surface_cases():
    """The per-surface system-test cases (strategy, null semantics, builders)."""
    return harness.SURFACE_CASES
