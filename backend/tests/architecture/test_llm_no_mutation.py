"""AC10 architecture test (E5-S4, durable version): `ai_orchestration` and
`llm_provider` never import `rules_engine` (deterministic calculation
functions must never be reachable from LLM-adjacent code -- CLAUDE.md's
Core Engineering Principle), and neither package can reach case-decision,
dispute-resolution, compliance-decision, approval or payment-recording
operations.

Two AST-import-scan checks, deliberately not `.importlinter`, mirroring
`test_e5_s3_ai_orchestration_isolated.py`'s own reasoning (belt-and-braces
with the new `.importlinter` `ai-orchestration-no-rules-engine-or-higher-layers`
contract this story also adds -- see `backend/.importlinter`):

  1. Neither `ai_orchestration/**` (including this story's new `tools/` and
     `schemas/` subpackages -- AC10's own instruction to extend the scan to
     them; `Path.rglob` already walks subdirectories, so nothing extra is
     needed beyond pointing the scan at the package root) nor
     `llm_provider/**` imports `collectai.rules_engine` (AC10 clause 1).
     `ai_orchestration` additionally may not import `domain_services`,
     `persistence`, `api`, `application` or `bootstrap` -- the full layer-5b
     boundary this story's `.importlinter` contract now also encodes
     durably.
  2. AC10 clause 2 ("no LLM-reachable code path calls case decision,
     dispute resolution, compliance decision, approval or payment-recording
     operations") has no target functions to call yet: as of this story, no
     module anywhere in this codebase implements case-decision,
     dispute-resolution, compliance-decision, approval or payment-recording
     behavior (those are later stories -- E7-S2/S4/S5, E8-S4, E6-S3). The
     import-boundary check above already fully proves the clause: since
     `ai_orchestration` cannot import `domain_services`, `persistence` or
     `application` at all -- the only layers such an operation could ever
     live in -- there is no code path by which it could ever reach one,
     today or once those modules are built (a later story adding such an
     operation would have to violate check 1 above to make it reachable
     from `ai_orchestration`, which this test would then catch). We
     deliberately do not invent placeholder target functions just to assert
     against them, per this story's brief.
"""

from __future__ import annotations

import ast
from pathlib import Path

_SRC_ROOT = Path(__file__).resolve().parents[2] / "src" / "collectai"
_AI_ORCHESTRATION_DIR = _SRC_ROOT / "ai_orchestration"
_LLM_PROVIDER_DIR = _SRC_ROOT / "llm_provider"

_AI_ORCHESTRATION_FORBIDDEN: tuple[str, ...] = (
    "collectai.rules_engine",
    "collectai.domain_services",
    "collectai.persistence",
    "collectai.api",
    "collectai.application",
    "collectai.bootstrap",
)
_LLM_PROVIDER_FORBIDDEN: tuple[str, ...] = ("collectai.rules_engine",)


def _python_files(directory: Path) -> list[Path]:
    return list(directory.rglob("*.py"))


def _imported_modules(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    modules: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            modules.append(node.module)
    return modules


def _forbidden_hits(path: Path, forbidden: tuple[str, ...]) -> list[str]:
    imported = _imported_modules(path)
    return [
        module
        for module in imported
        if any(module == item or module.startswith(f"{item}.") for item in forbidden)
    ]


def test_ai_orchestration_scan_covers_the_new_tools_and_schemas_subpackages() -> None:
    """Sanity check: the scan actually walks the `tools/` and `schemas/`
    subpackages this story adds, not just the package root (guards a silent
    no-op if `rglob` or the directory layout ever changed)."""
    top_level_subpackages = {
        path.relative_to(_AI_ORCHESTRATION_DIR).parts[0]
        for path in _python_files(_AI_ORCHESTRATION_DIR)
        if len(path.relative_to(_AI_ORCHESTRATION_DIR).parts) > 1
    }
    assert "tools" in top_level_subpackages
    assert "schemas" in top_level_subpackages


def test_ai_orchestration_imports_no_forbidden_layer() -> None:
    offenders = {
        str(path.relative_to(_SRC_ROOT)): hits
        for path in _python_files(_AI_ORCHESTRATION_DIR)
        if (hits := _forbidden_hits(path, _AI_ORCHESTRATION_FORBIDDEN))
    }
    assert offenders == {}, f"ai_orchestration files importing a forbidden layer: {offenders}"


def test_llm_provider_imports_no_rules_engine_calculation_functions() -> None:
    offenders = {
        str(path.relative_to(_SRC_ROOT)): hits
        for path in _python_files(_LLM_PROVIDER_DIR)
        if (hits := _forbidden_hits(path, _LLM_PROVIDER_FORBIDDEN))
    }
    assert offenders == {}, f"llm_provider files importing rules_engine: {offenders}"
