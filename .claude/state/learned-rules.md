# Learned Rules

Project-specific decisions made during previous sprints (naming conventions, library choices, API
patterns, anti-patterns found in review). Injected verbatim into every `/implement` teammate prompt.

No prior sprints have run yet — this file is intentionally empty. Add a dated entry below each time
a code review or retro surfaces a rule the team must not relearn.

## Format

```
## <date> — <short title>
**Context:** what happened
**Rule:** the do/don't, stated as an instruction
**Anti-pattern:**
\`\`\`<language>
// what not to do
\`\`\`
**Better approach:**
\`\`\`<language>
// what to do instead
\`\`\`
```

## 2026-09-22 — Group A review (E1-S1, E1-S2): enforce "unique" contract constraints explicitly

**Context:** The policy contract states several list parameters must be "non-empty, unique"
(`vulnerability.categories`, `compliance.review_outcomes`). The E1-S2 validator enforced
non-empty (via `Field(min_length=1)`) but silently accepted duplicates on both fields —
caught only in code review, not by any test, because no test asserted rejection of a
duplicate entry.

**Rule:** When a contract/spec says a list must be "unique" (or "non-duplicate"), add an
explicit duplicate check in the validator AND a test that submits a duplicate and asserts
rejection. Do not rely on `Field(min_length=1)` alone — it only proves non-empty, not unique.
Follow the same pattern already used for `payment.payable_options` duplicate detection in
`config/policy/validator.py` for every other "unique" list field.

**Anti-pattern:**
```python
categories: Annotated[list[VulnerabilityCategory], Field(min_length=1)]
# no dedup check anywhere -> ["OTHER", "OTHER"] silently passes validation
```

**Better approach:**
```python
if len(parameters.vulnerability.categories) != len(set(parameters.vulnerability.categories)):
    raise PolicyValidationError(
        parameter="vulnerability.categories",
        reason="must not contain duplicate values",
    )
```
```python
def test_duplicate_vulnerability_category_raises_named_error() -> None:
    with pytest.raises(PolicyValidationError, match="vulnerability.categories"):
        validate_policy_parameters(seed_with_duplicate_vulnerability_category())
```

## 2026-09-22 — Group A review: cap every string id/version field consistently

**Context:** `PolicyRuleSet.policy_version` was defined with `Field(min_length=1)` but no
`max_length`, while every other model that stores a `policy_version` reference
(`PromiseToPay.policy_version`, `EscalationCase.routing_policy_version`) correctly bounds it
to `max_length=40` per `data-models.md`. The inconsistency wasn't caught by tests because
nothing exercised a 41+ character version string.

**Rule:** When a field appears in multiple entities referencing the same logical value
(e.g. a version string, a bounded id), apply the same `Field(max_length=...)` (or other
constraint) at the field's point of origin, not just at each place that copies it. Grep for
the field name across `data-models.md` before finalizing a model to catch every table that
constrains it.

## 2026-09-22 — Group A review: keep settings/config builder functions under 50 lines

**Context:** `config/settings.py::load_settings` reached 55 lines by inlining every
`Settings(...)` keyword argument alongside its own read-and-validate call, exceeding the
code-gen skill's 50-line function threshold. Still correct, but harder to scan and test
in isolation.

**Rule:** When a "load and validate N independent config keys, then construct one object"
function grows past ~40 lines, extract the kwarg-building into a private helper (e.g.
`_read_validated_fields(env) -> dict[str, object]`) that `load_settings` then unpacks into
the constructor. Each helper becomes independently testable and keeps the top-level function
under the 50-line threshold.

## 2026-09-22 — Group A review: files nearing the 200-line warning threshold need the comment the skill asks for

**Context:** `config/policy/validator.py` reached 229 lines (above the code-gen skill's
200-line warning threshold, below the 300-line block threshold) with no comment noting the
file is growing large, as principle #1 requires.

**Rule:** When a file crosses ~200 lines, add a short comment near the top noting the size
and, if applicable, the planned split point (e.g. "# NOTE: nearing the 300-line block
threshold; consider splitting per-section validators (priority/ptp/arrangement/routing)
into validator/ submodules if this grows further"). This gives the next teammate who edits
the file an early warning before a routine addition forces an unplanned refactor.
