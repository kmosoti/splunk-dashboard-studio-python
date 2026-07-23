# Business Journey and SLO

- Catalog ID: `business_journey_slo`
- Priority: `medium`
- Checked target: Splunk Enterprise `9.4.3`
- Telemetry contract: `portable-observability-v1`

This generated example applies sli_slo, red to event, trace telemetry. It assumes the logical
indexes `business_events`, `otel_traces`; map those names and the required semantic fields to your local Splunk app
before deployment. It does not create saved searches, publish a view, or include sample data.

## Panels

- `viz_journey_success` — Measure whether users complete the intended journey.
- `viz_journey_latency` — Track customer-perceived journey duration.
- `viz_journey_abandonment` — Measure journeys that start but do not complete.
- `viz_business_freshness` — Detect stale or interrupted journey telemetry.
- `viz_error_budget_burn` — Compare observed journey failures with the declared SLO budget.

## Rebuild

```console
uv run python examples/catalog/business_journey_slo/builder.py
uv run splunk-studio catalog build business_journey_slo --target 9.4.3 --artifact bundle
```

`dashboard.json` is the canonical minimum-target definition. `manifest.json` records its hash,
native validation status, validator evidence grade, provenance, and deferred live-test caveat.
