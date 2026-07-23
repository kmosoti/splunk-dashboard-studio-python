"""Layered, deterministic native validation for Dashboard Studio definitions."""

from __future__ import annotations

import json
from collections.abc import Iterable
from typing import Any

from pydantic import ValidationError

from splunk_dashboard_studio.dos import validate_dos_tree
from splunk_dashboard_studio.graph import analyze_search_graph
from splunk_dashboard_studio.issues import (
    IssueOrigin,
    Severity,
    ValidationIssue,
    ValidationReport,
)
from splunk_dashboard_studio.models import (
    DashboardDefinition,
    LayoutDefinition,
    LayoutStructureItem,
    unwrap_definition,
)
from splunk_dashboard_studio.profiles import (
    Feature,
    UnsupportedEnterpriseVersion,
    introduced_in,
    profile_for,
)
from splunk_dashboard_studio.spl import KNOWN_COMMANDS, SplSyntaxError, parse_spl
from splunk_dashboard_studio.version import TargetPlatform

_FIELD_ALIASES = {
    "application_properties": "applicationProperties",
    "container_options": "containerOptions",
    "data_sources": "dataSources",
    "event_handlers": "eventHandlers",
    "global_inputs": "globalInputs",
    "layout_definitions": "layoutDefinitions",
    "layout_id": "layoutId",
}

_CHART_TRELLIS_TYPES = {
    "splunk.area",
    "splunk.bar",
    "splunk.column",
    "splunk.line",
}


def _json_pointer(location: Iterable[object]) -> str:
    parts = []
    for item in location:
        value = _FIELD_ALIASES.get(str(item), str(item))
        parts.append(value.replace("~", "~0").replace("/", "~1"))
    return "$" + "".join(f"/{part}" for part in parts)


def _pydantic_issues(error: ValidationError) -> list[ValidationIssue]:
    return [
        ValidationIssue(
            code=f"pydantic.{item['type']}",
            path=_json_pointer(item["loc"]),
            message=item["msg"],
            origin=IssueOrigin.PYDANTIC,
        )
        for item in error.errors(include_url=False, include_context=False, include_input=False)
    ]


def _detected_features(definition: DashboardDefinition) -> set[Feature]:
    features: set[Feature] = set()
    if definition.layout.tabs is not None:
        features.add(Feature.TABBED_LAYOUTS)
    if "collapseNavigation" in definition.application_properties:
        features.add(Feature.COLLAPSE_NAVIGATION)
    if "downsampleVisualizations" in definition.application_properties:
        features.add(Feature.OPTIMIZED_RENDERING)
    if definition.expressions:
        features.add(Feature.EXPRESSION_TOKENS)
    if any(
        source.type in {"ds.spl2", "ds.spl2.view"} for source in definition.data_sources.values()
    ):
        features.add(Feature.SPL2_DATA_SOURCE)
    for visualization in definition.visualizations.values():
        visualization_type = visualization.type.lower()
        uses_trellis = any(
            key == "splitByLayout" or key.startswith("trellis") for key in visualization.options
        )
        if visualization_type in _CHART_TRELLIS_TYPES and uses_trellis:
            features.add(Feature.CHART_TRELLIS)
        if visualization_type in {"splunk.timeline", "viz.timeline"}:
            features.add(Feature.TIMELINE)
        if "." in visualization_type and not (
            visualization_type.startswith("splunk.") or visualization_type == "viz.timeline"
        ):
            features.add(Feature.CUSTOM_VISUALIZATIONS)
        if visualization_type in {
            "splunk.networkGraph",
            "splunk.networkgraph",
            "splunk.network_graph",
        }:
            features.add(Feature.NETWORK_GRAPH)
    return features


def _compatibility_issues(
    definition: DashboardDefinition,
    target: TargetPlatform,
) -> list[ValidationIssue]:
    profile = profile_for(target)
    issues: list[ValidationIssue] = []
    for feature in sorted(_detected_features(definition), key=str):
        if profile.supports(feature):
            continue
        required = introduced_in(feature)
        issues.append(
            ValidationIssue(
                code="feature_not_available",
                path="$",
                message=(
                    f"Feature {feature.value!r} is unavailable for {target}; "
                    f"it requires Splunk Enterprise {required} or later"
                ),
                origin=IssueOrigin.COMPATIBILITY,
                feature=feature.value,
                required_version=str(required),
                context={"target": str(target)},
            )
        )
    return issues


