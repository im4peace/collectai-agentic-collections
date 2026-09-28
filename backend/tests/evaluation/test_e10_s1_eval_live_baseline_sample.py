"""`eval_ds_v2_live_baseline_sample.json`: a small, deterministic, category-representative
subset of eval-ds-v2 for a BRD Slice-1 LIVE-baseline *existence* run ("at least one LIVE
baseline run reported with the 4.4 fields", `brd.md` line 293) -- never a replacement dataset,
never big enough to support an accuracy or recall claim. Pure and DB-free.

Every case here is copied verbatim from eval-ds-v2, so this file proves two things: the sample
really is an unmodified subset (never rewritten text), and it stays far under the 30-case
minimum BRD 4.4 (D-025) and `reporting_rules.MIN_CASES_FOR_CLAIM` both require before any
accuracy or recall claim -- so a run of this file can only ever be reported as an observation.
"""

from __future__ import annotations

from pathlib import Path

from collectai_eval.datasets.loader import load_dataset
from collectai_eval.datasets.quality import run_all_checks
from collectai_eval.reporting_rules import MIN_CASES_FOR_CLAIM

_PATH = Path(__file__).resolve().parents[2] / "src" / "collectai_eval" / "datasets" / (
    "eval_ds_v2_live_baseline_sample.json"
)

_TARGET_CATEGORIES = {
    "FINANCIAL_HARDSHIP",
    "DISPUTE",
    "REQUEST_HUMAN",
    "POLICY_EXCEPTION",
    "POLICY_SETTLEMENT",
    "VULNERABLE_CUSTOMER",
    "PAY_NOW",
    "PROMISE_TO_PAY",
    "PAYMENT_PLAN",
    "UNKNOWN",
}


def test_file_exists() -> None:
    assert _PATH.is_file()


def test_dataset_version_is_distinct_so_a_reader_cannot_mistake_it_for_the_full_run() -> None:
    sample = load_dataset(_PATH)
    full = load_dataset()  # the CLI's own default, unaffected by this file's existence
    assert sample.dataset_version != full.dataset_version
    assert sample.dataset_version.startswith("eval-ds-v2")  # names its parent, per provenance


def test_has_exactly_one_case_per_target_category_and_no_others() -> None:
    sample = load_dataset(_PATH)
    assert len(sample.cases) == len(_TARGET_CATEGORIES)
    categories = [case.category for case in sample.cases]
    assert set(categories) == _TARGET_CATEGORIES
    assert len(categories) == len(set(categories))  # exactly one each, never two of a kind


def test_case_count_stays_far_below_the_minimum_any_claim_would_need() -> None:
    sample = load_dataset(_PATH)
    assert len(sample.cases) < MIN_CASES_FOR_CLAIM


def test_every_case_is_copied_verbatim_from_eval_ds_v2() -> None:
    sample = load_dataset(_PATH)
    full_by_id = {case.case_id: case for case in load_dataset().cases}
    for case in sample.cases:
        assert case.case_id in full_by_id, f"{case.case_id} is not a real eval-ds-v2 case_id"
        assert case == full_by_id[case.case_id], f"{case.case_id} diverges from its source"


def test_loading_twice_gives_the_identical_case_order() -> None:
    first = [case.case_id for case in load_dataset(_PATH).cases]
    second = [case.case_id for case in load_dataset(_PATH).cases]
    assert first == second


def test_passes_every_existing_content_quality_check() -> None:
    sample = load_dataset(_PATH)
    assert run_all_checks(sample.cases) == []


def test_provenance_discloses_the_selection_method_and_the_claim_limitation() -> None:
    sample = load_dataset(_PATH)
    assert "one case per target category" in sample.provenance["change_summary"]
    assert "OBSERVATION_ONLY" in sample.provenance["known_limitations"]
    assert "NOT REVIEWED" in sample.provenance["human_review_status"]
