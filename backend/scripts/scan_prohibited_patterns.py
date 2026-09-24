"""Prohibited-pattern scan over seed output, prompt templates, fixtures and
captured test logs (E9-S4 AC2; specs/design/deployment.md's `data-safety`
CI job).

Reuses `collectai.persistence.seed.scanner`'s pattern core --
`scan_text_for_dangerous_patterns` (13-19 digit card-shaped runs, SSN-shaped
`###-##-####`, CVV/PIN-labelled numbers) and `scan_seed_dataset` (the same
core plus the seed dataset's own email/phone allow-list) -- so a single set
of regexes backs both the E1-S3 seed-generation gate and this broader,
whole-repo scan; tightening one tightens both.

Exit code 0 means clean; exit code 1 means at least one finding, printed to
stderr. `backend/.github/workflows/ci.yml`'s `data-safety` job runs this
against the repository's real prompt templates and fixtures on every push,
so a planted card number anywhere in scope fails the build.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT / "src"))

from collectai.persistence.seed.generator import (  # noqa: E402
    MIN_ACCOUNT_COUNT,
    generate_seed_dataset,
)
from collectai.persistence.seed.scanner import (  # noqa: E402
    scan_seed_dataset,
    scan_text_for_dangerous_patterns,
)

# Default scan scope: everything specs/design/deployment.md names for this
# job -- prompt templates, fixtures -- plus a freshly generated seed
# dataset (never the demo database itself: this never needs a live Postgres
# instance, keeping the CI job fast and hermetic).
_DEFAULT_TEXT_GLOBS: tuple[str, ...] = (
    "src/collectai/ai_orchestration/prompts/*.py",
    "src/collectai/config/policy/*.json",
    "tests/fixtures/**/*.json",
)


def scan_text_file(path: Path) -> list[str]:
    """Findings in one file's raw text, prefixed with its path for a
    readable report."""
    text = path.read_text(encoding="utf-8", errors="replace")
    return [f"{path}: {finding}" for finding in scan_text_for_dangerous_patterns(text)]


def scan_paths(paths: list[Path]) -> list[str]:
    findings: list[str] = []
    for path in paths:
        if path.is_file():
            findings.extend(scan_text_file(path))
    return findings


def scan_default_scope(*, repo_root: Path = _REPO_ROOT) -> list[str]:
    """The default scan: prompt templates, policy JSON and fixture files on
    disk, plus a freshly generated in-memory seed dataset -- covers "seed
    output" without needing a live database."""
    findings: list[str] = []
    for pattern in _DEFAULT_TEXT_GLOBS:
        findings.extend(scan_paths(sorted(repo_root.glob(pattern))))
    seed_findings = scan_seed_dataset(generate_seed_dataset(account_count=MIN_ACCOUNT_COUNT))
    findings.extend(f"seed dataset: {f.entity}/{f.entity_id}: {f.detail}" for f in seed_findings)
    return findings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "paths",
        nargs="*",
        type=Path,
        help=(
            "Extra files to scan (e.g. a captured test-log file) in addition to the "
            "default prompt/policy/fixture/seed-dataset scope."
        ),
    )
    args = parser.parse_args(argv)

    findings = scan_default_scope()
    findings.extend(scan_paths(args.paths))

    if findings:
        print(f"Prohibited-pattern scan found {len(findings)} issue(s):", file=sys.stderr)
        for finding in findings:
            print(f"  - {finding}", file=sys.stderr)
        return 1

    print("Prohibited-pattern scan: clean.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