def _data_source_issues(definition: DashboardDefinition) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    known_types = {"ds.chain", "ds.savedSearch", "ds.search", "ds.spl2", "ds.spl2.view", "ds.test"}
    for data_source_id, data_source in sorted(definition.data_sources.items()):
        path = f"$/dataSources/{data_source_id}"
        if data_source.type not in known_types:
            issues.append(
                ValidationIssue(
                    code="unknown_data_source_type",
                    path=f"{path}/type",
                    message=f"No native validator is registered for {data_source.type!r}",
                    severity=Severity.WARNING,
                    origin=IssueOrigin.REFERENCE,
                )
            )
            continue
        if data_source.type in {"ds.search", "ds.chain", "ds.spl2"}:
            query = data_source.options.get("query")
            if not isinstance(query, str) or not query.strip():
                issues.append(
                    ValidationIssue(
                        code="search_query_required",
                        path=f"{path}/options/query",
                        message=f"{data_source.type} requires a non-empty options.query",
                        origin=IssueOrigin.SPL,
                    )
                )
            elif not data_source.type.startswith("ds.spl2"):
                try:
                    pipeline = parse_spl(query)
                except SplSyntaxError as error:
                    issues.append(
                        ValidationIssue(
                            code="invalid_spl_syntax",
                            path=f"{path}/options/query",
                            message=str(error),
                            origin=IssueOrigin.SPL,
                        )
                    )
                else:
                    for command_index, command in enumerate(pipeline.commands):
                        if command.name not in KNOWN_COMMANDS:
                            issues.append(
                                ValidationIssue(
                                    code="unknown_spl_command",
                                    path=f"{path}/options/query",
                                    message=(
                                        f"SPL command {command.name!r} is not in the local catalog"
                                    ),
                                    severity=Severity.WARNING,
                                    origin=IssueOrigin.SPL,
                                    context={"command_index": command_index},
                                )
                            )
        if data_source.type == "ds.chain":
            forbidden = sorted(
                key
                for key in {"queryParameters", "refresh", "refreshType"}
                if key in data_source.options
            )
            for key in forbidden:
                issues.append(
                    ValidationIssue(
                        code="chain_inherited_option",
                        path=f"{path}/options/{key}",
                        message=f"ds.chain inherits {key} from its parent and must not redefine it",
                        origin=IssueOrigin.SEARCH_GRAPH,
                    )
                )
        if data_source.type == "ds.savedSearch":
            reference = data_source.options.get("ref")
            if not isinstance(reference, str) or not reference.strip():
                issues.append(
                    ValidationIssue(
                        code="saved_search_reference_required",
                        path=f"{path}/options/ref",
                        message="ds.savedSearch requires a non-empty options.ref",
                        origin=IssueOrigin.REFERENCE,
                    )
                )
    return issues


def _reference_issues(definition: DashboardDefinition) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    data_source_ids = set(definition.data_sources)
    for visualization_id, visualization in sorted(definition.visualizations.items()):
        for role, data_source_id in sorted(visualization.data_sources.items()):
            if data_source_id not in data_source_ids:
                issues.append(
                    ValidationIssue(
                        code="visualization_data_source_missing",
                        path=f"$/visualizations/{visualization_id}/dataSources/{role}",
                        message=(
                            f"Visualization {visualization_id!r} references missing "
                            f"data source {data_source_id!r}"
                        ),
                        origin=IssueOrigin.REFERENCE,
                    )
                )
    for input_id, input_definition in sorted(definition.inputs.items()):
        for role, data_source_id in sorted(input_definition.data_sources.items()):
            if data_source_id not in data_source_ids:
                issues.append(
                    ValidationIssue(
                        code="input_data_source_missing",
                        path=f"$/inputs/{input_id}/dataSources/{role}",
                        message=(
                            f"Input {input_id!r} references missing data source {data_source_id!r}"
                        ),
                        origin=IssueOrigin.REFERENCE,
                    )
                )
    return issues


def _dos_issues(definition: DashboardDefinition) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    for visualization_id, visualization in sorted(definition.visualizations.items()):
        escaped_id = visualization_id.replace("~", "~0").replace("/", "~1")
        issues.extend(
            validate_dos_tree(
                visualization.options,
                f"$/visualizations/{escaped_id}/options",
            )
        )
    for input_id, input_definition in sorted(definition.inputs.items()):
        escaped_id = input_id.replace("~", "~0").replace("/", "~1")
        issues.extend(
            validate_dos_tree(
                input_definition.options,
                f"$/inputs/{escaped_id}/options",
            )
        )
    visualization_defaults = definition.defaults.get("visualizations")
    if visualization_defaults is not None:
        issues.extend(
            validate_dos_tree(
                visualization_defaults,
                "$/defaults/visualizations",
            )
        )
    return issues


