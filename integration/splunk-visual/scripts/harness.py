#!/usr/bin/env python3
"""Prepare and operate the disposable Splunk visual-regression fixture.

This script intentionally uses only the Python standard library and the local package. It is not
part of the distributed Python package and it never persists credentials.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import re
import shutil
import ssl
import sys
import time
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

from splunk_dashboard_studio import (
    DashboardBuilder,
    DashboardDefinition,
    EnterpriseVersion,
    StudioView,
    build_catalog_dashboard,
    build_source_template,
    canonical_json,
    catalog_entries,
    compare_roundtrip,
    encode_view_xml,
    portable_telemetry_contract,
    source_template_entries,
)

ROOT: Final = Path(__file__).resolve().parents[1]
REPO_ROOT: Final = ROOT.parents[1]
IMAGES_PATH: Final = ROOT / "images.json"
FIXTURES_PATH: Final = ROOT / "fixtures.json"
SOURCE_LOCK_PATH: Final = ROOT / "source-lock.json"
SOURCE_VENDOR_ROOT: Final = ROOT / "vendor" / "rcastley-splunk-custom-visualizations"
SCHEMA_VERSION: Final = "splunk-visual-run/v1"
RESULT_SCHEMA_VERSION: Final = "splunk-visual-results/v1"
HEALTH_HARNESS_BY_PANEL: Final = {
    "viz_forwarder_heatmap": "forwarder_heatmap",
    "viz_index_storage": "index_storage",
    "viz_indexing_pipeline": "indexing_pipeline_flow",
    "viz_license_gauge": "license_gauge",
    "viz_resource_gauge": "resource_gauge",
    "viz_scheduler_health": "scheduler_health",
    "viz_search_activity": "search_activity",
    "viz_status_board": "splunk_status_board",
}
PORTABLE_SOURCE_VISUALIZATIONS: Final = {"splunk.singlevalue", "splunk.table"}


class HarnessError(RuntimeError):
    """A deterministic harness or Splunk API failure."""


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise HarnessError(f"Unable to read JSON from {path}: {error}") from error
    if not isinstance(value, dict):
        raise HarnessError(f"Expected a JSON object in {path}")
    return value


def _write_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def image_record(target: str) -> dict[str, Any]:
    registry = _load_json(IMAGES_PATH)
    targets = registry.get("targets")
    if not isinstance(targets, dict) or target not in targets:
        available = ", ".join(sorted(targets if isinstance(targets, dict) else ()))
        raise HarnessError(f"Unsupported image target {target!r}; available targets: {available}")
    record = targets[target]
    if not isinstance(record, dict):
        raise HarnessError(f"Invalid image record for target {target!r}")
    return record


def _selected_ids(suite: str, target: str, fixtures: Mapping[str, Any]) -> list[str]:
    suites = fixtures.get("suites")
    if not isinstance(suites, dict) or suite not in suites:
        available = ", ".join(sorted(suites if isinstance(suites, dict) else ()))
        raise HarnessError(f"Unknown fixture suite {suite!r}; available suites: {available}")
    configured = suites[suite]
    if not isinstance(configured, list) or not all(isinstance(item, str) for item in configured):
        raise HarnessError(f"Fixture suite {suite!r} must be a string array")
    requested = (
        {entry.example_id for entry in catalog_entries()}
        if configured == ["*"]
        else set(configured)
    )
    platform = EnterpriseVersion.parse(target)
    return [
        entry.example_id
        for entry in catalog_entries()
        if entry.example_id in requested and platform >= entry.minimum_target
    ]


def _selected_template_ids(suite: str, target: str, fixtures: Mapping[str, Any]) -> list[str]:
    suites = fixtures.get("source_template_suites")
    if not isinstance(suites, dict) or suite not in suites:
        raise HarnessError(f"Fixture suite {suite!r} has no source-template selection")
    configured = suites[suite]
    if isinstance(configured, dict):
        configured = configured.get(target)
        if configured is None:
            raise HarnessError(
                f"Source-template suite {suite!r} has no selection for target {target!r}"
            )
    if not isinstance(configured, list) or not all(isinstance(item, str) for item in configured):
        raise HarnessError(f"Source-template suite {suite!r} must be a string array")
    entries = source_template_entries()
    requested = {entry.template_id for entry in entries} if configured == ["*"] else set(configured)
    known = {entry.template_id for entry in entries}
    unknown = requested - known
    if unknown:
        raise HarnessError(f"Unknown source-template IDs: {', '.join(sorted(unknown))}")
    platform = EnterpriseVersion.parse(target)
    return [
        entry.template_id
        for entry in entries
        if entry.template_id in requested and platform >= entry.minimum_target
    ]


def _visualization_contracts(fixtures: Mapping[str, Any]) -> Mapping[str, Any]:
    contracts = fixtures.get("visualization_contracts")
    if not isinstance(contracts, dict):
        raise HarnessError("fixtures.json requires visualization_contracts")
    return contracts


def _fixture_dashboard(
    example_id: str,
    target: str,
    fixtures: Mapping[str, Any],
) -> tuple[
    DashboardDefinition,
    list[dict[str, Any]],
    list[dict[str, str]],
    list[dict[str, Any]],
]:
    original = build_catalog_dashboard(example_id, target)
    payload = json.loads(canonical_json(original))
    contracts = _visualization_contracts(fixtures)
    panel_contracts: list[dict[str, Any]] = []
    fixture_searches_by_source: dict[str, dict[str, Any]] = {}
    for visualization_id, visualization in payload["visualizations"].items():
        visualization_type = visualization["type"]
        title = visualization.get("title", visualization_id)
        contract = contracts.get(visualization_type)
        if not isinstance(contract, dict):
            raise HarnessError(f"No render contract for visualization type {visualization_type!r}")
        source_id = visualization["dataSources"].get("primary")
        if not isinstance(source_id, str):
            raise HarnessError(f"{example_id}/{visualization_id} has no primary data source")
        fixture_query = contract.get("query")
        expected_rows = contract.get("expected_rows")
        ui_markers = contract.get("ui_markers")
        if not isinstance(fixture_query, str) or not isinstance(expected_rows, list):
            raise HarnessError(f"Invalid render contract for {visualization_type!r}")
        if not isinstance(ui_markers, list) or not all(
            isinstance(item, str) for item in ui_markers
        ):
            raise HarnessError(f"Invalid UI markers for {visualization_type!r}")
        panel_contracts.append(
            {
                "data_source_id": source_id,
                "expected_rows": expected_rows,
                "fixture_query": fixture_query,
                "panel_id": visualization_id,
                "title": title,
                "ui_markers": ui_markers,
                "visualization_type": visualization_type,
            }
        )
        auxiliary_contracts = contract.get("auxiliary_data_sources", {})
        if not isinstance(auxiliary_contracts, dict):
            raise HarnessError(f"Invalid auxiliary contracts for {visualization_type!r}")
        for role, bound_source_id in visualization["dataSources"].items():
            if not isinstance(bound_source_id, str):
                raise HarnessError(f"{example_id}/{visualization_id}/{role} is not a source ID")
            source_contract = contract if role == "primary" else auxiliary_contracts.get(role)
            if not isinstance(source_contract, dict):
                raise HarnessError(
                    f"No {role!r} render contract for {example_id}/{visualization_id}"
                )
            bound_query = source_contract.get("query")
            bound_expected_rows = source_contract.get("expected_rows")
            if role == "primary" and not isinstance(bound_query, str):
                raise HarnessError(f"Invalid {role!r} render query for {visualization_type!r}")
            if bound_query is not None and not isinstance(bound_query, str):
                raise HarnessError(f"Invalid {role!r} render query for {visualization_type!r}")
            if not isinstance(bound_expected_rows, list):
                raise HarnessError(f"Invalid {role!r} render contract for {visualization_type!r}")
            fixture_search = {
                "data_source_id": bound_source_id,
                "expected_rows": bound_expected_rows,
                "query_override": bound_query,
            }
            previous = fixture_searches_by_source.setdefault(bound_source_id, fixture_search)
            if previous != fixture_search:
                raise HarnessError(
                    f"{example_id}/{bound_source_id} has incompatible fixture contracts"
                )

    original_queries: dict[str, str] = {}
    for source_id, source in payload["dataSources"].items():
        source_type = source.get("type")
        if source_type not in {"ds.search", "ds.chain"}:
            raise HarnessError(
                f"Visual fixtures currently require ds.search or ds.chain; found {source_type}"
            )
        original_query = source.get("options", {}).get("query")
        if not isinstance(original_query, str):
            raise HarnessError(f"{example_id}/{source_id} has no source query")
        original_queries[source_id] = original_query
        fixture_search = fixture_searches_by_source.get(source_id)
        if fixture_search is None:
            raise HarnessError(f"{example_id}/{source_id} is not bound to a visualization")
        query_override = fixture_search["query_override"]
        if source_type == "ds.search":
            if not isinstance(query_override, str):
                raise HarnessError(f"{example_id}/{source_id} requires a fixture query")
            source["options"]["query"] = query_override
        elif query_override is not None:
            raise HarnessError(
                f"{example_id}/{source_id} is a chain; fixture data must come from its parent"
            )

    def expanded_query(source_id: str, *, fixture: bool) -> str:
        source = payload["dataSources"].get(source_id)
        if not isinstance(source, dict):
            raise HarnessError(f"{example_id}/{source_id} references an unknown source")
        source_type = source.get("type")
        own_query = source["options"]["query"] if fixture else original_queries[source_id]
        if source_type == "ds.search":
            return own_query
        parent_id = source["options"].get("extend")
        if not isinstance(parent_id, str):
            raise HarnessError(f"{example_id}/{source_id} chain has no parent")
        return f"{expanded_query(parent_id, fixture=fixture)} {own_query}".strip()

    source_queries: list[dict[str, str]] = []
    fixture_searches: list[dict[str, Any]] = []
    for source_id in payload["dataSources"]:
        source_queries.append(
            {"data_source_id": source_id, "query": expanded_query(source_id, fixture=False)}
        )
        expectation = fixture_searches_by_source[source_id]
        fixture_searches.append(
            {
                "data_source_id": source_id,
                "expected_rows": expectation["expected_rows"],
                "fixture_query": expanded_query(source_id, fixture=True),
            }
        )
    return (
        DashboardDefinition.model_validate(payload),
        panel_contracts,
        source_queries,
        fixture_searches,
    )


def _source_snapshot() -> dict[str, Any]:
    lock = _load_json(SOURCE_LOCK_PATH)
    if lock.get("schema_version") != "splunk-source-template-lock/v1":
        raise HarnessError("Unsupported source-template lock schema")
    rcastley_ids = {"rcastley_splunk_health", "rcastley_splunk_health_portable"}
    entries = tuple(
        entry for entry in source_template_entries() if entry.template_id in rcastley_ids
    )
    if {entry.template_id for entry in entries} != rcastley_ids:
        raise HarnessError("Source-template registry is missing a rcastley Splunk Health variant")
    original = next(
        (entry for entry in entries if entry.template_id == "rcastley_splunk_health"), None
    )
    if original is None or any(
        entry.origin.revision != original.origin.revision for entry in entries
    ):
        raise HarnessError("Source-template revisions disagree")
    if lock.get("revision") != original.origin.revision:
        raise HarnessError("Source-template package metadata and integration lock disagree")
    if any(entry.origin.repository != original.origin.repository for entry in entries):
        raise HarnessError("Source-template repositories disagree")
    if lock.get("repository") != original.origin.repository:
        raise HarnessError("Source-template repository metadata and integration lock disagree")
    definition = lock.get("definition")
    if not isinstance(definition, dict) or definition.get("sha256") != (
        original.origin.definition_sha256
    ):
        raise HarnessError("Source-template definition metadata and integration lock disagree")

    def require_digest(path: Path, expected: object) -> None:
        if not isinstance(expected, str) or not path.is_file():
            raise HarnessError(f"Missing locked source-template file {path}")
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        if actual != expected:
            raise HarnessError(f"Locked source-template file drifted: {path}")

    license_path = lock.get("license_path")
    if not isinstance(license_path, str):
        raise HarnessError("Source-template lock has no license path")
    require_digest(REPO_ROOT / license_path, lock.get("license_sha256"))

    app = lock.get("app")
    if not isinstance(app, dict) or not isinstance(app.get("files"), dict):
        raise HarnessError("Source-template lock has no app file inventory")
    app_hashes: dict[str, str] = {}
    for source_path, expected in sorted(app["files"].items()):
        if not isinstance(source_path, str) or not isinstance(expected, str):
            raise HarnessError("Source-template app inventory must map paths to SHA-256 values")
        require_digest(SOURCE_VENDOR_ROOT / source_path, expected)
        app_hashes[source_path] = expected
    tree_content = "".join(
        f"{digest}  {path}\n" for path, digest in sorted(app_hashes.items())
    ).encode("utf-8")
    if hashlib.sha256(tree_content).hexdigest() != app.get("tree_sha256"):
        raise HarnessError("Source-template app tree digest does not match its file inventory")

    harnesses = lock.get("harnesses")
    if not isinstance(harnesses, list) or len(harnesses) != 8:
        raise HarnessError("Source-template lock requires eight visualization harnesses")
    for harness in harnesses:
        if not isinstance(harness, dict) or not isinstance(harness.get("vendor_path"), str):
            raise HarnessError("Invalid source-template harness lock record")
        require_digest(REPO_ROOT / harness["vendor_path"], harness.get("sha256"))
    return lock


def _harness_rows(name: str) -> tuple[list[str], list[dict[str, str]], dict[str, Any]]:
    harness = _load_json(SOURCE_VENDOR_ROOT / "harness" / f"{name}.json")
    data = harness.get("data")
    if not isinstance(data, dict):
        raise HarnessError(f"Upstream harness {name!r} has no data contract")
    columns = data.get("columns")
    if (
        not isinstance(columns, list)
        or not columns
        or not all(
            isinstance(column, str) and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", column)
            for column in columns
        )
    ):
        raise HarnessError(f"Upstream harness {name!r} has invalid columns")

    mode = data.get("mode")
    rows: list[list[object]]
    if mode == "multi_row":
        raw_rows = data.get("sampleRows")
        if not isinstance(raw_rows, list) or not raw_rows:
            raise HarnessError(f"Upstream harness {name!r} has no sample rows")
        rows = raw_rows
        row_count_field = data.get("rowCountField")
        if row_count_field is not None:
            fields = harness.get("fields")
            if not isinstance(fields, list):
                raise HarnessError(f"Upstream harness {name!r} has invalid fields")
            row_count = next(
                (
                    field.get("default")
                    for field in fields
                    if isinstance(field, dict) and field.get("name") == row_count_field
                ),
                None,
            )
            if not isinstance(row_count, int) or row_count < 1:
                raise HarnessError(f"Upstream harness {name!r} has invalid rowCountField")
            rows = rows[:row_count]
    elif mode == "single_row":
        fields = harness.get("fields")
        if not isinstance(fields, list):
            raise HarnessError(f"Upstream harness {name!r} has invalid fields")
        defaults = {
            str(field["name"]): field.get("default")
            for field in fields
            if isinstance(field, dict) and isinstance(field.get("name"), str)
        }
        missing = [column for column in columns if column not in defaults]
        if missing:
            raise HarnessError(
                f"Upstream harness {name!r} has no defaults for {', '.join(missing)}"
            )
        rows = [[defaults[column] for column in columns]]
    else:
        raise HarnessError(f"Upstream harness {name!r} has unsupported data mode {mode!r}")

    expected_rows: list[dict[str, str]] = []
    for row in rows:
        if not isinstance(row, list) or len(row) != len(columns):
            raise HarnessError(f"Upstream harness {name!r} has a malformed sample row")
        expected_rows.append(
            {
                column: str(value).lower() if isinstance(value, bool) else str(value)
                for column, value in zip(columns, row, strict=True)
            }
        )
    return columns, expected_rows, harness


def _rows_query(columns: Sequence[str], rows: Sequence[Mapping[str, str]]) -> str:
    parts = [f"| makeresults count={len(rows)}", "| streamstats count AS fixture_row"]
    for column in columns:
        clauses = ",".join(
            f"fixture_row={index},{json.dumps(row[column], ensure_ascii=False)}"
            for index, row in enumerate(rows, start=1)
        )
        parts.append(f"| eval {column}=case({clauses})")
    parts.append(f"| table {' '.join(columns)}")
    return " ".join(parts)


def _fixture_source_template(
    template_id: str,
    target: str,
) -> tuple[
    DashboardDefinition,
    list[dict[str, Any]],
    list[dict[str, str]],
    list[dict[str, Any]],
]:
    original = build_source_template(template_id, target)
    payload = json.loads(canonical_json(original))
    panel_contracts: list[dict[str, Any]] = []
    fixture_searches: list[dict[str, Any]] = []
    source_queries: list[dict[str, str]] = []
    for visualization_id, visualization in payload["visualizations"].items():
        visualization_type = visualization["type"]
        name = HEALTH_HARNESS_BY_PANEL.get(visualization_id)
        if name is None:
            raise HarnessError(
                f"Source template {template_id!r} has unexpected panel {visualization_id!r}"
            )
        expected_custom_type = f"splunk_health.{name}"
        custom_render = visualization_type == expected_custom_type
        if not custom_render and visualization_type not in PORTABLE_SOURCE_VISUALIZATIONS:
            raise HarnessError(
                f"Source template {template_id!r} has unexpected type {visualization_type!r}"
            )
        columns, expected_rows, harness = _harness_rows(name)
        source_id = visualization.get("dataSources", {}).get("primary")
        if not isinstance(source_id, str):
            raise HarnessError(f"Source template panel {visualization_id!r} has no data source")
        source = payload["dataSources"].get(source_id)
        if not isinstance(source, dict) or source.get("type") != "ds.search":
            raise HarnessError(f"Source template data source {source_id!r} is not ds.search")
        original_query = source.get("options", {}).get("query")
        if not isinstance(original_query, str):
            raise HarnessError(f"Source template data source {source_id!r} has no query")
        fixture_query = _rows_query(columns, expected_rows)
        source["options"]["query"] = fixture_query
        source_queries.append({"data_source_id": source_id, "query": original_query})
        fixture_searches.append(
            {
                "data_source_id": source_id,
                "expected_rows": expected_rows,
                "fixture_query": fixture_query,
            }
        )
        formatter = harness.get("formatter", [])
        formatter_defaults = {
            str(item["name"]): item.get("default")
            for item in formatter
            if isinstance(item, dict) and isinstance(item.get("name"), str)
        }
        panel_contract = {
            "data_source_id": source_id,
            "default_size": harness.get("defaultSize"),
            "expected_rows": expected_rows,
            "fixture_query": fixture_query,
            "formatter_defaults": formatter_defaults,
            "no_data_message": harness.get("noDataMessage"),
            "panel_id": visualization_id,
            "title": visualization.get("title", visualization_id),
            "ui_markers": [],
            "visualization_type": visualization_type,
        }
        if custom_render:
            panel_contract["render_kind"] = "canvas"
        panel_contracts.append(panel_contract)
    return (
        DashboardDefinition.model_validate(payload),
        panel_contracts,
        source_queries,
        fixture_searches,
    )


def _state_dashboard(
    state_id: str,
    target: str,
    fixtures: Mapping[str, Any],
) -> tuple[DashboardDefinition, list[dict[str, Any]]]:
    cases = fixtures.get("state_cases")
    if not isinstance(cases, dict) or not isinstance(cases.get(state_id), dict):
        raise HarnessError(f"Unknown state case {state_id!r}")
    case = cases[state_id]
    title = case.get("title")
    query = case.get("query")
    visualization_type = case.get("visualization_type")
    expected_rows = case.get("expected_rows")
    ui_patterns = case.get("ui_patterns")
    if not all(isinstance(item, str) for item in (title, query, visualization_type)):
        raise HarnessError(f"State case {state_id!r} has invalid string fields")
    if not isinstance(expected_rows, list) or not isinstance(ui_patterns, list):
        raise HarnessError(f"State case {state_id!r} has invalid expectations")
    builder = DashboardBuilder(
        title=title, description="Intentional visual-state fixture.", target=target
    )
    source_id = builder.add_search(query, name=title, data_source_id=f"ds_{state_id}")
    panel_id = builder.add_visualization(
        visualization_type,
        name=title,
        visualization_id=f"viz_{state_id}",
        data_sources={"primary": source_id},
        title=title,
    )
    definition = builder.build(canvas_width=1440)
    return definition, [
        {
            "data_source_id": source_id,
            "expected_rows": expected_rows,
            "fixture_query": query,
            "panel_id": panel_id,
            "title": title,
            "ui_markers": [],
            "ui_patterns": ui_patterns,
            "visualization_type": visualization_type,
        }
    ]


def _view_id(target: str, identifier: str) -> str:
    target_slug = re.sub(r"[^0-9a-z]+", "_", target.lower()).strip("_")
    identifier_slug = re.sub(r"[^0-9a-z]+", "_", identifier.lower()).strip("_")
    return f"visual_qa_{target_slug}_{identifier_slug}"


def _title_visible(definition: DashboardDefinition) -> bool:
    """Mirror Dashboard Studio's explicit title/description visibility option."""

    return definition.layout.options.get("showTitleAndDescription") is not False


