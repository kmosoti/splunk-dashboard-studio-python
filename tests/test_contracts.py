from __future__ import annotations

import pytest

from splunk_dashboard_studio.contracts import (
    AgentSkill,
    CatalogEntry,
    ObservabilityFramework,
    PanelProvenance,
    TelemetryContract,
    TelemetryField,
    TelemetrySignal,
    observability_skill_descriptors,
)


def _panel(panel_id: str = "viz_requests") -> PanelProvenance:
    return PanelProvenance(
        panel_id=panel_id,
        purpose="Show request rate",
        frameworks=(ObservabilityFramework.RED,),
        signals=(TelemetrySignal.METRIC,),
        data_source_ids=("ds_requests",),
        required_fields=("service.name",),
    )


def test_observability_skill_taxonomy_is_complete_and_deterministic() -> None:
    descriptors = observability_skill_descriptors()
    assert tuple(descriptor.skill for descriptor in descriptors) == tuple(AgentSkill)
    assert observability_skill_descriptors() is descriptors
    assert all(descriptor.constraints for descriptor in descriptors)


def test_telemetry_contract_rejects_duplicate_fields() -> None:
    field = TelemetryField(
        name="service.name",
        signals=(TelemetrySignal.TRACE,),
        description="Stable service identity",
        semantic_convention="service.name",
    )
    with pytest.raises(ValueError, match="must be unique"):
        TelemetryContract(
            contract_id="portable-observability-v1",
            description="Portable telemetry",
            logical_indexes={"otel_traces": TelemetrySignal.TRACE},
            fields=(field, field),
        )


def test_catalog_entry_rejects_duplicate_panel_ids() -> None:
    with pytest.raises(ValueError, match="must be unique"):
        CatalogEntry(
            example_id="service_red",
            priority="high",
            title="Service RED",
            description="Service request health",
            minimum_target="9.4.3",
            telemetry_contract="portable-observability-v1",
            frameworks=(ObservabilityFramework.RED,),
            signals=(TelemetrySignal.METRIC,),
            logical_indexes=("otel_metrics",),
            panels=(_panel(), _panel()),
        )
