# API Gateway Overview

- Catalog ID: `api_gateway_overview`
- Priority: `high`
- Checked target: Splunk Enterprise `9.4.3`
- Telemetry contract: `portable-observability-v1`

This generated example applies red to log, trace telemetry. It assumes the logical
indexes `otel_logs`, `otel_traces`; map those names and the required semantic fields to your local Splunk app
before deployment. It does not create saved searches, publish a view, or include sample data.

## Panels

- `viz_route_red` — Compare request volume, failures, and latency by route.
- `viz_authentication_failures` — Track rejected authentication events by route.
- `viz_throttling` — Detect routes constrained by rate limits.
- `viz_top_tenants` — Rank tenant traffic without exposing raw user identifiers.
- `viz_latency_distribution` — Inspect route-level latency percentiles.

## Rebuild

```console
uv run python examples/catalog/api_gateway_overview/builder.py
uv run splunk-studio catalog build api_gateway_overview --target 9.4.3 --artifact bundle
```

`dashboard.json` is the canonical minimum-target definition. `manifest.json` records its hash,
native validation status, validator evidence grade, provenance, and deferred live-test caveat.
