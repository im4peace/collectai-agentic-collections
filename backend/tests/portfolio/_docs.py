"""Shared parsing for the portfolio-deliverable tests (E10-S5).

The completeness rules are derived from the *source of truth* (the BRD), never
from a hard-coded list, so a new BRD decision, failure scenario or KPI leaf can
never make a document silently incomplete: the tests just start failing.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
BRD_PATH = REPO_ROOT / "specs" / "brd" / "brd.md"
PORTFOLIO_DIR = REPO_ROOT / "docs" / "portfolio"


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def brd_section(number: str) -> str:
    """The text of BRD section `number` (for example "16" or "13.1"), up to the
    next heading of the same or a higher level."""
    text = read_text(BRD_PATH)
    level = number.count(".") + 2  # "## 16." is level 2; "### 13.1" is level 3
    match = re.search(rf"^#{{{level}}} {re.escape(number)}[. ].*$", text, re.MULTILINE)
    if match is None:
        raise AssertionError(f"BRD section {number} not found")
    rest = text[match.end() :]
    stop = re.search(rf"^#{{1,{level}}} ", rest, re.MULTILINE)
    return text[match.start() : match.end() + (stop.start() if stop else len(rest))]


def brd_decision_ids() -> list[str]:
    """Every decision ID in the BRD decision log (section 16)."""
    return re.findall(r"^\| (D-\d+) \|", brd_section("16"), re.MULTILINE)


def brd_failure_scenario_numbers() -> list[int]:
    """The numbers of the BRD 13.1 failure-scenario rows."""
    return [int(n) for n in re.findall(r"^\| (\d+) \|", brd_section("13.1"), re.MULTILINE)]


def brd_top_risk_count() -> int:
    """How many numbered top expected risks BRD 13.5 lists."""
    return len(re.findall(r"^\d+\. ", brd_section("13.5"), re.MULTILINE))


def brd_kpi_tree_leaves() -> list[str]:
    """The leaf lines of the BRD 4.5 KPI tree: tree lines with no deeper child."""
    block = re.search(r"```\n(Business outcome.*?)```", brd_section("4.5"), re.DOTALL)
    if block is None:
        raise AssertionError("BRD 4.5 KPI tree block not found")
    nodes: list[tuple[int, str]] = []
    for line in block.group(1).splitlines():
        marker = line.find("|- ")
        if marker != -1:
            nodes.append((marker, line[marker + 3 :].strip()))
    return [
        text
        for index, (depth, text) in enumerate(nodes)
        if index + 1 >= len(nodes) or nodes[index + 1][0] <= depth
    ]


def brd_deferred_kpis() -> list[str]:
    """The deferred KPI names BRD 4.5 lists ("Deferred, because ...: a, b, c.")."""
    match = re.search(r"Deferred, because[^:]*: (.+?)\. Each delivered", brd_section("4.5"))
    if match is None:
        raise AssertionError("BRD 4.5 deferred-KPI sentence not found")
    return [name.strip() for name in match.group(1).split(",")]


def table_rows(text: str, heading: str) -> list[dict[str, str]]:
    """The rows of the first markdown table under the `## heading`, keyed by
    column header. Cells are stripped; a cell must not contain a pipe."""
    start = re.search(rf"^##+ {re.escape(heading)}\s*$", text, re.MULTILINE)
    if start is None:
        raise AssertionError(f"heading {heading!r} not found")
    lines = text[start.end() :].splitlines()
    table = []
    for line in lines:
        if line.startswith("|"):
            table.append(line)
        elif table:
            break
    if len(table) < 2:
        raise AssertionError(f"no table under {heading!r}")
    headers = _cells(table[0])
    rows = []
    for line in table[2:]:
        cells = _cells(line)
        if len(cells) != len(headers):
            raise AssertionError(f"row has {len(cells)} cells, expected {len(headers)}: {line}")
        rows.append(dict(zip(headers, cells, strict=True)))
    return rows


def _cells(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def missing_ids(required: Iterable[str], text: str) -> list[str]:
    """Which of `required` never appear as a table row ID in `text`."""
    present = set(re.findall(r"^\| ([A-Z]-?\d+|[A-Z]+-\d+) \|", text, re.MULTILINE))
    return [item for item in required if item not in present]