def _reset_generated_output(output: Path) -> None:
    """Remove only artifacts owned by a previous harness run."""

    for directory in ("apps", "playwright-report", "screenshots", "test-results"):
        path = output / directory
        if path.exists():
            shutil.rmtree(path)
    for name in (
        "fixture-search-results.json",
        "playwright-results.json",
        "qa-overview.html",
        "qa-overview.json",
        "qa-overview.png",
        "roundtrip-results.json",
        "run-manifest.json",
        "source-search-results.json",
        "splunk-compose.log",
        "storage-state.json",
        "vision-contract.json",
        "vision-prompt.md",
        "vision-report.json",
    ):
        (output / name).unlink(missing_ok=True)
    for pattern in ("visual_qa_*.json", "visual_qa_*.xml"):
        for path in output.glob(pattern):
            path.unlink()


def prepare(
    *,
    target: str,
    suite: str,
    output: Path,
    include_state_cases: bool,
) -> Path:
    image = image_record(target)
    fixtures = _load_json(FIXTURES_PATH)
    output.mkdir(parents=True, exist_ok=True)
    _reset_generated_output(output)
    dashboards: list[dict[str, Any]] = []
    for example_id in _selected_ids(suite, target, fixtures):
        definition, panels, source_queries, fixture_searches = _fixture_dashboard(
            example_id, target, fixtures
        )
        view_id = _view_id(target, example_id)
        definition_name = f"{view_id}.json"
        xml_name = f"{view_id}.xml"
        encoded = canonical_json(definition, indent=2) + "\n"
        xml = encode_view_xml(
            StudioView(
                label=f"Visual QA | {definition.title}",
                description="Generated deterministic render fixture; not for production use.",
                definition=definition,
                theme="light",
                hiddenElements={"hideEdit": True, "hideExport": True, "hideOpenInSearch": True},
            )
        )
        (output / definition_name).write_text(encoded, encoding="utf-8")
        (output / xml_name).write_text(xml + "\n", encoding="utf-8")
        dashboards.append(
            {
                "definition_path": definition_name,
                "definition_sha256": _sha256(canonical_json(definition)),
                "example_id": example_id,
                "expected_state": "ready",
                "fixture_searches": fixture_searches,
                "panels": panels,
                "source_kind": "portable_catalog",
                "source_queries": source_queries,
                "title": definition.title,
                "title_visible": _title_visible(definition),
                "view_id": view_id,
                "view_xml_path": xml_name,
            }
        )

    selected_templates = _selected_template_ids(suite, target, fixtures)
    entries = {entry.template_id: entry for entry in source_template_entries()}
    source_snapshot: dict[str, Any] | None = None
    required_apps: list[dict[str, str]] = []
    if selected_templates:
        source_snapshot = _source_snapshot()
        seen_apps: set[str] = set()
        for template_id in selected_templates:
            for app in entries[template_id].required_apps:
                if app.app_id in seen_apps:
                    continue
                if app.app_id != "splunk_health":
                    raise HarnessError(f"Unsupported source-template app {app.app_id!r}")
                app_source = SOURCE_VENDOR_ROOT / app.app_id
                app_target = output / "apps" / app.app_id
                shutil.copytree(app_source, app_target)
                required_apps.append(
                    {
                        "app_id": app.app_id,
                        "path": str(app_target.relative_to(output)),
                        "revision": app.revision,
                    }
                )
                seen_apps.add(app.app_id)
    for template_id in selected_templates:
        definition, panels, source_queries, fixture_searches = _fixture_source_template(
            template_id, target
        )
        view_id = _view_id(target, template_id)
        definition_name = f"{view_id}.json"
        xml_name = f"{view_id}.xml"
        (output / definition_name).write_text(
            canonical_json(definition, indent=2) + "\n",
            encoding="utf-8",
        )
        xml = encode_view_xml(
            StudioView(
                label=f"Visual QA | {definition.title}",
                description="Pinned source-derived render fixture; not for production use.",
                definition=definition,
                theme="dark",
                hiddenElements={"hideEdit": True, "hideExport": True, "hideOpenInSearch": True},
            )
        )
        (output / xml_name).write_text(xml + "\n", encoding="utf-8")
        entry = entries[template_id]
        dashboards.append(
            {
                "definition_path": definition_name,
                "definition_sha256": _sha256(canonical_json(definition)),
                "example_id": template_id,
                "expected_state": "ready",
                "fixture_searches": fixture_searches,
                "panels": panels,
                "source_kind": "source_template",
                "source_queries": source_queries,
                "template_origin": entry.origin.model_dump(mode="json"),
                "title": definition.title,
                "title_visible": _title_visible(definition),
                "view_id": view_id,
                "view_xml_path": xml_name,
            }
        )

    if include_state_cases:
        cases = fixtures.get("state_cases", {})
        if not isinstance(cases, dict):
            raise HarnessError("fixtures.json state_cases must be an object")
        for state_id in sorted(cases):
            definition, panels = _state_dashboard(state_id, target, fixtures)
            view_id = _view_id(target, f"state_{state_id}")
            definition_name = f"{view_id}.json"
            xml_name = f"{view_id}.xml"
            (output / definition_name).write_text(
                canonical_json(definition, indent=2) + "\n",
                encoding="utf-8",
            )
            (output / xml_name).write_text(
                encode_view_xml(
                    StudioView(
                        label=f"Visual QA | {definition.title}",
                        description="Intentional visual-state fixture; not for production use.",
                        definition=definition,
                        theme="light",
                        hiddenElements={
                            "hideEdit": True,
                            "hideExport": True,
                            "hideOpenInSearch": True,
                        },
                    )
                )
                + "\n",
                encoding="utf-8",
            )
            dashboards.append(
                {
                    "definition_path": definition_name,
                    "definition_sha256": _sha256(canonical_json(definition)),
                    "example_id": f"state_{state_id}",
                    "expected_state": state_id,
                    "fixture_searches": [
                        {
                            "data_source_id": panel["data_source_id"],
                            "expected_rows": panel["expected_rows"],
                            "fixture_query": panel["fixture_query"],
                        }
                        for panel in panels
                    ],
                    "panels": panels,
                    "source_kind": "state_fixture",
                    "source_queries": [],
                    "title": definition.title,
                    "title_visible": _title_visible(definition),
                    "view_id": view_id,
                    "view_xml_path": xml_name,
                }
            )

    contract = portable_telemetry_contract()
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "architecture": _load_json(IMAGES_PATH)["architecture"],
        "dashboards": dashboards,
        "fixed_epoch": fixtures["fixed_epoch"],
        "image": image["image"],
        "indexes": {
            name: ("metric" if str(signal) == "metric" else "event")
            for name, signal in sorted(contract.logical_indexes.items())
        },
        "requires_general_terms": image["requires_general_terms"],
        "required_apps": required_apps,
        "source_snapshot": source_snapshot,
        "suite": suite,
        "target": target,
    }
    manifest_path = output / "run-manifest.json"
    _write_json(manifest_path, manifest)
    return manifest_path


