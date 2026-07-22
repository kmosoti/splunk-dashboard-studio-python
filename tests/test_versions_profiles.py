from __future__ import annotations

import pytest
from pydantic import ValidationError

from splunk_dashboard_studio.profiles import (
    EvidenceGrade,
    Feature,
    UnsupportedEnterpriseVersion,
    available_profiles,
    introduced_in,
    profile_for,
    profile_manifest,
)
from splunk_dashboard_studio.version import EnterpriseVersion, TargetPlatform


@pytest.mark.parametrize("value", ["9.4", "v9.4.3", "09.4.3", "9.04.3", "9.4.-1", ""])
def test_enterprise_version_requires_exact_triplet(value: str) -> None:
    with pytest.raises(ValidationError):
        EnterpriseVersion.parse(value)


def test_enterprise_version_comparison_hash_and_string() -> None:
    version = EnterpriseVersion.parse("10.2.1")
    assert version.parts == (10, 2, 1)
    assert version.release_line == (10, 2)
    assert str(version) == "10.2.1"
    assert version == "10.2.1"
    assert version != "not-a-version"
    assert version > "10.2.0"
    assert version < EnterpriseVersion.parse("10.4.0")
    assert len({version, EnterpriseVersion.parse("10.2.1")}) == 1


def test_target_is_enterprise_only() -> None:
    target = TargetPlatform.enterprise("9.4.3")
    assert str(target) == "splunk-enterprise@9.4.3"
    with pytest.raises(ValidationError):
        TargetPlatform.model_validate({"product": "splunk-cloud", "version": "10.2.0"})


@pytest.mark.parametrize(
    ("version", "profile_id", "engine", "evidence"),
    [
        ("9.4.3", "splunk-enterprise-9.4.3", "27.5.1", EvidenceGrade.TEMPORAL_SURROGATE),
        ("9.4.99", "splunk-enterprise-9.4.3", "27.5.1", EvidenceGrade.TEMPORAL_SURROGATE),
        ("10.0.7", "splunk-enterprise-10.0", "28.6.0", EvidenceGrade.TEMPORAL_SURROGATE),
        ("10.2.0", "splunk-enterprise-10.2", "28.6.0", EvidenceGrade.OFFICIAL_ATTRIBUTION),
        ("10.4.1", "splunk-enterprise-10.4", "29.8.0", EvidenceGrade.TEMPORAL_SURROGATE),
    ],
)
def test_profile_resolution(
    version: str,
    profile_id: str,
    engine: str,
    evidence: EvidenceGrade,
) -> None:
    profile = profile_for(version)
    assert profile.profile_id == profile_id
    assert profile.engine.dashboard_version == engine
    assert profile.engine.evidence == evidence


@pytest.mark.parametrize("version", ["9.3.9", "9.4.2", "10.1.0", "10.3.0", "11.0.0"])
def test_unknown_or_out_of_range_versions_fail_closed(version: str) -> None:
    with pytest.raises(UnsupportedEnterpriseVersion):
        profile_for(version)


def test_feature_registry_and_manifest_are_machine_readable() -> None:
    profiles = available_profiles()
    assert len(profiles) == 4
    assert profiles[0].supports(Feature.TABBED_LAYOUTS)
    assert not profiles[0].supports(Feature.SPL2_DATA_SOURCE)
    assert profiles[2].supports(Feature.SPL2_DATA_SOURCE)
    assert introduced_in(Feature.NETWORK_GRAPH) == "10.4.0"

    manifest = profile_manifest()
    assert manifest["product"] == "splunk-enterprise"
    assert manifest["minimum_supported"] == "9.4.3"
    assert manifest["feature_introductions"][Feature.SPL2_DATA_SOURCE.value] == "10.2.0"
    assert "/10.2/" in manifest["feature_sources"][Feature.SPL2_DATA_SOURCE.value]
    assert "enterprise_9_4" in manifest["sources"]
    for profile in manifest["profiles"]:
        assert profile["features"] == sorted(profile["features"])
