from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from splunk_dashboard_studio import (
    build_catalog_dashboard,
    canonical_json,
    compare_roundtrip,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
HARNESS_PATH = REPO_ROOT / "integration" / "splunk-visual" / "scripts" / "harness.py"
RUNNER_PATH = REPO_ROOT / "integration" / "splunk-visual" / "run.sh"
DEFAULTS_PATH = REPO_ROOT / "integration" / "splunk-visual" / "defaults.yml"
COMPOSE_PATH = REPO_ROOT / "integration" / "splunk-visual" / "compose.yaml"
SOURCE_COMPOSE_PATH = REPO_ROOT / "integration" / "splunk-visual" / "compose.source-template.yaml"
BASELINES_PATH = REPO_ROOT / "integration" / "splunk-visual" / "baselines"
IMAGES_PATH = REPO_ROOT / "integration" / "splunk-visual" / "images.json"
VISUAL_PACKAGE_PATH = REPO_ROOT / "integration" / "splunk-visual" / "package.json"
VISUAL_WORKFLOW_PATH = REPO_ROOT / ".github" / "workflows" / "visual-regression.yml"
SOURCE_LOCK_PATH = REPO_ROOT / "integration" / "splunk-visual" / "source-lock.json"


def load_harness() -> ModuleType:
    spec = importlib.util.spec_from_file_location("splunk_visual_harness", HARNESS_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def load_manifest(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def test_image_registry_pins_every_supported_target_by_digest() -> None:
    harness = load_harness()
    records = [harness.image_record(target) for target in ("9.4.3", "10.0.0", "10.2.0", "10.4.0")]
    assert all("@sha256:" in record["image"] for record in records)
    assert records[0]["requires_general_terms"] is False
    assert all(record["requires_general_terms"] is True for record in records[1:])


def test_runner_automatically_passes_target_appropriate_acceptance_flags() -> None:
    runner = RUNNER_PATH.read_text(encoding="utf-8")
    workflow = VISUAL_WORKFLOW_PATH.read_text(encoding="utf-8")
    assert "SPLUNK_TERMS_ACCEPTED" not in runner
    assert "SPLUNK_TERMS_ACCEPTED" not in workflow
    assert 'export SPLUNK_START_ARGS="--accept-license"' in runner
    assert 'if [[ "${requires_general_terms}" == "true" ]]' in runner
    assert 'export SPLUNK_GENERAL_TERMS="--accept-sgt-current-at-splunk-com"' in runner
    assert 'export SPLUNK_GENERAL_TERMS=""' in runner
    assert "up --detach --wait --wait-timeout 900" in runner
    assert 'if [[ -d "${output}/apps/splunk_health" ]]' in runner
    assert "compose.source-template.yaml" in runner
    assert 'chown -R "$(id -u):$(id -g)" /opt/splunk/etc/apps/splunk_health' in runner


def test_free_fixture_enables_remote_management_only_for_local_rest_checks() -> None:
    defaults = DEFAULTS_PATH.read_text(encoding="utf-8")
    compose = COMPOSE_PATH.read_text(encoding="utf-8")
    assert "allowRemoteLogin: always" in defaults
    assert "SPLUNK_DEFAULTS_URL: file:///tmp/visual-qa-defaults.yml" in compose
    assert "./defaults.yml:/tmp/visual-qa-defaults.yml:ro" in compose
    assert "127.0.0.1:${SPLUNK_WEB_PORT:-8000}:8000" in compose
    assert "127.0.0.1:${SPLUNK_MGMT_PORT:-8089}:8089" in compose
    source_compose = SOURCE_COMPOSE_PATH.read_text(encoding="utf-8")
    assert "SPLUNK_HEALTH_APP_PATH" in source_compose
    assert ":/opt/splunk/etc/apps/splunk_health" in source_compose


def test_source_snapshot_matches_every_locked_app_and_harness_file() -> None:
    harness = load_harness()
    lock = harness._source_snapshot()
    assert lock == load_manifest(SOURCE_LOCK_PATH)
    assert lock["revision"] == "7424755c461712022367c3fa081fd7e0edc91001"
    assert len(lock["app"]["files"]) == 42
    assert len(lock["harnesses"]) == 8


def test_baseline_manifest_matches_harness_platform_and_browser_lock() -> None:
    baseline_manifest = load_manifest(BASELINES_PATH / "manifest.json")
    image_manifest = load_manifest(IMAGES_PATH)
    visual_package = load_manifest(VISUAL_PACKAGE_PATH)
    assert baseline_manifest["schema_version"] == "splunk-visual-baselines/v1"
    assert baseline_manifest["architecture"] == image_manifest["architecture"]
    assert baseline_manifest["playwright"] == visual_package["devDependencies"]["@playwright/test"]


@pytest.mark.parametrize("target", ("9.4.3", "10.0.0", "10.2.0", "10.4.0"))
def test_reviewed_full_baseline_inventory_is_complete(target: str, tmp_path: Path) -> None:
    harness = load_harness()
    run_manifest = load_manifest(
        harness.prepare(
            target=target,
            suite="full",
            output=tmp_path,
            include_state_cases=True,
        )
    )
    expected = {
        f"{dashboard['example_id']}-full.png".replace("_", "-")
        for dashboard in run_manifest["dashboards"]
    }
    expected.update(
        f"{dashboard['example_id']}-{panel['panel_id']}.png".replace("_", "-")
        for dashboard in run_manifest["dashboards"]
        for panel in dashboard["panels"]
    )
    actual = {path.name for path in (BASELINES_PATH / target).glob("*.png")}
    assert actual == expected

    baseline_manifest = load_manifest(BASELINES_PATH / "manifest.json")
    target_record = baseline_manifest["targets"][target]
    assert target_record["image"] == harness.image_record(target)["image"]
    assert target_record["result"] == "passed"
    assert target_record["suite"] == "full"
    assert target_record["screenshot_count"] == len(expected)
    digest_input = b"".join(
        f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.name}\n".encode()
        for path in sorted((BASELINES_PATH / target).glob("*.png"))
    )
    assert target_record["baseline_set_sha256"] == hashlib.sha256(digest_input).hexdigest()


def test_prepare_smoke_generates_fixture_views_without_mutating_catalog(tmp_path: Path) -> None:
    harness = load_harness()
    production_before = canonical_json(build_catalog_dashboard("business_journey_slo", "10.4.0"))

    manifest_path = harness.prepare(
        target="10.4.0",
        suite="smoke",
        output=tmp_path,
        include_state_cases=True,
    )

    manifest = load_manifest(manifest_path)
    assert manifest["schema_version"] == "splunk-visual-run/v1"
    assert manifest["suite"] == "smoke"
    assert manifest["target"] == "10.4.0"
    assert manifest["indexes"]["otel_metrics"] == "metric"
    dashboards = manifest["dashboards"]
    assert [item["example_id"] for item in dashboards] == [
        "microservice_service_map",
        "business_journey_slo",
        "rcastley_splunk_health",
        "state_no_data",
        "state_search_error",
    ]
    assert manifest["source_snapshot"]["revision"] == ("7424755c461712022367c3fa081fd7e0edc91001")
    assert manifest["required_apps"] == [
        {
            "app_id": "splunk_health",
            "path": "apps/splunk_health",
            "revision": "7424755c461712022367c3fa081fd7e0edc91001",
        }
    ]
    assert (tmp_path / "apps" / "splunk_health" / "default" / "app.conf").is_file()

    catalog_dashboards = [item for item in dashboards if item["expected_state"] == "ready"]
    assert all(item["source_queries"] for item in catalog_dashboards)
    assert all(
        search["fixture_query"].startswith("| makeresults")
        for dashboard in dashboards
        for search in dashboard["fixture_searches"]
    )
    assert all(
        "makeresults" not in source["query"]
        for dashboard in catalog_dashboards
        for source in dashboard["source_queries"]
    )
    assert canonical_json(build_catalog_dashboard("business_journey_slo", "10.4.0")) == (
        production_before
    )

    source_template = next(
        item for item in dashboards if item["example_id"] == "rcastley_splunk_health"
    )
    assert source_template["source_kind"] == "source_template"
    assert source_template["title_visible"] is False
    assert source_template["template_origin"]["definition_sha256"] == (
        "0371e79ed06eb10ee6298d6e54f32d5a99b744e44d812400845ad141de72febd"
    )
    assert len(source_template["panels"]) == 8
    assert all(panel["render_kind"] == "canvas" for panel in source_template["panels"])
    license_panel = next(
        panel
        for panel in source_template["panels"]
        if panel["visualization_type"] == "splunk_health.license_gauge"
    )
    assert license_panel["expected_rows"] == [{"used_gb": "42.5", "quota_gb": "100"}]
    assert license_panel["no_data_message"] == "Awaiting license data"
    assert license_panel["formatter_defaults"]["warningThreshold"] == "80"

    single_value = next(
        panel
        for dashboard in dashboards
        for panel in dashboard["panels"]
        if panel["visualization_type"] == "splunk.singlevalue"
    )
    assert single_value["expected_rows"] == [{"value": "99.95"}]
    assert single_value["ui_markers"] == ["100"]

    service_map = next(
        item for item in dashboards if item["example_id"] == "microservice_service_map"
    )
    assert service_map["title_visible"] is True
    network_graph = next(
        panel
        for panel in service_map["panels"]
        if panel["visualization_type"] == "splunk.networkGraph"
    )
    assert network_graph["ui_markers"] == ["gateway", "catalog", "checkout", "payments"]
    node_fixture = next(
        search
        for search in service_map["fixture_searches"]
        if search["data_source_id"] == "ds_dependency_map_nodes"
    )
    assert node_fixture["expected_rows"] == [
        {"nodeIds": "catalog", "nodeTexts": "catalog", "nodeValues": "120"},
        {"nodeIds": "checkout", "nodeTexts": "checkout", "nodeValues": "137"},
        {"nodeIds": "gateway", "nodeTexts": "gateway", "nodeValues": "215"},
        {"nodeIds": "payments", "nodeTexts": "payments", "nodeValues": "42"},
    ]
    service_map_definition = json.loads(
        (tmp_path / service_map["definition_path"]).read_text(encoding="utf-8")
    )
    assert service_map_definition["dataSources"]["ds_dependency_map_nodes"]["type"] == ("ds.chain")
    assert service_map_definition["visualizations"]["viz_dependency_map"]["dataSources"] == {
        "nodeSource": "ds_dependency_map_nodes",
        "primary": "ds_dependency_map",
    }

    no_data = next(item for item in dashboards if item["expected_state"] == "no_data")
    assert "no search results returned" in no_data["panels"][0]["ui_patterns"]

    for dashboard in dashboards:
        xml = (tmp_path / dashboard["view_xml_path"]).read_text(encoding="utf-8")
        assert compare_roundtrip(xml, xml).equivalent
        definition = json.loads((tmp_path / dashboard["definition_path"]).read_text())
        assert definition["title"] == dashboard["title"]


def test_prepare_removes_only_stale_harness_artifacts(tmp_path: Path) -> None:
    harness = load_harness()
    (tmp_path / "screenshots" / "stale").mkdir(parents=True)
    (tmp_path / "screenshots" / "stale" / "old.png").write_bytes(b"old")
    (tmp_path / "qa-overview.json").write_text("{}", encoding="utf-8")
    (tmp_path / "visual_qa_stale.xml").write_text("stale", encoding="utf-8")
    (tmp_path / "keep.txt").write_text("unrelated", encoding="utf-8")

    harness.prepare(
        target="10.4.0",
        suite="smoke",
        output=tmp_path,
        include_state_cases=False,
    )

    assert not (tmp_path / "screenshots").exists()
    assert not (tmp_path / "qa-overview.json").exists()
    assert not (tmp_path / "visual_qa_stale.xml").exists()
    assert (tmp_path / "keep.txt").read_text(encoding="utf-8") == "unrelated"


def test_full_suite_respects_catalog_minimum_target(tmp_path: Path) -> None:
    harness = load_harness()
    target_94 = harness.prepare(
        target="9.4.3",
        suite="full",
        output=tmp_path / "94",
        include_state_cases=False,
    )
    target_104 = harness.prepare(
        target="10.4.0",
        suite="full",
        output=tmp_path / "104",
        include_state_cases=False,
    )
    ids_94 = {item["example_id"] for item in load_manifest(target_94)["dashboards"]}
    ids_104 = {item["example_id"] for item in load_manifest(target_104)["dashboards"]}
    assert len(ids_94) == 10
    assert len(ids_104) == 11
    assert "microservice_service_map" not in ids_94
    assert "microservice_service_map" in ids_104
    assert "rcastley_splunk_health" not in ids_94
    assert "rcastley_splunk_health_portable" in ids_94
    assert "rcastley_splunk_health" in ids_104
    assert "rcastley_splunk_health_portable" not in ids_104


def test_splunk_9_suite_uses_portable_template_without_installing_app(tmp_path: Path) -> None:
    harness = load_harness()
    manifest = load_manifest(
        harness.prepare(
            target="9.4.3",
            suite="smoke",
            output=tmp_path,
            include_state_cases=False,
        )
    )
    assert manifest["required_apps"] == []
    assert manifest["source_snapshot"]["revision"] == ("7424755c461712022367c3fa081fd7e0edc91001")
    assert not (tmp_path / "apps").exists()
    source_template = next(
        item
        for item in manifest["dashboards"]
        if item["example_id"] == "rcastley_splunk_health_portable"
    )
    assert source_template["source_kind"] == "source_template"
    assert {panel["visualization_type"] for panel in source_template["panels"]} == {
        "splunk.singlevalue",
        "splunk.table",
    }
    assert all("render_kind" not in panel for panel in source_template["panels"])


def test_search_dispatch_prefix_preserves_generating_commands() -> None:
    harness = load_harness()
    assert harness._search_value("| makeresults") == "| makeresults"
    assert harness._search_value("search index=main") == "search index=main"
    assert harness._search_value("index=main | stats count") == "search index=main | stats count"


def test_fixture_search_validation_accepts_declared_error_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    harness = load_harness()
    manifest_path = harness.prepare(
        target="10.4.0",
        suite="smoke",
        output=tmp_path,
        include_state_cases=True,
    )
    manifest = load_manifest(manifest_path)
    expected_by_query = {
        search["fixture_query"]: search["expected_rows"]
        for dashboard in manifest["dashboards"]
        for search in dashboard["fixture_searches"]
    }

    def fake_run_search(
        _client: object, query: str
    ) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
        if "visual_qa_command_does_not_exist" in query:
            return [], [{"type": "ERROR", "text": "Unknown search command"}]
        return expected_by_query[query], []

    monkeypatch.setattr(harness, "run_search", fake_run_search)
    result = harness.validate_searches(object(), manifest_path, kind="fixture")
    assert result["failures"] == []
    error_check = next(item for item in result["checks"] if "state_search_error" in item["id"])
    assert error_check["passed"] is True
    assert error_check["rows"] == []


def test_search_export_accepts_structured_http_400_error() -> None:
    harness = load_harness()

    class FakeClient:
        allowed: tuple[int, ...] | None = None

        def request(self, *_args: Any, **kwargs: Any) -> object:
            self.allowed = kwargs["allowed"]
            body = b'{"messages":[{"type":"ERROR","text":"bad command"}]}\n'
            return harness.SplunkResponse(400, body)

    client = FakeClient()
    rows, messages = harness.run_search(client, "| invalid")
    assert client.allowed == (200, 400)
    assert rows == []
    assert messages == [{"type": "ERROR", "text": "bad command"}]
