"""Tests for policy contract validation (E1-S2 AC1, AC2, AC5)."""

from __future__ import annotations

from typing import Any

import pytest

from collectai.config.policy.validator import PolicyValidationError, validate_policy_parameters


def _dest(queue: str, reviewer_role: str) -> dict[str, str]:
    return {"queue": queue, "reviewer_role": reviewer_role}


def _valid_raw_parameters() -> dict[str, Any]:
    return {
        "priority": {
            "weights": {
                "dpd": "40",
                "overdue_amount": "25",
                "broken_ptp_count": "20",
                "recent_contact_outcome": "15",
            },
            "normalization": {
                "dpd_days": 90,
                "overdue_amount": "5000.00",
                "broken_ptp_count": 3,
            },
            "contact_outcome_scores": {
                "NO_CONTACT": "1.0",
                "CONTACT_NO_COMMITMENT": "0.7",
                "PTP_MADE": "0.2",
                "PTP_BROKEN": "0.9",
                "PAYMENT_MADE": "0.0",
            },
            "band_cutoffs": ["35", "65"],
        },
        "ptp": {"window_days": 30, "min_amount": "10.00", "qualifying_payment_min_amount": "5.00"},
        "payment": {"payable_options": ["OVERDUE_AMOUNT", "FULL_BALANCE"]},
        "arrangement": {
            "eligible_max_dpd": 89,
            "min_overdue_amount": "100.00",
            "installment_counts": [3, 6, 12],
            "min_installment_amount": "25.00",
            "max_start_delay_days": 30,
            "allow_with_active_ptp": False,
        },
        "exception": {
            "thresholds": {
                "max_installment_count": 24,
                "max_start_delay_days": 60,
                "min_installment_amount": "15.00",
            },
            "authority": {
                "collections_officer": {
                    "types": ["TERM", "START_DATE"],
                    "max_overdue_amount": "3000.00",
                }
            },
        },
        "contact": {"max_attempts": 3, "period_days": 7, "min_interval_hours": 24},
        "freshness": {"max_snapshot_age_minutes": 60},
        "suppression": {
            "dispute_scope": "ITEM",
            "hardship_scope": "ACCOUNT",
            "vulnerable_scope": "ACCOUNT",
            "release": "HUMAN_DECISION",
        },
        "vulnerability": {
            "categories": [
                "BEREAVEMENT",
                "SERIOUS_ILLNESS_OR_DISABILITY",
                "MENTAL_HEALTH_CONCERN",
                "DOMESTIC_ABUSE_OR_COERCION",
                "LIMITED_CAPACITY_TO_UNDERSTAND",
                "LANGUAGE_OR_COMMUNICATION_BARRIER",
                "OTHER",
            ]
        },
        "routing": {
            "table": {
                "REQUEST_HUMAN": _dest("COLLECTIONS_REVIEW", "COLLECTIONS_OFFICER"),
                "UNRESOLVED_UNKNOWN": _dest("COLLECTIONS_REVIEW", "COLLECTIONS_OFFICER"),
                "AI_FAILURE_FALLBACK": _dest("COLLECTIONS_REVIEW", "COLLECTIONS_OFFICER"),
                "EXCEPTIONAL_ARRANGEMENT": _dest(
                    "COLLECTIONS_EXCEPTION_REVIEW", "COLLECTIONS_OFFICER"
                ),
                "FINANCIAL_HARDSHIP": _dest("HARDSHIP_REVIEW", "COLLECTIONS_OFFICER"),
                "DISPUTE": _dest("DISPUTE_REVIEW", "COLLECTIONS_OFFICER"),
                "SETTLEMENT_REQUEST": _dest("COLLECTIONS_REVIEW", "COLLECTIONS_OFFICER"),
                "AMBIGUOUS_VALIDATION": _dest("COLLECTIONS_REVIEW", "COLLECTIONS_OFFICER"),
                "VULNERABLE_CUSTOMER": _dest("VULNERABLE_CUSTOMER_REVIEW", "COLLECTIONS_OFFICER"),
                "POLICY_EXCEPTION": _dest("COMPLIANCE_REVIEW", "COMPLIANCE_RISK"),
                "HIGH_RISK_COMPLIANCE": _dest("COMPLIANCE_REVIEW", "COMPLIANCE_RISK"),
            },
            "fallback": _dest("COLLECTIONS_REVIEW", "COLLECTIONS_OFFICER"),
            "priority_by_reason": {
                "REQUEST_HUMAN": "NORMAL",
                "UNRESOLVED_UNKNOWN": "NORMAL",
                "AI_FAILURE_FALLBACK": "NORMAL",
                "EXCEPTIONAL_ARRANGEMENT": "NORMAL",
                "FINANCIAL_HARDSHIP": "ELEVATED",
                "DISPUTE": "ELEVATED",
                "SETTLEMENT_REQUEST": "NORMAL",
                "AMBIGUOUS_VALIDATION": "NORMAL",
                "VULNERABLE_CUSTOMER": "URGENT",
                "POLICY_EXCEPTION": "ELEVATED",
                "HIGH_RISK_COMPLIANCE": "URGENT",
            },
            "reviewer_escalation_reasons": [
                "EXCEPTIONAL_ARRANGEMENT",
                "FINANCIAL_HARDSHIP",
                "DISPUTE",
                "SETTLEMENT_REQUEST",
                "AMBIGUOUS_VALIDATION",
                "VULNERABLE_CUSTOMER",
                "POLICY_EXCEPTION",
                "HIGH_RISK_COMPLIANCE",
            ],
            "aging_warning_hours": {"NORMAL": 48, "ELEVATED": 24, "URGENT": 4},
        },
        "compliance": {"review_outcomes": ["CLEARED", "NOT_CLEARED", "REMEDIATION_REQUIRED"]},
    }