def _ssl_context() -> ssl.SSLContext:
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    return context


@dataclass(frozen=True)
class SplunkResponse:
    status: int
    body: bytes


class SplunkClient:
    def __init__(self, base_url: str, username: str, password: str, *, timeout: float = 60) -> None:
        self.base_url = base_url.rstrip("/")
        credentials = base64.b64encode(f"{username}:{password}".encode()).decode()
        self.headers = {"Authorization": f"Basic {credentials}"}
        self.timeout = timeout
        self.context = _ssl_context()

    def request(
        self,
        method: str,
        path: str,
        *,
        form: Mapping[str, str] | None = None,
        allowed: Iterable[int] = (200, 201),
    ) -> SplunkResponse:
        headers = dict(self.headers)
        data: bytes | None = None
        if form is not None:
            data = urlencode(form).encode("utf-8")
            headers["Content-Type"] = "application/x-www-form-urlencoded"
        request = Request(
            f"{self.base_url}{path}",
            data=data,
            headers=headers,
            method=method,
        )
        try:
            with urlopen(request, context=self.context, timeout=self.timeout) as response:
                result = SplunkResponse(response.status, response.read())
        except HTTPError as error:
            result = SplunkResponse(error.code, error.read())
        except (TimeoutError, URLError) as error:
            raise HarnessError(f"Splunk request failed for {method} {path}: {error}") from error
        if result.status not in set(allowed):
            body = result.body.decode("utf-8", errors="replace")[:1000]
            raise HarnessError(f"Splunk returned HTTP {result.status} for {method} {path}: {body}")
        return result


