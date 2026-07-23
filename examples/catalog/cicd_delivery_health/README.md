# CI/CD Delivery Health

- Catalog ID: `cicd_delivery_health`
- Priority: `medium`
- Checked target: Splunk Enterprise `9.4.3`
- Telemetry contract: `portable-observability-v1`

This generated example applies red, sli_slo to event telemetry. It assumes the logical
indexes `cicd_events`, `platform_events`; map those names and the required semantic fields to your local Splunk app
before deployment. It does not create saved searches, publish a view, or include sample data.

## Panels

- `viz_delivery_lead_time` — Track time from accepted change to production deployment.
- `viz_pipeline_failures` — Compare failed and total pipeline runs.
- `viz_flaky_jobs` — Rank jobs alternating between pass and fail outcomes.
- `viz_pipeline_queue_time` — Track delivery-system saturation before jobs start.
- `viz_deployment_rollbacks` — Correlate rollback frequency with services and environments.

## Rebuild

```console
uv run python examples/catalog/cicd_delivery_health/builder.py
uv run splunk-studio catalog build cicd_delivery_health --target 9.4.3 --artifact bundle
```

`dashboard.json` is the canonical minimum-target definition. `manifest.json` records its hash,
native validation status, validator evidence grade, provenance, and deferred live-test caveat.
