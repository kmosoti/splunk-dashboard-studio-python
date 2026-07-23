from __future__ import annotations

import json

import pytest

from splunk_dashboard_studio import DashboardBuilder
from splunk_dashboard_studio.codec import (
    StudioView,
    StudioViewCodecError,
    compare_roundtrip,
    decode_view_xml,
    encode_view_xml,
)


def _view(*, query: str = "index=main | stats count") -> StudioView:
    builder = DashboardBuilder(title="Codec dashboard", target="10.2.0")
    source = builder.add_search(query, data_source_id="ds_events")
    builder.add_visualization(
        "splunk.table",
        name="Events",
        visualization_id="viz_events",
        data_sources={"primary": source},
    )
    return StudioView(
        label="Codec <dashboard> & evidence",
        description="Offline only",
        definition=builder.build(),
        theme="dark",
        hidden_elements={"hideEdit": False, "hideExport": True},
    )


def test_codec_roundtrips_documented_view_fields() -> None:
    view = _view()
    encoded = encode_view_xml(view)
    assert encoded.startswith('<dashboard version="2" theme="dark" hiddenElements=')
    assert "<![CDATA[" in encoded
    decoded = decode_view_xml(encoded)
    assert decoded == view
    comparison = compare_roundtrip(view, encoded)
    assert comparison.equivalent
    assert comparison.expected_sha256 == comparison.actual_sha256
    assert comparison.differences == ()


def test_codec_safely_splits_cdata_terminators() -> None:
    view = _view(query='index=main | eval marker="]] >" | eval exact="]] >"')
    payload = view.model_copy(
        update={
            "definition": view.definition.model_copy(
                update={
                    "description": "contains ]]> safely",
                }
            )
        }
    )
    encoded = encode_view_xml(payload)
    assert "]]]]><![CDATA[>" in encoded
    assert decode_view_xml(encoded) == payload


def test_codec_ignores_server_added_elements_and_attributes() -> None:
    encoded = encode_view_xml(_view())
    readback = encoded.replace(
        '<dashboard version="2"',
        '<dashboard version="2" isDashboard="1"',
    ).replace("</dashboard>", "<serverMetadata>ignored</serverMetadata></dashboard>")
    assert compare_roundtrip(encoded, readback).equivalent


def test_compare_roundtrip_returns_sorted_json_pointer_differences() -> None:
    expected = _view()
    changed_payload = expected.definition.as_json_value()
    changed_payload["title"] = "Changed title"
    changed_payload["description"] = "Changed description"
    actual = expected.model_copy(
        update={"definition": expected.definition.model_validate(changed_payload)}
    )
    comparison = compare_roundtrip(expected, actual)
    assert not comparison.equivalent
    assert [difference.path for difference in comparison.differences] == [
        "/definition/description",
        "/definition/title",
    ]
    assert all(difference.kind == "changed" for difference in comparison.differences)


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        ('<form version="2"></form>', "root must be"),
        ('<dashboard version="1"></dashboard>', "requires version"),
        (
            '<!DOCTYPE dashboard><dashboard version="2"></dashboard>',
            "DTD and entity",
        ),
        (
            '<dashboard version="2"><label>x</label></dashboard>',
            "requires a 'definition' element",
        ),
        (
            '<dashboard version="2" hiddenElements="[]"><label>x</label>'
            "<definition><![CDATA[{}]]></definition></dashboard>",
            "must map string keys",
        ),
    ],
)
def test_codec_rejects_invalid_xml_contract(payload: str, message: str) -> None:
    with pytest.raises(StudioViewCodecError, match=message):
        decode_view_xml(payload)


def test_codec_rejects_invalid_definition_json() -> None:
    payload = (
        '<dashboard version="2"><label>x</label><definition><![CDATA['
        + json.dumps({"not": "a dashboard"})
        + "]]></definition></dashboard>"
    )
    with pytest.raises(StudioViewCodecError, match="not a valid dashboard"):
        decode_view_xml(payload)
