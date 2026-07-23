from __future__ import annotations

from pathlib import Path

import pytest

from scripts.release_evidence import build_release_evidence, verify_release_tag


def test_release_tag_matches_project_and_runtime_versions() -> None:
    assert verify_release_tag("v0.2.0") == "0.2.0"
    with pytest.raises(ValueError, match="must equal"):
        verify_release_tag("v0.2.1")


def test_release_evidence_requires_both_distribution_formats(tmp_path: Path) -> None:
    (tmp_path / "splunk_dashboard_studio_python-0.2.0-py3-none-any.whl").write_bytes(b"wheel")
    with pytest.raises(ValueError, match="requires exactly one sdist"):
        build_release_evidence("v0.2.0", tmp_path)


def test_release_evidence_is_deterministic(tmp_path: Path) -> None:
    (tmp_path / "splunk_dashboard_studio_python-0.2.0-py3-none-any.whl").write_bytes(b"wheel")
    (tmp_path / "splunk_dashboard_studio_python-0.2.0.tar.gz").write_bytes(b"sdist")
    first = build_release_evidence("v0.2.0", tmp_path)
    second = build_release_evidence("v0.2.0", tmp_path)
    assert first == second
    assert first["schema_version"] == "release-evidence/v1"
    assert len(first["catalog"]) == 10


def test_release_evidence_rejects_stale_artifact_versions(tmp_path: Path) -> None:
    (tmp_path / "splunk_dashboard_studio_python-0.1.0-py3-none-any.whl").write_bytes(b"wheel")
    (tmp_path / "splunk_dashboard_studio_python-0.1.0.tar.gz").write_bytes(b"sdist")
    with pytest.raises(ValueError, match="does not match release"):
        build_release_evidence("v0.2.0", tmp_path)
