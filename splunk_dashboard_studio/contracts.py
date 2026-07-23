"""Typed observability, catalog, provenance, and agent-skill contracts."""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from splunk_dashboard_studio.models import DashboardDefinition
from splunk_dashboard_studio.profiles import EvidenceGrade
from splunk_dashboard_studio.version import EnterpriseVersion, TargetPlatform


class FrozenContract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, populate_by_name=True)


class ObservabilityFramework(StrEnum):
    RED = "red"
    USE = "use"
    FOUR_GOLDEN_SIGNALS = "four_golden_signals"
    MELT = "melt"
    SLI_SLO = "sli_slo"


class TelemetrySignal(StrEnum):
    METRIC = "metric"
    EVENT = "event"
    LOG = "log"
    TRACE = "trace"
    PROFILE = "profile"


class TelemetryField(FrozenContract):
    name: str = Field(min_length=1)
    signals: tuple[TelemetrySignal, ...] = Field(min_length=1)
    description: str = Field(min_length=1)
    required: bool = True
    semantic_convention: str | None = None
    unit: str | None = None


class TelemetryContract(FrozenContract):
    contract_id: str = Field(min_length=1)
    description: str = Field(min_length=1)
    logical_indexes: dict[str, TelemetrySignal]
    fields: tuple[TelemetryField, ...]
    notes: tuple[str, ...] = ()

    @model_validator(mode="after")
    def require_unique_fields(self) -> TelemetryContract:
        names = [field.name for field in self.fields]
        if len(names) != len(set(names)):
            raise ValueError("Telemetry field names must be unique")
        return self


class PanelProvenance(FrozenContract):
    panel_id: str = Field(min_length=1)
    purpose: str = Field(min_length=1)
    frameworks: tuple[ObservabilityFramework, ...] = Field(min_length=1)
    signals: tuple[TelemetrySignal, ...] = Field(min_length=1)
    data_source_ids: tuple[str, ...] = Field(min_length=1)
    required_fields: tuple[str, ...] = ()
    drilldown_signals: tuple[TelemetrySignal, ...] = ()


class SavedSearchSpec(FrozenContract):
    reference: str = Field(min_length=1)
    purpose: str = Field(min_length=1)
    rationale: str = Field(min_length=1)
    recommended_schedule: str | None = None
    source_indexes: tuple[str, ...] = ()
    ownership: Literal["external"] = "external"


class CatalogEntry(FrozenContract):
    example_id: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    priority: Literal["high", "medium"]
    title: str = Field(min_length=1)
    description: str = Field(min_length=1)
    minimum_target: EnterpriseVersion
    telemetry_contract: str = Field(min_length=1)
    frameworks: tuple[ObservabilityFramework, ...] = Field(min_length=1)
    signals: tuple[TelemetrySignal, ...] = Field(min_length=1)
    logical_indexes: tuple[str, ...] = Field(min_length=1)
    required_fields: tuple[str, ...] = ()
    panels: tuple[PanelProvenance, ...] = Field(min_length=1)
    saved_searches: tuple[SavedSearchSpec, ...] = ()
    tags: tuple[str, ...] = ()

    @model_validator(mode="after")
    def require_unique_panels(self) -> CatalogEntry:
        panel_ids = [panel.panel_id for panel in self.panels]
        if len(panel_ids) != len(set(panel_ids)):
            raise ValueError("Catalog panel IDs must be unique")
        return self


class DashboardEvidenceManifest(FrozenContract):
    schema_version: Literal["dashboard-evidence/v1"] = "dashboard-evidence/v1"
    example_id: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    target: TargetPlatform
    minimum_target: EnterpriseVersion
    generator_version: str = Field(min_length=1)
    telemetry_contract: str = Field(min_length=1)
    definition_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    canonical_json_bytes: int = Field(gt=0)
    native_validation: Literal["valid", "invalid"] = "valid"
    official_validation: Literal["valid", "invalid", "not_run"] = "not_run"
    official_engine_id: str = Field(min_length=1)
    official_engine_version: str = Field(min_length=1)
    engine_evidence: EvidenceGrade
    panels: tuple[PanelProvenance, ...]
    saved_searches: tuple[SavedSearchSpec, ...] = ()
    assumptions: tuple[str, ...] = ()


class DashboardArtifactBundle(FrozenContract):
    definition: DashboardDefinition
    manifest: DashboardEvidenceManifest


class SourceTemplateOrigin(FrozenContract):
    repository: str = Field(min_length=1)
    revision: str = Field(pattern=r"^[0-9a-f]{40}$")
    license: Literal["Apache-2.0"]
    source_paths: tuple[str, ...] = Field(min_length=1)
    definition_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    attribution: str = Field(min_length=1)


class RequiredSplunkApp(FrozenContract):
    app_id: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    repository: str = Field(min_length=1)
    revision: str = Field(pattern=r"^[0-9a-f]{40}$")
    install_scope: Literal["operator_or_integration"] = "operator_or_integration"


class SourceTemplateLesson(FrozenContract):
    lesson_id: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    summary: str = Field(min_length=1)
    enforcement: tuple[str, ...] = Field(min_length=1)


class SourceTemplateEntry(FrozenContract):
    template_id: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    title: str = Field(min_length=1)
    description: str = Field(min_length=1)
    minimum_target: EnterpriseVersion
    origin: SourceTemplateOrigin
    required_apps: tuple[RequiredSplunkApp, ...] = ()
    adaptations: tuple[str, ...] = ()
    lessons: tuple[SourceTemplateLesson, ...] = Field(min_length=1)
    tags: tuple[str, ...] = ()


