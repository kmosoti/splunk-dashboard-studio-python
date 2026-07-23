#!/usr/bin/env python3
"""Synchronize the public dashboard gallery from reviewed live Splunk baselines."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path
from typing import Final

ROOT: Final = Path(__file__).resolve().parents[1]
BASELINES: Final = ROOT / "integration" / "splunk-visual" / "baselines"
OUTPUT: Final = ROOT / "docs" / "images" / "dashboard-samples"
MANIFEST_PATH: Final = OUTPUT / "manifest.json"
SAMPLES: Final = (
    {
        "sample_id": "splunk_health_portable_94",
        "title": "Splunk Health portable port",
        "target": "9.4.3",
        "baseline": "rcastley-splunk-health-portable-full.png",
        "output": "splunk-health-portable-9.4.png",
    },
    {
        "sample_id": "kubernetes_workload_health_94",
        "title": "Kubernetes workload health",
        "target": "9.4.3",
        "baseline": "kubernetes-workload-health-full.png",
        "output": "kubernetes-workload-health-9.4.png",
    },
    {
        "sample_id": "business_journey_slo_102",
        "title": "Business journey SLO",
        "target": "10.2.0",
        "baseline": "business-journey-slo-full.png",
        "output": "business-journey-slo-10.2.png",
    },
    {
        "sample_id": "microservice_service_map_104",
        "title": "Microservice service map",
        "target": "10.4.0",
        "baseline": "microservice-service-map-full.png",
        "output": "microservice-service-map-10.4.png",
    },
    {
        "sample_id": "splunk_health_custom_104",
        "title": "Splunk Health custom visualization source",
        "target": "10.4.0",
        "baseline": "rcastley-splunk-health-full.png",
        "output": "splunk-health-custom-10.4.png",
    },
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _manifest() -> dict[str, object]:
    records = []
    for sample in SAMPLES:
        source = BASELINES / sample["target"] / sample["baseline"]
        if not source.is_file():
            raise FileNotFoundError(f"Missing reviewed baseline {source.relative_to(ROOT)}")
        records.append(
            {
                "baseline_path": source.relative_to(ROOT).as_posix(),
                "bytes": source.stat().st_size,
                "image_sha256": _sha256(source),
                "output_path": (OUTPUT / sample["output"]).relative_to(ROOT).as_posix(),
                "sample_id": sample["sample_id"],
                "target": sample["target"],
                "title": sample["title"],
            }
        )
    return {
        "schema_version": "dashboard-sample-gallery/v1",
        "source": "reviewed live Splunk Enterprise Playwright baselines",
        "samples": records,
    }


def sync(*, write: bool) -> list[dict[str, str]]:
    manifest = _manifest()
    expected_manifest = json.dumps(manifest, indent=2, sort_keys=True) + "\n"
    failures: list[dict[str, str]] = []
    if write:
        OUTPUT.mkdir(parents=True, exist_ok=True)
    for sample in SAMPLES:
        source = BASELINES / sample["target"] / sample["baseline"]
        destination = OUTPUT / sample["output"]
        if write:
            shutil.copyfile(source, destination)
        elif not destination.is_file():
            failures.append({"path": destination.relative_to(ROOT).as_posix(), "reason": "missing"})
        elif destination.read_bytes() != source.read_bytes():
            failures.append({"path": destination.relative_to(ROOT).as_posix(), "reason": "drifted"})
    if write:
        MANIFEST_PATH.write_text(expected_manifest, encoding="utf-8")
    elif not MANIFEST_PATH.is_file():
        failures.append({"path": MANIFEST_PATH.relative_to(ROOT).as_posix(), "reason": "missing"})
    elif MANIFEST_PATH.read_text(encoding="utf-8") != expected_manifest:
        failures.append({"path": MANIFEST_PATH.relative_to(ROOT).as_posix(), "reason": "drifted"})
    return failures


def main() -> int:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--write", action="store_true")
    arguments = parser.parse_args()
    try:
        failures = sync(write=arguments.write)
    except OSError as error:
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
                "failures": failures,
                "mode": "write" if arguments.write else "check",
                "samples": len(SAMPLES),
                "status": "drifted" if failures else "valid",
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
