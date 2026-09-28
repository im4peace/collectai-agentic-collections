"""`python -m collectai_eval run`'s CLI argument parsing only, for the LIVE-baseline-safety
additions (`--dataset`, `--max-cases`): pure `argparse` parsing, no database, no provider, no
network. `test_e10_s1_eval_runner.py` covers what these values do once inside `run_eval`;
`test_e10_s5_markdown_report.py` covers the `report` subcommand's own args.
"""

from __future__ import annotations

from pathlib import Path

from collectai_eval.cli import _build_arg_parser


def test_dataset_and_max_cases_default_to_none_so_omitting_them_changes_nothing() -> None:
    """The strong preference this design was built around: a command with neither flag must
    resolve to exactly today's behaviour (the CLI's own default dataset, no ceiling)."""
    args = _build_arg_parser().parse_args(["run", "--mode", "live", "--live-confirm"])

    assert args.dataset is None
    assert args.max_cases is None


def test_dataset_and_max_cases_are_accepted_and_typed_correctly() -> None:
    args = _build_arg_parser().parse_args(
        [
            "run",
            "--mode",
            "live",
            "--live-confirm",
            "--dataset",
            "some/sample.json",
            "--max-cases",
            "10",
        ]
    )

    assert args.dataset == Path("some/sample.json")
    assert args.max_cases == 10


def test_mock_mode_also_accepts_both_new_flags() -> None:
    """The new flags are not LIVE-only: a MOCK run against the sample file is exactly how it
    gets tested without a real provider (see test_e10_s1_eval_runner.py)."""
    args = _build_arg_parser().parse_args(
        ["run", "--mode", "mock", "--dataset", "some/sample.json", "--max-cases", "10"]
    )

    assert args.dataset == Path("some/sample.json")
    assert args.max_cases == 10
