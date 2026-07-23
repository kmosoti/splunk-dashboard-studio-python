# RDS and Database Health

- Catalog ID: `rds_database_health`
- Priority: `high`
- Checked target: Splunk Enterprise `9.4.3`
- Telemetry contract: `portable-observability-v1`

This generated example applies red, use to metric, log, trace telemetry. It assumes the logical
indexes `otel_metrics`, `otel_logs`, `otel_traces`; map those names and the required semantic fields to your local Splunk app
before deployment. It does not create saved searches, publish a view, or include sample data.

## Panels

- `viz_database_latency` — Track slow database operations by namespace.
- `viz_database_connections` — Find databases approaching connection limits.
- `viz_database_locks` — Surface lock waits and contention.
- `viz_database_storage` — Track remaining storage and write pressure.
- `viz_replication_lag` — Detect replicas falling behind primary databases.

## Rebuild

```console
uv run python examples/catalog/rds_database_health/builder.py
uv run splunk-studio catalog build rds_database_health --target 9.4.3 --artifact bundle
```

`dashboard.json` is the canonical minimum-target definition. `manifest.json` records its hash,
native validation status, validator evidence grade, provenance, and deferred live-test caveat.
