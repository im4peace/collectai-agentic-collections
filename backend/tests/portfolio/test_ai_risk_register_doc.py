"""E10-S5 AC3: `docs/portfolio/ai-risk-register.md` (P3) has one entry for each
BRD 13.1 failure scenario and each BRD 13.5 top risk, each with likelihood,
impact, control, owner and a *real* linked test. The expected counts come from
the BRD; every linked `path::test name` is checked to exist.
"""

from __future__ import annotations

import re
from pathlib import Path

from ._docs import (
    PORTFOLIO_DIR,
    REPO_ROOT,
    brd_failure_scenario_numbers,
    brd_top_risk_count,
    missing_ids,
    read_text,
    table_rows,
)

_DOC = PORTFOLIO_DIR / "ai-risk-register.md"
_LEVELS = {"LOW", "MEDIUM", "HIGH"}
_LINK = re.compile(r"`([^`]+?::[^`]+?)`")
_FIELDS = ("Likelihood", "Impact", "Control", "Owner", "Linked tests", "Coverage", "Gap")


def _scenarios() -> list[dict[str, str]]:
    return table_rows(read_text(_DOC), "Failure scenarios (BRD 13.1)")


def _risks() -> list[dict[str, str]]:
    return table_rows(read_text(_DOC), "Top expected risks (BRD 13.5)")


def test_there_is_one_entry_per_brd_failure_scenario() -> None:
    expected = [f"S{number}" for number in brd_failure_scenario_numbers()]

    assert len(expected) >= 27
    assert missing_ids(expected, read_text(_DOC)) == []
    assert [row["ID"] for row in _scenarios()] == expected


def test_there_is_one_entry_per_brd_top_risk() -> None:
    expected = [f"R{number}" for number in range(1, brd_top_risk_count() + 1)]

    assert len(expected) >= 9
    assert missing_ids(expected, read_text(_DOC)) == []
    assert [row["ID"] for row in _risks()] == expected


def test_every_entry_states_likelihood_impact_control_owner_and_linked_tests() -> None:
    for row in (*_scenarios(), *_risks()):
        for field in _FIELDS:
            assert row[field], f"{row['ID']}: empty {field!r}"
        assert row["Likelihood"] in _LEVELS, row["ID"]
        assert row["Impact"] in _LEVELS, row["ID"]
        assert _LINK.findall(row["Linked tests"]), f"{row['ID']}: no linked test"


def test_coverage_is_honest_a_partial_entry_names_its_gap_and_a_full_one_has_none() -> None:
    for row in (*_scenarios(), *_risks()):
        assert row["Coverage"] in {"FULL", "PARTIAL"}, row["ID"]
        if row["Coverage"] == "PARTIAL":
            assert row["Gap"] != "-", f"{row['ID']}: a PARTIAL entry must say what is missing"
        else:
            assert row["Gap"] == "-", f"{row['ID']}: a FULL entry must not carry a gap"


def _exists(link: str) -> bool:
    path_text, _, name = link.partition("::")
    path = REPO_ROOT / path_text
    if not path.is_file():
        return False
    source = path.read_text(encoding="utf-8")
    if path.suffix == ".py":
        pattern = rf"^\s*(?:async )?def {re.escape(name)}\("
        return re.search(pattern, source, re.MULTILINE) is not None
    return name in source  # a TypeScript/Playwright test title


def test_every_linked_test_exists_in_the_file_it_names() -> None:
    broken = [
        f"{row['ID']}: {link}"
        for row in (*_scenarios(), *_risks())
        for link in _LINK.findall(row["Linked tests"])
        if not _exists(link)
    ]

    assert broken == [], f"linked tests that do not exist: {broken}"


def test_the_existence_check_rejects_a_made_up_test() -> None:
    real = (
        "backend/tests/portfolio/test_ai_risk_register_doc.py"
        "::test_the_existence_check_rejects_a_made_up_test"
    )

    assert _exists(real)
    assert not _exists(real.replace("rejects_a_made_up_test", "does_not_exist"))
    assert not _exists("backend/tests/no_such_file.py::test_x")


def test_linked_paths_stay_inside_the_repository() -> None:
    for row in (*_scenarios(), *_risks()):
        for link in _LINK.findall(row["Linked tests"]):
            path = (REPO_ROOT / link.partition("::")[0]).resolve()
            assert Path(REPO_ROOT).resolve() in path.parents, f"{row['ID']}: {link}"