def wait_for_splunk(client: SplunkClient, timeout: float) -> None:
    deadline = time.monotonic() + timeout
    last_error = "not attempted"
    while time.monotonic() < deadline:
        try:
            client.request("GET", "/services/server/info?output_mode=json")
            return
        except HarnessError as error:
            last_error = str(error)
            time.sleep(5)
    raise HarnessError(f"Splunk did not become ready within {timeout:g}s: {last_error}")


def provision_indexes(client: SplunkClient, manifest: Mapping[str, Any]) -> None:
    indexes = manifest.get("indexes")
    if not isinstance(indexes, dict):
        raise HarnessError("Run manifest has no index contract")
    for name, datatype in sorted(indexes.items()):
        client.request(
            "POST",
            "/services/data/indexes",
            form={"name": str(name), "datatype": str(datatype), "output_mode": "json"},
            allowed=(200, 201, 409),
        )


def _dashboard_path(view_id: str) -> str:
    return f"/servicesNS/admin/search/data/ui/views/{quote(view_id, safe='')}"


def publish(client: SplunkClient, manifest_path: Path) -> dict[str, Any]:
    manifest = _load_json(manifest_path)
    base = manifest_path.parent
    comparisons: list[dict[str, Any]] = []
    for dashboard in manifest["dashboards"]:
        view_id = dashboard["view_id"]
        xml = (base / dashboard["view_xml_path"]).read_text(encoding="utf-8")
        client.request("DELETE", _dashboard_path(view_id), allowed=(200, 404))
        client.request(
            "POST",
            "/servicesNS/admin/search/data/ui/views",
            form={"name": view_id, "eai:data": xml, "output_mode": "json"},
        )
        response = client.request("GET", f"{_dashboard_path(view_id)}?output_mode=json")
        try:
            payload = json.loads(response.body)
            readback = payload["entry"][0]["content"]["eai:data"]
        except (json.JSONDecodeError, KeyError, IndexError, TypeError) as error:
            raise HarnessError(f"Unable to read back dashboard {view_id!r}") from error
        comparison = compare_roundtrip(xml, readback)
        comparisons.append(
            {
                "actual_sha256": comparison.actual_sha256,
                "differences": [item.model_dump(mode="json") for item in comparison.differences],
                "equivalent": comparison.equivalent,
                "expected_sha256": comparison.expected_sha256,
                "view_id": view_id,
            }
        )
    result = {"schema_version": RESULT_SCHEMA_VERSION, "roundtrip": comparisons}
    _write_json(base / "roundtrip-results.json", result)
    failures = [item for item in comparisons if not item["equivalent"]]
    if failures:
        raise HarnessError(f"{len(failures)} dashboard readback comparisons differed")
    return result


