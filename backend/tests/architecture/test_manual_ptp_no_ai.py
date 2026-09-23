"""E6-S6 AC3: the manual PTP workflow has no dependency on
`collectai.ai_orchestration`, so it keeps working with the LLM provider
fully down.

Mirrors `tests/architecture/test_e5_s3_ai_orchestration_isolated.py`'s
AST-import-scan technique: a hand-rolled `ast.parse` + `ast.walk` scan, not
`.importlinter`, since this is one story's own narrow promise about its own
two files rather than a durable, package-wide layering contract.

Scans `domain_services/ptp_service.py` and `api/routers/ptps.py` (the two
files the story names) plus the private sibling modules `ptp_service.py`
was split into once it crossed the code-gen skill's 300-line hard block
(`_ptp_exceptions.py`, `_ptp_helpers.py`, `_ptp_idempotency.py` -- see
`ptp_service.py`'s own module docstring): together these are still "this
module" AC3 describes, just organized across more than one file on disk.
"""

from __future__ import annotations

import ast
from pathlib import Path

_SRC_ROOT = Path(__file__).resolve().parents[2] / "src" / "collectai"
_SCANNED_FILES: tuple[Path, ...] = (
    _SRC_ROOT / "domain_services" / "ptp_service.py",
    _SRC_ROOT / "domain_services" / "_ptp_exceptions.py",
    _SRC_ROOT / "domain_services" / "_ptp_helpers.py",
    _SRC_ROOT / "domain_services" / "_ptp_idempotency.py",
    _SRC_ROOT / "api" / "routers" / "ptps.py",
)
_FORBIDDEN_TOP_LEVEL_MODULE = "collectai.ai_orchestration"


def _imported_modules(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    modules: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            modules.append(node.module)
    return modules


def test_scanned_files_exist() -> None:
    assert all(path.is_file() for path in _SCANNED_FILES), _SCANNED_FILES


def test_manual_ptp_files_import_no_ai_orchestration() -> None:
    offenders: dict[str, list[str]] = {}
    for path in _SCANNED_FILES:
        forbidden_hits = [
            module
            for module in _imported_modules(path)
            if module == _FORBIDDEN_TOP_LEVEL_MODULE
            or module.startswith(f"{_FORBIDDEN_TOP_LEVEL_MODULE}.")
        ]
        if forbidden_hits:
            offenders[str(path.relative_to(_SRC_ROOT))] = forbidden_hits

    assert offenders == {}, f"Manual-PTP files importing ai_orchestration: {offenders}"
