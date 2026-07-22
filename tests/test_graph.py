from __future__ import annotations

from splunk_dashboard_studio.graph import (
    MAX_CHAIN_CHILDREN,
    analyze_search_graph,
    plan_search_optimizations,
)
from splunk_dashboard_studio.models import DataSource


def search(query: str, **options: object) -> DataSource:
    return DataSource(type="ds.search", options={"query": query, **options})


def chain(parent: str | None, query: str = "| head 5", **options: object) -> DataSource:
    values: dict[str, object] = {"query": query, **options}
    if parent is not None:
        values["extend"] = parent
    return DataSource.model_validate({"type": "ds.chain", "options": values})


def issue_codes(data_sources: dict[str, DataSource]) -> set[str]:
    return {issue.code for issue in analyze_search_graph(data_sources).issues}


def test_valid_search_graph_has_deterministic_topology_and_depth() -> None:
    analysis = analyze_search_graph(
        {
            "ds_base": search("index=main | stats count by host"),
            "ds_child": chain("ds_base"),
            "ds_grandchild": chain("ds_child"),
        }
    )
    assert analysis.is_valid
    assert analysis.topological_order == ("ds_base", "ds_child", "ds_grandchild")
    assert analysis.depth_by_node == {"ds_base": 0, "ds_child": 1, "ds_grandchild": 2}


def test_graph_reports_missing_self_cycle_depth_and_spl2_parent() -> None:
    assert "chain_parent_required" in issue_codes({"child": chain(None)})
    assert "chain_parent_missing" in issue_codes({"child": chain("missing")})
    assert "chain_self_reference" in issue_codes({"child": chain("child")})
    assert "chain_cycle" in issue_codes({"a": chain("b"), "b": chain("a")})
    assert "spl2_chain_unsupported" in issue_codes(
        {
            "base": DataSource(type="ds.spl2", options={"query": "$from main"}),
            "child": chain("base"),
        }
    )
    assert "chain_depth_exceeded" in issue_codes(
        {
            "base": search("index=main | stats count"),
            "one": chain("base"),
            "two": chain("one"),
            "three": chain("two"),
        }
    )


def test_graph_reports_excessive_fanout() -> None:
    sources = {"base": search("index=main | stats count")}
    sources.update({f"child_{index}": chain("base") for index in range(MAX_CHAIN_CHILDREN + 1)})
    analysis = analyze_search_graph(sources)
    issue = next(issue for issue in analysis.issues if issue.code == "chain_fanout_exceeded")
    assert issue.context["maximum"] == MAX_CHAIN_CHILDREN


def test_optimization_proposes_only_safe_transforming_prefix() -> None:
    plan = plan_search_optimizations(
        {
            "ds_errors": search("index=main | stats count by level | search level=error"),
            "ds_warnings": search("index=main | stats count by level | search level=warn"),
        }
    )
    assert not plan.applied
    assert len(plan.candidates) == 1
    candidate = plan.candidates[0]
    assert candidate.eligible
    assert candidate.confidence == "high"
    assert candidate.common_prefix == "index=main | stats count by level"
    assert candidate.suggested_chain_queries["ds_errors"] == "| search level=error"


def test_optimization_rejects_unsafe_or_nonmatching_groups() -> None:
    unsafe = plan_search_optimizations(
        {
            "a": search("index=main | eval x=1 | head 5"),
            "b": search("index=main | eval x=1 | tail 5"),
        }
    )
    assert len(unsafe.candidates) == 1
    assert not unsafe.candidates[0].eligible
    assert unsafe.candidates[0].risks

    distinct_parameters = plan_search_optimizations(
        {
            "a": search("index=main | stats count", queryParameters={"earliest": "-1h"}),
            "b": search("index=main | stats count", queryParameters={"earliest": "-24h"}),
            "broken": search("search ("),
            "chain": chain("a"),
        }
    )
    assert distinct_parameters.candidates == ()

    distinct_refresh = plan_search_optimizations(
        {
            "a": search("index=main | stats count | head 1", refresh="1m"),
            "b": search("index=main | stats count | tail 1", refresh="5m"),
        }
    )
    assert distinct_refresh.candidates == ()
