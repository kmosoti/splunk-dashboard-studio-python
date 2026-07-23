from __future__ import annotations

import string

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from pydantic import JsonValue

from splunk_dashboard_studio.catalog import (
    CatalogTargetUnsupported,
    build_catalog_dashboard,
    catalog_entries,
)
from splunk_dashboard_studio.codec import StudioView, compare_roundtrip, encode_view_xml
from splunk_dashboard_studio.generation import DashboardBuilder, canonical_json
from splunk_dashboard_studio.graph import MAX_CHAIN_CHILDREN, MAX_CHAIN_DEPTH, analyze_search_graph
from splunk_dashboard_studio.models import DataSource
from splunk_dashboard_studio.validation import validate_dashboard
from splunk_dashboard_studio.version import EnterpriseVersion

DETERMINISTIC = settings(max_examples=50, deadline=None, derandomize=True)
IDENTIFIER_LABELS = st.text(
    alphabet=string.ascii_letters + string.digits + " _-./:@",
    min_size=1,
    max_size=32,
)
SCOPES = st.from_regex(r"[a-z][a-z0-9_.]{0,20}", fullmatch=True)
JSON_SCALARS: st.SearchStrategy[JsonValue] = st.one_of(
    st.none(),
    st.booleans(),
    st.integers(min_value=-10_000, max_value=10_000),
    st.text(alphabet=string.printable, max_size=24),
)


@DETERMINISTIC
@given(st.lists(IDENTIFIER_LABELS, min_size=1, max_size=12))
def test_generated_ids_are_stable_and_unique(labels: list[str]) -> None:
    first = DashboardBuilder(title="Identifiers", target="10.2.0")
    second = DashboardBuilder(title="Identifiers", target="10.2.0")
    first_ids = [first.add_search("| makeresults | stats count", name=label) for label in labels]
    second_ids = [second.add_search("| makeresults | stats count", name=label) for label in labels]
    assert first_ids == second_ids
    assert len(first_ids) == len(set(first_ids))


@DETERMINISTIC
@given(depth=st.integers(min_value=0, max_value=6))
def test_chain_depth_property(depth: int) -> None:
    sources = {"base": DataSource(type="ds.search", options={"query": "| makeresults"})}
    parent = "base"
    for index in range(depth):
        child = f"child_{index}"
        sources[child] = DataSource(
            type="ds.chain",
            options={"extend": parent, "query": "| head 1"},
        )
        parent = child
    codes = {issue.code for issue in analyze_search_graph(sources).issues}
    assert ("chain_depth_exceeded" in codes) is (depth > MAX_CHAIN_DEPTH)


@DETERMINISTIC
@given(fanout=st.integers(min_value=0, max_value=15))
def test_chain_fanout_property(fanout: int) -> None:
    sources = {"base": DataSource(type="ds.search", options={"query": "| makeresults"})}
    sources.update(
        {
            f"child_{index}": DataSource(
                type="ds.chain",
                options={"extend": "base", "query": "| head 1"},
            )
            for index in range(fanout)
        }
    )
    codes = {issue.code for issue in analyze_search_graph(sources).issues}
    assert ("chain_fanout_exceeded" in codes) is (fanout > MAX_CHAIN_CHILDREN)


@DETERMINISTIC
@given(existing=st.booleans())
def test_visualization_reference_property(existing: bool) -> None:
    builder = DashboardBuilder(title="References", target="10.2.0")
    source = builder.add_search("| makeresults | stats count", data_source_id="ds_source")
    builder.add_visualization(
        "splunk.table",
        name="Reference",
        data_sources={"primary": source if existing else "ds_missing"},
    )
    definition = builder.build(validate=False)
    codes = {issue.code for issue in validate_dashboard(definition, target="10.2.0").issues}
    assert ("visualization_data_source_missing" in codes) is (not existing)


@DETERMINISTIC
@given(
    scopes=st.lists(SCOPES, min_size=1, max_size=8, unique=True),
    values=st.lists(JSON_SCALARS, min_size=1, max_size=8),
)
def test_defaults_and_canonical_json_are_order_stable(
    scopes: list[str],
    values: list[JsonValue],
) -> None:
    pairs = list(zip(scopes, values, strict=False))
    first = DashboardBuilder(title="Defaults", target="10.2.0")
    second = DashboardBuilder(title="Defaults", target="10.2.0")
    for scope, value in pairs:
        first.set_visualization_defaults(scope, {"value": value})
    for scope, value in reversed(pairs):
        second.set_visualization_defaults(scope, {"value": value})
    assert canonical_json(first.build()) == canonical_json(second.build())


@DETERMINISTIC
@given(
    example_id=st.sampled_from(tuple(entry.example_id for entry in catalog_entries())),
    target=st.sampled_from(("9.4.3", "10.0.0", "10.2.0", "10.4.0")),
)
def test_catalog_target_support_property(example_id: str, target: str) -> None:
    entry = next(entry for entry in catalog_entries() if entry.example_id == example_id)
    if EnterpriseVersion.parse(target) < entry.minimum_target:
        with pytest.raises(CatalogTargetUnsupported):
            build_catalog_dashboard(example_id, target)
    else:
        assert build_catalog_dashboard(example_id, target).title == entry.title


@DETERMINISTIC
@given(
    label=st.text(
        alphabet=string.ascii_letters + string.digits + " &<>'\"é",
        min_size=1,
        max_size=30,
    ),
    prefix=st.text(alphabet=string.ascii_letters + " &<>", max_size=20),
    suffix=st.text(alphabet=string.ascii_letters + " &<>", max_size=20),
)
def test_offline_codec_roundtrip_property(label: str, prefix: str, suffix: str) -> None:
    builder = DashboardBuilder(
        title="Codec property",
        description=f"{prefix}]]>{suffix}",
        target="10.2.0",
    )
    view = StudioView(label=label, definition=builder.build(), description=f"{suffix}]]>{prefix}")
    assert compare_roundtrip(view, encode_view_xml(view)).equivalent
