"""Agent-facing JSON Schema generation."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict

from splunk_dashboard_studio.contracts import (
    DashboardArtifactBundle,
    SkillDescriptor,
    TelemetryContract,
    observability_skill_descriptors,
)
from splunk_dashboard_studio.models import DashboardDefinition
from splunk_dashboard_studio.profiles import profile_manifest
from splunk_dashboard_studio.version import TargetPlatform


class DashboardAgentContract(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target: TargetPlatform
    definition: DashboardDefinition


def dashboard_definition_schema() -> dict[str, Any]:
    return DashboardDefinition.model_json_schema(by_alias=True, mode="validation")


def agent_contract_schema() -> dict[str, Any]:
    schema = DashboardAgentContract.model_json_schema(by_alias=True, mode="validation")
    schema["x-splunk-enterprise"] = profile_manifest()
    schema["x-observability-skills"] = [
        descriptor.model_dump(mode="json") for descriptor in observability_skill_descriptors()
    ]
    return schema


def schema_bundle() -> dict[str, Any]:
    """Return every stable machine-facing v0.2 contract in one document."""

    return {
        "schema_version": "splunk-dashboard-studio-schema-bundle/v1",
        "schemas": {
            "agent": agent_contract_schema(),
            "artifact_bundle": DashboardArtifactBundle.model_json_schema(
                by_alias=True,
                mode="validation",
            ),
            "dashboard": dashboard_definition_schema(),
            "skill_descriptor": SkillDescriptor.model_json_schema(mode="validation"),
            "telemetry_contract": TelemetryContract.model_json_schema(mode="validation"),
        },
        "x-splunk-enterprise": profile_manifest(),
        "x-observability-skills": [
            descriptor.model_dump(mode="json") for descriptor in observability_skill_descriptors()
        ],
    }