def _layout_definition_issues(
    *,
    layout_id: str,
    layout_definition: LayoutDefinition,
    valid_items: set[str],
) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    width = layout_definition.options.get("width")
    height = layout_definition.options.get("height")
    canvas_width = width if isinstance(width, int) and not isinstance(width, bool) else None
    canvas_height = height if isinstance(height, int) and not isinstance(height, bool) else None
    for index, structure_item in enumerate(layout_definition.structure):
        base_path = f"$/layout/layoutDefinitions/{layout_id}/structure/{index}"
        issues.extend(_structure_item_issues(structure_item, base_path, valid_items))
        position = structure_item.position
        if position is None:
            continue
        if canvas_width is not None and position.x + position.w > canvas_width:
            issues.append(
                ValidationIssue(
                    code="layout_horizontal_overflow",
                    path=f"{base_path}/position",
                    message=(
                        f"Item right edge {position.x + position.w} exceeds canvas width "
                        f"{canvas_width}"
                    ),
                    origin=IssueOrigin.LAYOUT,
                )
            )
        if canvas_height is not None and position.y + position.h > canvas_height:
            issues.append(
                ValidationIssue(
                    code="layout_vertical_overflow",
                    path=f"{base_path}/position",
                    message=(
                        f"Item bottom edge {position.y + position.h} exceeds canvas height "
                        f"{canvas_height}"
                    ),
                    origin=IssueOrigin.LAYOUT,
                )
            )
    return issues


def _structure_item_issues(
    structure_item: LayoutStructureItem,
    path: str,
    valid_items: set[str],
) -> list[ValidationIssue]:
    if structure_item.item is None or structure_item.item in valid_items:
        return []
    return [
        ValidationIssue(
            code="layout_item_missing",
            path=f"{path}/item",
            message=f"Layout references missing dashboard item {structure_item.item!r}",
            origin=IssueOrigin.LAYOUT,
        )
    ]


def _layout_issues(definition: DashboardDefinition) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    valid_items = set(definition.visualizations) | set(definition.inputs)
    for input_id in definition.layout.global_inputs:
        if input_id not in definition.inputs:
            issues.append(
                ValidationIssue(
                    code="global_input_missing",
                    path="$/layout/globalInputs",
                    message=f"Layout references missing global input {input_id!r}",
                    origin=IssueOrigin.LAYOUT,
                )
            )
    if definition.layout.layout_definitions is not None:
        layouts = definition.layout.layout_definitions
        for layout_id, layout_definition in sorted(layouts.items()):
            issues.extend(
                _layout_definition_issues(
                    layout_id=layout_id,
                    layout_definition=layout_definition,
                    valid_items=valid_items,
                )
            )
        assert definition.layout.tabs is not None
        for index, tab in enumerate(definition.layout.tabs.items):
            if tab.layout_id not in layouts:
                issues.append(
                    ValidationIssue(
                        code="tab_layout_missing",
                        path=f"$/layout/tabs/items/{index}/layoutId",
                        message=f"Tab references missing layout {tab.layout_id!r}",
                        origin=IssueOrigin.LAYOUT,
                    )
                )
    elif definition.layout.structure is not None:
        for index, structure_item in enumerate(definition.layout.structure):
            issues.extend(
                _structure_item_issues(
                    structure_item,
                    f"$/layout/structure/{index}",
                    valid_items,
                )
            )
    return issues


def validate_dashboard(
    payload: DashboardDefinition | dict[str, Any],
    *,
    target: TargetPlatform | str,
    strict_warnings: bool = False,
) -> ValidationReport:
    target_platform = (
        target if isinstance(target, TargetPlatform) else TargetPlatform.enterprise(target)
    )
    raw_definition = unwrap_definition(payload)
    try:
        definition = (
            raw_definition
            if isinstance(raw_definition, DashboardDefinition)
            else DashboardDefinition.model_validate(raw_definition)
        )
    except ValidationError as error:
        return ValidationReport.from_issues(
            target=target_platform,
            issues=_pydantic_issues(error),
            stats={"pydantic_errors": error.error_count()},
        )

    try:
        profile = profile_for(target_platform)
    except UnsupportedEnterpriseVersion as error:
        return ValidationReport.from_issues(
            target=target_platform,
            issues=[
                ValidationIssue(
                    code="unsupported_enterprise_version",
                    path="$/target/version",
                    message=str(error),
                    origin=IssueOrigin.COMPATIBILITY,
                )
            ],
        )

    graph = analyze_search_graph(definition.data_sources)
    issues = [
        *_compatibility_issues(definition, target_platform),
        *_data_source_issues(definition),
        *_reference_issues(definition),
        *_layout_issues(definition),
        *graph.issues,
        *_dos_issues(definition),
    ]
    if strict_warnings:
        issues = [
            issue.model_copy(update={"severity": Severity.ERROR})
            if issue.severity == Severity.WARNING
            else issue
            for issue in issues
        ]
    issues.sort(key=lambda issue: (issue.path, issue.code, issue.message))
    return ValidationReport.from_issues(
        target=target_platform,
        profile=profile.profile_id,
        issues=issues,
        stats={
            "data_sources": len(definition.data_sources),
            "graph_edges": len(graph.edges),
            "inputs": len(definition.inputs),
            "visualizations": len(definition.visualizations),
        },
    )


def validate_dashboard_json(
    raw: str | bytes,
    *,
    target: TargetPlatform | str,
    strict_warnings: bool = False,
) -> ValidationReport:
    return validate_dashboard(
        json.loads(raw),
        target=target,
        strict_warnings=strict_warnings,
    )
