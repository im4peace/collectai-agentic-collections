"""Regenerate `backend/constraints.txt`, the pip constraints file CI and Docker install with.

    python scripts/generate_constraints.py

It resolves `pyproject.toml`'s dependencies plus the `dev` extra as pip would on **Python 3.11 /
Linux** (the interpreter and platform CI and the backend Docker image use), whichever machine or
Python runs this script, and writes every resolved package as `name==version`. It needs network
access to the package index, installs nothing (`pip install --dry-run`) and only writes the file.

pip evaluates environment markers (`sys_platform == "win32"` and so on) for the machine it runs
on, whatever `--platform` says. So the script re-walks pip's dependency report with Linux /
Python 3.11 markers: packages only a Windows install needs (`colorama`, `tzdata`) are dropped, and
packages only Linux needs (`uvloop`) are added and resolved. It uses `packaging`, a declared dev
dependency.

Refresh it deliberately, when you want newer dependencies, and review the diff: the whole point
of the file is that dependency versions change only when someone changes them.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import tomllib
from pathlib import Path
from typing import Any

from packaging.markers import default_environment
from packaging.requirements import Requirement
from packaging.utils import canonicalize_name

BACKEND = Path(__file__).resolve().parent.parent
OUTPUT = BACKEND / "constraints.txt"
_PLATFORMS = ("manylinux2014_x86_64", "manylinux_2_28_x86_64", "any")
_TARGET_ENVIRONMENT: dict[str, Any] = {
    **default_environment(),
    "sys_platform": "linux",
    "platform_system": "Linux",
    "os_name": "posix",
    "platform_machine": "x86_64",
    "platform_python_implementation": "CPython",
    "implementation_name": "cpython",
    "python_version": "3.11",
    "python_full_version": "3.11.0",
    "implementation_version": "3.11.0",
}

_HEADER = """\
# Pip constraints for reproducible backend installs (CI and the backend Docker image).
#
# Used as:  pip install -c constraints.txt -e ".[dev]"     (CI, from backend/)
#           pip install -c constraints.txt .               (backend/Dockerfile)
# Resolved for Python 3.11 / Linux from pyproject.toml's dependencies plus the `dev` extra.
# A constraints file only pins versions; it does not add packages. On another Python or OS
# (for example a local Windows virtualenv) it is optional and may not install cleanly.
#
# Do not edit by hand. Refresh (needs network, installs nothing):
#   python scripts/generate_constraints.py
# `tests/unit/config/test_dependency_constraints.py` fails if a direct dependency is missing here
# or pinned outside the range pyproject.toml allows.
"""


def _requirements() -> list[str]:
    project = tomllib.loads((BACKEND / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    return [*project["dependencies"], *project["optional-dependencies"]["dev"]]


def _resolve(requirements: list[str]) -> dict[str, dict[str, Any]]:
    """pip's dry-run report for `requirements`, keyed by canonical package name."""
    with tempfile.TemporaryDirectory() as tmp:
        report = Path(tmp) / "report.json"
        command = [
            sys.executable, "-m", "pip", "install", "--dry-run", "--quiet",
            "--disable-pip-version-check", "--ignore-installed", "--only-binary=:all:",
            "--python-version", "3.11", "--implementation", "cp", "--abi", "cp311",
            "--target", str(Path(tmp) / "target"), "--report", str(report),
        ]
        for platform in _PLATFORMS:
            command += ["--platform", platform]
        subprocess.run([*command, *requirements], check=True)
        installed = json.loads(report.read_text(encoding="utf-8"))["install"]
    return {canonicalize_name(item["metadata"]["name"]): item["metadata"] for item in installed}


def _walk(
    roots: list[str], packages: dict[str, dict[str, Any]]
) -> tuple[set[str], list[str]]:
    """The packages a Linux / Python 3.11 install of `roots` needs, and the requirements of
    those that `packages` (resolved with this machine's markers) does not contain."""
    needed: dict[str, set[str]] = {}
    missing: list[str] = []
    pending = [Requirement(root) for root in roots]
    while pending:
        requirement = pending.pop()
        name = canonicalize_name(requirement.name)
        extras = set(requirement.extras)
        if name in needed and extras <= needed[name]:
            continue
        needed.setdefault(name, set()).update(extras)
        metadata = packages.get(name)
        if metadata is None:
            missing.append(f"{requirement.name}[{','.join(sorted(extras))}]" if extras else name)
            continue
        for spec in metadata.get("requires_dist") or []:
            child = Requirement(spec)
            if child.marker is None or any(
                child.marker.evaluate({**_TARGET_ENVIRONMENT, "extra": extra})
                for extra in (needed[name] or {""})
            ):
                pending.append(child)
    return set(needed), missing


def _linux_pins(requirements: list[str]) -> list[tuple[str, str]]:
    wanted = list(requirements)
    for _ in range(5):  # each round can only add packages Linux needs and this machine did not
        packages = _resolve(wanted)
        needed, missing = _walk(requirements, packages)
        if not missing:
            break
        wanted += [m for m in missing if m not in wanted]
    else:
        raise SystemExit(f"dependency walk did not settle; still missing: {missing}")
    return sorted(
        ((str(packages[n]["name"]), str(packages[n]["version"])) for n in needed),
        key=lambda pair: pair[0].lower(),
    )


def main() -> None:
    pins = _linux_pins(_requirements())
    body = "".join(f"{name}=={version}\n" for name, version in pins)
    OUTPUT.write_bytes((_HEADER + "\n" + body).encode("utf-8"))
    print(f"Wrote {len(pins)} pins to {OUTPUT}")


if __name__ == "__main__":
    main()
