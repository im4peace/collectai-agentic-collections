"""Loads the checked-in `eval_ds_v1.json` into `collectai_eval.schemas
.EvalDataset` (E10-S1 AC1, AC6). The dataset file is the single source of
truth for `dataset_version` -- bump it in the JSON (and regenerate via
`_build_eval_ds_v1.py` if the templates changed) to publish a new version;
this loader and every `EvalRun` it feeds record whatever version the file
itself declares, never a hardcoded constant here.
"""

from __future__ import annotations

import json
from pathlib import Path

from collectai_eval.schemas import EvalCase, EvalDataset

_DEFAULT_PATH = Path(__file__).resolve().parent / "eval_ds_v1.json"


def load_dataset(path: Path = _DEFAULT_PATH) -> EvalDataset:
    raw = json.loads(path.read_text(encoding="utf-8"))
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
