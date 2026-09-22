"""Templated fallback text for a blocked AI message (E5-S3 AC2).

Built only from `GroundedFacts` -- the deterministic service output -- never
from the model's own words, so a customer never sees a hallucinated figure
even in the fallback path. Contains no hedging language ("I believe",
"probably"): every sentence here states only figures the caller already
confirmed.
"""

from __future__ import annotations

from collectai.ai_orchestration.grounding import GroundedFacts

_GENERIC_FALLBACK = (
    "We were unable to confirm the details of that response against your "
    "account. Please review your account summary, or contact us for the "
    "current figures."
)


def build_grounding_fallback(facts: GroundedFacts) -> str:
    """A safe, factual message built only from `facts`; a generic,
    hedge-free message when no facts are available at all."""
    stated = [
        sentence
        for sentence in (
            _amounts_sentence(facts.currency_amounts),
            _dates_sentence(facts.dates),
            _options_sentence(facts.option_ids),
        )
        if sentence is not None
    ]
    if not stated:
        return _GENERIC_FALLBACK
    return " ".join(stated)


def _amounts_sentence(amounts: frozenset[str]) -> str | None:
    if not amounts:
        return None
    formatted = ", ".join(f"${amount}" for amount in sorted(amounts))
    return f"The confirmed amount on your account is {formatted}."


def _dates_sentence(dates: frozenset[str]) -> str | None:
    if not dates:
        return None
    formatted = ", ".join(sorted(dates))
    return f"The relevant date on your account is {formatted}."


def _options_sentence(option_ids: frozenset[str]) -> str | None:
    if not option_ids:
        return None
    formatted = ", ".join(sorted(option_ids))
    return f"The available option on your account is {formatted}."
