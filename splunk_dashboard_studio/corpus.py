"""Deterministic coverage corpus for native and official-engine CI validation."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, JsonValue

from splunk_dashboard_studio.catalog import build_catalog_dashboard, catalog_entries
from splunk_dashboard_studio.generation import DashboardBuilder
from splunk_dashboard_studio.source_templates import (
    build_source_template,
    source_template_entries,
)
from splunk_dashboard_studio.version import TargetPlatform


class CorpusCase(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    case_id: str
    target: TargetPlatform
    expected_native: Literal["valid", "invalid"]
    expected_npm: Literal["valid", "invalid", "skip"]
    tags: tuple[str, ...] = ()
    definition: dict[str, JsonValue]


def _base_definition(target: TargetPlatform) -> dict[str, Any]:
    builder = DashboardBuilder(title="Compatibility corpus", target=target)
    search = builder.add_search(
        "| makeresults | eval count=1 | stats sum(count) AS count",
        name="count",
        data_source_id="ds_count",
    )
    builder.add_visualization(
        "splunk.singlevalue",
        name="count",
        visualization_id="viz_count",
        data_sources={"primary": search},
        options={
            "majorValue": '> primary | seriesByName("count") | firstPoint()',
            "showSparklineAreaGraph": False,
        },
        position={"x": 20, "y": 20, "w": 400, "h": 240},
    )
    builder.set_application_property("collapseNavigation", False)
    builder.set_application_property("downsampleVisualizations", True)
    return builder.build().as_json_value()


def generate_corpus(target: TargetPlatform | str) -> tuple[CorpusCase, ...]:
    platform = target if isinstance(target, TargetPlatform) else TargetPlatform.enterprise(target)
    base = _base_definition(platform)
    cases: list[CorpusCase] = [
        CorpusCase(
            case_id="valid-minimal-singlevalue",
            target=platform,
            expected_native="valid",
            expected_npm="valid",
            tags=("positive", "singlevalue", "dos", "absolute-layout"),
            definition=base,
        )
    ]

    for entry in catalog_entries():
        if platform.version < entry.minimum_target:
            continue
        cases.append(
            CorpusCase(
                case_id=f"catalog-{entry.example_id}",
                target=platform,
                expected_native="valid",
                expected_npm="valid",
                tags=("positive", "catalog", *entry.tags),
                definition=build_catalog_dashboard(
                    entry.example_id,
                    platform,
                ).as_json_value(),
            )
        )

    for source_entry in source_template_entries():
        if platform.version < source_entry.minimum_target:
            continue
        cases.append(
            CorpusCase(
                case_id=f"source-template-{source_entry.template_id}",
                target=platform,
                expected_native="valid",
                expected_npm="skip" if source_entry.required_apps else "valid",
                tags=("positive", "source-template", *source_entry.tags),
                definition=build_source_template(
                    source_entry.template_id,
                    str(platform.version),
                ).as_json_value(),
            )
        )

    chain = copy.deepcopy(base)
    chain["dataSources"]["ds_base"] = {
        "type": "ds.search",
        "options": {
            "query": "index=_internal | stats count by sourcetype",
            "queryParameters": {"earliest": "-24h@h", "latest": "now"},
        },
    }
    chain["dataSources"]["ds_top"] = {
        "type": "ds.chain",
        "options": {"extend": "ds_base", "query": "| sort - count | head 5"},
    }
    cases.append(
        CorpusCase(
            case_id="valid-base-chain",
            target=platform,
            expected_native="valid",
            expected_npm="valid",
            tags=("positive", "search-chain"),
            definition=chain,
        )
    )

    missing_reference = copy.deepcopy(base)
    missing_reference["visualizations"]["viz_count"]["dataSources"]["primary"] = "ds_missing"
    cases.append(
        CorpusCase(
            case_id="invalid-missing-data-source",
            target=platform,
            expected_native="invalid",
            expected_npm="skip",
            tags=("negative", "reference"),
            definition=missing_reference,
        )
    )

    malformed_dos = copy.deepcopy(base)
    malformed_dos["visualizations"]["viz_count"]["options"]["majorValue"] = (
        '> primary seriesByName("count")'
    )
    cases.append(
        CorpusCase(
            case_id="invalid-dos",
            target=platform,
            expected_native="invalid",
            expected_npm="invalid",
            tags=("negative", "dos"),
            definition=malformed_dos,
        )
    )

    wrong_option_type = copy.deepcopy(base)
    wrong_option_type["visualizations"]["viz_count"]["options"]["showSparklineAreaGraph"] = "false"
    cases.append(
        CorpusCase(
            case_id="invalid-option-type",
            target=platform,
            expected_native="valid",
            expected_npm="invalid",
            tags=("negative", "official-schema"),
            definition=wrong_option_type,
        )
    )

    cycle = copy.deepcopy(base)
    cycle["dataSources"].update(
        {
            "ds_cycle_a": {
                "type": "ds.chain",
                "options": {"extend": "ds_cycle_b", "query": "| head 1"},
            },
            "ds_cycle_b": {
                "type": "ds.chain",
                "options": {"extend": "ds_cycle_a", "query": "| head 1"},
            },
        }
    )
    cases.append(
        CorpusCase(
            case_id="invalid-chain-cycle",
            target=platform,
            expected_native="invalid",
            expected_npm="skip",
            tags=("negative", "search-chain", "cycle"),
            definition=cycle,
        )
    )

    overflow = copy.deepcopy(base)
    overflow["layout"]["layoutDefinitions"]["layout_main"]["structure"][0]["position"]["x"] = 1300
    cases.append(
        CorpusCase(
            case_id="invalid-canvas-overflow",
            target=platform,
            expected_native="invalid",
            expected_npm="skip",
            tags=("negative", "layout", "boundary"),
            definition=overflow,
        )
    )

    spl2 = copy.deepcopy(base)
    spl2["dataSources"]["ds_spl2"] = {
        "type": "ds.spl2",
        "options": {"query": "$from main | stats count() AS count"},
    }
    supports_spl2 = platform.version >= "10.2.0"
    cases.append(
        CorpusCase(
            case_id="version-boundary-spl2",
            target=platform,
            expected_native="valid" if supports_spl2 else "invalid",
            expected_npm="skip",
            tags=("version-boundary", "spl2"),
            definition=spl2,
        )
    )
    return tuple(cases)


def corpus_jsonl(target: TargetPlatform | str) -> str:
    return (
        "\n".join(
            json.dumps(case.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
            for case in generate_corpus(target)
        )
        + "\n"
    )


def write_corpus(path: Path, target: TargetPlatform | str) -> None:
    path.write_text(corpus_jsonl(target), encoding="utf-8")
