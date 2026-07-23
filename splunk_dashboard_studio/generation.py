"""Deterministic Dashboard Studio builder APIs."""

from __future__ import annotations

import json
import re
from collections import defaultdict
from collections.abc import Mapping, Sequence
from typing import Any, cast

from pydantic import JsonValue

from splunk_dashboard_studio.models import (
    DashboardDefinition,
    DataSource,
    InputDefinition,
    Layout,
    LayoutDefinition,
    LayoutStructureItem,
    Position,
    TabItem,
    Tabs,
    Visualization,
)
from splunk_dashboard_studio.validation import validate_dashboard
from splunk_dashboard_studio.version import TargetPlatform

_NON_IDENTIFIER = re.compile(r"[^A-Za-z0-9_]+")


class DashboardGenerationError(ValueError):
    pass


def canonical_json(
    value: DashboardDefinition | Mapping[str, Any],
    *,
    indent: int | None = None,
) -> str:
    payload = value.as_json_value() if isinstance(value, DashboardDefinition) else dict(value)
    separators = None if indent is not None else (",", ":")
    return json.dumps(
        payload,
        ensure_ascii=False,
        indent=indent,
        separators=separators,
        sort_keys=True,
    )


def _slug(value: str) -> str:
    slug = _NON_IDENTIFIER.sub("_", value.strip()).strip("_").lower()
    return slug or "item"


