"""E5-S3 AC2: a blocked message is replaced by templated text built only
from the deterministic service output (`GroundedFacts`), never from the
model's own words."""

from __future__ import annotations

from collectai.ai_orchestration.grounding import GroundedFacts
from collectai.ai_orchestration.templates import build_grounding_fallback

_HEDGING_PHRASES = ("i believe", "probably", "i think", "should be", "approximately")


def test_fallback_states_the_actual_amounts_dates_and_options() -> None:
    facts = GroundedFacts(
        currency_amounts=frozenset({"1240.00"}),
        dates=frozenset({"2026-10-15"}),
        option_ids=frozenset({"OPT-A1"}),
    )

    text = build_grounding_fallback(facts)

    assert "1240.00" in text
    assert "2026-10-15" in text
    assert "OPT-A1" in text


def test_fallback_contains_no_hedging_language() -> None:
    facts = GroundedFacts(
        currency_amounts=frozenset({"1240.00"}),
        dates=frozenset(),
        option_ids=frozenset(),
    )

    text = build_grounding_fallback(facts).lower()

    assert not any(phrase in text for phrase in _HEDGING_PHRASES)


def test_fallback_with_no_facts_available_gives_a_safe_generic_message() -> None:
    facts = GroundedFacts(currency_amounts=frozenset(), dates=frozenset(), option_ids=frozenset())

    text = build_grounding_fallback(facts)

    assert text
    assert not any(phrase in text.lower() for phrase in _HEDGING_PHRASES)
