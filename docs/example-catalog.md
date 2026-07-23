# Observability example catalog

The v0.2 catalog compiles ten operational dashboards from one
`portable-observability-v1` telemetry contract. Every dashboard uses SPL1, a global `-24h@h,now`
time input, centralized `ds.search` query parameters, no automatic refresh, no external assets, and
a deterministic 1440-pixel two-column layout.

| Catalog ID | Minimum target | Frameworks | Operational focus |
|---|---:|---|---|
| `kubernetes_workload_health` | 9.4.3 | RED, USE | Error rate, p95 latency, restarts, CPU/memory saturation, failing pods |
| `ec2_host_capacity` | 9.4.3 | USE | CPU, memory, disk, network/load, host errors |
| `rds_database_health` | 9.4.3 | RED, USE | Operation latency, connections, locks, storage, replication lag |
| `load_balancer_edge_health` | 9.4.3 | Four Golden Signals | Traffic, 4xx/5xx, p95/p99, backend failures, saturation |
| `api_gateway_overview` | 9.4.3 | RED | Route health, authentication, throttling, tenants, latency distribution |
| `microservice_service_map` | 10.4.0 | RED, Four Golden Signals | Service health, network graph, dependency hotspots, deploys, traces |
| `batch_cron_reliability` | 9.4.3 | RED, SLI/SLO | Schedule adherence, duration, backlog, failure, freshness |
| `cicd_delivery_health` | 9.4.3 | RED, SLI/SLO | Lead time, failures, flakiness, queue time, rollbacks |
| `security_operations_overview` | 9.4.3 | Four Golden Signals | Authentication, risk, noisy detections, ingestion and platform health |
| `business_journey_slo` | 9.4.3 | SLI/SLO, RED | Success, latency, abandonment, freshness, error-budget burn |

## Logical data sources

The contract declares these deployment-time logical indexes:

- `otel_metrics`, `otel_logs`, and `otel_traces`;
- `platform_events`;
- `batch_events` and `cicd_events`;
- `security_events`; and
- `business_events`.

Fields use OpenTelemetry semantic-convention names where stable, including `service.name`,
`deployment.environment.name`, `http.route`, `http.response.status_code`, Kubernetes resource
attributes, host attributes, and database attributes. Derived names such as `duration_ms`,
`business.outcome`, and `ingest_lag_seconds` are explicitly catalog-level normalization
requirements. Inspect the machine-readable contract with `splunk-studio catalog list`.

## Build and inspect

```console
uv run splunk-studio catalog list
uv run splunk-studio catalog build api_gateway_overview --target 10.2.0
uv run splunk-studio catalog build business_journey_slo \
  --target 9.4.3 --artifact bundle --output business-slo.json
```

Python callers use `catalog_entries()`, `build_catalog_dashboard()`,
`build_catalog_bundle()`, and `portable_telemetry_contract()`.

## Checked artifacts

Each directory under `examples/catalog/` has:

- `builder.py`, a runnable package API example;
- `dashboard.json`, canonical JSON at the minimum target;
- `manifest.json`, hash, target, validator evidence, provenance, and assumptions; and
- `README.md`, a short operational description.

Run `uv run python scripts/check_examples.py --check` to detect drift or `--write` to regenerate.
CI also generates every eligible target variant through the compatibility corpus.

## Saved-search proposals

The RDS, CI/CD, and business-SLO entries include typed `SavedSearchSpec` recommendations for
expensive shared rollups. These stay in manifests and are not silently substituted into the
checked dashboard JSON. An operator must create, schedule, own, and authorize any saved search
outside this package.

## Portability boundary

These are structurally valid templates, not promises that local telemetry already has the required
indexes, units, or fields. Before deployment, profile the data, map logical indexes, verify units,
bound high-cardinality dimensions, review SPL cost, and run the exact target's official validator.
