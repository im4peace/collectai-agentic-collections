"""E10-S5 AC4: `docs/portfolio/decision-log.md` (P4) contains every decision in
the BRD decision log. The required IDs are parsed from BRD section 16 at test
time, so a decision added to the BRD later fails this test until it is added to
the file -- the acceptance criterion never needs editing.
"""

from __future__ import annotations

from ._docs import (
    PORTFOLIO_DIR,
    brd_decision_ids,
    missing_ids,
    read_text,
    table_rows,
)

_DOC = PORTFOLIO_DIR / "decision-log.md"


def test_the_brd_decision_log_is_parsed_and_non_empty() -> None:
    ids = brd_decision_ids()

    assert ids, "no decision IDs parsed from BRD section 16"
    assert len(ids) == len(set(ids)), "duplicate decision IDs in the BRD"


def test_every_brd_decision_id_appears_in_the_decision_log() -> None:
    missing = missing_ids(brd_decision_ids(), read_text(_DOC))

    assert missing == [], f"decision-log.md is missing BRD decisions: {missing}"


def test_a_missing_decision_id_would_be_detected() -> None:
    """The guard itself works: drop one BRD decision row and it is reported."""
    text = read_text(_DOC)
    dropped = brd_decision_ids()[0]
    without = "\n".join(
        line for line in text.splitlines() if not line.startswith(f"| {dropped} |")
    )

    assert missing_ids(brd_decision_ids(), without) == [dropped]


def test_every_decision_row_has_status_alternatives_and_rationale() -> None:
    text = read_text(_DOC)
    for section in ("BRD decisions", "Implementation decisions after the BRD"):
        rows = table_rows(text, section)
        assert rows, section
        for row in rows:
            for column in ("ID", "Status", "Decision", "Alternatives considered", "Rationale"):
                assert row[column], f"{row['ID']}: empty {column!r}"


def test_implementation_decision_ids_never_collide_with_the_brd_sequence() -> None:
    rows = table_rows(read_text(_DOC), "Implementation decisions after the BRD")
    ids = [row["ID"] for row in rows]

    assert len(ids) == len(set(ids))
    assert set(ids).isdisjoint(brd_decision_ids())
    assert all(item.startswith("K-") for item in ids)
