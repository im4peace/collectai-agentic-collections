"""E10-S1 AC7: no production package (`collectai.*`) imports the evaluation
package (`collectai_eval`) -- the reverse direction of every other
architecture contract in this codebase, which restrict a *lower* layer from
importing *upward*. `collectai_eval` is deliberately the highest layer of
all (folder-structure.md: "imports production code, imported by none"), so
this is the one boundary this codebase enforces top-down.

A hand-rolled AST scan, not `.importlinter`, by design: `.importlinter`'s
`root_package = collectai` cannot express a forbidden edge whose target is
a *different* root package (`collectai_eval`, not `collectai.anything`) --
see `.importlinter`'s own top-of-file comment for the same reasoning
`test_e5_s3_ai_orchestration_isolated.py` already established for a
different, temporarily-inexpressible boundary.
"""

from __future__ import annotations

import ast
from pathlib import Path

_SRC_ROOT = Path(__file__).resolve().parents[2] / "src"
_PRODUCTION_PACKAGE_DIR = _SRC_ROOT / "collectai"
_EVAL_PACKAGE_DIR = _SRC_ROOT / "collectai_eval"
_FORBIDDEN_TOP_LEVEL_MODULE = "collectai_eval"


def _production_python_files() -> list[Path]:
    return list(_PRODUCTION_PACKAGE_DIR.rglob("*.py"))


def _imported_modules(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    modules: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            modules.append(node.module)
    return modules


def test_eval_package_exists() -> None:
    assert _EVAL_PACKAGE_DIR.is_dir()
    assert (_EVAL_PACKAGE_DIR / "runner.py").is_file()


def test_no_production_file_imports_collectai_eval() -> None:
    offenders: dict[str, list[str]] = {}
    for path in _production_python_files():
        forbidden_hits = [
            module
            for module in _imported_modules(path)
            if module == _FORBIDDEN_TOP_LEVEL_MODULE
            or module.startswith(f"{_FORBIDDEN_TOP_LEVEL_MODULE}.")
        ]
        if forbidden_hits:
            offenders[str(path.relative_to(_SRC_ROOT))] = forbidden_hits

    assert offenders == {}, f"production files importing collectai_eval: {offenders}"


def test_collectai_eval_itself_does_import_production_code() -> None:
    """The other direction is expected and required (folder-structure.md:
    "imports production code") -- confirms this isn't accidentally isolated
    to the point of being useless, not just that the forbidden direction is
    clean."""
    found_a_production_import = False
    for path in _EVAL_PACKAGE_DIR.rglob("*.py"):
        if any(module.startswith("collectai.") for module in _imported_modules(path)):
            found_a_production_import = True
            break
    assert found_a_production_import, "collectai_eval never imports any collectai.* production code"
