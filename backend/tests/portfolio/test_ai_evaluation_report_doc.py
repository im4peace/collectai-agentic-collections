"""E10-S5 AC2: the committed `docs/portfolio/ai-evaluation-report.md` (P2) stays
consistent with the dataset it reports on and keeps MOCK and LIVE separate.
The document itself is generated (`python -m collectai_eval report`); the
renderer's own rules are tested in `tests/evaluation/test_e10_s5_markdown_report.py`.
"""

from __future__ import annotations

import re
from collections import Counter

from collectai_eval.datasets.loader import load_dataset

from ._docs import PORTFOLIO_DIR, read_text, table_rows

_DOC = PORTFOLIO_DIR / "ai-evaluation-report.md"


def _section(heading: str) -> str:
    text = read_text(_DOC)
    start = text.index(f"## {heading}")
    following = text.find("\n## ", start + 1)
    return text[start : following if following != -1 else len(text)]


def test_the_committed_report_matches_the_dataset_provenance_and_counts() -> None:
    dataset = load_dataset()
    provenance = _section("Dataset provenance")

    assert f"`{dataset.dataset_version}`" in provenance
    assert f"**Labelled cases:** {len(dataset.cases)}" in provenance
    for key, value in dataset.provenance.items():
        assert value in provenance, f"provenance {key!r} is missing"
    counts = Counter(case.category for case in dataset.cases)
    rows = table_rows(read_text(_DOC), "Dataset provenance")
    documented = {row["Category"]: int(row["Cases"]) for row in rows}
    assert documented == dict(counts)


def test_the_report_documents_the_sample_size_limitation() -> None:
    provenance = _section("Dataset provenance")

    assert "Sample-size limitation" in provenance
    assert "OBSERVATION_ONLY" in provenance
    assert "30 labelled LIVE cases" in provenance


def test_mock_and_live_are_separate_sections_in_a_fixed_order() -> None:
    text = read_text(_DOC)

    assert text.index("## MOCK regression run") < text.index("## LIVE evaluation run")
    assert "Do not edit by hand" in text


def test_the_live_section_is_either_a_plain_no_live_run_or_a_labelled_live_run() -> None:
    live = _section("LIVE evaluation run")

    if "**No LIVE run.**" in live:
        assert "%" not in live and "| Model |" not in live
    else:
        assert "| Data label | LIVE |" in live
        assert "| Model |" in live and "| Prompt version |" in live
        assert "| Evaluation date (UTC) |" in live


def test_the_mock_section_never_claims_pass_or_fail_and_covers_every_category() -> None:
    mock = _section("MOCK regression run")
    if "**No MOCK run.**" in mock:
        return
    rows = table_rows(read_text(_DOC), "Per-category results")

    assert "| Data label | MOCK |" in mock
    assert "never evidence of real-model quality" in mock
    assert {row["Claim status"] for row in rows} <= {"OBSERVATION_ONLY"}
    assert {row["Category"] for row in rows} <= {case.category for case in load_dataset().cases}
    for row in rows:
        assert re.fullmatch(r"\d+\.\d{2}%", row["Recall"]), row
        assert int(row["True positives"]) + int(row["False negatives"]) == int(row["Cases"])