class DashboardBuilder:
    """Stateful builder with deterministic IDs and a validated immutable result."""

    def __init__(
        self,
        *,
        title: str,
        target: TargetPlatform | str,
        description: str = "",
    ) -> None:
        self.title = title
        self.description = description
        self.target = (
            target if isinstance(target, TargetPlatform) else TargetPlatform.enterprise(target)
        )
        self._data_sources: dict[str, DataSource] = {}
        self._visualizations: dict[str, Visualization] = {}
        self._inputs: dict[str, InputDefinition] = {}
        self._counters: defaultdict[str, int] = defaultdict(int)
        self._positions: dict[str, Position] = {}
        self._application_properties: dict[str, JsonValue] = {}
        self._expressions: dict[str, JsonValue] = {}
        self._data_source_defaults: dict[str, dict[str, JsonValue]] = {}
        self._visualization_defaults: dict[str, dict[str, JsonValue]] = {}
        self._token_defaults: dict[str, dict[str, JsonValue]] = {}

    def _identifier(self, prefix: str, label: str, explicit: str | None) -> str:
        if explicit:
            candidate = explicit
        else:
            base = f"{prefix}_{_slug(label)}"
            self._counters[base] += 1
            suffix = "" if self._counters[base] == 1 else f"_{self._counters[base]}"
            candidate = f"{base}{suffix}"
        occupied = set(self._data_sources) | set(self._visualizations) | set(self._inputs)
        if candidate in occupied:
            raise DashboardGenerationError(f"Duplicate Dashboard Studio ID {candidate!r}")
        return candidate

    def add_search(
        self,
        query: str,
        *,
        name: str = "search",
        data_source_id: str | None = None,
        earliest: str | None = "-24h@h",
        latest: str | None = "now",
        refresh: str | None = None,
        refresh_type: str | None = None,
    ) -> str:
        identifier = self._identifier("ds", name, data_source_id)
        query_parameters: dict[str, JsonValue] = {}
        if earliest is not None:
            query_parameters["earliest"] = earliest
        if latest is not None:
            query_parameters["latest"] = latest
        options: dict[str, JsonValue] = {"query": query}
        if query_parameters:
            options["queryParameters"] = query_parameters
        if refresh is not None:
            options["refresh"] = refresh
        if refresh_type is not None:
            options["refreshType"] = refresh_type
        self._data_sources[identifier] = DataSource(
            type="ds.search",
            name=name,
            options=options,
        )
        return identifier

    def add_chain(
        self,
        *,
        parent: str,
        query: str,
        name: str = "chain",
        data_source_id: str | None = None,
    ) -> str:
        identifier = self._identifier("ds", name, data_source_id)
        self._data_sources[identifier] = DataSource(
            type="ds.chain",
            name=name,
            options={"extend": parent, "query": query},
        )
        return identifier

    def add_saved_search(
        self,
        reference: str,
        *,
        name: str = "saved_search",
        data_source_id: str | None = None,
    ) -> str:
        identifier = self._identifier("ds", name, data_source_id)
        self._data_sources[identifier] = DataSource(
            type="ds.savedSearch",
            name=name,
            options={"ref": reference},
        )
        return identifier

    def add_visualization(
        self,
        visualization_type: str,
        *,
        name: str,
        data_sources: Mapping[str, str] | None = None,
        options: Mapping[str, JsonValue] | None = None,
        visualization_id: str | None = None,
        position: Position | Mapping[str, int] | None = None,
        title: str | None = None,
        description: str | None = None,
        context: Mapping[str, JsonValue] | None = None,
        event_handlers: Sequence[Mapping[str, JsonValue]] | Mapping[str, JsonValue] | None = None,
        container_options: Mapping[str, JsonValue] | None = None,
    ) -> str:
        identifier = self._identifier("viz", name, visualization_id)
        normalized_handlers: list[dict[str, JsonValue]] | dict[str, JsonValue] | None
        if event_handlers is None:
            normalized_handlers = None
        elif isinstance(event_handlers, Mapping):
            normalized_handlers = dict(event_handlers)
        else:
            normalized_handlers = [dict(handler) for handler in event_handlers]
        self._visualizations[identifier] = Visualization(
            type=visualization_type,
            data_sources=dict(data_sources or {}),
            options=dict(options or {}),
            context=dict(context or {}),
            event_handlers=normalized_handlers,
            container_options=(dict(container_options) if container_options is not None else None),
            title=title,
            description=description,
        )
        if position is not None:
            self._positions[identifier] = (
                position if isinstance(position, Position) else Position.model_validate(position)
            )
        return identifier

    def add_input(
        self,
        input_type: str,
        *,
        name: str,
        options: Mapping[str, JsonValue] | None = None,
        data_sources: Mapping[str, str] | None = None,
        input_id: str | None = None,
        title: str | None = None,
        context: Mapping[str, JsonValue] | None = None,
        container_options: Mapping[str, JsonValue] | None = None,
    ) -> str:
        identifier = self._identifier("input", name, input_id)
        self._inputs[identifier] = InputDefinition(
            type=input_type,
            options=dict(options or {}),
            data_sources=dict(data_sources or {}),
            title=title,
            context=dict(context or {}),
            container_options=(dict(container_options) if container_options is not None else None),
        )
        return identifier

    @staticmethod
    def _require_default_name(kind: str, value: str) -> None:
        if not value.strip():
            raise DashboardGenerationError(f"{kind} must be non-empty")

    def set_data_source_defaults(
        self,
        scope: str,
        values: Mapping[str, JsonValue],
    ) -> DashboardBuilder:
        """Set one global or data-source-type default without overwriting prior intent."""

        self._require_default_name("Data source default scope", scope)
        if scope in self._data_source_defaults:
            raise DashboardGenerationError(f"Duplicate data source default scope {scope!r}")
        self._data_source_defaults[scope] = dict(values)
        return self

    def set_visualization_defaults(
        self,
        scope: str,
        values: Mapping[str, JsonValue],
    ) -> DashboardBuilder:
        """Set one global or visualization-type default without implicit merging."""

        self._require_default_name("Visualization default scope", scope)
        if scope in self._visualization_defaults:
            raise DashboardGenerationError(f"Duplicate visualization default scope {scope!r}")
        self._visualization_defaults[scope] = dict(values)
        return self

    def set_token_default(
        self,
        name: str,
        value: JsonValue,
        *,
        namespace: str = "default",
    ) -> DashboardBuilder:
        """Set a Dashboard Studio token default in the documented value envelope."""

        self._require_default_name("Token name", name)
        self._require_default_name("Token namespace", namespace)
        token_namespace = self._token_defaults.setdefault(namespace, {})
        if name in token_namespace:
            raise DashboardGenerationError(f"Duplicate token default {namespace!r}/{name!r}")
        token_namespace[name] = value
        return self

    def set_application_property(self, name: str, value: JsonValue) -> DashboardBuilder:
        self._application_properties[name] = value
        return self

    def set_expression(self, name: str, value: JsonValue) -> DashboardBuilder:
        self._expressions[name] = value
        return self

    def _position_for(self, identifier: str, index: int, width: int) -> Position:
        if identifier in self._positions:
            return self._positions[identifier]
        columns = 2
        gutter = 20
        item_width = (width - gutter * (columns + 1)) // columns
        item_height = 260
        column = index % columns
        row = index // columns
        return Position(
            x=gutter + column * (item_width + gutter),
            y=gutter + row * (item_height + gutter),
            w=item_width,
            h=item_height,
        )

    def build(
        self,
        *,
        canvas_width: int = 1440,
        canvas_height: int | None = None,
        validate: bool = True,
    ) -> DashboardDefinition:
        item_ids = list(self._visualizations)
        positions = [
            self._position_for(identifier, index, canvas_width)
            for index, identifier in enumerate(item_ids)
        ]
        required_height = max((position.y + position.h + 20 for position in positions), default=720)
        height = canvas_height or max(720, required_height)
        structure = [
            LayoutStructureItem(type="block", item=identifier, position=position)
            for identifier, position in zip(item_ids, positions, strict=True)
        ]
        layout = Layout(
            global_inputs=list(self._inputs),
            options={},
            layout_definitions={
                "layout_main": LayoutDefinition(
                    type="absolute",
                    options={"width": canvas_width, "height": height},
                    structure=structure,
                )
            },
            tabs=Tabs(items=[TabItem(layout_id="layout_main", label="Overview")]),
        )
        defaults: dict[str, JsonValue] = {}
        if self._data_source_defaults:
            defaults["dataSources"] = cast(JsonValue, self._data_source_defaults)
        if self._visualization_defaults:
            defaults["visualizations"] = cast(JsonValue, self._visualization_defaults)
        if self._token_defaults:
            defaults["tokens"] = {
                namespace: {name: {"value": value} for name, value in sorted(token_values.items())}
                for namespace, token_values in sorted(self._token_defaults.items())
            }
        definition = DashboardDefinition(
            title=self.title,
            description=self.description,
            data_sources=dict(self._data_sources),
            visualizations=dict(self._visualizations),
            inputs=dict(self._inputs),
            defaults=defaults,
            layout=layout,
            application_properties=dict(self._application_properties),
            expressions=dict(self._expressions),
        )
        if validate:
            report = validate_dashboard(definition, target=self.target)
            if not report.is_valid:
                messages = "; ".join(f"{issue.path}: {issue.message}" for issue in report.issues)
                raise DashboardGenerationError(messages)
        return definition
