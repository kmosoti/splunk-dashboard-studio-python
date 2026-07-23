from __future__ import annotations

import json
from pathlib import Path

import pytest

from splunk_dashboard_studio import (
    SourceTemplateNotFound,
    SourceTemplateTargetUnsupported,
    build_source_template,
    build_source_template_bundle,
    canonical_json,
    source_template_entries,
)
from splunk_dashboard_studio.cli import main
from splunk_dashboard_studio.validation import validate_dashboard


def test_source_template_registry_preserves_upstream_provenance() -> None:
    entries = source_template_entries()
    assert len(entries) == 2
    by_id = {entry.template_id: entry for entry in entries}
    entry = by_id["rcastley_splunk_health"]
    assert entry.template_id == "rcastley_splunk_health"
    assert str(entry.minimum_target) == "10.2.0"
    assert entry.origin.repository == "https://github.com/rcastley/splunk-custom-visualizations"
    assert entry.origin.revision == "7424755c461712022367c3fa081fd7e0edc91001"
    assert entry.origin.license == "Apache-2.0"
    assert entry.origin.definition_sha256 == (
        "0371e79ed06eb10ee6298d6e54f32d5a99b744e44d812400845ad141de72febd"
    )
    assert entry.required_apps[0].app_id == "splunk_health"
    assert {lesson.lesson_id for lesson in entry.lessons} == {
        "canvas_render_invariants",
        "explicit_custom_viz_boundary",
        "manifest_driven_render_contracts",
        "provenance_locked_import",
    }
    portable = by_id["rcastley_splunk_health_portable"]
    assert str(portable.minimum_target) == "9.4.3"
    assert portable.required_apps == ()
    assert portable.origin.repository == entry.origin.repository
    assert portable.origin.revision == entry.origin.revision
    assert portable.origin.definition_sha256 == (
        "738c77fb0938575037a39552e3c86742167b5abe5272f7a5a814bbedbb80fdf9"
    )


@pytest.mark.parametrize("target", ["10.2.0", "10.4.0"])
def test_source_template_build_is_deterministic_and_natively_valid(target: str) -> None:
    first = build_source_template("rcastley_splunk_health", target)
    second = build_source_template("rcastley_splunk_health", target)
    assert canonical_json(first) == canonical_json(second)
    assert first is not second
    assert first.title == "Splunk Health"
    assert len(first.visualizations) == len(first.data_sources) == 8
    assert {visualization.type for visualization in first.visualizations.values()} == {
        "splunk_health.forwarder_heatmap",
        "splunk_health.index_storage",
        "splunk_health.indexing_pipeline_flow",
        "splunk_health.license_gauge",
        "splunk_health.resource_gauge",
        "splunk_health.scheduler_health",
        "splunk_health.search_activity",
        "splunk_health.splunk_status_board",
    }
    layout = first.layout.layout_definitions["layout_1"]  # type: ignore[index]
    assert layout.options == {"display": "auto-scale", "height": 1080, "width": 1920}
    assert validate_dashboard(first, target=target).is_valid


def test_source_template_build_rejects_unknown_and_pre_10_2_targets() -> None:
    with pytest.raises(SourceTemplateNotFound, match="available templates"):
        build_source_template("missing", "10.4.0")
    with pytest.raises(
        SourceTemplateTargetUnsupported,
        match=r"requires Splunk Enterprise 10\.2\.0",
    ):
        build_source_template("rcastley_splunk_health", "10.0.0")


@pytest.mark.parametrize("target", ["9.4.3", "10.0.0", "10.2.0", "10.4.0"])
def test_portable_source_template_uses_only_app_free_builtins(target: str) -> None:
    definition = build_source_template("rcastley_splunk_health_portable", target)
    assert definition.title == "Splunk Health (Portable)"
    assert len(definition.visualizations) == len(definition.data_sources) == 8
    types = {visualization.type for visualization in definition.visualizations.values()}
    assert types == {"splunk.singlevalue", "splunk.table"}
    assert all(not visualization.options for visualization in definition.visualizations.values())
    assert validate_dashboard(definition, target=target).is_valid

    source = build_source_template("rcastley_splunk_health", "10.2.0")
    assert {
        source.data_sources[source_id].options["query"] for source_id in source.data_sources
    } == {
        definition.data_sources[source_id].options["query"] for source_id in definition.data_sources
    }


def test_source_template_bundle_keeps_definition_and_origin_together() -> None:
    bundle = build_source_template_bundle("rcastley_splunk_health", "10.2.0")
    assert bundle.template.template_id == "rcastley_splunk_health"
    assert bundle.definition.title == bundle.template.title


def test_source_template_cli_lists_and_builds_machine_readable_artifacts(
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    assert main(["template", "list"]) == 0
    listing = json.loads(capsys.readouterr().out)
    assert listing["schema_version"] == "dashboard-source-templates/v1"
    assert listing["entries"][0]["origin"]["license"] == "Apache-2.0"

    output = tmp_path / "splunk-health.json"
    assert (
        main(
            [
                "template",
                "build",
                "rcastley_splunk_health",
                "--target",
                "10.2.0",
                "--artifact",
                "bundle",
                "--output",
                str(output),
            ]
        )
        == 0
    )
    artifact = json.loads(output.read_text(encoding="utf-8"))
    assert artifact["definition"]["title"] == "Splunk Health"
    assert artifact["template"]["origin"]["revision"].startswith("7424755c")

    portable_output = tmp_path / "splunk-health-portable.json"
    assert (
        main(
            [
                "template",
                "build",
                "rcastley_splunk_health_portable",
                "--target",
                "9.4.3",
                "--output",
                str(portable_output),
            ]
        )
        == 0
    )
    assert json.loads(portable_output.read_text(encoding="utf-8"))["title"] == (
        "Splunk Health (Portable)"
    )

    assert (
        main(
            [
                "template",
                "build",
                "rcastley_splunk_health",
                "--target",
                "10.0.0",
            ]
        )
        == 2
    )
    assert json.loads(capsys.readouterr().out)["error_type"] == ("SourceTemplateTargetUnsupported")
