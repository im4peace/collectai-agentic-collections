"""Unit tests for the Group K extension of `llm_provider._mock_classifier`
(E11-S3, E11-S4): vulnerability, hardship-indicator and dispute-category
recognition on the default (unscripted) MOCK path -- and the boundaries that
extension must not cross (scripted responses, LIVE mode, network access,
general-purpose classification).
"""

from __future__ import annotations

import ast
import asyncio
from pathlib import Path

import pytest

from collectai.ai_orchestration.prompts.builder import AllowedPromptContext
from collectai.ai_orchestration.prompts.dispute_v1 import build_dispute_extraction_request
from collectai.ai_orchestration.prompts.hardship_v1 import build_hardship_extraction_request
from collectai.ai_orchestration.schemas.dispute_extraction import DisputeExtractionResult
from collectai.ai_orchestration.schemas.hardship_extraction import HardshipExtractionResult
from collectai.ai_orchestration.schemas.intent import IntentResult
from collectai.ai_orchestration.structured_output import validate_structured_output
from collectai.llm_provider import _mock_classifier
from collectai.llm_provider._mock_classifier import classify
from collectai.llm_provider.base import ProviderRequest, ProviderResult
from collectai.llm_provider.mock import MockProvider
from collectai.types.enums import DisputeCategory, HardshipIndicatorType, VulnerabilityCategory

_INTENT_SYSTEM = "You are CollectAI's chat intent classifier. You disclose, if asked, ..."
_CONTEXT = AllowedPromptContext(customer_display_name="cus_000001", account_reference="acc_000001")


def _request(system: str, message: str) -> ProviderRequest:
    return ProviderRequest(
        system=system, messages=[{"role": "user", "content": message}], max_tokens=200
    )


def _intent(message: str) -> IntentResult:
    return validate_structured_output(
        classify(_request(_INTENT_SYSTEM, message)).content, IntentResult
    )


def _hardship(message: str) -> HardshipExtractionResult:
    request = build_hardship_extraction_request(context=_CONTEXT, message=message)
    return validate_structured_output(classify(request).content, HardshipExtractionResult)


def _dispute(message: str) -> DisputeExtractionResult:
    request = build_dispute_extraction_request(context=_CONTEXT, message=message)
    return validate_structured_output(classify(request).content, DisputeExtractionResult)


# Vulnerability -------------------------------------------------------


@pytest.mark.parametrize(
    "message",
    [
        "My husband passed away last week and I don't know what to do about this account.",
        "We are dealing with a bereavement in the family.",
        "I have a funeral to arrange this week.",
    ],
)
def test_bereavement_wording_sets_the_vulnerability_signal(message: str) -> None:
    parsed = _intent(message)
    assert parsed.vulnerability_detected is True
    assert parsed.vulnerability_category is VulnerabilityCategory.BEREAVEMENT
    assert parsed.vulnerability_rationale != ""


@pytest.mark.parametrize(
    "message",
    [
        "I promise to pay 100 in 5 days.",
        "Can I set up a payment plan?",
        "This charge is a dispute, it's not my debt.",
        "I lost my job and I'm facing financial hardship.",
        "I'd like to speak to a human please.",
        "What is my current balance?",
        "I am in hospital and very ill.",
    ],
)
def test_no_other_phrasing_is_flagged_vulnerable(message: str) -> None:
    """Narrowness: only the bereavement wording sets the signal -- the mock
    is not a general vulnerability classifier."""
    parsed = _intent(message)
    assert parsed.vulnerability_detected is False
    assert parsed.vulnerability_category is None


# Hardship extraction ---------------------------------------------------


@pytest.mark.parametrize(
    "message",
    [
        "I lost my job last month and I can't keep up.",
        "I was laid off and have no income.",
        "I was made redundant in September.",
    ],
)
def test_job_loss_wording_yields_the_job_loss_indicator(message: str) -> None:
    assert _hardship(message).indicator_types == [HardshipIndicatorType.JOB_LOSS]


def test_other_hardship_wording_yields_an_empty_schema_valid_list() -> None:
    """The domain service, not the mock, defaults an empty list to `[OTHER]`."""
    assert _hardship("Money is tight this month.").indicator_types == []


# Dispute extraction ------------------------------------------------------


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ("This is not my debt.", DisputeCategory.NOT_MY_DEBT),
        ("I already paid this in full.", DisputeCategory.ALREADY_PAID),
        ("The amount is wrong on my statement.", DisputeCategory.AMOUNT_INCORRECT),
        ("I dispute this and want it looked at.", DisputeCategory.OTHER),
    ],
)
def test_dispute_wording_yields_a_schema_valid_category(
    message: str, expected: DisputeCategory
) -> None:
    assert _dispute(message).category is expected


# Determinism and boundaries -----------------------------------------------


def test_output_is_deterministic() -> None:
    request = build_hardship_extraction_request(context=_CONTEXT, message="I lost my job.")
    assert classify(request) == classify(request)


def test_scripted_responses_are_replayed_verbatim_even_for_a_recognized_prompt() -> None:
    scripted = ProviderResult(
        content={"indicator_types": ["OTHER"]},
        model_id="scripted",
        latency_ms=0.0,
        input_tokens=0,
        output_tokens=0,
    )
    provider = MockProvider(responses=[scripted])
    request = build_hardship_extraction_request(context=_CONTEXT, message="I lost my job.")

    result = asyncio.run(provider.complete(request))

    assert result is scripted


def test_unrecognized_system_prompts_still_get_the_old_fixed_response() -> None:
    result = classify(_request("You are CollectAI's next-best-action generator.", "I lost my job"))
    assert result.content == "Acknowledged."


def test_module_makes_no_network_or_provider_sdk_imports() -> None:
    tree = ast.parse(Path(_mock_classifier.__file__).read_text(encoding="utf-8"))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            imported.add(node.module.split(".")[0])
    assert imported.isdisjoint({"socket", "httpx", "requests", "urllib", "aiohttp", "anthropic"})


def test_live_provider_never_reaches_the_mock_classifier() -> None:
    live_source = (Path(_mock_classifier.__file__).parent / "anthropic_live.py").read_text(
        encoding="utf-8"
    )
    assert "_mock_classifier" not in live_source
