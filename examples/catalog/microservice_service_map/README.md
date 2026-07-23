# Microservice Service Map

- Catalog ID: `microservice_service_map`
- Priority: `high`
- Checked target: Splunk Enterprise `10.4.0`
- Telemetry contract: `portable-observability-v1`

This generated example applies red, four_golden_signals to metric, event, log, trace telemetry. It assumes the logical
indexes `otel_metrics`, `otel_logs`, `otel_traces`, `platform_events`; map those names and the required semantic fields to your local Splunk app
before deployment. It does not create saved searches, publish a view, or include sample data.

## Panels

- `viz_service_red` — Compare request health across services.
- `viz_dependency_map` — Show request flow between instrumented services.
- `viz_dependency_hotspots` — Rank slow and failing downstream dependencies.
- `viz_recent_deployments` — Correlate service health with recent changes.
- `viz_trace_samples` — Provide trace identifiers for deep diagnosis.

## Rebuild

```console
uv run python examples/catalog/microservice_service_map/builder.py
uv run splunk-studio catalog build microservice_service_map --target 10.4.0 --artifact bundle
```

`dashboard.json` is the canonical minimum-target definition. `manifest.json` records its hash,
native validation status, validator evidence grade, provenance, and deferred live-test caveat.
