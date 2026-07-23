"""Packaged observability dashboard catalog and artifact generation."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Literal

from splunk_dashboard_studio._version import __version__
from splunk_dashboard_studio.contracts import (
    CatalogEntry,
    DashboardArtifactBundle,
    DashboardEvidenceManifest,
    ObservabilityFramework,
    PanelProvenance,
    SavedSearchSpec,
    TelemetryContract,
    TelemetryField,
    TelemetrySignal,
)
from splunk_dashboard_studio.generation import DashboardBuilder, canonical_json
from splunk_dashboard_studio.models import DashboardDefinition
from splunk_dashboard_studio.profiles import profile_for
from splunk_dashboard_studio.version import EnterpriseVersion, TargetPlatform

PORTABLE_TELEMETRY_CONTRACT_ID = "portable-observability-v1"


class CatalogEntryNotFound(ValueError):
    pass


class CatalogTargetUnsupported(ValueError):
    pass


def _field(
    name: str,
    signals: tuple[TelemetrySignal, ...],
    description: str,
    *,
    semantic_convention: str | None = None,
    unit: str | None = None,
) -> TelemetryField:
    return TelemetryField(
        name=name,
        signals=signals,
        description=description,
        semantic_convention=semantic_convention,
        unit=unit,
    )


_PORTABLE_TELEMETRY_CONTRACT = TelemetryContract(
    contract_id=PORTABLE_TELEMETRY_CONTRACT_ID,
    description=(
        "Portable normalized telemetry for the catalog. Semantic-convention names are used "
        "where stable; catalog-specific derived fields are explicitly identified."
    ),
    logical_indexes={
        "otel_metrics": TelemetrySignal.METRIC,
        "otel_logs": TelemetrySignal.LOG,
        "otel_traces": TelemetrySignal.TRACE,
        "platform_events": TelemetrySignal.EVENT,
        "batch_events": TelemetrySignal.EVENT,
        "cicd_events": TelemetrySignal.EVENT,
        "security_events": TelemetrySignal.EVENT,
        "business_events": TelemetrySignal.EVENT,
    },
    fields=(
        _field(
            "service.name",
            (TelemetrySignal.METRIC, TelemetrySignal.LOG, TelemetrySignal.TRACE),
            "Logical service identity.",
            semantic_convention="service.name",
        ),
        _field(
            "deployment.environment.name",
            (TelemetrySignal.METRIC, TelemetrySignal.LOG, TelemetrySignal.TRACE),
            "Deployment environment identity.",
            semantic_convention="deployment.environment.name",
        ),
        _field(
            "http.route",
            (TelemetrySignal.METRIC, TelemetrySignal.LOG, TelemetrySignal.TRACE),
            "Low-cardinality HTTP route template.",
            semantic_convention="http.route",
        ),
        _field(
            "http.request.method",
            (TelemetrySignal.LOG, TelemetrySignal.TRACE),
            "HTTP request method.",
            semantic_convention="http.request.method",
        ),
        _field(
            "http.response.status_code",
            (TelemetrySignal.LOG, TelemetrySignal.TRACE),
            "HTTP response status code.",
            semantic_convention="http.response.status_code",
        ),
        _field(
            "duration_ms",
            (TelemetrySignal.EVENT, TelemetrySignal.LOG, TelemetrySignal.TRACE),
            "Normalized operation duration in milliseconds.",
            unit="ms",
        ),
        _field(
            "trace_id",
            (TelemetrySignal.LOG, TelemetrySignal.TRACE),
            "Trace correlation identifier.",
            semantic_convention="trace_id",
        ),
        _field(
            "span_id",
            (TelemetrySignal.LOG, TelemetrySignal.TRACE),
            "Span correlation identifier.",
            semantic_convention="span_id",
        ),
        _field(
            "peer.service",
            (TelemetrySignal.LOG, TelemetrySignal.TRACE),
            "Normalized downstream dependency identity.",
        ),
        _field(
            "tenant.id",
            (TelemetrySignal.LOG,),
            "Pseudonymous tenant identity for aggregate traffic analysis.",
        ),
        _field(
            "k8s.namespace.name",
            (TelemetrySignal.METRIC, TelemetrySignal.LOG, TelemetrySignal.TRACE),
            "Kubernetes namespace identity.",
            semantic_convention="k8s.namespace.name",
        ),
        _field(
            "k8s.workload.name",
            (TelemetrySignal.METRIC, TelemetrySignal.LOG, TelemetrySignal.TRACE),
            "Normalized Kubernetes workload identity.",
        ),
        _field(
            "k8s.pod.name",
            (TelemetrySignal.METRIC, TelemetrySignal.LOG, TelemetrySignal.TRACE),
            "Kubernetes pod identity.",
            semantic_convention="k8s.pod.name",
        ),
        _field(
            "host.name",
            (TelemetrySignal.METRIC, TelemetrySignal.LOG),
            "Host identity.",
            semantic_convention="host.name",
        ),
        _field(
            "cloud.provider",
            (TelemetrySignal.METRIC, TelemetrySignal.EVENT),
            "Cloud provider identity.",
            semantic_convention="cloud.provider",
        ),
        _field(
            "cloud.region",
            (TelemetrySignal.METRIC, TelemetrySignal.EVENT),
            "Cloud region identity.",
            semantic_convention="cloud.region",
        ),
        _field(
            "cloud.availability_zone",
            (TelemetrySignal.METRIC, TelemetrySignal.EVENT),
            "Cloud availability-zone identity.",
            semantic_convention="cloud.availability_zone",
        ),
        _field(
            "db.system.name",
            (TelemetrySignal.METRIC, TelemetrySignal.LOG, TelemetrySignal.TRACE),
            "Database system identity.",
            semantic_convention="db.system.name",
        ),
        _field(
            "db.namespace",
            (TelemetrySignal.METRIC, TelemetrySignal.LOG, TelemetrySignal.TRACE),
            "Database namespace identity.",
            semantic_convention="db.namespace",
        ),
        _field(
            "db.operation.name",
            (TelemetrySignal.LOG, TelemetrySignal.TRACE),
            "Database operation name.",
            semantic_convention="db.operation.name",
        ),
        _field(
            "metric_name",
            (TelemetrySignal.METRIC,),
            "Normalized metric identity used by Splunk metric indexes.",
        ),
        _field(
            "job.name",
            (TelemetrySignal.EVENT,),
            "Batch or scheduled job identity.",
        ),
        _field(
            "job.status",
            (TelemetrySignal.EVENT,),
            "Normalized job outcome.",
        ),
        _field(
            "scheduled_time",
            (TelemetrySignal.EVENT,),
            "Expected execution time as an epoch value.",
            unit="s",
        ),
        _field(
            "queue.backlog",
            (TelemetrySignal.EVENT, TelemetrySignal.METRIC),
            "Pending work count.",
            unit="{item}",
        ),
        _field(
            "cicd.pipeline.name",
            (TelemetrySignal.EVENT,),
            "CI/CD pipeline identity.",
        ),
        _field(
            "cicd.job.name",
            (TelemetrySignal.EVENT,),
            "CI/CD job identity.",
        ),
        _field(
            "cicd.status",
            (TelemetrySignal.EVENT,),
            "Normalized CI/CD outcome.",
        ),
        _field(
            "change.type",
            (TelemetrySignal.EVENT,),
            "Deployment or delivery change category.",
        ),
        _field(
            "event.name",
            (TelemetrySignal.EVENT, TelemetrySignal.LOG),
            "Normalized event identity.",
            semantic_convention="event.name",
        ),
        _field(
            "security.severity",
            (TelemetrySignal.EVENT,),
            "Normalized security severity.",
        ),
        _field(
            "detection.name",
            (TelemetrySignal.EVENT,),
            "Security detection identity.",
        ),
        _field(
            "risk.score",
            (TelemetrySignal.EVENT,),
            "Normalized security risk score.",
        ),
        _field(
            "ingest_lag_seconds",
            (TelemetrySignal.EVENT,),
            "Telemetry ingestion delay.",
            unit="s",
        ),
        _field(
            "business.journey.name",
            (TelemetrySignal.EVENT,),
            "Business journey identity.",
        ),
        _field(
            "business.outcome",
            (TelemetrySignal.EVENT,),
            "Normalized journey outcome.",
        ),
        _field(
            "business.value",
            (TelemetrySignal.EVENT,),
            "Optional numeric journey value.",
        ),
    ),
    notes=(
        "Metric names referenced in SPL are normalized names, not a promise that every "
        "upstream collector emits them without mapping.",
        "Fields without semantic_convention are catalog-level normalization requirements.",
        "Logical index names are deployment-time aliases and may be mapped to local indexes.",
    ),
)


@dataclass(frozen=True)
class _PanelSpec:
    slug: str
    title: str
    purpose: str
    query: str
    visualization_type: str
    frameworks: tuple[ObservabilityFramework, ...]
    signals: tuple[TelemetrySignal, ...]
    required_fields: tuple[str, ...]
    drilldown_signals: tuple[TelemetrySignal, ...] = ()


@dataclass(frozen=True)
class _DashboardSpec:
    example_id: str
    priority: Literal["high", "medium"]
    title: str
    description: str
    minimum_target: str
    frameworks: tuple[ObservabilityFramework, ...]
    signals: tuple[TelemetrySignal, ...]
    logical_indexes: tuple[str, ...]
    panels: tuple[_PanelSpec, ...]
    saved_searches: tuple[SavedSearchSpec, ...] = ()
    tags: tuple[str, ...] = ()


def _panel(
    slug: str,
    title: str,
    purpose: str,
    query: str,
    visualization_type: str,
    frameworks: tuple[ObservabilityFramework, ...],
    signals: tuple[TelemetrySignal, ...],
    required_fields: tuple[str, ...],
    *,
    drilldown_signals: tuple[TelemetrySignal, ...] = (),
) -> _PanelSpec:
    return _PanelSpec(
        slug=slug,
        title=title,
        purpose=purpose,
        query=query,
        visualization_type=visualization_type,
        frameworks=frameworks,
        signals=signals,
        required_fields=required_fields,
        drilldown_signals=drilldown_signals,
    )


RED = (ObservabilityFramework.RED,)
USE = (ObservabilityFramework.USE,)
GOLDEN = (ObservabilityFramework.FOUR_GOLDEN_SIGNALS,)
SLO = (ObservabilityFramework.SLI_SLO,)


_SPECS = (
    _DashboardSpec(
        example_id="kubernetes_workload_health",
        priority="high",
        title="Kubernetes Workload Health",
        description="Namespace and workload RED signals with pod-level resource saturation.",
        minimum_target="9.4.3",
        frameworks=(ObservabilityFramework.RED, ObservabilityFramework.USE),
        signals=(TelemetrySignal.METRIC, TelemetrySignal.LOG, TelemetrySignal.TRACE),
        logical_indexes=("otel_metrics", "otel_logs", "otel_traces"),
        panels=(
            _panel(
                "workload_error_rate",
                "Workload error rate",
                "Identify workloads whose request failures are rising.",
                "index=otel_logs k8s.namespace.name=* | stats count AS requests "
                "count(eval(http.response.status_code>=500)) AS errors by "
                "k8s.namespace.name k8s.workload.name | eval value=round(errors*100/requests,2)",
                "splunk.singlevalue",
                RED,
                (TelemetrySignal.LOG,),
                ("k8s.namespace.name", "k8s.workload.name", "http.response.status_code"),
                drilldown_signals=(TelemetrySignal.TRACE,),
            ),
            _panel(
                "workload_p95_latency",
                "Workload p95 latency",
                "Track user-visible workload latency over time.",
                "index=otel_traces k8s.namespace.name=* | timechart span=5m "
                "perc95(duration_ms) AS p95_ms by k8s.workload.name",
                "splunk.line",
                RED,
                (TelemetrySignal.TRACE,),
                ("k8s.namespace.name", "k8s.workload.name", "duration_ms"),
                drilldown_signals=(TelemetrySignal.LOG,),
            ),
            _panel(
                "pod_restarts",
                "Pod restarts",
                "Surface unstable pods and workload churn.",
                "| mstats sum(_value) AS restarts WHERE index=otel_metrics "
                'metric_name="k8s.pod.restart.count" BY k8s.namespace.name k8s.pod.name span=5m',
                "splunk.line",
                USE,
                (TelemetrySignal.METRIC,),
                ("metric_name", "k8s.namespace.name", "k8s.pod.name"),
            ),
            _panel(
                "resource_saturation",
                "CPU and memory saturation",
                "Locate pods approaching resource limits.",
                "| mstats max(_value) AS saturation WHERE index=otel_metrics "
                'metric_name IN ("k8s.container.cpu.utilization",'
                '"k8s.container.memory.utilization") BY metric_name k8s.pod.name span=5m',
                "splunk.line",
                USE,
                (TelemetrySignal.METRIC,),
                ("metric_name", "k8s.pod.name"),
            ),
            _panel(
                "failing_pods",
                "Top failing pods",
                "Rank pods emitting the most error events.",
                "index=otel_logs k8s.pod.name=* http.response.status_code>=500 "
                "| stats count AS failures by k8s.namespace.name k8s.pod.name "
                "| sort - failures | head 20",
                "splunk.table",
                RED,
                (TelemetrySignal.LOG,),
                ("k8s.namespace.name", "k8s.pod.name", "http.response.status_code"),
                drilldown_signals=(TelemetrySignal.TRACE,),
            ),
        ),
        tags=("kubernetes", "platform", "red", "use"),
    ),
    _DashboardSpec(
        example_id="ec2_host_capacity",
        priority="high",
        title="EC2 and Host Capacity",
        description="USE-oriented host and autoscaling capacity overview.",
        minimum_target="9.4.3",
        frameworks=(ObservabilityFramework.USE,),
        signals=(TelemetrySignal.METRIC, TelemetrySignal.LOG),
        logical_indexes=("otel_metrics", "otel_logs", "platform_events"),
        panels=(
            _panel(
                "host_cpu",
                "CPU utilization",
                "Track sustained host CPU utilization.",
                "| mstats avg(_value) AS utilization WHERE index=otel_metrics "
                'metric_name="system.cpu.utilization" BY host.name span=5m',
                "splunk.line",
                USE,
                (TelemetrySignal.METRIC,),
                ("metric_name", "host.name"),
            ),
            _panel(
                "host_memory",
                "Memory utilization",
                "Find hosts with memory pressure.",
                "| mstats max(_value) AS utilization WHERE index=otel_metrics "
                'metric_name="system.memory.utilization" BY host.name span=5m',
                "splunk.line",
                USE,
                (TelemetrySignal.METRIC,),
                ("metric_name", "host.name"),
            ),
            _panel(
                "host_disk",
                "Disk utilization",
                "Identify full or rapidly filling filesystems.",
                "| mstats max(_value) AS utilization WHERE index=otel_metrics "
                'metric_name="system.filesystem.utilization" BY host.name span=5m',
                "splunk.line",
                USE,
                (TelemetrySignal.METRIC,),
                ("metric_name", "host.name"),
            ),
            _panel(
                "host_network_load",
                "Network and load",
                "Compare network throughput with system load.",
                "| mstats avg(_value) AS value WHERE index=otel_metrics metric_name IN "
                '("system.network.io","system.cpu.load_average.15m") '
                "BY metric_name host.name span=5m",
                "splunk.line",
                USE,
                (TelemetrySignal.METRIC,),
                ("metric_name", "host.name"),
            ),
            _panel(
                "host_errors",
                "Host errors",
                "Rank hosts by operating-system and agent errors.",
                "index=otel_logs host.name=* event.name=*error* | stats count AS errors "
                "by host.name event.name | sort - errors | head 20",
                "splunk.table",
                USE,
                (TelemetrySignal.LOG,),
                ("host.name", "event.name"),
            ),
        ),
        tags=("aws", "ec2", "hosts", "capacity", "use"),
    ),
    _DashboardSpec(
        example_id="rds_database_health",
        priority="high",
        title="RDS and Database Health",
        description="Database latency, concurrency, errors, and storage pressure.",
        minimum_target="9.4.3",
        frameworks=(ObservabilityFramework.RED, ObservabilityFramework.USE),
        signals=(TelemetrySignal.METRIC, TelemetrySignal.LOG, TelemetrySignal.TRACE),
        logical_indexes=("otel_metrics", "otel_logs", "otel_traces"),
        panels=(
            _panel(
                "database_latency",
                "Operation p95 latency",
                "Track slow database operations by namespace.",
                "index=otel_traces db.system.name=* | timechart span=5m "
                "perc95(duration_ms) AS p95_ms by db.namespace",
                "splunk.line",
                RED,
                (TelemetrySignal.TRACE,),
                ("db.system.name", "db.namespace", "duration_ms"),
                drilldown_signals=(TelemetrySignal.LOG,),
            ),
            _panel(
                "database_connections",
                "Connection utilization",
                "Find databases approaching connection limits.",
                "| mstats max(_value) AS connections WHERE index=otel_metrics "
                'metric_name="db.client.connections.usage" BY db.system.name db.namespace span=5m',
                "splunk.line",
                USE,
                (TelemetrySignal.METRIC,),
                ("metric_name", "db.system.name", "db.namespace"),
            ),
            _panel(
                "database_locks",
                "Lock pressure",
                "Surface lock waits and contention.",
                "| mstats max(_value) AS lock_waits WHERE index=otel_metrics "
                'metric_name="db.lock.waits" BY db.system.name db.namespace span=5m',
                "splunk.line",
                USE,
                (TelemetrySignal.METRIC,),
                ("metric_name", "db.system.name", "db.namespace"),
            ),
            _panel(
                "database_storage",
                "Storage pressure",
                "Track remaining storage and write pressure.",
                "| mstats min(_value) AS remaining WHERE index=otel_metrics "
                'metric_name="db.storage.remaining" BY db.system.name db.namespace span=5m',
                "splunk.line",
                USE,
                (TelemetrySignal.METRIC,),
                ("metric_name", "db.system.name", "db.namespace"),
            ),
            _panel(
                "replication_lag",
                "Replication lag",
                "Detect replicas falling behind primary databases.",
                "| mstats max(_value) AS lag_seconds WHERE index=otel_metrics "
                'metric_name="db.replication.lag" BY db.system.name db.namespace span=5m',
                "splunk.line",
                USE,
                (TelemetrySignal.METRIC,),
                ("metric_name", "db.system.name", "db.namespace"),
            ),
        ),
        saved_searches=(
            SavedSearchSpec(
                reference="Platform - Database Health Rollup",
                purpose="Precompute shared database health aggregates for high-viewer dashboards.",
                rationale="Scheduled aggregation avoids one expensive trace query per viewer.",
                recommended_schedule="*/5 * * * *",
                source_indexes=("otel_metrics", "otel_traces"),
            ),
        ),
        tags=("aws", "rds", "database", "red", "use"),
    ),
    _DashboardSpec(
        example_id="load_balancer_edge_health",
        priority="high",
        title="Load Balancer Edge Health",
        description="Four Golden Signals for ingress and backend target health.",
        minimum_target="9.4.3",
        frameworks=(ObservabilityFramework.FOUR_GOLDEN_SIGNALS,),
        signals=(TelemetrySignal.LOG, TelemetrySignal.METRIC),
        logical_indexes=("otel_logs", "otel_metrics"),
        panels=(
            _panel(
                "edge_traffic",
                "Request traffic",
                "Track ingress demand over time.",
                "index=otel_logs service.name=load-balancer | timechart span=5m count AS requests",
                "splunk.line",
                GOLDEN,
                (TelemetrySignal.LOG,),
                ("service.name",),
            ),
            _panel(
                "edge_errors",
                "4xx and 5xx rate",
                "Separate client and server failure rates.",
                "index=otel_logs service.name=load-balancer | timechart span=5m "
                "count(eval(http.response.status_code>=400 AND "
                "http.response.status_code<500)) AS 4xx "
                "count(eval(http.response.status_code>=500)) AS 5xx",
                "splunk.line",
                GOLDEN,
                (TelemetrySignal.LOG,),
                ("service.name", "http.response.status_code"),
            ),
            _panel(
                "edge_latency",
                "p95 and p99 latency",
                "Track tail latency at the edge.",
                "index=otel_logs service.name=load-balancer | timechart span=5m "
                "perc95(duration_ms) AS p95_ms perc99(duration_ms) AS p99_ms",
                "splunk.line",
                GOLDEN,
                (TelemetrySignal.LOG,),
                ("service.name", "duration_ms"),
            ),
            _panel(
                "backend_failures",
                "Backend target failures",
                "Rank unhealthy backend services.",
                "index=otel_logs service.name=load-balancer http.response.status_code>=500 "
                "| stats count AS failures by peer.service | sort - failures | head 20",
                "splunk.table",
                GOLDEN,
                (TelemetrySignal.LOG,),
                ("service.name", "http.response.status_code", "peer.service"),
            ),
            _panel(
                "edge_saturation",
                "Capacity saturation",
                "Show active connection pressure.",
                "| mstats max(_value) AS saturation WHERE index=otel_metrics "
                'metric_name="http.server.active_requests" BY service.name span=5m',
                "splunk.line",
                GOLDEN,
                (TelemetrySignal.METRIC,),
                ("metric_name", "service.name"),
            ),
        ),
        tags=("load-balancer", "edge", "golden-signals"),
    ),
    _DashboardSpec(
        example_id="api_gateway_overview",
        priority="high",
        title="API Gateway Overview",
        description="Route and tenant RED signals with authentication and throttling health.",
        minimum_target="9.4.3",
        frameworks=(ObservabilityFramework.RED,),
        signals=(TelemetrySignal.LOG, TelemetrySignal.TRACE),
        logical_indexes=("otel_logs", "otel_traces"),
        panels=(
            _panel(
                "route_red",
                "Route RED summary",
                "Compare request volume, failures, and latency by route.",
                "index=otel_logs service.name=api-gateway | stats count AS requests "
                "count(eval(http.response.status_code>=500)) AS errors "
                "perc95(duration_ms) AS p95_ms by http.route",
                "splunk.table",
                RED,
                (TelemetrySignal.LOG,),
                ("service.name", "http.route", "http.response.status_code", "duration_ms"),
                drilldown_signals=(TelemetrySignal.TRACE,),
            ),
            _panel(
                "authentication_failures",
                "Authentication failures",
                "Track rejected authentication events by route.",
                "index=otel_logs service.name=api-gateway event.name=auth.failure "
                "| timechart span=5m count AS failures by http.route",
                "splunk.line",
                RED,
                (TelemetrySignal.LOG,),
                ("service.name", "event.name", "http.route"),
            ),
            _panel(
                "throttling",
                "Throttled requests",
                "Detect routes constrained by rate limits.",
                "index=otel_logs service.name=api-gateway http.response.status_code=429 "
                "| timechart span=5m count AS throttled by http.route",
                "splunk.line",
                RED,
                (TelemetrySignal.LOG,),
                ("service.name", "http.response.status_code", "http.route"),
            ),
            _panel(
                "top_tenants",
                "Top tenants",
                "Rank tenant traffic without exposing raw user identifiers.",
                "index=otel_logs service.name=api-gateway tenant.id=* "
                "| stats count AS requests by tenant.id | sort - requests | head 20",
                "splunk.table",
                RED,
                (TelemetrySignal.LOG,),
                ("service.name", "tenant.id"),
            ),
            _panel(
                "latency_distribution",
                "Latency distribution",
                "Inspect route-level latency percentiles.",
                "index=otel_traces service.name=api-gateway | stats perc50(duration_ms) AS p50_ms "
                "perc95(duration_ms) AS p95_ms perc99(duration_ms) AS p99_ms by http.route",
                "splunk.table",
                RED,
                (TelemetrySignal.TRACE,),
                ("service.name", "duration_ms", "http.route"),
                drilldown_signals=(TelemetrySignal.LOG,),
            ),
        ),
        tags=("api", "gateway", "red"),
    ),
    _DashboardSpec(
        example_id="microservice_service_map",
        priority="high",
        title="Microservice Service Map",
        description="Service RED health, dependency hotspots, changes, and trace drill-through.",
        minimum_target="10.4.0",
        frameworks=(ObservabilityFramework.RED, ObservabilityFramework.FOUR_GOLDEN_SIGNALS),
        signals=(
            TelemetrySignal.METRIC,
            TelemetrySignal.EVENT,
            TelemetrySignal.LOG,
            TelemetrySignal.TRACE,
        ),
        logical_indexes=("otel_metrics", "otel_logs", "otel_traces", "platform_events"),
        panels=(
            _panel(
                "service_red",
                "Service RED summary",
                "Compare request health across services.",
                "index=otel_traces service.name=* | stats count AS requests "
                "count(eval(http.response.status_code>=500)) AS errors "
                "perc95(duration_ms) AS p95_ms by service.name",
                "splunk.table",
                RED,
                (TelemetrySignal.TRACE,),
                ("service.name", "http.response.status_code", "duration_ms"),
                drilldown_signals=(TelemetrySignal.LOG,),
            ),
            _panel(
                "dependency_map",
                "Dependency map",
                "Show request flow between instrumented services.",
                "index=otel_traces service.name=* peer.service=* | stats count AS value "
                "by service.name peer.service | rename service.name AS source "
                "peer.service AS target",
                "splunk.networkGraph",
                GOLDEN,
                (TelemetrySignal.TRACE,),
                ("service.name", "peer.service"),
                drilldown_signals=(TelemetrySignal.LOG,),
            ),
            _panel(
                "dependency_hotspots",
                "Dependency hotspots",
                "Rank slow and failing downstream dependencies.",
                "index=otel_traces peer.service=* | stats perc95(duration_ms) AS p95_ms "
                "count(eval(http.response.status_code>=500)) AS errors "
                "by service.name peer.service "
                "| sort - p95_ms | head 20",
                "splunk.table",
                RED,
                (TelemetrySignal.TRACE,),
                ("service.name", "peer.service", "duration_ms", "http.response.status_code"),
            ),
            _panel(
                "recent_deployments",
                "Recent deployments",
                "Correlate service health with recent changes.",
                "index=platform_events change.type=deployment service.name=* "
                "| table _time service.name deployment.environment.name change.type | sort - _time",
                "splunk.table",
                GOLDEN,
                (TelemetrySignal.EVENT,),
                ("service.name", "deployment.environment.name", "change.type"),
            ),
            _panel(
                "trace_samples",
                "Slow trace samples",
                "Provide trace identifiers for deep diagnosis.",
                "index=otel_traces service.name=* | sort - duration_ms "
                "| table _time service.name trace_id span_id duration_ms http.route | head 50",
                "splunk.table",
                RED,
                (TelemetrySignal.TRACE,),
                ("service.name", "trace_id", "span_id", "duration_ms", "http.route"),
                drilldown_signals=(TelemetrySignal.LOG,),
            ),
        ),
        tags=("microservices", "service-map", "traces", "red"),
    ),
    _DashboardSpec(
        example_id="batch_cron_reliability",
        priority="medium",
        title="Batch and Cron Reliability",
        description="Schedule adherence, duration, backlog, failures, and freshness.",
        minimum_target="9.4.3",
        frameworks=(ObservabilityFramework.RED, ObservabilityFramework.SLI_SLO),
        signals=(TelemetrySignal.EVENT,),
        logical_indexes=("batch_events",),
        panels=(
            _panel(
                "schedule_adherence",
                "Schedule adherence",
                "Find jobs that start materially after their schedules.",
                "index=batch_events job.name=* | eval delay_seconds=_time-scheduled_time "
                "| stats perc95(delay_seconds) AS p95_delay_seconds by job.name",
                "splunk.table",
                SLO,
                (TelemetrySignal.EVENT,),
                ("job.name", "scheduled_time"),
            ),
            _panel(
                "job_duration",
                "Job duration",
                "Track duration regressions by job.",
                "index=batch_events job.name=* | timechart span=1h perc95(duration_ms) AS p95_ms "
                "by job.name",
                "splunk.line",
                RED,
                (TelemetrySignal.EVENT,),
                ("job.name", "duration_ms"),
            ),
            _panel(
                "job_backlog",
                "Queue backlog",
                "Detect pending work accumulation.",
                "index=batch_events queue.backlog=* | timechart span=5m "
                "max(queue.backlog) AS backlog "
                "by job.name",
                "splunk.line",
                RED,
                (TelemetrySignal.EVENT,),
                ("job.name", "queue.backlog"),
            ),
            _panel(
                "job_failures",
                "Job failures",
                "Rank recurring job failures.",
                "index=batch_events job.status=failure | stats count AS failures by job.name "
                "| sort - failures | head 20",
                "splunk.table",
                RED,
                (TelemetrySignal.EVENT,),
                ("job.name", "job.status"),
            ),
            _panel(
                "job_freshness",
                "Job freshness",
                "Show elapsed time since each job last succeeded.",
                "index=batch_events job.status=success "
                "| stats latest(_time) AS last_success by job.name "
                "| eval freshness_seconds=now()-last_success | sort - freshness_seconds",
                "splunk.table",
                SLO,
                (TelemetrySignal.EVENT,),
                ("job.name", "job.status"),
            ),
        ),
        tags=("batch", "cron", "freshness", "slo"),
    ),
    _DashboardSpec(
        example_id="cicd_delivery_health",
        priority="medium",
        title="CI/CD Delivery Health",
        description="Delivery lead time, reliability, queueing, flaky jobs, and rollback signals.",
        minimum_target="9.4.3",
        frameworks=(ObservabilityFramework.RED, ObservabilityFramework.SLI_SLO),
        signals=(TelemetrySignal.EVENT,),
        logical_indexes=("cicd_events", "platform_events"),
        panels=(
            _panel(
                "delivery_lead_time",
                "Delivery lead time",
                "Track time from accepted change to production deployment.",
                "index=cicd_events event.name=deployment.completed "
                "| timechart span=1d perc95(duration_ms) AS p95_lead_time_ms",
                "splunk.line",
                SLO,
                (TelemetrySignal.EVENT,),
                ("event.name", "duration_ms"),
            ),
            _panel(
                "pipeline_failures",
                "Pipeline failure rate",
                "Compare failed and total pipeline runs.",
                "index=cicd_events cicd.pipeline.name=* | timechart span=1h count AS runs "
                'count(eval(cicd.status="failure")) AS failures by cicd.pipeline.name',
                "splunk.line",
                RED,
                (TelemetrySignal.EVENT,),
                ("cicd.pipeline.name", "cicd.status"),
            ),
            _panel(
                "flaky_jobs",
                "Flaky jobs",
                "Rank jobs alternating between pass and fail outcomes.",
                "index=cicd_events cicd.job.name=* | stats dc(cicd.status) AS outcomes "
                'count(eval(cicd.status="failure")) AS failures by cicd.job.name '
                "| where outcomes>1 | sort - failures | head 20",
                "splunk.table",
                RED,
                (TelemetrySignal.EVENT,),
                ("cicd.job.name", "cicd.status"),
            ),
            _panel(
                "pipeline_queue_time",
                "Queue time",
                "Track delivery-system saturation before jobs start.",
                "index=cicd_events event.name=job.started | timechart span=1h "
                "perc95(duration_ms) AS p95_queue_ms by cicd.pipeline.name",
                "splunk.line",
                RED,
                (TelemetrySignal.EVENT,),
                ("event.name", "duration_ms", "cicd.pipeline.name"),
            ),
            _panel(
                "deployment_rollbacks",
                "Deployment rollbacks",
                "Correlate rollback frequency with services and environments.",
                "index=platform_events change.type=rollback | stats count AS rollbacks "
                "by service.name deployment.environment.name | sort - rollbacks",
                "splunk.table",
                SLO,
                (TelemetrySignal.EVENT,),
                ("change.type", "service.name", "deployment.environment.name"),
            ),
        ),
        saved_searches=(
            SavedSearchSpec(
                reference="Platform - CI CD Delivery Rollup",
                purpose="Precompute daily delivery and change-failure indicators.",
                rationale="Cross-event lead-time calculations are expensive and widely shared.",
                recommended_schedule="15 * * * *",
                source_indexes=("cicd_events", "platform_events"),
            ),
        ),
        tags=("cicd", "delivery", "dora", "slo"),
    ),
    _DashboardSpec(
        example_id="security_operations_overview",
        priority="medium",
        title="Security Operations Overview",
        description="Authentication failures, risk, noisy detections, and ingestion health.",
        minimum_target="9.4.3",
        frameworks=(ObservabilityFramework.FOUR_GOLDEN_SIGNALS,),
        signals=(TelemetrySignal.EVENT,),
        logical_indexes=("security_events", "platform_events"),
        panels=(
            _panel(
                "auth_failures",
                "Authentication failures",
                "Track authentication failure volume without exposing user values.",
                "index=security_events event.name=authentication.failure "
                "| timechart span=5m count AS failures by security.severity",
                "splunk.line",
                GOLDEN,
                (TelemetrySignal.EVENT,),
                ("event.name", "detection.name", "security.severity"),
            ),
            _panel(
                "high_risk_events",
                "High-risk events",
                "Rank current high-risk security signals.",
                "index=security_events risk.score>=70 "
                "| stats count AS events max(risk.score) AS risk "
                "by event.name security.severity | sort - risk | head 20",
                "splunk.table",
                GOLDEN,
                (TelemetrySignal.EVENT,),
                ("risk.score", "event.name", "security.severity"),
            ),
            _panel(
                "noisy_detections",
                "Noisy detections",
                "Find detections producing disproportionate volume.",
                "index=security_events event.name=detection.triggered "
                "| stats count AS triggers by detection.name security.severity "
                "| sort - triggers | head 20",
                "splunk.table",
                GOLDEN,
                (TelemetrySignal.EVENT,),
                ("event.name", "security.severity"),
            ),
            _panel(
                "ingestion_lag",
                "Ingestion lag",
                "Detect delayed security telemetry.",
                "index=security_events ingest_lag_seconds=* | timechart span=5m "
                "perc95(ingest_lag_seconds) AS p95_lag_seconds",
                "splunk.line",
                GOLDEN,
                (TelemetrySignal.EVENT,),
                ("ingest_lag_seconds",),
            ),
            _panel(
                "security_platform_health",
                "Security platform health",
                "Track collection and detection pipeline errors.",
                "index=platform_events event.name=security.pipeline.error "
                "| stats count AS errors by service.name | sort - errors",
                "splunk.table",
                GOLDEN,
                (TelemetrySignal.EVENT,),
                ("event.name", "service.name"),
            ),
        ),
        tags=("security", "soc", "risk", "platform-health"),
    ),
    _DashboardSpec(
        example_id="business_journey_slo",
        priority="medium",
        title="Business Journey and SLO",
        description="User-journey success, latency, abandonment, freshness, and error-budget burn.",
        minimum_target="9.4.3",
        frameworks=(ObservabilityFramework.SLI_SLO, ObservabilityFramework.RED),
        signals=(TelemetrySignal.EVENT, TelemetrySignal.TRACE),
        logical_indexes=("business_events", "otel_traces"),
        panels=(
            _panel(
                "journey_success",
                "Journey success rate",
                "Measure whether users complete the intended journey.",
                "index=business_events business.journey.name=* | stats count AS attempts "
                'count(eval(business.outcome="success")) AS successes by business.journey.name '
                "| eval value=round(successes*100/attempts,2)",
                "splunk.singlevalue",
                SLO,
                (TelemetrySignal.EVENT,),
                ("business.journey.name", "business.outcome"),
                drilldown_signals=(TelemetrySignal.TRACE,),
            ),
            _panel(
                "journey_latency",
                "Journey p95 latency",
                "Track customer-perceived journey duration.",
                "index=business_events business.journey.name=* | timechart span=5m "
                "perc95(duration_ms) AS p95_ms by business.journey.name",
                "splunk.line",
                SLO,
                (TelemetrySignal.EVENT,),
                ("business.journey.name", "duration_ms"),
            ),
            _panel(
                "journey_abandonment",
                "Journey abandonment",
                "Measure journeys that start but do not complete.",
                "index=business_events business.outcome=abandoned "
                "| timechart span=5m count AS abandoned by business.journey.name",
                "splunk.line",
                SLO,
                (TelemetrySignal.EVENT,),
                ("business.journey.name", "business.outcome"),
            ),
            _panel(
                "business_freshness",
                "Business event freshness",
                "Detect stale or interrupted journey telemetry.",
                "index=business_events business.journey.name=* "
                "| stats latest(_time) AS latest_event by business.journey.name "
                "| eval freshness_seconds=now()-latest_event | sort - freshness_seconds",
                "splunk.table",
                SLO,
                (TelemetrySignal.EVENT,),
                ("business.journey.name",),
            ),
            _panel(
                "error_budget_burn",
                "Error-budget burn",
                "Compare observed journey failures with the declared SLO budget.",
                "index=business_events business.journey.name=* "
                "| bin _time span=5m | stats count AS attempts "
                'count(eval(business.outcome!="success")) AS failures '
                "by _time business.journey.name "
                "| eval burn_rate=(failures/attempts)/0.001",
                "splunk.line",
                SLO,
                (TelemetrySignal.EVENT,),
                ("business.journey.name", "business.outcome"),
            ),
        ),
        saved_searches=(
            SavedSearchSpec(
                reference="Platform - Business Journey SLO Rollup",
                purpose="Precompute shared journey SLIs and error-budget windows.",
                rationale="Multi-window burn rates should be consistent across viewers and alerts.",
                recommended_schedule="*/5 * * * *",
                source_indexes=("business_events",),
            ),
        ),
        tags=("business", "journey", "sli", "slo", "error-budget"),
    ),
)


def portable_telemetry_contract() -> TelemetryContract:
    """Return the immutable portable telemetry contract used by every example."""

    return _PORTABLE_TELEMETRY_CONTRACT


def _provenance(panel: _PanelSpec) -> PanelProvenance:
    return PanelProvenance(
        panel_id=f"viz_{panel.slug}",
        purpose=panel.purpose,
        frameworks=panel.frameworks,
        signals=panel.signals,
        data_source_ids=(f"ds_{panel.slug}",),
        required_fields=panel.required_fields,
        drilldown_signals=panel.drilldown_signals,
    )


def _entry(spec: _DashboardSpec) -> CatalogEntry:
    return CatalogEntry(
        example_id=spec.example_id,
        priority=spec.priority,
        title=spec.title,
        description=spec.description,
        minimum_target=EnterpriseVersion.parse(spec.minimum_target),
        telemetry_contract=PORTABLE_TELEMETRY_CONTRACT_ID,
        frameworks=spec.frameworks,
        signals=spec.signals,
        logical_indexes=spec.logical_indexes,
        required_fields=tuple(
            sorted({field for panel in spec.panels for field in panel.required_fields})
        ),
        panels=tuple(_provenance(panel) for panel in spec.panels),
        saved_searches=spec.saved_searches,
        tags=spec.tags,
    )


_ENTRIES = tuple(_entry(spec) for spec in _SPECS)
_SPECS_BY_ID = {spec.example_id: spec for spec in _SPECS}
_ENTRIES_BY_ID = {entry.example_id: entry for entry in _ENTRIES}


def catalog_entries() -> tuple[CatalogEntry, ...]:
    """Return deterministic catalog metadata in documented priority order."""

    return _ENTRIES


def _resolve(example_id: str) -> tuple[_DashboardSpec, CatalogEntry]:
    spec = _SPECS_BY_ID.get(example_id)
    entry = _ENTRIES_BY_ID.get(example_id)
    if spec is None or entry is None:
        available = ", ".join(entry.example_id for entry in catalog_entries())
        raise CatalogEntryNotFound(
            f"Unknown catalog dashboard {example_id!r}; available dashboards: {available}"
        )
    return spec, entry


def _target(target: TargetPlatform | str) -> TargetPlatform:
    return target if isinstance(target, TargetPlatform) else TargetPlatform.enterprise(target)


def build_catalog_dashboard(
    example_id: str,
    target: TargetPlatform | str,
) -> DashboardDefinition:
    """Build one catalog dashboard for an explicitly supported Enterprise target."""

    spec, entry = _resolve(example_id)
    platform = _target(target)
    profile_for(platform)
    if platform.version < entry.minimum_target:
        raise CatalogTargetUnsupported(
            f"Catalog dashboard {example_id!r} requires Splunk Enterprise "
            f"{entry.minimum_target} or newer; received {platform.version}"
        )

    builder = DashboardBuilder(
        title=spec.title,
        description=spec.description,
        target=platform,
    )
    builder.add_input(
        "input.timerange",
        name="Global Time Range",
        input_id="input_global_time",
        title="Global Time Range",
        options={"token": "global_time", "defaultValue": "-24h@h,now"},
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
    builder.set_application_property("collapseNavigation", False)
    builder.set_application_property("downsampleVisualizations", True)

    for panel in spec.panels:
        data_source_id = builder.add_search(
            panel.query,
            name=panel.title,
            data_source_id=f"ds_{panel.slug}",
            earliest=None,
            latest=None,
        )
        builder.add_visualization(
            panel.visualization_type,
            name=panel.title,
            visualization_id=f"viz_{panel.slug}",
            data_sources={"primary": data_source_id},
            title=panel.title,
            description=panel.purpose,
        )
    return builder.build(canvas_width=1440)


def build_catalog_bundle(
    example_id: str,
    target: TargetPlatform | str,
) -> DashboardArtifactBundle:
    """Build one canonical definition with honest native and engine evidence metadata."""

    _, entry = _resolve(example_id)
    platform = _target(target)
    definition = build_catalog_dashboard(example_id, platform)
    encoded = canonical_json(definition).encode("utf-8")
    engine = profile_for(platform).engine
    manifest = DashboardEvidenceManifest(
        example_id=example_id,
        target=platform,
        minimum_target=entry.minimum_target,
        generator_version=__version__,
        telemetry_contract=entry.telemetry_contract,
        definition_sha256=hashlib.sha256(encoded).hexdigest(),
        canonical_json_bytes=len(encoded),
        official_engine_id=engine.engine_id,
        official_engine_version=engine.dashboard_version,
        engine_evidence=engine.evidence,
        panels=entry.panels,
        saved_searches=entry.saved_searches,
        assumptions=(
            "Logical index names are mapped by the deploying Splunk Enterprise app.",
            "Official NPM validation is performed in CI and is not claimed by this generated file.",
            "Live Splunk REST ingestion and readback remain deferred.",
        ),
    )
    return DashboardArtifactBundle(definition=definition, manifest=manifest)
