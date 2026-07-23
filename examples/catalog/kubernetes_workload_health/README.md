# Kubernetes Workload Health

- Catalog ID: `kubernetes_workload_health`
- Priority: `high`
- Checked target: Splunk Enterprise `9.4.3`
- Telemetry contract: `portable-observability-v1`

This generated example applies red, use to metric, log, trace telemetry. It assumes the logical
indexes `otel_metrics`, `otel_logs`, `otel_traces`; map those names and the required semantic fields to your local Splunk app
before deployment. It does not create saved searches, publish a view, or include sample data.

## Panels

- `viz_workload_error_rate` — Identify workloads whose request failures are rising.
- `viz_workload_p95_latency` — Track user-visible workload latency over time.
- `viz_pod_restarts` — Surface unstable pods and workload churn.
- `viz_resource_saturation` — Locate pods approaching resource limits.
- `viz_failing_pods` — Rank pods emitting the most error events.

## Rebuild

```console
uv run python examples/catalog/kubernetes_workload_health/builder.py
uv run splunk-studio catalog build kubernetes_workload_health --target 9.4.3 --artifact bundle
```

`dashboard.json` is the canonical minimum-target definition. `manifest.json` records its hash,
native validation status, validator evidence grade, provenance, and deferred live-test caveat.
