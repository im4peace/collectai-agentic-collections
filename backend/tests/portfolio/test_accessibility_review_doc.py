"""E11-S6 AC1-AC3: `docs/portfolio/accessibility-review.md` records a manual
accessibility review, every finding carries a severity and status, no
conformance is claimed while the review is incomplete or a critical finding is
open, and the README and docs say the product *targets* WCAG 2.1 AA.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from pathlib import Path

from ._docs import PORTFOLIO_DIR, REPO_ROOT, read_text, table_rows

_DOC = PORTFOLIO_DIR / "accessibility-review.md"
_JOURNEYS = ("Journey A", "Journey B1", "Journey B2", "Journey C")
_RESULT = re.compile(r"^(PASS|FAIL \(F-\d+\)|N/A|NOT_EXECUTED)$")
_SEVERITIES = {"CRITICAL", "SERIOUS", "MODERATE", "MINOR"}
_STATUSES = {"OPEN", "RESOLVED", "ACCEPTED"}
_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
# BRD / E11-S6 AC1: the five things the checklist must cover.
_REQUIRED_TOPICS = {
    "keyboard": "keyboard",
    "screen reader": "screen-reader",
    "contrast": "contrast",
    "zoom": "zoom",
    "focus order": "focus order",
}


def _checklist() -> list[dict[str, str]]:
    return table_rows(read_text(_DOC), "Checklist results")


def _findings() -> list[dict[str, str]]:
    return table_rows(read_text(_DOC), "Findings")


def _status_block() -> dict[str, str]:
    return {row["Field"]: row["Value"] for row in table_rows(read_text(_DOC), "Review status")}


def may_claim_conformance(
    status: str, findings: Iterable[dict[str, str]], checklist: Iterable[dict[str, str]]
) -> bool:
    """The publishing rule (AC2, with the review's stricter house rule): the
    review is COMPLETE, every checklist item was executed, and no CRITICAL or
    SERIOUS finding is OPEN."""
    findings = list(findings)
    executed = all(
        "NOT_EXECUTED" not in (row[journey] for journey in _JOURNEYS) for row in checklist
    )
    blocked = any(
        f["Status"] == "OPEN" and f["Severity"] in {"CRITICAL", "SERIOUS"} for f in findings
    )
    return status == "COMPLETE" and executed and not blocked


_NEGATION = re.compile(
    r"\b(not|no|never|without|until|only|before|unless|neither|cannot|may be|must|"
    r"required?|if|when|rules?|would|targets?|stricter)\b|n't",
    re.IGNORECASE,
)
_CLAIM_VERB = re.compile(
    r"\b(conforms?|conformant|compliant|complies|certified|meets)\b", re.IGNORECASE
)


def affirmative_claims(text: str) -> list[str]:
    """Sentences that affirmatively claim WCAG conformance: they mention WCAG and
    a claiming verb, and are not negated, conditional or about the target."""
    sentences = re.split(r"(?<=[.!?])\s+|\n+|\|", text)
    return [
        sentence.strip()
        for sentence in sentences
        if re.search(r"WCAG", sentence)
        and _CLAIM_VERB.search(sentence)
        and not _NEGATION.search(sentence)
    ]


def _documentation_files() -> list[Path]:
    files = [
        REPO_ROOT / "README.md",
        REPO_ROOT / "frontend" / "e2e" / "accessibility" / "README.md",
    ]
    files += sorted((REPO_ROOT / "docs").rglob("*.md"))
    return files


# AC1 -------------------------------------------------------------------------


def test_the_checklist_covers_keyboard_screen_reader_contrast_zoom_and_focus_order() -> None:
    items = " ".join(row["Checklist item"].lower() for row in _checklist())

    for topic, keyword in _REQUIRED_TOPICS.items():
        assert keyword in items, f"the checklist has no {topic!r} item"


def test_every_checklist_item_has_a_result_for_every_primary_journey() -> None:
    rows = _checklist()

    assert len({row["ID"] for row in rows}) == len(rows), "duplicate checklist IDs"
    for row in rows:
        for journey in _JOURNEYS:
            assert _RESULT.match(row[journey]), f"{row['ID']} {journey}: {row[journey]!r}"


def test_every_checklist_item_records_a_reviewer_and_a_date() -> None:
    for row in _checklist():
        assert row["Reviewer"], row["ID"]
        assert row["Date"], row["ID"]
        executed = "NOT_EXECUTED" not in (row[journey] for journey in _JOURNEYS)
        if executed:
            assert _ISO_DATE.match(row["Date"]), f"{row['ID']}: executed items need an ISO date"
        else:
            assert row["Date"] == "not yet run" and row["Reviewer"] == "not yet run", row["ID"]


def test_every_failed_result_points_at_a_real_finding() -> None:
    finding_ids = {finding["ID"] for finding in _findings()}

    for row in _checklist():
        for journey in _JOURNEYS:
            match = re.search(r"\((F-\d+)\)", row[journey])
            if match:
                assert match.group(1) in finding_ids, f"{row['ID']} {journey}: {match.group(1)}"


# AC2 -------------------------------------------------------------------------


def test_every_finding_has_a_severity_and_a_status() -> None:
    findings = _findings()

    assert findings, "the review recorded no findings"
    assert len({finding["ID"] for finding in findings}) == len(findings)
    for finding in findings:
        assert finding["Severity"] in _SEVERITIES, finding["ID"]
        assert finding["Status"] in _STATUSES, finding["ID"]
        for field in ("Title", "WCAG SC", "Journeys", "Evidence", "Proposed fix"):
            assert finding[field], f"{finding['ID']}: empty {field!r}"


def test_every_resolved_finding_records_its_remediation_and_validation_date() -> None:
    resolved = [finding for finding in _findings() if finding["Status"] == "RESOLVED"]

    assert resolved, "the SERIOUS findings F-01 to F-03 were remediated"
    for finding in resolved:
        assert finding["Remediation and validation"].strip("- "), finding["ID"]
        assert _ISO_DATE.match(finding["Validated on"]), f"{finding['ID']}: needs a date"
        assert finding["Severity"] in _SEVERITIES, "resolving keeps the original severity"


def test_open_findings_stay_open_and_the_screen_reader_was_run_by_a_human() -> None:
    by_id = {finding["ID"]: finding for finding in _findings()}

    for finding_id in ("F-01", "F-02", "F-03"):
        assert by_id[finding_id]["Severity"] == "SERIOUS"
        assert by_id[finding_id]["Status"] == "RESOLVED"
    # The human S3 run did not fix or re-rate these: they stay OPEN with their severities.
    for finding_id, severity in (
        ("F-04", "MODERATE"),
        ("F-05", "MODERATE"),
        ("F-06", "MODERATE"),
        ("F-07", "MODERATE"),
        ("F-08", "MINOR"),
    ):
        assert by_id[finding_id]["Status"] == "OPEN", finding_id
        assert by_id[finding_id]["Severity"] == severity, finding_id
    s3 = next(row for row in _checklist() if row["ID"] == "S3")
    assert all(s3[journey] == "PASS" for journey in _JOURNEYS)
    assert s3["Reviewer"].startswith("Human reviewer"), "S3 is human evidence, not tooling"
    assert _ISO_DATE.match(s3["Date"])


def test_only_the_screen_reader_row_is_human_evidence_and_the_rest_stay_tooling_evidence() -> None:
    for row in _checklist():
        if row["ID"] == "S3":
            continue
        assert row["Reviewer"].startswith("Claude"), f"{row['ID']} is a tooling result"


def test_the_status_block_matches_the_checklist_and_findings() -> None:
    block = _status_block()
    open_critical = sum(
        1 for f in _findings() if f["Severity"] == "CRITICAL" and f["Status"] == "OPEN"
    )
    has_unexecuted = any(
        "NOT_EXECUTED" in (row[journey] for journey in _JOURNEYS) for row in _checklist()
    )

    open_serious = sum(
        1 for f in _findings() if f["Severity"] == "SERIOUS" and f["Status"] == "OPEN"
    )

    assert block["Open CRITICAL findings"] == str(open_critical)
    assert block["Open SERIOUS findings"].split()[0] == str(open_serious)
    assert block["Review status"] in {"INCOMPLETE", "COMPLETE"}
    if has_unexecuted:
        assert block["Review status"] == "INCOMPLETE", "unexecuted items mean an incomplete review"
    else:
        assert block["Review status"] == "COMPLETE", "every item executed means a complete review"
        # COMPLETE finishes the checklist. It must never read as a conformance statement.
        assert "does **not** mean the product conforms" in block["Why"]
        assert block["Conformance statement"].startswith("None published")


def test_no_conformance_claim_exists_unless_the_publishing_rule_is_met() -> None:
    text = read_text(_DOC)
    claims = affirmative_claims(text)
    allowed = may_claim_conformance(_status_block()["Review status"], _findings(), _checklist())

    assert claims == [] or allowed, f"conformance claimed too early: {claims}"
    # The rule may permit a statement (COMPLETE, no open CRITICAL or SERIOUS finding), but none
    # has been decided on: the document must claim nothing and say so.
    assert claims == [], f"no conformance statement has been approved: {claims}"
    assert "does **not** make a conformance claim" in text
    assert "**No statement is made.**" in text


def test_the_publishing_rule_blocks_on_each_condition() -> None:
    complete = [{"ID": "K1", **{j: "PASS" for j in _JOURNEYS}}]
    unexecuted = [{"ID": "S3", **{j: "NOT_EXECUTED" for j in _JOURNEYS}}]
    minor = [{"ID": "F-1", "Severity": "MINOR", "Status": "OPEN"}]
    open_critical = [{"ID": "F-2", "Severity": "CRITICAL", "Status": "OPEN"}]
    open_serious = [{"ID": "F-3", "Severity": "SERIOUS", "Status": "OPEN"}]
    resolved_critical = [{"ID": "F-4", "Severity": "CRITICAL", "Status": "RESOLVED"}]

    assert may_claim_conformance("COMPLETE", minor + resolved_critical, complete)
    assert not may_claim_conformance("INCOMPLETE", [], complete)
    assert not may_claim_conformance("COMPLETE", [], unexecuted)
    assert not may_claim_conformance("COMPLETE", open_critical, complete)
    assert not may_claim_conformance("COMPLETE", open_serious, complete)


# AC3 -------------------------------------------------------------------------


def test_the_readme_says_the_product_targets_wcag_2_1_aa() -> None:
    readme = read_text(REPO_ROOT / "README.md")

    assert re.search(r"targets\s+WCAG\s+2\.1\s+(Level\s+)?AA", readme, re.IGNORECASE)
    assert re.search(r"does\s+\*\*not\*\*\s+claim\s+conformance", readme, re.IGNORECASE)
    assert "docs/portfolio/accessibility-review.md" in readme


def test_no_readme_or_documentation_claims_wcag_conformance() -> None:
    claims = {
        str(path.relative_to(REPO_ROOT)): affirmative_claims(read_text(path))
        for path in _documentation_files()
    }

    assert {path: found for path, found in claims.items() if found} == {}


def test_the_claim_detector_flags_affirmative_wording_and_ignores_negated_wording() -> None:
    assert affirmative_claims("CollectAI conforms to WCAG 2.1 AA.")
    assert affirmative_claims("The product is WCAG 2.1 AA compliant.")
    assert affirmative_claims("It meets WCAG 2.1 Level AA.")
    assert not affirmative_claims("CollectAI targets WCAG 2.1 AA and does not claim conformance.")
    assert not affirmative_claims(
        "Conformance is claimed only after a manual review of WCAG 2.1 AA."
    )
    assert not affirmative_claims("This is not a WCAG 2.1 AA compliant product yet.")
