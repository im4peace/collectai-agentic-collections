"""Architecture test (E5-S1 AC4): only `llm_provider` may import `anthropic`.

`ai_orchestration` does not exist yet as a package in this batch (it is a
later story's responsibility), so the statement this test proves today is
the fuller one: no package anywhere in `collectai/` except `llm_provider`
imports the `anthropic` SDK. A future story (E5-S4) is expected to add a
durable `import-linter` contract once `ai_orchestration` exists to actually
import `llm_provider`; this test does not depend on `backend/.importlinter`
at all, by design (see E5-S1 story instructions).
"""

from __future__ import annotations

import ast
from pathlib import Path

_SRC_ROOT = Path(__file__).resolve().parents[2] / "src" / "collectai"
_ALLOWED_PACKAGE = "llm_provider"


def _python_files_outside_llm_provider() -> list[Path]:
    return [
        path
        for path in _SRC_ROOT.rglob("*.py")
        if _ALLOWED_PACKAGE not in path.relative_to(_SRC_ROOT).parts
    ]


def _imports_anthropic(path: Path) -> bool:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import) and any(
            alias.name == "anthropic" or alias.name.startswith("anthropic.")
            for alias in node.names
        ):
            return True
        if isinstance(node, ast.ImportFrom) and node.module is not None:
            if node.module == "anthropic" or node.module.startswith("anthropic."):
                return True
    return False


def test_no_package_outside_llm_provider_imports_the_anthropic_sdk() -> None:
    offending = [path for path in _python_files_outside_llm_provider() if _imports_anthropic(path)]

    assert offending == [], (
        "These files import the `anthropic` SDK outside `llm_provider/`: "
        f"{[str(path.relative_to(_SRC_ROOT)) for path in offending]}"
    )


def test_anthropic_live_module_is_the_one_file_that_imports_anthropic() -> None:
    anthropic_live = _SRC_ROOT / "llm_provider" / "anthropic_live.py"

    assert anthropic_live.exists()
    assert _imports_anthropic(anthropic_live)


def test_llm_provider_source_tree_contains_python_files_to_scan() -> None:
    """Sanity check: the scan actually walks a non-empty tree (guards a silent no-op)."""
    assert len(_python_files_outside_llm_provider()) > 5