def test_valid_seed_parameters_pass_validation() -> None:
    parameters = validate_policy_parameters(_valid_raw_parameters())
    assert parameters.priority.band_cutoffs == [pytest.approx(35), pytest.approx(65)]
    assert len(parameters.routing.table) == 11


def test_missing_required_parameter_raises_named_error() -> None:
    raw = _valid_raw_parameters()
    del raw["ptp"]["min_amount"]
    with pytest.raises(PolicyValidationError) as exc_info:
        validate_policy_parameters(raw)
    assert "ptp" in exc_info.value.parameter
    assert "min_amount" in exc_info.value.parameter


def test_wrong_typed_value_raises_named_error() -> None:
    raw = _valid_raw_parameters()
    raw["contact"]["max_attempts"] = "not-a-number"
    with pytest.raises(PolicyValidationError) as exc_info:
        validate_policy_parameters(raw)
    assert "max_attempts" in exc_info.value.parameter


def test_out_of_range_value_raises_named_error() -> None:
    raw = _valid_raw_parameters()
    raw["ptp"]["window_days"] = 400
    with pytest.raises(PolicyValidationError) as exc_info:
        validate_policy_parameters(raw)
    assert "window_days" in exc_info.value.parameter


def test_negative_weight_raises_named_error() -> None:
    raw = _valid_raw_parameters()
    raw["priority"]["weights"]["dpd"] = "-1"
    with pytest.raises(PolicyValidationError) as exc_info:
        validate_policy_parameters(raw)
    assert "dpd" in exc_info.value.parameter


def test_unordered_band_cutoffs_raises_named_error() -> None:
    raw = _valid_raw_parameters()
    raw["priority"]["band_cutoffs"] = ["65", "35"]
    with pytest.raises(PolicyValidationError) as exc_info:
        validate_policy_parameters(raw)
    assert "band_cutoffs" in exc_info.value.parameter


def test_band_cutoff_above_weight_sum_raises_named_error() -> None:
    raw = _valid_raw_parameters()
    raw["priority"]["band_cutoffs"] = ["35", "999"]
    with pytest.raises(PolicyValidationError) as exc_info:
        validate_policy_parameters(raw)
    assert "band_cutoffs" in exc_info.value.parameter


def test_all_zero_weights_raises_named_error() -> None:
    raw = _valid_raw_parameters()
    raw["priority"]["weights"] = {
        "dpd": "0",
        "overdue_amount": "0",
        "broken_ptp_count": "0",
        "recent_contact_outcome": "0",
    }
    with pytest.raises(PolicyValidationError) as exc_info:
        validate_policy_parameters(raw)
    assert "weights" in exc_info.value.parameter


def test_missing_contact_outcome_score_raises_named_error() -> None:
    raw = _valid_raw_parameters()
    del raw["priority"]["contact_outcome_scores"]["PAYMENT_MADE"]
    with pytest.raises(PolicyValidationError) as exc_info:
        validate_policy_parameters(raw)
    assert "contact_outcome_scores" in exc_info.value.parameter