class SourceTemplateBundle(FrozenContract):
    template: SourceTemplateEntry
    definition: DashboardDefinition


class AgentSkill(StrEnum):
    DATA_DISCOVERY = "data_discovery"
    SPL_OPTIMIZATION = "spl_optimization"
    VISUALIZATION_SELECTION = "visualization_selection"
    ALERTING_SLO = "alerting_slo"
    PROVENANCE = "provenance"
    VALIDATION = "validation"
    DRIFT_DETECTION = "drift_detection"
    ACCESS_CONTROL = "access_control"


class SkillDescriptor(FrozenContract):
    skill: AgentSkill
    purpose: str = Field(min_length=1)
    inputs: tuple[str, ...] = Field(min_length=1)
    outputs: tuple[str, ...] = Field(min_length=1)
    heuristics: tuple[str, ...] = Field(min_length=1)
    constraints: tuple[str, ...] = Field(min_length=1)
    tools: tuple[str, ...] = Field(min_length=1)


_SKILL_DESCRIPTORS = (
    SkillDescriptor(
        skill=AgentSkill.DATA_DISCOVERY,
        purpose="Profile available telemetry and map stable entity fields.",
        inputs=("field inventory", "sample telemetry", "semantic-convention registry"),
        outputs=("dataset profile", "candidate entities", "suitability score"),
        heuristics=("Prefer semantic-convention entities over index-local aliases.",),
        constraints=("Do not infer field stability from one sample.",),
        tools=("field_profiler", "semconv_resolver", "sample_runner"),
    ),
    SkillDescriptor(
        skill=AgentSkill.SPL_OPTIMIZATION,
        purpose="Propose transparent SPL and search-graph improvements.",
        inputs=("draft SPL", "dashboard graph", "panel intent"),
        outputs=("optimization proposals", "shared-base candidates"),
        heuristics=("Share a base only when common semantics remain explicit.",),
        constraints=("Never silently rewrite SPL.",),
        tools=("spl_parser", "chain_graph_analyzer", "optimizer"),
    ),
    SkillDescriptor(
        skill=AgentSkill.VISUALIZATION_SELECTION,
        purpose="Choose diagnostic visualizations from result shape and audience.",
        inputs=("panel intent", "result cardinality", "metric type", "audience"),
        outputs=("visualization type", "option defaults"),
        heuristics=("Use KPI, trend, top-N, and distribution views for their matching questions.",),
        constraints=("Avoid decorative visuals without diagnostic value.",),
        tools=("viz_rules", "cardinality_estimator", "defaults_policy"),
    ),
    SkillDescriptor(
        skill=AgentSkill.ALERTING_SLO,
        purpose="Align user-journey SLIs, error budgets, and saved-search proposals.",
        inputs=("SLI specification", "thresholds", "burn-rate policy"),
        outputs=("SLO dashboard sections", "saved-search specifications"),
        heuristics=("Page on user-visible symptoms and use burn-rate overlays.",),
        constraints=("Do not create alerts or saved searches.",),
        tools=("sli_catalog", "burn_rate_policy", "saved_search_builder"),
    ),
    SkillDescriptor(
        skill=AgentSkill.PROVENANCE,
        purpose="Make telemetry and derivation dependencies explicit per panel.",
        inputs=("source-to-panel mapping", "schema registry", "dashboard definition"),
        outputs=("panel provenance", "evidence metadata"),
        heuristics=("Label every derived KPI with its signal and entity assumptions.",),
        constraints=("Do not emit unlabeled derived KPIs.",),
        tools=("schema_registry", "source_annotator"),
    ),
    SkillDescriptor(
        skill=AgentSkill.VALIDATION,
        purpose="Validate native semantics and locked official-engine compatibility.",
        inputs=("dashboard definition", "target profile", "engine locks"),
        outputs=("normalized validation report", "evidence manifest"),
        heuristics=("Fail closed on target ambiguity and dangling references.",),
        constraints=("Keep NPM validators outside Python distributions.",),
        tools=("native_validator", "official_npm_validator"),
    ),
    SkillDescriptor(
        skill=AgentSkill.DRIFT_DETECTION,
        purpose="Distinguish product, validator, artifact, and telemetry drift.",
        inputs=("historical corpus", "artifact snapshots", "schema deltas"),
        outputs=("compatibility diff", "regeneration tasks"),
        heuristics=("Classify product drift separately from telemetry drift.",),
        constraints=("Do not equate NPM publication time with product attribution.",),
        tools=("corpus_diff", "roundtrip_codec", "schema_drift_check"),
    ),
    SkillDescriptor(
        skill=AgentSkill.ACCESS_CONTROL,
        purpose="Describe least-privilege and publication boundaries.",
        inputs=("app context", "role policy", "publish intent"),
        outputs=("ACL-safe deployment guidance", "publication warnings"),
        heuristics=("Default to private or app-scoped dashboards.",),
        constraints=("Advisory only; never publish or mutate ACLs.",),
        tools=("acl_policy", "publish_guard", "secret_scan"),
    ),
)


def observability_skill_descriptors() -> tuple[SkillDescriptor, ...]:
    """Return the immutable, deterministic eight-skill observability taxonomy."""

    return _SKILL_DESCRIPTORS
