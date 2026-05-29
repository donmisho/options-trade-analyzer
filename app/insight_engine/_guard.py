"""
Domain-decoupling guard for the Insight Engine package.

Enforced at import time (from ``__init__.py``) and by CI test
(``tests/insight_engine/test_domain_boundary.py``).

The engine package must not import from any domain package, LLM client,
or DB driver. It must not contain ``if strategy_id == ...`` or
``if strategy_key == ...`` branches. Both constraints derive from
``insight_engine.md`` §2 principles 2 and 5.
"""

from __future__ import annotations

import ast
import os
from pathlib import Path


class EngineDomainLeakError(Exception):
    """Raised when the engine package imports a forbidden module or
    contains a strategy-identity branch."""


# ── Forbidden import roots ──────────────────────────────────────────────
# Domain packages within the app
_FORBIDDEN_APP_PACKAGES = frozenset({
    "app.agents",
    "app.ai",
    "app.analysis",
    "app.api",
    "app.auth",
    "app.core",
    "app.middleware",
    "app.models",
    "app.providers",
    "app.services",
    "app.skills",
    "app.validators",
})

# LLM client libraries
_FORBIDDEN_LLM = frozenset({
    "anthropic",
    "openai",
    "azure.ai",
})

# DB drivers and ORMs
_FORBIDDEN_DB = frozenset({
    "pyodbc",
    "sqlalchemy",
    "aioodbc",
    "alembic",
    "databases",
})

_ALL_FORBIDDEN = _FORBIDDEN_APP_PACKAGES | _FORBIDDEN_LLM | _FORBIDDEN_DB


def _is_forbidden(module_name: str) -> str | None:
    """Return the matched forbidden root if *module_name* starts with one,
    else ``None``."""
    for root in _ALL_FORBIDDEN:
        if module_name == root or module_name.startswith(root + "."):
            return root
    return None


def _collect_python_files(package_dir: Path) -> list[Path]:
    """Return all ``.py`` files under *package_dir*, recursively."""
    return sorted(package_dir.rglob("*.py"))


def _scan_file(filepath: Path) -> list[str]:
    """AST-scan a single file for forbidden imports and strategy-identity
    branches. Returns a list of violation descriptions (empty = clean)."""
    source = filepath.read_text(encoding="utf-8")
    try:
        tree = ast.parse(source, filename=str(filepath))
    except SyntaxError:
        return [f"{filepath}: SyntaxError — could not parse"]

    violations: list[str] = []
    rel = filepath.as_posix()

    for node in ast.walk(tree):
        # ── Import checks ───────────────────────────────────────────
        if isinstance(node, ast.Import):
            for alias in node.names:
                matched = _is_forbidden(alias.name)
                if matched:
                    violations.append(
                        f"{rel}:{node.lineno}: forbidden import '{alias.name}' "
                        f"(matched root '{matched}')"
                    )
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                matched = _is_forbidden(node.module)
                if matched:
                    violations.append(
                        f"{rel}:{node.lineno}: forbidden from-import "
                        f"'{node.module}' (matched root '{matched}')"
                    )

        # ── Strategy-identity branch check ──────────────────────────
        # Catches: if strategy_id == ... / if strategy_key == ...
        if isinstance(node, (ast.If, ast.IfExp)):
            test = node.test if isinstance(node, ast.If) else node.test
            if isinstance(test, ast.Compare):
                left = test.left
                if isinstance(left, ast.Name) and left.id in (
                    "strategy_id", "strategy_key",
                ):
                    for op in test.ops:
                        if isinstance(op, (ast.Eq, ast.NotEq)):
                            violations.append(
                                f"{rel}:{node.lineno}: strategy-identity "
                                f"branch on '{left.id}'"
                            )

    return violations


def scan_package(package_dir: Path | None = None) -> list[str]:
    """Scan the entire engine package for domain leaks.

    Parameters
    ----------
    package_dir : Path, optional
        Root of the ``app/insight_engine`` package. Defaults to the
        directory containing this module.

    Returns
    -------
    list[str]
        Violation descriptions. Empty list means the package is clean.
    """
    if package_dir is None:
        package_dir = Path(__file__).resolve().parent

    violations: list[str] = []
    for py_file in _collect_python_files(package_dir):
        # Skip __pycache__
        if "__pycache__" in py_file.parts:
            continue
        violations.extend(_scan_file(py_file))
    return violations


def enforce_domain_boundary(package_dir: Path | None = None) -> None:
    """Run the domain-boundary scan and raise on any violation.

    Called from ``__init__.py`` at import time. Also callable from tests.
    """
    violations = scan_package(package_dir)
    if violations:
        detail = "\n  ".join(violations)
        raise EngineDomainLeakError(
            f"Engine domain-decoupling violation(s) detected:\n  {detail}"
        )
