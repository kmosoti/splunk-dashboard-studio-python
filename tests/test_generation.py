from __future__ import annotations

import json

import pytest

from splunk_dashboard_studio import DashboardBuilder, canonical_json
from splunk_dashboard_studio.generation import DashboardGenerationError
from splunk_dashboard_studio.models import Position


def test_builder_generates_deterministic_ids_layout_and_json() -> None:
    builder = DashboardBuilder(title="Health", description="Overview", target="9.4.3")
    first = builder.add_search("index=main | stats count", name="Events")
    second = builder.add_search("index=other | stats count", name="Events")
    assert first == "ds_events"
    assert second == "ds_events_2"
    builder.add_visualization(
        "splunk.singlevalue",
        name="Count",
        data_sources={"primary": first},
        options={"majorValue": '> primary | seriesByName("count") | firstPoint()'},
    )
    builder.add_visualization(
        "splunk.table",
        name="Details",
        data_sources={"primary": second},
        position=Position(x=40, y=400, w=800, h=200),
    )
    definition = builder.build()
    rendered = canonical_json(definition)
    assert rendered == canonical_json(json.loads(rendered))
    assert json.loads(rendered)["dataSources"][first]["type"] == "ds.search"
    layout = definition.layout.layout_definitions["layout_main"]
    assert layout.options["width"] == 1440
    assert layout.structure[1].position == Position(x=40, y=400, w=800, h=200)


def test_builder_supports_search_saved_search_chain_inputs_and_properties() -> None:
    builder = DashboardBuilder(title="Complete", target="10.2.0")
    base = builder.add_search(
        "index=main | stats count by host",
        data_source_id="ds_base",
        earliest=None,
        latest=None,
        refresh="1m",
        refresh_type="delay",
    )
    chain = builder.add_chain(parent=base, query="| head 10", data_source_id="ds_top")
    saved = builder.add_saved_search("Weekly report", data_source_id="ds_saved")
    input_id = builder.add_input(
        "input.dropdown",
        name="Host",
        input_id="input_host",
        options={"token": "host"},
        data_sources={"primary": saved},
        title="Host",
        context={"label": "host"},
        container_options={"visibility": {"show": True}},
    )
    builder.add_visualization(
        "splunk.table",
        name="top",
        data_sources={"primary": chain},
        description="Top hosts",
        context={"rowColors": ["#ffffff"]},
        event_handlers=[{"type": "drilldown.setToken", "options": {"token": "host"}}],
        container_options={"visibility": {"show": True}},
    )
    builder.set_data_source_defaults(
        "ds.search",
        {
            "options": {
                "queryParameters": {
                    "earliest": "$global_time.earliest$",
                    "latest": "$global_time.latest$",
                }
            }
        },
    )
    builder.set_visualization_defaults("global", {"showProgressBar": True})
    builder.set_token_default("host", "*")
    builder.set_application_property("collapseNavigation", True)
    builder.set_expression("condition_visible", {"name": "visible", "value": "true()"})
    definition = builder.build()
    assert definition.data_sources[base].options == {
        "query": "index=main | stats count by host",
        "refresh": "1m",
        "refreshType": "delay",
    }
    assert definition.data_sources[chain].options["extend"] == base
    assert definition.data_sources[saved].options["ref"] == "Weekly report"
    assert definition.layout.global_inputs == [input_id]
    assert definition.inputs[input_id].data_sources == {"primary": saved}
    assert definition.inputs[input_id].container_options == {"visibility": {"show": True}}
    assert definition.application_properties["collapseNavigation"] is True
    assert "condition_visible" in definition.expressions
    assert definition.defaults == {
        "dataSources": {
            "ds.search": {
                "options": {
                    "queryParameters": {
                        "earliest": "$global_time.earliest$",
                        "latest": "$global_time.latest$",
                    }
                }
            }
        },
        "tokens": {"default": {"host": {"value": "*"}}},
        "visualizations": {"global": {"showProgressBar": True}},
    }
    visualization = definition.visualizations["viz_top"]
    assert visualization.description == "Top hosts"
    assert visualization.event_handlers is not None


def test_builder_rejects_duplicate_ids_and_invalid_result() -> None:
    builder = DashboardBuilder(title="Duplicates", target="10.2.0")
    builder.add_search("index=main | stats count", data_source_id="item")
    with pytest.raises(DashboardGenerationError, match="Duplicate"):
        builder.add_input("input.text", name="same", input_id="item")

    builder.add_visualization(
        "splunk.table",
        name="broken",
        data_sources={"primary": "missing"},
    )
    with pytest.raises(DashboardGenerationError, match="missing"):
        builder.build()
    assert builder.build(validate=False).title == "Duplicates"


def test_custom_canvas_height_is_preserved() -> None:
    builder = DashboardBuilder(title="Canvas", target="10.2.0")
    definition = builder.build(canvas_width=1200, canvas_height=500)
    layout = definition.layout.layout_definitions["layout_main"]
    assert layout.options == {"width": 1200, "height": 500}


@pytest.mark.parametrize(
    ("configure", "message"),
    [
        (
            lambda builder: (
                builder.set_data_source_defaults("global", {"options": {}}),
                builder.set_data_source_defaults("global", {"options": {}}),
            ),
            "Duplicate data source default scope",
        ),
        (
            lambda builder: (
                builder.set_visualization_defaults("global", {}),
                builder.set_visualization_defaults("global", {}),
            ),
            "Duplicate visualization default scope",
        ),
        (
            lambda builder: (
                builder.set_token_default("service", "*"),
                builder.set_token_default("service", "api"),
            ),
            "Duplicate token default",
        ),
    ],
)
def test_builder_rejects_duplicate_defaults(configure: object, message: str) -> None:
    builder = DashboardBuilder(title="Defaults", target="10.2.0")
    with pytest.raises(DashboardGenerationError, match=message):
        configure(builder)  # type: ignore[operator]


@pytest.mark.parametrize(
    "configure",
    [
        lambda builder: builder.set_data_source_defaults(" ", {}),
        lambda builder: builder.set_visualization_defaults("", {}),
        lambda builder: builder.set_token_default("", "value"),
        lambda builder: builder.set_token_default("name", "value", namespace=" "),
    ],
)
def test_builder_rejects_blank_default_names(configure: object) -> None:
    with pytest.raises(DashboardGenerationError, match="non-empty"):
        configure(DashboardBuilder(title="Defaults", target="10.2.0"))  # type: ignore[operator]
