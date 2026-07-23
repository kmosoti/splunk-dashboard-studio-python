# Load Balancer Edge Health

- Catalog ID: `load_balancer_edge_health`
- Priority: `high`
- Checked target: Splunk Enterprise `9.4.3`
- Telemetry contract: `portable-observability-v1`

This generated example applies four_golden_signals to log, metric telemetry. It assumes the logical
indexes `otel_logs`, `otel_metrics`; map those names and the required semantic fields to your local Splunk app
before deployment. It does not create saved searches, publish a view, or include sample data.

## Panels

- `viz_edge_traffic` — Track ingress demand over time.
- `viz_edge_errors` — Separate client and server failure rates.
- `viz_edge_latency` — Track tail latency at the edge.
- `viz_backend_failures` — Rank unhealthy backend services.
- `viz_edge_saturation` — Show active connection pressure.

## Rebuild

```console
uv run python examples/catalog/load_balancer_edge_health/builder.py
uv run splunk-studio catalog build load_balancer_edge_health --target 9.4.3 --artifact bundle
```

`dashboard.json` is the canonical minimum-target definition. `manifest.json` records its hash,
native validation status, validator evidence grade, provenance, and deferred live-test caveat.
