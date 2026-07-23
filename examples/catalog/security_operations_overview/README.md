# Security Operations Overview

- Catalog ID: `security_operations_overview`
- Priority: `medium`
- Checked target: Splunk Enterprise `9.4.3`
- Telemetry contract: `portable-observability-v1`

This generated example applies four_golden_signals to event telemetry. It assumes the logical
indexes `security_events`, `platform_events`; map those names and the required semantic fields to your local Splunk app
before deployment. It does not create saved searches, publish a view, or include sample data.

## Panels

- `viz_auth_failures` — Track authentication failure volume without exposing user values.
- `viz_high_risk_events` — Rank current high-risk security signals.
- `viz_noisy_detections` — Find detections producing disproportionate volume.
- `viz_ingestion_lag` — Detect delayed security telemetry.
- `viz_security_platform_health` — Track collection and detection pipeline errors.

## Rebuild

```console
uv run python examples/catalog/security_operations_overview/builder.py
uv run splunk-studio catalog build security_operations_overview --target 9.4.3 --artifact bundle
```

`dashboard.json` is the canonical minimum-target definition. `manifest.json` records its hash,
native validation status, validator evidence grade, provenance, and deferred live-test caveat.
