"""
CI test: domain-decoupling guard for the Insight Engine package.

Runs the same AST scan as the import-time guard and fails the build on
any forbidden import or strategy-identity branch. See insight_engine.md
§2 principles 2 (strategy independence) and 5 (domain decoupling).
"""

import textwrap
import tempfile
from pathlib import Path

import pytest

from app.insight_engine._guard import (
    EngineDomainLeakError,
    enforce_domain_boundary,
    scan_package,
)


class TestCleanPackage:
    """The engine package as committed must be domain-clean."""

    def test_scan_passes_on_clean_package(self):
        violations = scan_package()
        assert violations == [], (
            "Domain-decoupling violations found in app/insight_engine/:\n"
            + "\n".join(violations)
        )

    def test_enforce_does_not_raise_on_clean_package(self):
        enforce_domain_boundary()

    def test_import_succeeds(self):
        import app.insight_engine  # noqa: F401

    def test_evaluate_stub_raises(self):
        from app.insight_engine import evaluate

        with pytest.raises(NotImplementedError, match="OTA-701"):
            evaluate(
                candidates=[],
                strategy_key="test",
                source_app_id="TEST",
                adapter=None,
                sink=None,
            )


class TestInjectedLeaks:
    """Verify the guard catches forbidden imports and strategy branches."""

    @staticmethod
    def _make_temp_package(code: str) -> Path:
        """Create a temporary package directory with a single module."""
        tmp = Path(tempfile.mkdtemp())
        pkg = tmp / "fake_engine"
        pkg.mkdir()
        (pkg / "__init__.py").write_text("")
        (pkg / "leak.py").write_text(textwrap.dedent(code))
        return pkg

    def test_catches_domain_import(self):
        pkg = self._make_temp_package("from app.analysis import vertical_engine\n")
        violations = scan_package(pkg)
        assert len(violations) == 1
        assert "app.analysis" in violations[0]

    def test_catches_llm_import(self):
        pkg = self._make_temp_package("import anthropic\n")
        violations = scan_package(pkg)
        assert len(violations) == 1
        assert "anthropic" in violations[0]

    def test_catches_db_import(self):
        pkg = self._make_temp_package("import sqlalchemy\n")
        violations = scan_package(pkg)
        assert len(violations) == 1
        assert "sqlalchemy" in violations[0]

    def test_catches_strategy_id_branch(self):
        pkg = self._make_temp_package(
            "def f(strategy_id):\n    if strategy_id == 'x':\n        pass\n"
        )
        violations = scan_package(pkg)
        assert len(violations) == 1
        assert "strategy_id" in violations[0]

    def test_catches_strategy_key_branch(self):
        pkg = self._make_temp_package(
            "def f(strategy_key):\n    if strategy_key == 'y':\n        pass\n"
        )
        violations = scan_package(pkg)
        assert len(violations) == 1
        assert "strategy_key" in violations[0]

    def test_enforce_raises_on_leak(self):
        pkg = self._make_temp_package("from app.models import database\n")
        with pytest.raises(EngineDomainLeakError):
            enforce_domain_boundary(pkg)

    def test_clean_temp_package_passes(self):
        pkg = self._make_temp_package("x = 1\n")
        violations = scan_package(pkg)
        assert violations == []
