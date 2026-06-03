"""
Shared fixtures for engine-config API tests (OTA-782 / OTA-783).

Save-time validation (OTA-783) runs the engine-load path on every write, which
consults the live formula registry. Tests don't stand up the real screening
registry; they stub it to an empty ``StubFormulaRegistry`` so a config with no
``formula:<name>`` rules loads cleanly (and a rule that *does* carry a formula
ref deterministically fails the live-registry membership check — exactly the
rejection path the formula test exercises).
"""

from __future__ import annotations

import pytest

from app.insight_engine.registry import StubFormulaRegistry


@pytest.fixture(autouse=True)
def _stub_formula_registry(monkeypatch):
    monkeypatch.setattr(
        "app.api.engine_config_validation._get_registry",
        lambda: StubFormulaRegistry(),
    )
