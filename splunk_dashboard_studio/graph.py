"""Search-chain graph validation and conservative optimization analysis."""

from __future__ import annotations

import heapq
import json
from collections import defaultdict

from pydantic import BaseModel, ConfigDict, JsonValue

from splunk_dashboard_studio.issues import IssueOrigin, ValidationIssue
from splunk_dashboard_studio.models import DataSource
from splunk_dashboard_studio.spl import (
    TRANSFORMING_COMMANDS,
    SplPipeline,
    SplSyntaxError,
    longest_common_prefix,
    parse_spl,
)

MAX_CHAIN_DEPTH = 2
MAX_CHAIN_CHILDREN = 10


class SearchEdge(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    parent: str
    child: str


class GraphAnalysis(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    nodes: tuple[str, ...]
    edges: tuple[SearchEdge, ...]
    topological_order: tuple[str, ...]
    depth_by_node: dict[str, int]
    cycles: tuple[tuple[str, ...], ...]
    issues: tuple[ValidationIssue, ...]

    @property
    def is_valid(self) -> bool:
        return not self.issues


class OptimizationCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    candidate_ids: tuple[str, ...]
    eligible: bool
    common_prefix: str
    suggested_base_id: str
    suggested_chain_queries: dict[str, str]
    confidence: str
    reasons: tuple[str, ...]
    risks: tuple[str, ...]


class SearchOptimizationPlan(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    applied: bool = False
    candidates: tuple[OptimizationCandidate, ...] = ()


def _cycle_paths(
    nodes: tuple[str, ...],
    parent_by_child: dict[str, str],
) -> tuple[tuple[str, ...], ...]:
    cycles: set[tuple[str, ...]] = set()
    globally_seen: set[str] = set()
    for start in nodes:
        if start in globally_seen:
            continue
        order: list[str] = []
        positions: dict[str, int] = {}
        current = start
        while current in parent_by_child and current not in globally_seen:
            if current in positions:
                cycle = order[positions[current] :]
                pivot = min(range(len(cycle)), key=cycle.__getitem__)
                normalized = tuple(cycle[pivot:] + cycle[:pivot] + [cycle[pivot]])
                cycles.add(normalized)
                break
            positions[current] = len(order)
            order.append(current)
            current = parent_by_child[current]
        globally_seen.update(order)
    return tuple(sorted(cycles))


def analyze_search_graph(data_sources: dict[str, DataSource]) -> GraphAnalysis:
    nodes = tuple(sorted(data_sources))
    edges: list[SearchEdge] = []
    issues: list[ValidationIssue] = []
    parent_by_child: dict[str, str] = {}
    children_by_parent: dict[str, list[str]] = defaultdict(list)

    for child_id in nodes:
        data_source = data_sources[child_id]
        if data_source.type != "ds.chain":
            continue
        parent = data_source.options.get("extend")
        if not isinstance(parent, str) or not parent.strip():
            issues.append(
                ValidationIssue(
                    code="chain_parent_required",
                    path=f"$/dataSources/{child_id}/options/extend",
                    message="ds.chain requires a non-empty options.extend parent ID",
                    origin=IssueOrigin.SEARCH_GRAPH,
                )
            )
            continue
        if parent == child_id:
            issues.append(
                ValidationIssue(
                    code="chain_self_reference",
                    path=f"$/dataSources/{child_id}/options/extend",
                    message=f"Chain search {child_id!r} cannot extend itself",
                    origin=IssueOrigin.SEARCH_GRAPH,
                )
            )
        if parent not in data_sources:
            issues.append(
                ValidationIssue(
                    code="chain_parent_missing",
                    path=f"$/dataSources/{child_id}/options/extend",
                    message=f"Chain search {child_id!r} references missing parent {parent!r}",
                    origin=IssueOrigin.SEARCH_GRAPH,
                    context={"parent": parent},
                )
            )
            continue
        if data_sources[parent].type.startswith("ds.spl2"):
            issues.append(
                ValidationIssue(
                    code="spl2_chain_unsupported",
                    path=f"$/dataSources/{child_id}/options/extend",
                    message="SPL2 data sources cannot be parents of ds.chain searches",
                    origin=IssueOrigin.SEARCH_GRAPH,
                )
            )
        parent_by_child[child_id] = parent
        children_by_parent[parent].append(child_id)
        edges.append(SearchEdge(parent=parent, child=child_id))

    for parent, children in sorted(children_by_parent.items()):
        if len(children) > MAX_CHAIN_CHILDREN:
            issues.append(
                ValidationIssue(
                    code="chain_fanout_exceeded",
                    path=f"$/dataSources/{parent}",
                    message=(
                        f"Search {parent!r} has {len(children)} chain children; "
                        f"the supported maximum is {MAX_CHAIN_CHILDREN}"
                    ),
                    origin=IssueOrigin.SEARCH_GRAPH,
                    context={
                        "children": list[JsonValue](sorted(children)),
                        "maximum": MAX_CHAIN_CHILDREN,
                    },
                )
            )

    cycles = _cycle_paths(nodes, parent_by_child)
    for cycle in cycles:
        issues.append(
            ValidationIssue(
                code="chain_cycle",
                path="$/dataSources",
                message=f"Search-chain cycle detected: {' -> '.join(cycle)}",
                origin=IssueOrigin.SEARCH_GRAPH,
                context={"cycle": list(cycle)},
            )
        )

    indegree = {node: 0 for node in nodes}
    outgoing: dict[str, list[str]] = defaultdict(list)
    for edge in edges:
        outgoing[edge.parent].append(edge.child)
        indegree[edge.child] += 1
    ready = [node for node, degree in indegree.items() if degree == 0]
    heapq.heapify(ready)
    topological: list[str] = []
    while ready:
        node = heapq.heappop(ready)
        topological.append(node)
        for child in sorted(outgoing[node]):
            indegree[child] -= 1
            if indegree[child] == 0:
                heapq.heappush(ready, child)

    cyclic_nodes = {node for cycle in cycles for node in cycle}
    depth_by_node: dict[str, int] = {}

    def depth(node: str) -> int:
        if node in depth_by_node:
            return depth_by_node[node]
        if node in cyclic_nodes or node not in parent_by_child:
            depth_by_node[node] = 0
            return 0
        value = depth(parent_by_child[node]) + 1
        depth_by_node[node] = value
        return value

    for node in nodes:
        value = depth(node)
        if value > MAX_CHAIN_DEPTH:
            issues.append(
                ValidationIssue(
                    code="chain_depth_exceeded",
                    path=f"$/dataSources/{node}/options/extend",
                    message=(
                        f"Chain search {node!r} has depth {value}; "
                        f"the supported maximum is {MAX_CHAIN_DEPTH}"
                    ),
                    origin=IssueOrigin.SEARCH_GRAPH,
                    context={"depth": value, "maximum": MAX_CHAIN_DEPTH},
                )
            )

    return GraphAnalysis(
        nodes=nodes,
        edges=tuple(sorted(edges, key=lambda edge: (edge.parent, edge.child))),
        topological_order=tuple(topological),
        depth_by_node=dict(sorted(depth_by_node.items())),
        cycles=cycles,
        issues=tuple(sorted(issues, key=lambda issue: (issue.path, issue.code))),
    )


def _inherited_options_key(data_source: DataSource) -> str:
    inherited = {
        key: data_source.options.get(key)
        for key in ("queryParameters", "refresh", "refreshType")
        if key in data_source.options
    }
    return json.dumps(inherited, sort_keys=True, separators=(",", ":"))


def plan_search_optimizations(data_sources: dict[str, DataSource]) -> SearchOptimizationPlan:
    groups: dict[str, list[tuple[str, SplPipeline]]] = defaultdict(list)
    for data_source_id, data_source in sorted(data_sources.items()):
        if data_source.type != "ds.search":
            continue
        query = data_source.options.get("query")
        if not isinstance(query, str):
            continue
        try:
            pipeline = parse_spl(query)
        except SplSyntaxError:
            continue
        groups[_inherited_options_key(data_source)].append((data_source_id, pipeline))

    candidates: list[OptimizationCandidate] = []
    for group in groups.values():
        if len(group) < 2:
            continue
        prefix = longest_common_prefix(pipeline for _, pipeline in group)
        if not prefix:
            continue
        ids = tuple(data_source_id for data_source_id, _ in group)
        prefix_pipeline = SplPipeline(commands=prefix)
        transforming = prefix[-1].name in TRANSFORMING_COMMANDS
        suffixes: dict[str, str] = {}
        for data_source_id, pipeline in group:
            suffix = pipeline.commands[len(prefix) :]
            suffixes[data_source_id] = (
                SplPipeline(commands=suffix).render(force_leading_pipe=True) if suffix else ""
            )
        candidates.append(
            OptimizationCandidate(
                candidate_ids=ids,
                eligible=transforming and all(suffixes.values()),
                common_prefix=prefix_pipeline.render(),
                suggested_base_id=f"ds_base_{ids[0].removeprefix('ds_')}",
                suggested_chain_queries=suffixes,
                confidence="high" if transforming and all(suffixes.values()) else "low",
                reasons=(
                    f"{len(ids)} searches share {len(prefix)} leading SPL commands",
                    "queryParameters, refresh, and refreshType are identical",
                ),
                risks=()
                if transforming and all(suffixes.values())
                else (
                    "The common prefix is not a transforming search or a child has no suffix; "
                    "do not apply automatically.",
                ),
            )
        )
    return SearchOptimizationPlan(
        applied=False,
        candidates=tuple(sorted(candidates, key=lambda candidate: candidate.candidate_ids)),
    )
