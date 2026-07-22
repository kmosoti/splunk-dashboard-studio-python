"""Agent-facing JSON Schema generation."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict

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
    return schema
