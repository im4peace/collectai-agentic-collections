"""Risk R5 (BRD 13.5, "scope creep: dashboard or streaming ahead of slices"): the
control is the vertical-slice rule, enforced here on the story files -- a story
never depends on a story in a later slice, and the manager dashboard is built
after every journey story (BRD 7: "the dashboard must not move ahead of Slice
1's journey", D-017).
"""

from __future__ import annotations

import re

from ._docs import REPO_ROOT, read_text

_STORIES = REPO_ROOT / "specs" / "stories"
_JOURNEY_STORIES = ("E11-S1", "E11-S2", "E11-S3", "E11-S4")
_DASHBOARD_STORY = "E10-S4"


def _stories() -> dict[str, dict[str, object]]:
    stories: dict[str, dict[str, object]] = {}
    for path in sorted(_STORIES.glob("E*-S*.md")):
        text = read_text(path)
        story_id = re.search(r"\*\*ID:\*\* (\S+)", text)
        slice_number = re.search(r"\*\*Slice:\*\* (\d+)", text)
        depends = re.search(r"\*\*depends_on:\*\* (.*)", text)
        assert story_id and slice_number, path.name
        stories[story_id.group(1)] = {
            "slice": int(slice_number.group(1)),
            "depends_on": (
                []
                if depends is None or depends.group(1).strip() in {"", "-", "none"}
                else [item.strip() for item in depends.group(1).split(",")]
            ),
        }
    return stories


def test_the_story_files_are_parsed() -> None:
    stories = _stories()

    assert len(stories) >= 50
    assert _DASHBOARD_STORY in stories


def test_no_story_depends_on_a_story_in_a_later_slice() -> None:
    stories = _stories()

    violations = [
        f"{story_id} (slice {info['slice']}) depends on {dep} (slice {stories[dep]['slice']})"
        for story_id, info in stories.items()
        for dep in info["depends_on"]  # type: ignore[attr-defined]
        if dep in stories and stories[dep]["slice"] > info["slice"]  # type: ignore[operator]
    ]
    assert violations == []


def test_the_dashboard_story_is_built_after_every_journey_story() -> None:
    stories = _stories()
    dashboard_slice = stories[_DASHBOARD_STORY]["slice"]

    for journey in _JOURNEY_STORIES:
        assert dashboard_slice > stories[journey]["slice"], (  # type: ignore[operator]
            f"{_DASHBOARD_STORY} must come after journey {journey}"
        )
