from __future__ import annotations

import json
from pathlib import Path

import pytest

from splunk_dashboard_studio.cli import main
from splunk_dashboard_studio.corpus import corpus_jsonl, generate_corpus, write_corpus
from splunk_dashboard_studio.models import DashboardDefinition, Layout
from splunk_dashboard_studio.schema import (
    agent_contract_schema,
    dashboard_definition_schema,
    schema_bundle,
)


def test_agent_schema_contains_aliases_and_capability_extension() -> None:
    dashboard_schema = dashboard_definition_schema()
    assert "dataSources" in dashboard_schema["properties"]
    assert "data_sources" not in dashboard_schema["properties"]

    agent_schema = agent_contract_schema()
    assert agent_schema["properties"]["target"]
    assert agent_schema["x-splunk-enterprise"]["minimum_supported"] == "9.4.3"
    assert len(agent_schema["x-observability-skills"]) == 8

    bundle = schema_bundle()
    assert bundle["schema_version"] == "splunk-dashboard-studio-schema-bundle/v1"
    assert set(bundle["schemas"]) == {
        "agent",
        "artifact_bundle",
        "dashboard",
        "skill_descriptor",
        "telemetry_contract",
    }


def test_layout_shape_must_be_complete() -> None:
    with pytest.raises(ValueError, match="both layoutDefinitions and tabs"):
        Layout.model_validate({"layoutDefinitions": {}})
    with pytest.raises(ValueError, match="Legacy layouts require"):
        Layout.model_validate({})


def test_dashboard_forbids_unknown_top_level_fields(dashboard_payload: dict[str, object]) -> None:
    dashboard_payload["unknown"] = True
    with pytest.raises(ValueError):
        DashboardDefinition.model_validate(dashboard_payload)


def test_corpus_is_deterministic_and_writable(tmp_path: Path) -> None:
    first = corpus_jsonl("10.2.0")
    second = corpus_jsonl("10.2.0")
    assert first == second
    assert first.endswith("\n")
    cases = [json.loads(line) for line in first.splitlines()]
    assert len(cases) == 17
    assert {case["case_id"] for case in cases} == {
        case.case_id for case in generate_corpus("10.2.0")
    }

    output = tmp_path / "corpus.jsonl"
    write_corpus(output, "10.2.0")
    assert output.read_text(encoding="utf-8") == first


def test_cli_schema_profiles_and_corpus(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    assert main(["schema", "profiles"]) == 0
    profiles = json.loads(capsys.readouterr().out)
    assert profiles["product"] == "splunk-enterprise"

    assert main(["schema", "dashboard"]) == 0
    assert "properties" in json.loads(capsys.readouterr().out)

    assert main(["schema", "agent"]) == 0
    assert "x-splunk-enterprise" in json.loads(capsys.readouterr().out)

    assert main(["schema", "bundle"]) == 0
    assert json.loads(capsys.readouterr().out)["schema_version"].endswith("/v1")

    output = tmp_path / "generated.jsonl"
    assert main(["corpus", "--target", "9.4.3", "--output", str(output)]) == 0
    assert len(output.read_text(encoding="utf-8").splitlines()) == 17


def test_cli_validate_optimize_and_error(
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    dashboard_payload: dict[str, object],
) -> None:
    path = tmp_path / "dashboard.json"
    path.write_text(json.dumps(dashboard_payload), encoding="utf-8")
    assert main(["validate", str(path), "--target", "10.2.0"]) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "valid"

    assert main(["optimize", str(path)]) == 0
    assert json.loads(capsys.readouterr().out)["applied"] is False

    invalid = tmp_path / "invalid.json"
    invalid.write_text("not-json", encoding="utf-8")
    assert main(["validate", str(invalid), "--target", "10.2.0"]) == 2
    assert json.loads(capsys.readouterr().out)["status"] == "error"


def test_cli_invalid_dashboard_returns_one(
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    dashboard_payload: dict[str, object],
) -> None:
    dashboard_payload["visualizations"]["viz_events"]["dataSources"]["primary"] = "missing"
    path = tmp_path / "invalid-dashboard.json"
    path.write_text(json.dumps(dashboard_payload), encoding="utf-8")
    assert main(["validate", str(path), "--target", "10.2.0"]) == 1
    assert json.loads(capsys.readouterr().out)["status"] == "invalid"
