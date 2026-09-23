"""E5-S3/E5-S2: `ai_orchestration` imports nothing from `rules_engine`,
`domain_services`, `persistence`, `api`, `application` or `bootstrap`
(folder-structure.md section 5's layer-5b row: "AI: types, config, audit,
llm_provider").

E5-S3 originally forbade `collectai.audit` too, as "this story's own
decoupling choice, not yet a durable contract" (see git history). E5-S2's
`orchestrator.py` now writes AI-interaction audit events directly, which the
layer-5b row always allowed, so that entry is removed here; the restriction
this test still enforces (no `rules_engine`/`domain_services`/`persistence`/
`api`/`application`/`bootstrap`, and no direct `anthropic` import) is
otherwise unchanged.

A hand-rolled AST scan, not `.importlinter`, by design: `backend/.importlinter`
already documents (see its own top-of-file comment) that the durable
`ai_orchestration` contract is added by E5-S4, once `ai_orchestration` also
needs to import `llm_provider` for real. This test only needs to hold today's
narrower promise -- this package touches no other forbidden production layer
-- and should be deleted or superseded once that later contract exists.
"""

from __future__ import annotations

import ast
from pathlib import Path

_SRC_ROOT = Path(__file__).resolve().parents[2] / "src" / "collectai"
_PACKAGE_DIR = _SRC_ROOT / "ai_orchestration"
_FORBIDDEN_TOP_LEVEL_MODULES = (
    "collectai.rules_engine",
    "collectai.domain_services",
    "collectai.persistence",
    "collectai.api",
    "collectai.application",
    "collectai.bootstrap",
    "anthropic",
)


def _ai_orchestration_python_files() -> list[Path]:
    return list(_PACKAGE_DIR.rglob("*.py"))


def _imported_modules(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    modules: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            modules.append(node.module)
    return modules


def test_ai_orchestration_package_exists() -> None:
    assert _PACKAGE_DIR.is_dir()
    assert len(_ai_orchestration_python_files()) >= 4


def test_ai_orchestration_imports_no_forbidden_layer() -> None:
    offenders: dict[str, list[str]] = {}
    for path in _ai_orchestration_python_files():
        forbidden_hits = [
            module
            for module in _imported_modules(path)
            if any(
                module == forbidden or module.startswith(f"{forbidden}.")
                for forbidden in _FORBIDDEN_TOP_LEVEL_MODULES
            )
        ]
        if forbidden_hits:
            offenders[str(path.relative_to(_SRC_ROOT))] = forbidden_hits

    assert offenders == {}, f"ai_orchestration files importing a forbidden layer: {offenders}"
