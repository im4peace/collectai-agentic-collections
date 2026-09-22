"""E5-S3 AC1-AC3: post-generation grounding check.

A customer-facing AI message may only state currency figures, dates and
option identifiers that a deterministic service actually returned
(`GroundedFacts`). Any figure absent from those facts blocks the message
(BRD 4.2 critical-violation item 2).
"""

from __future__ import annotations

from collectai.ai_orchestration.grounding import (
    GROUNDING_VIOLATION_EVENT_TYPE,
    GroundedFacts,
    check_grounding,
)

_FALLBACK = "Please see your account summary for the current balance and dates."


def _facts(
    *,
    currency: frozenset[str] = frozenset({"1240.00"}),
    dates: frozenset[str] = frozenset({"2026-10-15"}),
    options: frozenset[str] = frozenset({"OPT-A1"}),
) -> GroundedFacts:
    return GroundedFacts(currency_amounts=currency, dates=dates, option_ids=options)


def test_message_with_all_figures_grounded_passes_unchanged() -> None:
    text = (
        "Your outstanding balance on account acc_000123 is $1,240.00. "
        "A promise-to-pay dated 2026-10-15 is available under option OPT-A1."
    )

    result = check_grounding(text, _facts(), fallback_template=_FALLBACK)

    assert result.is_grounded is True
    assert result.violations == ()
    assert result.final_text == text
    assert result.audit_event_type is None


def test_message_with_unlisted_currency_figure_is_blocked() -> None:
    text = "You can settle this today for $999.99."

    result = check_grounding(text, _facts(), fallback_template=_FALLBACK)

    assert result.is_grounded is False
    assert any(v.kind == "CURRENCY" and v.value == "999.99" for v in result.violations)
    assert result.final_text == _FALLBACK
    assert result.audit_event_type == GROUNDING_VIOLATION_EVENT_TYPE == "GROUNDING_VIOLATION"


def test_message_with_unlisted_date_is_blocked() -> None:
    text = "Your balance of $1,240.00 is due by 2026-11-30."

    result = check_grounding(text, _facts(), fallback_template=_FALLBACK)

    assert result.is_grounded is False
    assert any(v.kind == "DATE" and v.value == "2026-11-30" for v in result.violations)
    assert result.final_text == _FALLBACK


def test_message_with_unlisted_option_id_is_blocked() -> None:
    text = "Your balance of $1,240.00 qualifies for option OPT-Z9."

    result = check_grounding(text, _facts(), fallback_template=_FALLBACK)

    assert result.is_grounded is False
    assert any(v.kind == "OPTION" and v.value == "OPT-Z9" for v in result.violations)
    assert result.final_text == _FALLBACK


def test_one_fabricated_figure_among_otherwise_correct_figures_still_blocks() -> None:
    """AC1's literal wording: block 'if any is absent' — a message mixing a
    grounded figure with a fabricated one is not partially trusted."""
    text = "Your balance of $1,240.00 is due 2026-10-15, and you can also settle for $50.00."

    result = check_grounding(text, _facts(), fallback_template=_FALLBACK)

    assert result.is_grounded is False
    assert any(v.kind == "CURRENCY" and v.value == "50.00" for v in result.violations)


def test_currency_figure_matches_regardless_of_dollar_sign_or_comma_formatting() -> None:
    text = "Your balance is 1240.0 as of today."

    result = check_grounding(text, _facts(), fallback_template=_FALLBACK)

    assert result.is_grounded is True
    assert result.final_text == text


def test_no_figures_in_text_is_trivially_grounded() -> None:
    text = "Thank you for contacting us. How can we help today?"

    result = check_grounding(text, _facts(), fallback_template=_FALLBACK)

    assert result.is_grounded is True
    assert result.final_text == text