def cleanup(client: SplunkClient, manifest_path: Path) -> None:
    manifest = _load_json(manifest_path)
    for dashboard in manifest["dashboards"]:
        client.request("DELETE", _dashboard_path(dashboard["view_id"]), allowed=(200, 404))


def _search_value(query: str) -> str:
    stripped = query.strip()
    if stripped.startswith("|") or stripped.lower().startswith("search "):
        return stripped
    return f"search {stripped}"


def run_search(
    client: SplunkClient, query: str
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    response = client.request(
        "POST",
        "/services/search/jobs/export",
        form={
            "output_mode": "json",
            "search": _search_value(query),
            "search_mode": "normal",
        },
        allowed=(200, 400),
    )
    rows: list[dict[str, str]] = []
    messages: list[dict[str, str]] = []
    for line in response.body.decode("utf-8", errors="replace").splitlines():
        if not line.strip():
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError as error:
            raise HarnessError(f"Search export returned non-JSON output: {line[:500]}") from error
        result = item.get("result")
        if isinstance(result, dict):
            rows.append({str(key): str(value) for key, value in result.items()})
        raw_messages = item.get("messages")
        if isinstance(raw_messages, list):
            for message in raw_messages:
                if isinstance(message, dict):
                    messages.append({str(key): str(value) for key, value in message.items()})
    if response.status >= 400 and not any(
        message.get("type", "").upper() in {"ERROR", "FATAL"} for message in messages
    ):
        messages.append(
            {
                "type": "ERROR",
                "text": f"Search export returned HTTP {response.status}",
            }
        )
    return rows, messages


def _fatal_messages(messages: Sequence[Mapping[str, str]]) -> list[Mapping[str, str]]:
    return [
        message for message in messages if message.get("type", "").upper() in {"ERROR", "FATAL"}
    ]


def _project_rows(
    rows: Sequence[Mapping[str, str]],
    expected: Sequence[Mapping[str, str]],
) -> list[dict[str, str]]:
    keys = tuple(expected[0]) if expected else ()
    return [{key: row.get(key, "") for key in keys} for row in rows]


def validate_searches(
    client: SplunkClient,
    manifest_path: Path,
    *,
    kind: str,
) -> dict[str, Any]:
    manifest = _load_json(manifest_path)
    checks: list[dict[str, Any]] = []
    failures: list[str] = []
    for dashboard in manifest["dashboards"]:
        if kind == "source":
            queries = [
                {
                    "id": item["data_source_id"],
                    "query": item["query"],
                    "expected_rows": None,
                }
                for item in dashboard["source_queries"]
            ]
        else:
            queries = [
                {
                    "id": item["data_source_id"],
                    "query": item["fixture_query"],
                    "expected_rows": item["expected_rows"],
                }
                for item in dashboard["fixture_searches"]
            ]
        for item in queries:
            rows, messages = run_search(client, item["query"])
            fatal = _fatal_messages(messages)
            check_id = f"{dashboard['example_id']}/{item['id']}"
            passed = not fatal
            expected_rows = item["expected_rows"]
            projected: list[dict[str, str]] = []
            if kind == "fixture" and dashboard["expected_state"] == "search_error":
                passed = bool(fatal)
            elif kind == "fixture" and expected_rows is not None:
                projected = _project_rows(rows, expected_rows)
                passed = passed and projected == expected_rows
            else:
                projected = rows
            if not passed:
                failures.append(check_id)
            checks.append(
                {
                    "fatal_messages": fatal,
                    "id": check_id,
                    "kind": kind,
                    "passed": passed,
                    "rows": projected if kind == "fixture" else [],
                }
            )
    result = {
        "schema_version": RESULT_SCHEMA_VERSION,
        "checks": checks,
        "failures": failures,
        "kind": kind,
    }
    _write_json(manifest_path.parent / f"{kind}-search-results.json", result)
    if failures:
        raise HarnessError(f"{kind} search checks failed: {', '.join(failures)}")
    return result


def _client(arguments: argparse.Namespace) -> SplunkClient:
    return SplunkClient(
        arguments.management_url,
        arguments.username,
        arguments.password,
        timeout=arguments.request_timeout,
    )


def _add_client_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--management-url",
        default=os.environ.get("SPLUNK_MGMT_URL", "https://127.0.0.1:8089"),
    )
    parser.add_argument("--username", default=os.environ.get("SPLUNK_USERNAME", "admin"))
    parser.add_argument("--password", default=os.environ.get("SPLUNK_PASSWORD"), required=False)
    parser.add_argument("--request-timeout", type=float, default=60)


