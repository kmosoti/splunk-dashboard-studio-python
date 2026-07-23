#!/usr/bin/env python3
"""Import the pinned rcastley source template and integration-only Splunk app snapshot."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
import subprocess
from pathlib import Path
from typing import Any, Final

ROOT: Final = Path(__file__).resolve().parents[1]
INTEGRATION_ROOT: Final = ROOT / "integration" / "splunk-visual"
VENDOR_ROOT: Final = INTEGRATION_ROOT / "vendor" / "rcastley-splunk-custom-visualizations"
LOCK_PATH: Final = INTEGRATION_ROOT / "source-lock.json"
TEMPLATE_PATH: Final = (
    ROOT / "splunk_dashboard_studio" / "template_data" / "rcastley_splunk_health.json"
)
PORTABLE_TEMPLATE_PATH: Final = (
    ROOT / "splunk_dashboard_studio" / "template_data" / "rcastley_splunk_health_portable.json"
)
TEMPLATE_MANIFEST: Final = ROOT / "splunk_dashboard_studio" / "template_data" / "manifest.json"
REPOSITORY: Final = "https://github.com/rcastley/splunk-custom-visualizations"
REVISION: Final = "7424755c461712022367c3fa081fd7e0edc91001"
APP_SOURCE: Final = Path("splunk_health")
DEFINITION_SOURCE: Final = APP_SOURCE / "default/data/ui/views/splunk_health.xml"
HEALTH_VISUALIZATIONS: Final = (
    "forwarder_heatmap",
    "index_storage",
    "indexing_pipeline_flow",
    "license_gauge",
    "resource_gauge",
    "scheduler_health",
    "search_activity",
    "splunk_status_board",
)
EXCLUDED_APP_FILES: Final = {Path("splunk_health/.gitignore"), Path("splunk_health/build.sh")}
PORTABLE_VISUALIZATION_TYPES: Final = {
    "splunk_health.forwarder_heatmap": "splunk.table",
    "splunk_health.index_storage": "splunk.table",
    "splunk_health.indexing_pipeline_flow": "splunk.table",
    "splunk_health.license_gauge": "splunk.singlevalue",
    "splunk_health.resource_gauge": "splunk.table",
    "splunk_health.scheduler_health": "splunk.table",
    "splunk_health.search_activity": "splunk.table",
    "splunk_health.splunk_status_board": "splunk.table",
}


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _revision(source: Path) -> str:
    result = subprocess.run(
        ["git", "-C", str(source), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def _definition(source: Path) -> tuple[dict[str, Any], str]:
    xml = (source / DEFINITION_SOURCE).read_text(encoding="utf-8")
    match = re.search(r"<definition><!\[CDATA\[(.*)\]\]></definition>", xml, re.DOTALL)
    if match is None:
        raise ValueError(f"No Dashboard Studio definition found in {DEFINITION_SOURCE}")
    payload = json.loads(match.group(1))
    if not isinstance(payload, dict):
        raise ValueError("Upstream Dashboard Studio definition must be a JSON object")
    normalized = json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return payload, _sha256(normalized)


def _portable_definition(definition: dict[str, Any]) -> tuple[dict[str, Any], str]:
    """Adapt the pinned source dashboard to app-free built-ins without changing its SPL."""

    payload = copy.deepcopy(definition)
    payload["title"] = "Splunk Health (Portable)"
    payload["description"] = (
        "App-free built-in visualization port for Splunk Enterprise 9.4 and later."
    )
    visualizations = payload.get("visualizations")
    if not isinstance(visualizations, dict):
        raise ValueError("Upstream Dashboard Studio definition requires visualizations")
    for visualization_id, visualization in visualizations.items():
        if not isinstance(visualization, dict):
            raise ValueError(f"Visualization {visualization_id!r} must be an object")
        source_type = visualization.get("type")
        if not isinstance(source_type, str) or source_type not in PORTABLE_VISUALIZATION_TYPES:
            raise ValueError(
                f"Visualization {visualization_id!r} has unmapped source type {source_type!r}"
            )
        visualization["type"] = PORTABLE_VISUALIZATION_TYPES[source_type]
        visualization["options"] = {}
    normalized = json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return payload, _sha256(normalized)


def _app_files(source: Path) -> list[Path]:
    return [
        path.relative_to(source)
        for path in sorted((source / APP_SOURCE).rglob("*"))
        if path.is_file() and path.relative_to(source) not in EXCLUDED_APP_FILES
    ]


def _tree_hash(files: dict[str, str]) -> str:
    content = "".join(f"{digest}  {path}\n" for path, digest in sorted(files.items()))
    return _sha256(content.encode("utf-8"))


def _harness_source(name: str) -> Path:
    return Path(f"examples/{name}/appserver/static/visualizations/{name}/harness.json")


def _expected(source: Path) -> tuple[dict[str, Any], dict[str, str], dict[Path, bytes]]:
    revision = _revision(source)
    if revision != REVISION:
        raise ValueError(f"Source revision {revision!r} must equal pinned revision {REVISION!r}")
    definition, definition_hash = _definition(source)
    portable_definition, portable_definition_hash = _portable_definition(definition)
    generated: dict[Path, bytes] = {
        TEMPLATE_PATH: (
            json.dumps(definition, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
        ).encode("utf-8"),
        PORTABLE_TEMPLATE_PATH: (
            json.dumps(portable_definition, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
        ).encode("utf-8"),
        VENDOR_ROOT / "LICENSE": (source / "LICENSE").read_bytes(),
    }

    app_hashes: dict[str, str] = {}
    for source_path in _app_files(source):
        content = (source / source_path).read_bytes()
        app_hashes[source_path.as_posix()] = _sha256(content)
        generated[VENDOR_ROOT / source_path] = content

    harnesses = []
    for name in HEALTH_VISUALIZATIONS:
        source_path = _harness_source(name)
        content = (source / source_path).read_bytes()
        vendor_path = Path("harness") / f"{name}.json"
        generated[VENDOR_ROOT / vendor_path] = content
        harnesses.append(
            {
                "name": name,
                "sha256": _sha256(content),
                "source_path": source_path.as_posix(),
                "vendor_path": (VENDOR_ROOT.relative_to(ROOT) / vendor_path).as_posix(),
            }
        )

    lock = {
        "schema_version": "splunk-source-template-lock/v1",
        "repository": REPOSITORY,
        "revision": REVISION,
        "license": "Apache-2.0",
        "license_path": (VENDOR_ROOT.relative_to(ROOT) / "LICENSE").as_posix(),
        "license_sha256": _sha256((source / "LICENSE").read_bytes()),
        "definition": {
            "source_path": DEFINITION_SOURCE.as_posix(),
            "package_path": TEMPLATE_PATH.relative_to(ROOT).as_posix(),
            "sha256": definition_hash,
        },
        "app": {
            "app_id": "splunk_health",
            "source_path": APP_SOURCE.as_posix(),
            "vendor_path": (VENDOR_ROOT.relative_to(ROOT) / APP_SOURCE).as_posix(),
            "tree_sha256": _tree_hash(app_hashes),
            "files": app_hashes,
        },
        "harnesses": harnesses,
    }
    generated[LOCK_PATH] = (
        json.dumps(lock, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    ).encode("utf-8")
    definition_hashes = {
        "rcastley_splunk_health": definition_hash,
        "rcastley_splunk_health_portable": portable_definition_hash,
    }
    return lock, definition_hashes, generated


def _metadata_hashes() -> dict[str, str]:
    manifest = json.loads(TEMPLATE_MANIFEST.read_text(encoding="utf-8"))
    return {
        str(record["entry"]["template_id"]): str(record["entry"]["origin"]["definition_sha256"])
        for record in manifest["templates"]
    }


def sync(source: Path, *, check: bool) -> list[dict[str, str]]:
    _, definition_hashes, expected = _expected(source.resolve())
    metadata_hashes = _metadata_hashes()
    if any(
        metadata_hashes.get(template_id) != digest
        for template_id, digest in definition_hashes.items()
    ):
        raise ValueError(
            "Package source-template metadata does not match the imported definition hashes"
        )

    failures: list[dict[str, str]] = []
    for path, content in sorted(expected.items()):
        if check:
            if not path.exists():
                failures.append({"path": str(path.relative_to(ROOT)), "reason": "missing"})
            elif path.read_bytes() != content:
                failures.append({"path": str(path.relative_to(ROOT)), "reason": "drifted"})
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)

    if check and VENDOR_ROOT.exists():
        allowed = {path for path in expected if path.is_relative_to(VENDOR_ROOT)}
        vendor_files = (candidate for candidate in VENDOR_ROOT.rglob("*") if candidate.is_file())
        for path in sorted(vendor_files):
            if path not in allowed:
                failures.append({"path": str(path.relative_to(ROOT)), "reason": "unexpected"})
    return failures


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True, help="Pinned upstream Git checkout")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--write", action="store_true")
    arguments = parser.parse_args()
    try:
        failures = sync(arguments.source, check=arguments.check)
    except (OSError, ValueError, subprocess.CalledProcessError, json.JSONDecodeError) as error:
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
                "status": "drifted" if failures else "valid",
                "mode": "check" if arguments.check else "write",
                "revision": REVISION,
                "failures": failures,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
