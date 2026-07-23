from __future__ import annotations

import copy
import json
from typing import Any

import pytest

from splunk_dashboard_studio.corpus import generate_corpus
from splunk_dashboard_studio.issues import Severity
from splunk_dashboard_studio.validation import validate_dashboard, validate_dashboard_json


def codes(payload: dict[str, Any], target: str = "10.2.0", *, strict: bool = False) -> set[str]:
    report = validate_dashboard(payload, target=target, strict_warnings=strict)
    return {issue.code for issue in report.issues}


@pytest.mark.parametrize("target", ["9.4.3", "10.0.0", "10.2.0", "10.4.0"])
def test_native_corpus_matches_expectations(target: str) -> None:
    for case in generate_corpus(target):
        assert validate_dashboard(case.definition, target=target).status == case.expected_native


def test_envelope_and_json_validation(dashboard_payload: dict[str, Any]) -> None:
    report = validate_dashboard({"definition": dashboard_payload}, target="10.2.0")
    assert report.is_valid
    from_json = validate_dashboard_json(json.dumps(dashboard_payload), target="10.2.0")
    assert from_json == report
    assert report.stats == {
        "data_sources": 1,
        "graph_edges": 0,
        "inputs": 0,
        "visualizations": 1,
    }


def test_pydantic_errors_use_json_alias_paths(dashboard_payload: dict[str, Any]) -> None:
    broken = copy.deepcopy(dashboard_payload)
    del broken["dataSources"]
    broken["unexpected"] = True
    report = validate_dashboard(broken, target="10.2.0")
    assert not report.is_valid
    assert report.profile is None
    assert any(issue.path == "$/unexpected" for issue in report.issues)


def test_unsupported_target_is_a_report_not_an_exception(dashboard_payload: dict[str, Any]) -> None:
    report = validate_dashboard(dashboard_payload, target="9.4.2")
    assert report.status == "invalid"
    assert report.issues[0].code == "unsupported_enterprise_version"


@pytest.mark.parametrize(
    ("mutation", "older", "newer", "feature"),
    [
        ("trellis", "9.4.3", "10.0.0", "dashboard.visualization.chart_trellis"),
        ("expression", "10.0.0", "10.2.0", "dashboard.expressions"),
        ("spl2", "10.0.0", "10.2.0", "dashboard.data_source.spl2"),
        ("timeline", "10.0.0", "10.2.0", "dashboard.visualization.timeline"),
        ("custom", "10.0.0", "10.2.0", "dashboard.visualization.custom"),
        ("network", "10.2.0", "10.4.0", "dashboard.visualization.network_graph"),
    ],
)
def test_versioned_feature_boundaries(
    dashboard_payload: dict[str, Any],
    mutation: str,
    older: str,
    newer: str,
    feature: str,
) -> None:
    payload = copy.deepcopy(dashboard_payload)
    if mutation == "trellis":
        payload["visualizations"]["viz_events"]["type"] = "splunk.line"
        payload["visualizations"]["viz_events"]["options"]["splitByLayout"] = "trellis"
    elif mutation == "expression":
        payload["expressions"] = {"condition": {"name": "show", "value": "true()"}}
    elif mutation == "spl2":
        payload["dataSources"]["ds_spl2"] = {
            "type": "ds.spl2",
            "options": {"query": "$from main | stats count()"},
        }
    elif mutation == "timeline":
        payload["visualizations"]["viz_events"]["type"] = "splunk.timeline"
    elif mutation == "custom":
        payload["visualizations"]["viz_events"]["type"] = "viz.example.custom"
    else:
        payload["visualizations"]["viz_events"]["type"] = "splunk.networkGraph"

    older_report = validate_dashboard(payload, target=older)
    issue = next(issue for issue in older_report.issues if issue.code == "feature_not_available")
    assert issue.feature == feature
    assert validate_dashboard(payload, target=newer).is_valid


