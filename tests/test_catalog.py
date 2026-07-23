from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from splunk_dashboard_studio.catalog import (
    CatalogEntryNotFound,
    CatalogTargetUnsupported,
    build_catalog_bundle,
    build_catalog_dashboard,
    catalog_entries,
    portable_telemetry_contract,
)
from splunk_dashboard_studio.cli import main
from splunk_dashboard_studio.generation import canonical_json
from splunk_dashboard_studio.version import EnterpriseVersion

TARGETS = ("9.4.3", "10.0.0", "10.2.0", "10.4.0")


def test_catalog_has_ten_stable_entries_and_declared_fields() -> None:
    entries = catalog_entries()
    assert len(entries) == 10
    assert tuple(entry.example_id for entry in entries) == tuple(
        [
            "kubernetes_workload_health",
            "ec2_host_capacity",
            "rds_database_health",
            "load_balancer_edge_health",
            "api_gateway_overview",
            "microservice_service_map",
            "batch_cron_reliability",
            "cicd_delivery_health",
            "security_operations_overview",
            "business_journey_slo",
        ]
    )
    assert len({entry.example_id for entry in entries}) == 10
    assert [entry.priority for entry in entries].count("high") == 6
    assert [entry.priority for entry in entries].count("medium") == 4

    contract = portable_telemetry_contract()
    assert contract.contract_id == "portable-observability-v1"
    assert set(contract.logical_indexes) == {
        "otel_metrics",
        "otel_logs",
        "otel_traces",
        "platform_events",
        "batch_events",
        "cicd_events",
        "security_events",
        "business_events",
    }
    declared_fields = {field.name for field in contract.fields}
    assert all(set(entry.required_fields) <= declared_fields for entry in entries)


@pytest.mark.parametrize(
    ("example_id", "minimum_target"),
    [(entry.example_id, str(entry.minimum_target)) for entry in catalog_entries()],
)
def test_catalog_dashboard_builds_deterministically_at_minimum_target(
    example_id: str,
    minimum_target: str,
) -> None:
    first = build_catalog_dashboard(example_id, minimum_target)
    second = build_catalog_dashboard(example_id, minimum_target)
    assert canonical_json(first) == canonical_json(second)
    assert first.layout.global_inputs == ["input_global_time"]
    assert first.inputs["input_global_time"].options["defaultValue"] == "-24h@h,now"
    assert first.defaults["dataSources"] == {
        "ds.search": {
            "options": {
                "queryParameters": {
                    "earliest": "$global_time.earliest$",
                    "latest": "$global_time.latest$",
                }
            }
        }
    }
    layout = first.layout.layout_definitions["layout_main"]
    assert layout.options["width"] == 1440
    assert len(layout.structure) == len(first.visualizations) == 5
    assert all("refresh" not in source.options for source in first.data_sources.values())


@pytest.mark.parametrize("target", TARGETS)
def test_catalog_builds_every_eligible_dashboard_for_each_profile(target: str) -> None:
    for entry in catalog_entries():
        if EnterpriseVersion.parse(target) < entry.minimum_target:
            continue
        definition = build_catalog_dashboard(entry.example_id, target)
        assert definition.title == entry.title


def test_catalog_rejects_unknown_and_unsupported_targets() -> None:
    with pytest.raises(CatalogEntryNotFound, match="Unknown catalog dashboard"):
        build_catalog_dashboard("missing", "10.4.0")
    with pytest.raises(CatalogTargetUnsupported, match=r"requires Splunk Enterprise 10\.4\.0"):
        build_catalog_dashboard("microservice_service_map", "10.2.0")


def test_catalog_bundle_hashes_the_canonical_definition() -> None:
    bundle = build_catalog_bundle("business_journey_slo", "9.4.3")
    encoded = canonical_json(bundle.definition).encode()
    assert bundle.manifest.definition_sha256 == hashlib.sha256(encoded).hexdigest()
    assert bundle.manifest.canonical_json_bytes == len(encoded)
    assert bundle.manifest.native_validation == "valid"
    assert bundle.manifest.official_validation == "not_run"
    assert bundle.manifest.saved_searches[0].ownership == "external"


def test_catalog_cli_lists_and_builds_artifacts(
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    assert main(["catalog", "list"]) == 0
    listing = json.loads(capsys.readouterr().out)
    assert listing["schema_version"] == "dashboard-catalog/v1"
    assert len(listing["entries"]) == 10

    output = tmp_path / "definition.json"
    assert (
        main(
            [
                "catalog",
                "build",
                "kubernetes_workload_health",
                "--target",
                "9.4.3",
                "--output",
                str(output),
            ]
        )
        == 0
    )
    assert json.loads(output.read_text())["title"] == "Kubernetes Workload Health"

    assert (
        main(
            [
                "catalog",
                "build",
                "business_journey_slo",
                "--target",
                "9.4.3",
                "--artifact",
                "bundle",
            ]
        )
        == 0
    )
    assert json.loads(capsys.readouterr().out)["manifest"]["schema_version"] == (
        "dashboard-evidence/v1"
    )


def test_catalog_cli_unsupported_target_returns_two(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert (
        main(
            [
                "catalog",
                "build",
                "microservice_service_map",
                "--target",
                "10.2.0",
            ]
        )
        == 2
    )
    assert json.loads(capsys.readouterr().out)["status"] == "error"