def _require_password(arguments: argparse.Namespace) -> None:
    if not arguments.password:
        raise HarnessError("Set SPLUNK_PASSWORD or pass --password")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    image = commands.add_parser("image", help="Resolve one pinned Splunk image record")
    image.add_argument("--target", required=True)
    image.add_argument("--field", choices=("image", "requires_general_terms"))

    prepare_parser = commands.add_parser("prepare", help="Generate test-only dashboards")
    prepare_parser.add_argument("--target", required=True)
    prepare_parser.add_argument("--suite", choices=("smoke", "full"), default="smoke")
    prepare_parser.add_argument("--output", type=Path, required=True)
    prepare_parser.add_argument("--include-state-cases", action="store_true")

    wait_parser = commands.add_parser("wait", help="Wait for the management API")
    _add_client_arguments(wait_parser)
    wait_parser.add_argument("--startup-timeout", type=float, default=900)

    indexes = commands.add_parser("provision-indexes", help="Create empty logical test indexes")
    _add_client_arguments(indexes)
    indexes.add_argument("--manifest", type=Path, required=True)

    publish_parser = commands.add_parser("publish", help="Publish and verify dashboard readback")
    _add_client_arguments(publish_parser)
    publish_parser.add_argument("--manifest", type=Path, required=True)

    searches = commands.add_parser("validate-searches", help="Run source or fixture searches")
    _add_client_arguments(searches)
    searches.add_argument("--manifest", type=Path, required=True)
    searches.add_argument("--kind", choices=("source", "fixture"), required=True)

    cleanup_parser = commands.add_parser("cleanup", help="Delete test dashboard views")
    _add_client_arguments(cleanup_parser)
    cleanup_parser.add_argument("--manifest", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    try:
        if arguments.command == "image":
            record = image_record(arguments.target)
            if arguments.field:
                value = record[arguments.field]
                print(str(value).lower() if isinstance(value, bool) else value)
            else:
                print(json.dumps(record, indent=2, sort_keys=True))
        elif arguments.command == "prepare":
            path = prepare(
                target=arguments.target,
                suite=arguments.suite,
                output=arguments.output,
                include_state_cases=arguments.include_state_cases,
            )
            print(path)
        else:
            _require_password(arguments)
            client = _client(arguments)
            if arguments.command == "wait":
                wait_for_splunk(client, arguments.startup_timeout)
            elif arguments.command == "provision-indexes":
                provision_indexes(client, _load_json(arguments.manifest))
            elif arguments.command == "publish":
                print(json.dumps(publish(client, arguments.manifest), indent=2, sort_keys=True))
            elif arguments.command == "validate-searches":
                print(
                    json.dumps(
                        validate_searches(client, arguments.manifest, kind=arguments.kind),
                        indent=2,
                        sort_keys=True,
                    )
                )
            elif arguments.command == "cleanup":
                cleanup(client, arguments.manifest)
        return 0
    except HarnessError as error:
        print(
            json.dumps({"status": "error", "message": str(error)}, sort_keys=True), file=sys.stderr
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