def test_qualifying_payment_above_min_amount_raises_named_error() -> None:
    raw = _valid_raw_parameters()
    raw["ptp"]["qualifying_payment_min_amount"] = "20.00"
    with pytest.raises(PolicyValidationError) as exc_info:
        validate_policy_parameters(raw)
    assert "qualifying_payment_min_amount" in exc_info.value.parameter


def test_unascending_installment_counts_raises_named_error() -> None:
    raw = _valid_raw_parameters()
    raw["arrangement"]["installment_counts"] = [6, 3, 12]
    with pytest.raises(PolicyValidationError) as exc_info:
        validate_policy_parameters(raw)
    assert "installment_counts" in exc_info.value.parameter


def test_duplicate_installment_counts_raises_named_error() -> None:
    raw = _valid_raw_parameters()
    raw["arrangement"]["installment_counts"] = [3, 3, 12]
    with pytest.raises(PolicyValidationError) as exc_info:
        validate_policy_parameters(raw)
    assert "installment_counts" in exc_info.value.parameter


def test_exception_max_installment_count_not_above_arrangement_raises_named_error() -> None:
    raw = _valid_raw_parameters()
    raw["exception"]["thresholds"]["max_installment_count"] = 12
    with pytest.raises(PolicyValidationError) as exc_info:
        validate_policy_parameters(raw)
    assert "max_installment_count" in exc_info.value.parameter


def test_exception_min_installment_amount_above_arrangement_raises_named_error() -> None:
    raw = _valid_raw_parameters()
    raw["exception"]["thresholds"]["min_installment_amount"] = "50.00"
    with pytest.raises(PolicyValidationError) as exc_info:
        validate_policy_parameters(raw)
    assert "min_installment_amount" in exc_info.value.parameter


def test_exception_max_start_delay_below_arrangement_raises_named_error() -> None:
    raw = _valid_raw_parameters()
    raw["exception"]["thresholds"]["max_start_delay_days"] = 10
    with pytest.raises(PolicyValidationError) as exc_info:
        validate_policy_parameters(raw)
    assert "max_start_delay_days" in exc_info.value.parameter


def test_routing_table_missing_a_reason_raises_named_error() -> None:
    raw = _valid_raw_parameters()
    del raw["routing"]["table"]["HIGH_RISK_COMPLIANCE"]
    with pytest.raises(PolicyValidationError) as exc_info:
        validate_policy_parameters(raw)
    assert "routing.table" in exc_info.value.parameter


def test_routing_table_unknown_queue_raises_named_error() -> None:
    raw = _valid_raw_parameters()
    raw["routing"]["table"]["DISPUTE"]["queue"] = "NOT_A_REAL_QUEUE"
    with pytest.raises(PolicyValidationError) as exc_info:
        validate_policy_parameters(raw)
    assert "routing" in exc_info.value.parameter


def test_routing_table_unknown_role_raises_named_error() -> None:
    raw = _valid_raw_parameters()
    raw["routing"]["table"]["DISPUTE"]["reviewer_role"] = "NOT_A_REAL_ROLE"
    with pytest.raises(PolicyValidationError) as exc_info:
        validate_policy_parameters(raw)
    assert "routing" in exc_info.value.parameter


def test_routing_fallback_must_match_required_destination() -> None:
    raw = _valid_raw_parameters()
    raw["routing"]["fallback"] = _dest("HARDSHIP_REVIEW", "COLLECTIONS_OFFICER")
    with pytest.raises(PolicyValidationError) as exc_info:
        validate_policy_parameters(raw)
    assert "routing.fallback" in exc_info.value.parameter


def test_routing_priority_by_reason_hardship_below_elevated_raises_named_error() -> None:
    raw = _valid_raw_parameters()
    raw["routing"]["priority_by_reason"]["FINANCIAL_HARDSHIP"] = "NORMAL"
    with pytest.raises(PolicyValidationError) as exc_info:
        validate_policy_parameters(raw)
    assert "priority_by_reason" in exc_info.value.parameter


def test_reviewer_escalation_reasons_cannot_include_request_human() -> None:
    raw = _valid_raw_parameters()
    raw["routing"]["reviewer_escalation_reasons"].append("REQUEST_HUMAN")
    with pytest.raises(PolicyValidationError) as exc_info:
        validate_policy_parameters(raw)
    assert "reviewer_escalation_reasons" in exc_info.value.parameter


def test_invalid_json_root_type_raises_named_error() -> None:
    with pytest.raises(PolicyValidationError):
        validate_policy_parameters([])  # type: ignore[arg-type]
