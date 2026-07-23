# EC2 and Host Capacity

- Catalog ID: `ec2_host_capacity`
- Priority: `high`
- Checked target: Splunk Enterprise `9.4.3`
- Telemetry contract: `portable-observability-v1`

This generated example applies use to metric, log telemetry. It assumes the logical
indexes `otel_metrics`, `otel_logs`, `platform_events`; map those names and the required semantic fields to your local Splunk app
before deployment. It does not create saved searches, publish a view, or include sample data.

## Panels

- `viz_host_cpu` — Track sustained host CPU utilization.
- `viz_host_memory` — Find hosts with memory pressure.
- `viz_host_disk` — Identify full or rapidly filling filesystems.
- `viz_host_network_load` — Compare network throughput with system load.
- `viz_host_errors` — Rank hosts by operating-system and agent errors.

## Rebuild

```console
uv run python examples/catalog/ec2_host_capacity/builder.py
uv run splunk-studio catalog build ec2_host_capacity --target 9.4.3 --artifact bundle
```

`dashboard.json` is the canonical minimum-target definition. `manifest.json` records its hash,
native validation status, validator evidence grade, provenance, and deferred live-test caveat.
