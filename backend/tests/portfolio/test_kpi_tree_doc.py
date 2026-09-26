"""E10-S5 AC1: `docs/portfolio/kpi-tree.md` (P1) documents every KPI in the BRD
4.5 tree with definition, formula, data source, owner persona, label and
implementation status, and lists the deferred KPIs. The required leaves and the
deferred names are parsed from the BRD at test time. (That every KPI the API
returns is documented is checked in `tests/api/test_e10_s3_kpi_api.py`, which
owns the seeded KPI fixture.)
"""

from __future__ import annotations

import re

from ._docs import PORTFOLIO_DIR, brd_deferred_kpis, brd_kpi_tree_leaves, read_text, table_rows

_DOC = PORTFOLIO_DIR / "kpi-tree.md"
_STATUSES = {"IMPLEMENTED", "EVAL_REPORT_ONLY", "NOT_YET_MEASURABLE", "DEFERRED"}
_PERSONAS = {
    "CUSTOMER",
    "COLLECTIONS_OFFICER",
    "COLLECTIONS_MANAGER",
    "COMPLIANCE_RISK",
}
_FIELDS = (
    "BRD 4.5 leaf",
    "KPI",
    "KPI id",
    "Definition",
    "Formula",
    "Data source",
    "Owner persona",
    "Data label",
    "Status",
)


def _catalogue() -> list[dict[str, str]]:
    return table_rows(read_text(_DOC), "KPI catalogue")


def test_the_brd_tree_leaves_are_parsed() -> None:
    leaves = brd_kpi_tree_leaves()

    assert len(leaves) >= 15, leaves
    assert "Total delinquent accounts" in leaves
    assert "Recovery effectiveness" not in leaves  # a group node, not a leaf


def test_every_brd_4_5_leaf_appears_in_the_catalogue() -> None:
    documented = {row["BRD 4.5 leaf"] for row in _catalogue()}

    missing = [leaf for leaf in brd_kpi_tree_leaves() if leaf not in documented]
    assert missing == [], f"kpi-tree.md is missing BRD 4.5 KPIs: {missing}"


def test_a_missing_leaf_would_be_detected() -> None:
    documented = {row["BRD 4.5 leaf"] for row in _catalogue()}
    documented.discard(brd_kpi_tree_leaves()[0])

    assert [leaf for leaf in brd_kpi_tree_leaves() if leaf not in documented]


def test_every_kpi_states_definition_formula_source_owner_label_and_status() -> None:
    for row in _catalogue():
        for field in _FIELDS:
            assert row[field], f"{row['KPI']}: empty {field!r}"
        assert row["Status"] in _STATUSES, f"{row['KPI']}: unknown status {row['Status']!r}"
        assert row["Owner persona"] in _PERSONAS, f"{row['KPI']}: unknown owner persona"


def test_an_implemented_kpi_names_its_api_id_and_a_measured_label() -> None:
    for row in _catalogue():
        if row["Status"] == "IMPLEMENTED":
            assert re.fullmatch(r"`[a-z_]+`", row["KPI id"]), row["KPI"]
            assert row["Data label"] != "n/a", row["KPI"]
            assert row["Formula"] != "not defined", row["KPI"]


def test_an_unmeasured_kpi_claims_no_label_and_no_value() -> None:
    for row in _catalogue():
        if row["Status"] == "NOT_YET_MEASURABLE":
            assert row["Data label"] == "n/a", f"{row['KPI']} must not carry a data label"
            assert row["KPI id"] == "-", f"{row['KPI']} has no API id"


def test_the_deferred_kpis_are_listed_with_their_details() -> None:
    deferred = table_rows(read_text(_DOC), "Deferred KPIs")
    documented = {row["KPI"].lower() for row in deferred}

    for name in brd_deferred_kpis():
        assert name.lower() in documented, f"deferred KPI {name!r} is not listed"
    for row in deferred:
        assert row["Status"] == "DEFERRED"
        for field in ("Definition", "Formula", "Data source", "Owner persona", "Data label"):
            assert row[field], f"{row['KPI']}: empty {field!r}"


def test_deferred_kpis_are_absent_from_the_catalogue() -> None:
    catalogue_text = " ".join(row["KPI"].lower() for row in _catalogue())

    for name in brd_deferred_kpis():
        assert name.lower() not in catalogue_text