def test_single_value_trellis_is_available_in_enterprise_9_4(
    dashboard_payload: dict[str, Any],
) -> None:
    payload = copy.deepcopy(dashboard_payload)
    visualization = payload["visualizations"]["viz_events"]
    visualization["type"] = "splunk.singlevalue"
    visualization["options"]["splitByLayout"] = "trellis"
    assert validate_dashboard(payload, target="9.4.3").is_valid


def test_dos_validation_is_scoped_to_option_surfaces(dashboard_payload: dict[str, Any]) -> None:
    payload = copy.deepcopy(dashboard_payload)
    payload["description"] = "> This is prose, not Dynamic Options Syntax"
    payload["visualizations"]["viz_events"]["options"]["majorValue"] = "> primary no-pipe"
    issues = validate_dashboard(payload, target="10.2.0").issues
    dos_issues = [issue for issue in issues if issue.code == "invalid_dos_syntax"]
    assert [issue.path for issue in dos_issues] == [
        "$/visualizations/viz_events/options/majorValue"
    ]


@pytest.mark.parametrize(
    ("data_source", "expected"),
    [
        ({"type": "ds.search", "options": {}}, "search_query_required"),
        ({"type": "ds.search", "options": {"query": "search ("}}, "invalid_spl_syntax"),
        ({"type": "ds.savedSearch", "options": {}}, "saved_search_reference_required"),
        (
            {
                "type": "ds.chain",
                "options": {
                    "extend": "ds_events",
                    "query": "| head 1",
                    "queryParameters": {"earliest": "-1h"},
                },
            },
            "chain_inherited_option",
        ),
    ],
)
def test_data_source_validation(
    dashboard_payload: dict[str, Any],
    data_source: dict[str, Any],
    expected: str,
) -> None:
    payload = copy.deepcopy(dashboard_payload)
    payload["dataSources"]["ds_test"] = data_source
    assert expected in codes(payload)


def test_unknown_types_and_commands_can_be_strict(dashboard_payload: dict[str, Any]) -> None:
    payload = copy.deepcopy(dashboard_payload)
    payload["dataSources"]["ds_unknown"] = {"type": "ds.future", "options": {}}
    payload["dataSources"]["ds_events"]["options"]["query"] = "search * | futurecommand x"
    report = validate_dashboard(payload, target="10.2.0")
    warnings = [issue for issue in report.issues if issue.severity == Severity.WARNING]
    assert {issue.code for issue in warnings} == {
        "unknown_data_source_type",
        "unknown_spl_command",
    }
    assert report.is_valid
    assert not validate_dashboard(payload, target="10.2.0", strict_warnings=True).is_valid


def test_reference_and_layout_errors(dashboard_payload: dict[str, Any]) -> None:
    payload = copy.deepcopy(dashboard_payload)
    payload["inputs"] = {
        "input_test": {
            "type": "input.dropdown",
            "dataSources": {"primary": "missing_input_source"},
        }
    }
    payload["layout"]["globalInputs"] = ["missing_input"]
    payload["layout"]["tabs"]["items"][0]["layoutId"] = "missing_layout"
    structure = payload["layout"]["layoutDefinitions"]["layout_main"]["structure"]
    structure[0]["item"] = "missing_item"
    assert {
        "global_input_missing",
        "input_data_source_missing",
        "layout_item_missing",
        "tab_layout_missing",
    }.issubset(codes(payload))


def test_horizontal_and_vertical_canvas_overflow(dashboard_payload: dict[str, Any]) -> None:
    payload = copy.deepcopy(dashboard_payload)
    position = payload["layout"]["layoutDefinitions"]["layout_main"]["structure"][0]["position"]
    position.update({"x": 1400, "y": 710, "w": 100, "h": 100})
    result = codes(payload)
    assert "layout_horizontal_overflow" in result
    assert "layout_vertical_overflow" in result


def test_legacy_layout_reference_validation(dashboard_payload: dict[str, Any]) -> None:
    payload = copy.deepcopy(dashboard_payload)
    payload["layout"] = {
        "type": "absolute",
        "options": {},
        "structure": [{"type": "block", "item": "missing"}],
        "globalInputs": [],
    }
    assert "layout_item_missing" in codes(payload)
