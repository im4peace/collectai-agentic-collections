"""E2-S1 AC5: rules_engine imports nothing from AI orchestration or LLM
provider modules.

Enforced via the `import-linter` CLI (`lint-imports`) run as a subprocess
against `backend/.importlinter`, rather than a hand-rolled AST scan. Reasons:

- `.importlinter` is the single, versioned source of truth for every layering
  rule in the project (folder-structure.md section 5); a hand-rolled scan in
  this test would duplicate that contract and could silently drift from it.
- import-linter builds a real import graph (via `grimp`), so it also catches
  indirect violations (e.g. `rules_engine` importing a module that itself
  imports `llm_provider`), which a shallow per-file AST scan of
  `rules_engine/` alone would miss.
- Running the actual CLI is what CI and local `make lint`/`make arch` runs
  will use, so this test fails exactly when a real contract-check invocation
  would fail.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

_BACKEND_ROOT = Path(__file__).resolve().parents[2]


def _lint_imports_executable() -> Path:
    """The `lint-imports` console script installed alongside this interpreter.

    `import-linter` ships no `python -m importlinter` entry point, only the
    `lint-imports` console script, so it is located next to `sys.executable`
    rather than invoked as a module.
    """
    suffix = ".exe" if sys.platform == "win32" else ""
    return Path(sys.executable).with_name(f"lint-imports{suffix}")


def test_lint_imports_passes_for_rules_engine_contracts() -> None:
    result = subprocess.run(
        [str(_lint_imports_executable()), "--config", ".importlinter"],
        cwd=_BACKEND_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, (
        f"import-linter reported contract violations.\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
