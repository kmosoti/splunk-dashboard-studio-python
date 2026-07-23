"""Offline codec for Splunk ``data/ui/views`` Dashboard Studio XML payloads."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from typing import Any, Literal, cast
from xml.etree import ElementTree
from xml.sax.saxutils import escape, quoteattr

from pydantic import BaseModel, ConfigDict, Field, JsonValue

from splunk_dashboard_studio.generation import canonical_json
from splunk_dashboard_studio.models import DashboardDefinition, unwrap_definition


class StudioViewCodecError(ValueError):
    pass


class StudioView(BaseModel):
    """The documented Dashboard Studio portion of a ``data/ui/views`` payload."""

    model_config = ConfigDict(extra="forbid", frozen=True, populate_by_name=True)

    version: Literal["2"] = "2"
    label: str = Field(min_length=1)
    description: str = ""
    definition: DashboardDefinition
    theme: Literal["light", "dark"] | None = None
    hidden_elements: dict[str, bool] | None = Field(default=None, alias="hiddenElements")


class RoundTripDifference(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    path: str
    kind: Literal["added", "removed", "changed"]
    expected: JsonValue | None = None
    actual: JsonValue | None = None


class RoundTripComparison(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    equivalent: bool
    expected_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    actual_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    differences: tuple[RoundTripDifference, ...] = ()


def _safe_cdata(value: str) -> str:
    return value.replace("]]>", "]]]]><![CDATA[>")


def encode_view_xml(view: StudioView) -> str:
    """Encode a view into deterministic REST storage XML without performing I/O."""

    attributes = ['version="2"']
    if view.theme is not None:
        attributes.append(f"theme={quoteattr(view.theme)}")
    if view.hidden_elements is not None:
        hidden = json.dumps(view.hidden_elements, sort_keys=True, separators=(",", ":"))
        attributes.append(f"hiddenElements={quoteattr(hidden)}")
    definition = _safe_cdata(canonical_json(view.definition))
    return (
        f"<dashboard {' '.join(attributes)}>"
        f"<label>{escape(view.label)}</label>"
        f"<description>{escape(view.description)}</description>"
        f"<definition><![CDATA[{definition}]]></definition>"
        "</dashboard>"
    )


def _required_text(root: ElementTree.Element, tag: str) -> str:
    element = root.find(tag)
    if element is None:
        raise StudioViewCodecError(f"Dashboard Studio XML requires a {tag!r} element")
    return element.text or ""


def decode_view_xml(payload: str | bytes) -> StudioView:
    """Decode and normalize the documented fields from REST storage XML."""

    raw = payload.decode("utf-8") if isinstance(payload, bytes) else payload
    upper = raw.upper()
    if "<!DOCTYPE" in upper or "<!ENTITY" in upper:
        raise StudioViewCodecError("DTD and entity declarations are not accepted")
    try:
        root = ElementTree.fromstring(raw)
    except ElementTree.ParseError as error:
        raise StudioViewCodecError(f"Invalid Dashboard Studio XML: {error}") from error
    if root.tag != "dashboard":
        raise StudioViewCodecError("Dashboard Studio XML root must be <dashboard>")
    if root.attrib.get("version") != "2":
        raise StudioViewCodecError('Dashboard Studio XML requires version="2"')

    theme = root.attrib.get("theme")
    if theme not in {None, "light", "dark"}:
        raise StudioViewCodecError("Dashboard Studio theme must be 'light' or 'dark'")
    hidden_elements: dict[str, bool] | None = None
    if hidden := root.attrib.get("hiddenElements"):
        try:
            parsed_hidden = json.loads(hidden)
        except json.JSONDecodeError as error:
            raise StudioViewCodecError("hiddenElements must contain a JSON object") from error
        if not isinstance(parsed_hidden, dict) or not all(
            isinstance(key, str) and isinstance(value, bool) for key, value in parsed_hidden.items()
        ):
            raise StudioViewCodecError("hiddenElements must map string keys to booleans")
        hidden_elements = parsed_hidden

    definition_text = _required_text(root, "definition")
    try:
        raw_definition = json.loads(definition_text)
    except json.JSONDecodeError as error:
        raise StudioViewCodecError("definition must contain valid JSON") from error
    try:
        definition = DashboardDefinition.model_validate(unwrap_definition(raw_definition))
    except ValueError as error:
        raise StudioViewCodecError(f"definition is not a valid dashboard: {error}") from error
    label = _required_text(root, "label")
    if not label:
        raise StudioViewCodecError("Dashboard Studio label must be non-empty")
    description_element = root.find("description")
    description = (description_element.text or "") if description_element is not None else ""
    return StudioView(
        label=label,
        description=description,
        definition=definition,
        theme=cast(Literal["light", "dark"] | None, theme),
        hidden_elements=hidden_elements,
    )


def _normalized(view: StudioView) -> dict[str, JsonValue]:
    value: dict[str, JsonValue] = {
        "version": view.version,
        "label": view.label,
        "description": view.description,
        "definition": view.definition.as_json_value(),
    }
    if view.theme is not None:
        value["theme"] = view.theme
    if view.hidden_elements is not None:
        value["hiddenElements"] = cast(JsonValue, dict(sorted(view.hidden_elements.items())))
    return value


def _pointer(parent: str, item: str | int) -> str:
    escaped = str(item).replace("~", "~0").replace("/", "~1")
    return f"{parent}/{escaped}"


def _diff(expected: JsonValue, actual: JsonValue, path: str = "") -> list[RoundTripDifference]:
    if isinstance(expected, dict) and isinstance(actual, dict):
        differences: list[RoundTripDifference] = []
        for key in sorted(expected.keys() | actual.keys()):
            item_path = _pointer(path, key)
            if key not in expected:
                differences.append(
                    RoundTripDifference(
                        path=item_path,
                        kind="added",
                        actual=actual[key],
                    )
                )
            elif key not in actual:
                differences.append(
                    RoundTripDifference(
                        path=item_path,
                        kind="removed",
                        expected=expected[key],
                    )
                )
            else:
                differences.extend(_diff(expected[key], actual[key], item_path))
        return differences
    if isinstance(expected, list) and isinstance(actual, list):
        differences = []
        shared = min(len(expected), len(actual))
        for index in range(shared):
            differences.extend(_diff(expected[index], actual[index], _pointer(path, index)))
        for index in range(shared, len(expected)):
            differences.append(
                RoundTripDifference(
                    path=_pointer(path, index),
                    kind="removed",
                    expected=expected[index],
                )
            )
        for index in range(shared, len(actual)):
            differences.append(
                RoundTripDifference(
                    path=_pointer(path, index),
                    kind="added",
                    actual=actual[index],
                )
            )
        return differences
    if type(expected) is type(actual) and expected == actual:
        return []
    return [
        RoundTripDifference(
            path=path or "/",
            kind="changed",
            expected=expected,
            actual=actual,
        )
    ]


def _view(value: StudioView | str | bytes) -> StudioView:
    return decode_view_xml(value) if isinstance(value, (str, bytes)) else value


def compare_roundtrip(
    expected: StudioView | str | bytes,
    actual: StudioView | str | bytes,
) -> RoundTripComparison:
    """Compare two normalized views with deterministic SHA-256 and JSON-pointer diffs."""

    expected_value = _normalized(_view(expected))
    actual_value = _normalized(_view(actual))
    expected_json = canonical_json(cast(Mapping[str, Any], expected_value))
    actual_json = canonical_json(cast(Mapping[str, Any], actual_value))
    differences = tuple(_diff(expected_value, actual_value))
    return RoundTripComparison(
        equivalent=not differences,
        expected_sha256=hashlib.sha256(expected_json.encode("utf-8")).hexdigest(),
        actual_sha256=hashlib.sha256(actual_json.encode("utf-8")).hexdigest(),
        differences=differences,
    )
