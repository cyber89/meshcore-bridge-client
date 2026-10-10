"""Inspect phase-0 wheels without installing packages or importing the bridge.

Requires packaging from the existing development environment. This is an artifact
and metadata audit, not a test suite or a certificate of platform interoperability.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import zipfile
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from email.parser import BytesParser
from pathlib import Path

from packaging.markers import default_environment
from packaging.requirements import Requirement
from packaging.specifiers import SpecifierSet
from packaging.tags import compatible_tags, cpython_tags
from packaging.utils import canonicalize_name, parse_wheel_filename
from packaging.version import Version


@dataclass(frozen=True)
class Target:
    name: str
    python: str
    platform: str
    machine: str


TARGETS = (
    Target("win-cp310", "3.10", "Windows", "AMD64"),
    Target("win-cp312", "3.12", "Windows", "AMD64"),
    Target("linux-x64-cp310", "3.10", "Linux", "x86_64"),
    Target("linux-x64-cp312", "3.12", "Linux", "x86_64"),
    Target("linux-arm64-cp310", "3.10", "Linux", "aarch64"),
    Target("linux-arm64-cp312", "3.12", "Linux", "aarch64"),
)


@dataclass(frozen=True)
class Wheel:
    name: str
    version: str
    filename: str
    sha256: str
    size_bytes: int
    requires_python: str
    requires_dist: list[str]
    tags: list[str]


def inspect_wheel(path: Path) -> Wheel:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    with zipfile.ZipFile(path) as archive:
        names = [n for n in archive.namelist() if n.endswith(".dist-info/METADATA")]
        if len(names) != 1:
            raise ValueError(f"Expected one METADATA record in {path.name}")
        metadata = BytesParser().parsebytes(archive.read(names[0]))
    name = metadata.get("Name")
    version = metadata.get("Version")
    if not name or not version:
        raise ValueError(f"Missing package identity in {path.name}")
    file_name, file_version, _, tags = parse_wheel_filename(path.name)
    if canonicalize_name(name) != file_name or Version(version) != file_version:
        raise ValueError(f"Wheel filename and METADATA disagree in {path.name}")
    return Wheel(
        canonicalize_name(name), version, path.name, digest.hexdigest(),
        path.stat().st_size, metadata.get("Requires-Python", ""),
        metadata.get_all("Requires-Dist", []), sorted(str(tag) for tag in tags),
    )


def target_markers(target: Target) -> dict[str, str]:
    environment = dict(default_environment())
    environment.update(
        implementation_name="cpython",
        implementation_version=f"{target.python}.0",
        platform_python_implementation="CPython",
        python_version=target.python,
        python_full_version=f"{target.python}.0",
        sys_platform="win32" if target.platform == "Windows" else "linux",
        os_name="nt" if target.platform == "Windows" else "posix",
        platform_system=target.platform,
        platform_machine=target.machine,
        platform_release="",
        platform_version="",
        extra="",
    )
    return environment


def audit_target(target: Target, downloads: Path, manifests: Path) -> dict[str, object]:
    major, minor = target.python.split(".")
    python_version = (int(major), int(minor))
    interpreter = "cp" + target.python.replace(".", "")
    if target.platform == "Windows":
        platforms = ["win_amd64"]
    else:
        # glibc 2.17 can load wheels targeting earlier supported glibc versions.
        floor = 5 if target.machine == "x86_64" else 17
        platforms = [
            f"manylinux_2_{minor}_{target.machine}" for minor in range(17, floor - 1, -1)
        ]
        platforms.append(f"manylinux2014_{target.machine}")
        if target.machine == "x86_64":
            platforms.extend(["manylinux2010_x86_64", "manylinux1_x86_64"])
    accepted_tags = {
        str(tag) for tag in cpython_tags(python_version, [interpreter], platforms)
    } | {
        str(tag) for tag in compatible_tags(python_version, interpreter, platforms)
    }
    expected: dict[str, str] = {}
    for line in (manifests / f"{target.name}.txt").read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        match = re.fullmatch(r"([A-Za-z0-9_.-]+)==([^ ;]+)", line.strip())
        if match is None:
            raise ValueError(f"Unexpected requirement line: {line}")
        expected[canonicalize_name(match[1])] = match[2]

    wheels: dict[str, Wheel] = {}
    issues: list[str] = []
    for path in sorted((downloads / target.name).glob("*.whl")):
        wheel = inspect_wheel(path)
        if wheel.name in wheels:
            issues.append(f"Duplicate wheel for {wheel.name}")
        wheels[wheel.name] = wheel
    for name in sorted(expected.keys() | wheels.keys()):
        if name not in wheels:
            issues.append(f"Missing wheel: {name}")
        elif name not in expected:
            issues.append(f"Unresolved extra wheel: {name}")
        elif wheels[name].version != expected[name]:
            issues.append(f"Version mismatch: {name}")

    environment = target_markers(target)
    for wheel in wheels.values():
        if not accepted_tags.intersection(wheel.tags):
            issues.append(f"Wheel tag mismatch: {wheel.filename}")
        if wheel.requires_python and not SpecifierSet(wheel.requires_python).contains(
            Version(environment["python_full_version"]), prereleases=False,
        ):
            issues.append(f"Requires-Python mismatch: {wheel.name} {wheel.requires_python}")
        for raw_requirement in wheel.requires_dist:
            requirement = Requirement(raw_requirement)
            if requirement.marker and not requirement.marker.evaluate(environment):
                continue
            name = canonicalize_name(requirement.name)
            dependency = wheels.get(name)
            if dependency is None:
                issues.append(f"Missing dependency: {wheel.name} -> {raw_requirement}")
            elif not requirement.specifier.contains(Version(dependency.version), prereleases=False):
                issues.append(f"Dependency version mismatch: {wheel.name} -> {raw_requirement}")
            if requirement.extras:
                issues.append(f"Dependency extras need separate evaluation: {raw_requirement}")
    return {
        "target": asdict(target),
        "marker_environment": environment,
        "accepted_platforms": platforms,
        "manifest_sha256": hashlib.sha256(
            (manifests / f"{target.name}.txt").read_bytes(),
        ).hexdigest(),
        "package_count": len(wheels),
        "download_bytes": sum(w.size_bytes for w in wheels.values()),
        "wheels": [asdict(w) for w in wheels.values()],
        "issues": issues,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--downloads", type=Path, default=Path("artifacts/fastapi-phase0"))
    parser.add_argument("--manifests", type=Path, default=Path("docs/fastapi/dependencies"))
    parser.add_argument("--output", type=Path, default=Path("docs/fastapi/dependencies/resolution.json"))
    args = parser.parse_args()
    results = [audit_target(t, args.downloads, args.manifests) for t in TARGETS]
    report = {
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "scope": "wheel hashes, filename/METADATA identity, target tags, pinned versions, Requires-Python and dependency markers",
        "download_index": "https://pypi.org/simple",
        "input_sha256": hashlib.sha256((args.manifests / "candidate.in").read_bytes()).hexdigest(),
        "not_verified": ["runtime", "platform ABI execution", "bridge lifecycle", "performance"],
        "targets": results,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    for result in results:
        target = result["target"]
        print(f"{target}: {result['package_count']} wheels; issues={result['issues']}")
    return int(any(result["issues"] for result in results))


if __name__ == "__main__":
    raise SystemExit(main())
