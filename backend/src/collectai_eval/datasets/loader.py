"""Loads a checked-in evaluation dataset into `collectai_eval.schemas.EvalDataset` (E10-S1 AC1,
AC6). The dataset file is the single source of truth for `dataset_version` -- publish a new version
by adding a new file (never by editing a released one); this loader and every `EvalRun` it feeds
record whatever version the file itself declares, never a hardcoded constant here.

`eval-ds-v1` (`eval_ds_v1.json`) is the historical baseline and is kept unchanged. `eval-ds-v2`
(`eval_ds_v2.json`, built by `_build_eval_ds_v2.py`) extends it and is the default.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from collectai_eval.schemas import EvalCase, EvalDataset

DATASET_V1_PATH = Path(__file__).resolve().parent / "eval_ds_v1.json"
DATASET_V2_PATH = Path(__file__).resolve().parent / "eval_ds_v2.json"
_DEFAULT_PATH = DATASET_V2_PATH


def parse_dataset(raw: dict[str, Any]) -> EvalDataset:
    cases = [
        EvalCase(
            case_id=case["case_id"],
            category=case["category"],
            message=case["message"],
            expected_intent=case["expected_intent"],
            expected_vulnerability_detected=case["expected_vulnerability_detected"],
            expected_vulnerability_category=case["expected_vulnerability_category"],
            expected_special_request=case["expected_special_request"],
            expected_escalation_reason=case["expected_escalation_reason"],
        )
        for case in raw["cases"]
    ]
    return EvalDataset(
        dataset_version=raw["dataset_version"], provenance=raw["provenance"], cases=cases
    )


def load_dataset(path: Path = _DEFAULT_PATH) -> EvalDataset:
    return parse_dataset(json.loads(path.read_text(encoding="utf-8")))
