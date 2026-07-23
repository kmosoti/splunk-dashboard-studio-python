from __future__ import annotations

from pathlib import Path

import pytest

from scripts.release_evidence import build_release_evidence, verify_release_tag


def test_release_tag_matches_project_and_runtime_versions() -> None:
    assert verify_release_tag("v0.2.1") == "0.2.1"
    with pytest.raises(ValueError, match="must equal"):
        verify_release_tag("v0.2.0")


def test_release_evidence_requires_both_distribution_formats(tmp_path: Path) -> None:
    (tmp_path / "splunk_dashboard_studio_python-0.2.1-py3-none-any.whl").write_bytes(b"wheel")
    with pytest.raises(ValueError, match="requires exactly one sdist"):
        build_release_evidence("v0.2.1", tmp_path)


def test_release_evidence_is_deterministic(tmp_path: Path) -> None:
    (tmp_path / "splunk_dashboard_studio_python-0.2.1-py3-none-any.whl").write_bytes(b"wheel")
    (tmp_path / "splunk_dashboard_studio_python-0.2.1.tar.gz").write_bytes(b"sdist")
    first = build_release_evidence("v0.2.1", tmp_path)
    second = build_release_evidence("v0.2.1", tmp_path)
    assert first == second
    assert first["schema_version"] == "release-evidence/v1"
    assert len(first["catalog"]) == 10
    assert first["source_templates"] == [
        {
            "template_id": "rcastley_splunk_health",
            "minimum_target": "10.2.0",
            "repository": "https://github.com/rcastley/splunk-custom-visualizations",
            "revision": "7424755c461712022367c3fa081fd7e0edc91001",
            "license": "Apache-2.0",
            "source_definition_sha256": (
                "0371e79ed06eb10ee6298d6e54f32d5a99b744e44d812400845ad141de72febd"
            ),
            "normalized_definition_sha256": first["source_templates"][0][
                "normalized_definition_sha256"
            ],
            "required_apps": ["splunk_health"],
        },
        {
            "template_id": "rcastley_splunk_health_portable",
            "minimum_target": "9.4.3",
            "repository": "https://github.com/rcastley/splunk-custom-visualizations",
            "revision": "7424755c461712022367c3fa081fd7e0edc91001",
            "license": "Apache-2.0",
            "source_definition_sha256": (
                "738c77fb0938575037a39552e3c86742167b5abe5272f7a5a814bbedbb80fdf9"
            ),
            "normalized_definition_sha256": first["source_templates"][1][
                "normalized_definition_sha256"
            ],
            "required_apps": [],
        },
    ]
    assert first["verification"]["live_splunk_roundtrip"] == (
        "validated by the release visual matrix, including pinned source templates"
    )


def test_release_evidence_rejects_stale_artifact_versions(tmp_path: Path) -> None:
    (tmp_path / "splunk_dashboard_studio_python-0.1.0-py3-none-any.whl").write_bytes(b"wheel")
    (tmp_path / "splunk_dashboard_studio_python-0.1.0.tar.gz").write_bytes(b"sdist")
    with pytest.raises(ValueError, match="does not match release"):
        build_release_evidence("v0.2.1", tmp_path)
