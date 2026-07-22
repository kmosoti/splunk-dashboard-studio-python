"""Pydantic 2 models for the stable Dashboard Studio definition envelope."""

from __future__ import annotations

from typing import Literal, cast

from pydantic import BaseModel, ConfigDict, Field, JsonValue, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        populate_by_name=True,
        validate_assignment=True,
    )


class ExtensibleModel(BaseModel):
    """Extension boundary for Splunk-owned option surfaces.

    Exact option validation belongs to the version-matched official schema in CI.
    """

    model_config = ConfigDict(
        extra="allow",
        populate_by_name=True,
        validate_assignment=True,
    )


class DataSource(ExtensibleModel):
    type: str = Field(min_length=1)
    options: dict[str, JsonValue] = Field(default_factory=dict)
    name: str | None = None


class Visualization(ExtensibleModel):
    type: str = Field(min_length=1)
    data_sources: dict[str, str] = Field(default_factory=dict, alias="dataSources")
    options: dict[str, JsonValue] = Field(default_factory=dict)
    context: dict[str, JsonValue] = Field(default_factory=dict)
    event_handlers: list[dict[str, JsonValue]] | dict[str, JsonValue] | None = Field(
        default=None,
        alias="eventHandlers",
    )
    container_options: dict[str, JsonValue] | None = Field(
        default=None,
        alias="containerOptions",
    )
    title: str | None = None
    description: str | None = None


class InputDefinition(ExtensibleModel):
    type: str = Field(min_length=1)
    options: dict[str, JsonValue] = Field(default_factory=dict)
    data_sources: dict[str, str] = Field(default_factory=dict, alias="dataSources")
    title: str | None = None


class Position(StrictModel):
    x: int = Field(ge=0)
    y: int = Field(ge=0)
    w: int = Field(gt=0)
    h: int = Field(gt=0)


class LayoutStructureItem(ExtensibleModel):
    type: str = "block"
    item: str | None = None
    position: Position | None = None


class LayoutDefinition(ExtensibleModel):
    type: str
    options: dict[str, JsonValue] = Field(default_factory=dict)
    structure: list[LayoutStructureItem] = Field(default_factory=list)


class TabItem(ExtensibleModel):
    layout_id: str = Field(alias="layoutId")
    label: str | None = None
    icon: str | None = None
    visibility: dict[str, JsonValue] | None = None


class Tabs(ExtensibleModel):
    items: list[TabItem] = Field(min_length=1)
    options: dict[str, JsonValue] = Field(default_factory=dict)


class Layout(ExtensibleModel):
    """Supports legacy and tabbed Dashboard Studio layout envelopes."""

    type: str | None = None
    options: dict[str, JsonValue] = Field(default_factory=dict)
    structure: list[LayoutStructureItem] | None = None
    global_inputs: list[str] = Field(default_factory=list, alias="globalInputs")
    layout_definitions: dict[str, LayoutDefinition] | None = Field(
        default=None,
        alias="layoutDefinitions",
    )
    tabs: Tabs | None = None

    @model_validator(mode="after")
    def require_complete_layout_shape(self) -> Layout:
        uses_tabbed_shape = self.layout_definitions is not None or self.tabs is not None
        if uses_tabbed_shape and (self.layout_definitions is None or self.tabs is None):
            raise ValueError("Tabbed layouts require both layoutDefinitions and tabs")
        if not uses_tabbed_shape and (self.type is None or self.structure is None):
            raise ValueError("Legacy layouts require type and structure")
        return self


class DashboardDefinition(StrictModel):
    version: Literal["2"] = "2"
    title: str = Field(min_length=1)
    description: str = ""
    visualizations: dict[str, Visualization] = Field(default_factory=dict)
    data_sources: dict[str, DataSource] = Field(default_factory=dict, alias="dataSources")
    inputs: dict[str, InputDefinition] = Field(default_factory=dict)
    defaults: dict[str, JsonValue] = Field(default_factory=dict)
    layout: Layout
    application_properties: dict[str, JsonValue] = Field(
        default_factory=dict,
        alias="applicationProperties",
    )
    expressions: dict[str, JsonValue] = Field(default_factory=dict)

    def as_json_value(self) -> dict[str, JsonValue]:
        return cast(
            dict[str, JsonValue],
            self.model_dump(by_alias=True, exclude_none=True, mode="json"),
        )


class DashboardEnvelope(StrictModel):
    definition: DashboardDefinition


def unwrap_definition(payload: object) -> object:
    if isinstance(payload, dict) and "definition" in payload:
        return payload["definition"]
    return payload
