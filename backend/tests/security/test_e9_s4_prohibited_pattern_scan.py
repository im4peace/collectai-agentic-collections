"""E9-S4 AC2: `scripts/scan_prohibited_patterns.py`'s own self-test --
plants a card number in a temp file and asserts the scan fails (finds it),
then confirms a clean file passes. DB-free: the scan itself needs no
database (its "seed output" input is a freshly generated in-memory
`SeedDataset`, per that script's own docstring).
"""

from __future__ import annotations

import sys
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).resolve().parents[2] / "scripts"
sys.path.insert(0, str(_SCRIPTS_DIR))

from scan_prohibited_patterns import scan_default_scope, scan_paths, scan_text_file  # noqa: E402


def test_a_planted_card_number_is_found(tmp_path: Path) -> None:
    planted = tmp_path / "planted.txt"
    planted.write_text("Card on file: 4111111111111111, expires 12/29.", encoding="utf-8")

    findings = scan_text_file(planted)

    assert findings, "the scan did not find a planted 16-digit card number"
    assert "13-19 digit sequence" in findings[0]


def test_a_planted_ssn_shaped_pattern_is_found(tmp_path: Path) -> None:
    planted = tmp_path / "planted_ssn.txt"
    planted.write_text("Government id: 123-45-6789", encoding="utf-8")

    findings = scan_text_file(planted)

    assert findings, "the scan did not find a planted SSN-shaped pattern"


def test_a_planted_cvv_is_found(tmp_path: Path) -> None:
    planted = tmp_path / "planted_cvv.txt"
    planted.write_text("CVV: 123", encoding="utf-8")

    findings = scan_text_file(planted)

    assert findings, "the scan did not find a planted CVV-labelled number"


def test_a_clean_file_produces_no_findings(tmp_path: Path) -> None:
    clean = tmp_path / "clean.txt"
    clean.write_text("Your overdue amount is 500.00 AED, due 2026-10-15.", encoding="utf-8")

    assert scan_text_file(clean) == []


def test_scan_paths_aggregates_findings_across_multiple_files(tmp_path: Path) -> None:
    dirty = tmp_path / "dirty.txt"
    dirty.write_text("4111111111111111", encoding="utf-8")
    clean = tmp_path / "clean.txt"
    clean.write_text("nothing sensitive here", encoding="utf-8")

    findings = scan_paths([dirty, clean])

    assert len(findings) == 1
    assert "dirty.txt" in findings[0]


def test_the_real_repository_default_scope_is_currently_clean() -> None:
    """The CI `data-safety` job's actual, unmodified scan: the real prompt
    templates, policy JSON, fixtures and a freshly generated seed dataset
    must all be clean today -- a real regression, not just the planted
    self-tests above, would fail this."""
    assert scan_default_scope() == []
