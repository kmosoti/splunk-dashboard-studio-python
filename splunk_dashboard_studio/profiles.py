"""Versioned Splunk Enterprise feature and NPM-engine profiles."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict

from splunk_dashboard_studio.version import EnterpriseVersion, TargetPlatform


class Feature(StrEnum):
    TABBED_LAYOUTS = "dashboard.layout.tabs"
    COLLAPSE_NAVIGATION = "dashboard.application.collapse_navigation"
    OPTIMIZED_RENDERING = "dashboard.application.optimized_rendering"
    CHART_TRELLIS = "dashboard.visualization.chart_trellis"
    EXPRESSION_TOKENS = "dashboard.expressions"
    SPL2_DATA_SOURCE = "dashboard.data_source.spl2"
    TIMELINE = "dashboard.visualization.timeline"
    CUSTOM_VISUALIZATIONS = "dashboard.visualization.custom"
    NETWORK_GRAPH = "dashboard.visualization.network_graph"


class EvidenceGrade(StrEnum):
    OFFICIAL_ATTRIBUTION = "official_attribution"
    TEMPORAL_SURROGATE = "temporal_surrogate"
    VERIFIED_INSTALLATION = "verified_installation"


class NpmEngineProfile(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    engine_id: str
    dashboard_version: str
    visualization_encoding_version: str
    evidence: EvidenceGrade
    evidence_url: str
    note: str


class EnterpriseProfile(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    profile_id: str
    release_line: tuple[int, int]
    minimum_patch: int = 0
    features: frozenset[Feature]
    engine: NpmEngineProfile

    def supports(self, feature: Feature) -> bool:
        return feature in self.features

    def matches(self, version: EnterpriseVersion) -> bool:
        return version.release_line == self.release_line and version.parts[2] >= self.minimum_patch


_SPLUNK_94_DOC = (
    "https://help.splunk.com/en/splunk-enterprise/create-dashboards-and-reports/"
    "dashboard-studio/9.4/whats-new-in-dashboard-studio/whats-new-in-dashboard-studio"
)
_SPLUNK_94_CREDITS = (
    "https://help.splunk.com/en/splunk-enterprise/release-notes-and-updates/"
    "release-notes/9.4/third-party-software/credits"
)
_SPLUNK_94_RELEASE = (
    "https://help.splunk.com/en/splunk-enterprise/release-notes-and-updates/"
    "release-notes/9.4/whats-new/welcome-to-splunk-enterprise-9.4"
)
_SPLUNK_102_CREDITS = (
    "https://help.splunk.com/en/splunk-enterprise/release-notes-and-updates/"
    "release-notes/10.2/third-party-software/credits"
)
_SPLUNK_100_DOC = (
    "https://help.splunk.com/en/splunk-enterprise/create-dashboards-and-reports/"
    "dashboard-studio/10.0/whats-new-in-dashboard-studio/whats-new-in-dashboard-studio"
)
_SPLUNK_102_DOC = (
    "https://help.splunk.com/en/splunk-enterprise/create-dashboards-and-reports/"
    "dashboard-studio/10.2/whats-new-in-dashboard-studio/whats-new-in-dashboard-studio"
)
_SPLUNK_104_DOC = (
    "https://help.splunk.com/en/splunk-enterprise/create-dashboards-and-reports/"
    "dashboard-studio/10.4/whats-new-in-dashboard-studio/whats-new-in-dashboard-studio"
)

_BASE_FEATURES = frozenset(
    {
        Feature.TABBED_LAYOUTS,
        Feature.COLLAPSE_NAVIGATION,
        Feature.OPTIMIZED_RENDERING,
    }
)

ENTERPRISE_94 = EnterpriseProfile(
    profile_id="splunk-enterprise-9.4.3",
    release_line=(9, 4),
    minimum_patch=3,
    features=_BASE_FEATURES,
    engine=NpmEngineProfile(
        engine_id="dashboard-27.5.1",
        dashboard_version="27.5.1",
        visualization_encoding_version="26.4.1",
        evidence=EvidenceGrade.TEMPORAL_SURROGATE,
        evidence_url="https://registry.npmjs.org/%40splunk%2Fdashboard-validation",
        note=(
            "Last public dashboard-validation release before Enterprise 9.4 GA; "
            "not an official Enterprise package mapping."
        ),
    ),
)

ENTERPRISE_100 = EnterpriseProfile(
    profile_id="splunk-enterprise-10.0",
    release_line=(10, 0),
    features=_BASE_FEATURES | {Feature.CHART_TRELLIS},
    engine=NpmEngineProfile(
        engine_id="dashboard-28.6.0",
        dashboard_version="28.6.0",
        visualization_encoding_version="27.5.0",
        evidence=EvidenceGrade.TEMPORAL_SURROGATE,
        evidence_url="https://registry.npmjs.org/%40splunk%2Fdashboard-validation",
        note="Release-family surrogate pending an authoritative Enterprise 10.0 bundle manifest.",
    ),
)

ENTERPRISE_102 = EnterpriseProfile(
    profile_id="splunk-enterprise-10.2",
    release_line=(10, 2),
    features=_BASE_FEATURES
    | {
        Feature.CHART_TRELLIS,
        Feature.EXPRESSION_TOKENS,
        Feature.SPL2_DATA_SOURCE,
        Feature.TIMELINE,
        Feature.CUSTOM_VISUALIZATIONS,
    },
    engine=NpmEngineProfile(
        engine_id="dashboard-28.6.0",
        dashboard_version="28.6.0",
        visualization_encoding_version="27.5.0",
        evidence=EvidenceGrade.OFFICIAL_ATTRIBUTION,
        evidence_url=_SPLUNK_102_CREDITS,
        note="Enterprise 10.2 attribution lists Dashboard Framework packages in the 28.6 line.",
    ),
)

ENTERPRISE_104 = EnterpriseProfile(
    profile_id="splunk-enterprise-10.4",
    release_line=(10, 4),
    features=ENTERPRISE_102.features | {Feature.NETWORK_GRAPH},
    engine=NpmEngineProfile(
        engine_id="dashboard-29.8.0",
        dashboard_version="29.8.0",
        visualization_encoding_version="28.8.0",
        evidence=EvidenceGrade.TEMPORAL_SURROGATE,
        evidence_url="https://registry.npmjs.org/%40splunk%2Fdashboard-validation",
        note=(
            "Current public engine surrogate; requires authoritative Enterprise 10.4 confirmation."
        ),
    ),
)

_PROFILES = (ENTERPRISE_94, ENTERPRISE_100, ENTERPRISE_102, ENTERPRISE_104)

_INTRODUCED: dict[Feature, EnterpriseVersion] = {
    Feature.TABBED_LAYOUTS: EnterpriseVersion.parse("9.4.0"),
    Feature.COLLAPSE_NAVIGATION: EnterpriseVersion.parse("9.4.0"),
    Feature.OPTIMIZED_RENDERING: EnterpriseVersion.parse("9.4.0"),
    Feature.CHART_TRELLIS: EnterpriseVersion.parse("10.0.0"),
    Feature.EXPRESSION_TOKENS: EnterpriseVersion.parse("10.2.0"),
    Feature.SPL2_DATA_SOURCE: EnterpriseVersion.parse("10.2.0"),
    Feature.TIMELINE: EnterpriseVersion.parse("10.2.0"),
    Feature.CUSTOM_VISUALIZATIONS: EnterpriseVersion.parse("10.2.0"),
    Feature.NETWORK_GRAPH: EnterpriseVersion.parse("10.4.0"),
}

_FEATURE_SOURCES: dict[Feature, str] = {
    Feature.TABBED_LAYOUTS: _SPLUNK_94_DOC,
    Feature.COLLAPSE_NAVIGATION: _SPLUNK_94_DOC,
    Feature.OPTIMIZED_RENDERING: _SPLUNK_94_DOC,
    Feature.CHART_TRELLIS: _SPLUNK_100_DOC,
    Feature.EXPRESSION_TOKENS: _SPLUNK_102_DOC,
    Feature.SPL2_DATA_SOURCE: _SPLUNK_102_DOC,
    Feature.TIMELINE: _SPLUNK_102_DOC,
    Feature.CUSTOM_VISUALIZATIONS: _SPLUNK_102_DOC,
    Feature.NETWORK_GRAPH: _SPLUNK_104_DOC,
}


class UnsupportedEnterpriseVersion(ValueError):
    pass


def available_profiles() -> tuple[EnterpriseProfile, ...]:
    return _PROFILES


def profile_for(target: TargetPlatform | EnterpriseVersion | str) -> EnterpriseProfile:
    if isinstance(target, TargetPlatform):
        version = target.version
    else:
        version = EnterpriseVersion.parse(target)
    for profile in _PROFILES:
        if profile.matches(version):
            return profile
    supported = ", ".join(profile.profile_id for profile in _PROFILES)
    raise UnsupportedEnterpriseVersion(
        f"Unsupported Splunk Enterprise target {version}; verified profile lines: {supported}"
    )


def introduced_in(feature: Feature) -> EnterpriseVersion:
    return _INTRODUCED[feature]


def profile_manifest() -> dict[str, object]:
    profiles: list[dict[str, object]] = []
    for profile in _PROFILES:
        value = profile.model_dump(mode="json", exclude={"features"})
        value["features"] = sorted(feature.value for feature in profile.features)
        profiles.append(value)
    return {
        "product": "splunk-enterprise",
        "minimum_supported": "9.4.3",
        "profiles": profiles,
        "feature_introductions": {
            feature.value: str(version) for feature, version in sorted(_INTRODUCED.items())
        },
        "feature_sources": {
            feature.value: url for feature, url in sorted(_FEATURE_SOURCES.items())
        },
        "sources": {
            "enterprise_9_4": _SPLUNK_94_DOC,
            "enterprise_9_4_credits": _SPLUNK_94_CREDITS,
            "enterprise_9_4_release": _SPLUNK_94_RELEASE,
            "enterprise_10_0": _SPLUNK_100_DOC,
            "enterprise_10_2": _SPLUNK_102_DOC,
            "enterprise_10_2_credits": _SPLUNK_102_CREDITS,
            "enterprise_10_4": _SPLUNK_104_DOC,
        },
    }
