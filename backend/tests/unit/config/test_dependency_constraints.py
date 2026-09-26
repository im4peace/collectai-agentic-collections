"""`backend/constraints.txt` keeps CI and the backend image reproducible.

Without it every install resolved the newest release of every dependency (`sqlalchemy>=2.0,<3`
and so on), so a new upstream release could turn CI red overnight, which is what SQLAlchemy 2.1.0
did. These tests keep the file honest: every direct dependency is pinned exactly, inside the range
`pyproject.toml` declares, and the Dockerfile installs with it.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

from packaging.requirements import Requirement
from packaging.utils import canonicalize_name
from packaging.version import Version

BACKEND = Path(__file__).resolve().parents[3]
_PIN = re.compile(r"^(?P<name>[A-Za-z0-9][A-Za-z0-9._-]*)==(?P<version>[A-Za-z0-9.!+_-]+)$")


def _direct_requirements() -> list[Requirement]:
    project = tomllib.loads((BACKEND / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    specs = [*project["dependencies"], *project["optional-dependencies"]["dev"]]
    return [Requirement(spec) for spec in specs]


def _pins() -> dict[str, Version]:
    pins: dict[str, Version] = {}
    for line in (BACKEND / "constraints.txt").read_text(encoding="utf-8").splitlines():
        text = line.strip()
        if not text or text.startswith("#"):
            continue
        match = _PIN.match(text)
        assert match is not None, f"not an exact name==version pin: {line!r}"
        name = canonicalize_name(match["name"])
        assert name not in pins, f"{name} is pinned twice"
        pins[name] = Version(match["version"])
    return pins


def test_every_line_is_an_exact_pin_and_no_package_is_pinned_twice() -> None:
    assert len(_pins()) > 40


def test_every_direct_dependency_is_pinned_inside_the_range_pyproject_allows() -> None:
    pins = _pins()
    for requirement in _direct_requirements():
        name = canonicalize_name(requirement.name)
        assert name in pins, f"{requirement.name} has no pin in constraints.txt"
        assert requirement.specifier.contains(pins[name], prereleases=True), (
            f"{requirement.name}=={pins[name]} is outside pyproject's {requirement.specifier}"
        )


def test_the_project_itself_is_not_constrained() -> None:
    assert "collectai" not in _pins()


def test_ci_exercises_the_sqlalchemy_2_1_line_the_code_was_updated_for() -> None:
    """The typing fixes for SQLAlchemy 2.1 are verified on 2.0.x and 2.1.x; the lock deliberately
    sits on 2.1 so CI keeps exercising the newer line rather than falling back to 2.0."""
    version = _pins()["sqlalchemy"]
    assert Version("2.1") <= version < Version("3")


def test_the_pins_are_resolved_for_linux_not_for_the_machine_that_generated_them() -> None:
    """pip evaluates environment markers for the machine it runs on, so a file generated on
    Windows once pinned Windows-only packages and missed `uvloop`, which `uvicorn[standard]` pulls
    in on Linux (CI and the Docker image). The generator now re-walks the dependencies with Linux
    markers."""
    pins = _pins()

    assert {"colorama", "tzdata", "pywin32"}.isdisjoint(pins)
    assert "uvloop" in pins


def test_the_backend_image_installs_with_the_same_constraints() -> None:
    dockerfile = (BACKEND / "Dockerfile").read_text(encoding="utf-8")

    assert re.search(r"^COPY .*constraints\.txt", dockerfile, re.MULTILINE), (
        "the Dockerfile must copy constraints.txt into the build stage"
    )
    assert re.search(r"pip install .*-c constraints\.txt", dockerfile), (
        "the Dockerfile must install with -c constraints.txt"
    )
