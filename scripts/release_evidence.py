"""Verify release identity and create deterministic checksums and evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import tomllib
from pathlib import Path
from typing import Any

from splunk_dashboard_studio import __version__
from splunk_dashboard_studio.catalog import build_catalog_bundle, catalog_entries
from splunk_dashboard_studio.profiles import profile_manifest

ROOT = Path(__file__).resolve().parents[1]


def project_metadata() -> dict[str, Any]:
    value = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    project = value.get("project")
    if not isinstance(project, dict):
        raise ValueError("pyproject.toml must contain [project]")
    return project


def verify_release_tag(tag: str) -> str:
    project = project_metadata()
    version = project.get("version")
    if not isinstance(version, str):
        raise ValueError("project.version must be a string")
    if version != __version__:
        raise ValueError(
            f"pyproject version {version!r} does not match runtime version {__version__!r}"
        )
    expected_tag = f"v{version}"
    if tag != expected_tag:
        raise ValueError(f"Release tag {tag!r} must equal {expected_tag!r}")
    return version


def _artifact(path: Path) -> dict[str, str | int]:
    content = path.read_bytes()
    return {
        "name": path.name,
        "bytes": len(content),
        "sha256": hashlib.sha256(content).hexdigest(),
    }


def build_release_evidence(tag: str, distribution_directory: Path) -> dict[str, Any]:
    version = verify_release_tag(tag)
    artifacts = sorted(
        [
            *distribution_directory.glob("*.whl"),
            *distribution_directory.glob("*.tar.gz"),
        ]
    )
    project = project_metadata()
    distribution_name = str(project["name"]).replace("-", "_")
    expected_wheel_prefix = f"{distribution_name}-{version}-"
    expected_sdist = f"{distribution_name}-{version}.tar.gz"
    wheels = [path for path in artifacts if path.suffix == ".whl"]
    sdists = [path for path in artifacts if path.name.endswith(".tar.gz")]
    if len(wheels) != 1:
        raise ValueError("Release evidence requires exactly one wheel")
    if len(sdists) != 1:
        raise ValueError("Release evidence requires exactly one sdist")
    if not wheels[0].name.startswith(expected_wheel_prefix):
        raise ValueError(
            f"Wheel {wheels[0].name!r} does not match release {distribution_name}-{version}"
        )
    if sdists[0].name != expected_sdist:
        raise ValueError(f"Sdist {sdists[0].name!r} must equal {expected_sdist!r}")
    catalog = []
    for entry in catalog_entries():
        bundle = build_catalog_bundle(entry.example_id, str(entry.minimum_target))
        catalog.append(
            {
                "example_id": entry.example_id,
                "minimum_target": str(entry.minimum_target),
                "definition_sha256": bundle.manifest.definition_sha256,
            }
        )
    return {
        "schema_version": "release-evidence/v1",
        "package": {
            "name": project["name"],
            "version": version,
            "requires_python": project["requires-python"],
            "tag": tag,
        },
        "artifacts": [_artifact(path) for path in artifacts],
        "catalog": catalog,
        "compatibility": profile_manifest(),
        "verification": {
            "native": [
                "ruff format --check",
                "ruff check",
                "mypy",
                "pytest with branch coverage",
                "native compatibility corpus",
                "checked examples",
                "distribution inspection",
            ],
            "official_engines": "validated by the release workflow matrix",
            "live_splunk_roundtrip": "deferred",
        },
    }


def _write_outputs(
    evidence: dict[str, Any],
    output: Path,
    checksums_output: Path,
) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(evidence, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    artifacts = evidence["artifacts"]
    checksums_output.parent.mkdir(parents=True, exist_ok=True)
    checksums_output.write_text(
        "".join(f"{artifact['sha256']}  {artifact['name']}\n" for artifact in artifacts),
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tag", required=True)
    parser.add_argument("--dist", type=Path, default=ROOT / "dist")
    parser.add_argument("--output", type=Path, default=ROOT / "release" / "evidence.json")
    parser.add_argument(
        "--checksums-output",
        type=Path,
        default=ROOT / "release" / "SHA256SUMS",
    )
    parser.add_argument("--check-version-only", action="store_true")
    arguments = parser.parse_args()
    try:
        version = verify_release_tag(arguments.tag)
        if arguments.check_version_only:
            print(json.dumps({"status": "valid", "tag": arguments.tag, "version": version}))
            return 0
        evidence = build_release_evidence(arguments.tag, arguments.dist)
        _write_outputs(evidence, arguments.output, arguments.checksums_output)
    except (OSError, ValueError, KeyError) as error:
        print(
            json.dumps(
                {"status": "error", "error_type": type(error).__name__, "message": str(error)},
                sort_keys=True,
            )
        )
        return 2
    print(
        json.dumps(
            {
                "status": "valid",
                "tag": arguments.tag,
                "artifacts": len(evidence["artifacts"]),
                "output": str(arguments.output),
                "checksums": str(arguments.checksums_output),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
