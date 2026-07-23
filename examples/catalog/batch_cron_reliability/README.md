# Batch and Cron Reliability

- Catalog ID: `batch_cron_reliability`
- Priority: `medium`
- Checked target: Splunk Enterprise `9.4.3`
- Telemetry contract: `portable-observability-v1`

This generated example applies red, sli_slo to event telemetry. It assumes the logical
indexes `batch_events`; map those names and the required semantic fields to your local Splunk app
before deployment. It does not create saved searches, publish a view, or include sample data.

## Panels

- `viz_schedule_adherence` — Find jobs that start materially after their schedules.
- `viz_job_duration` — Track duration regressions by job.
- `viz_job_backlog` — Detect pending work accumulation.
- `viz_job_failures` — Rank recurring job failures.
- `viz_job_freshness` — Show elapsed time since each job last succeeded.

## Rebuild

```console
uv run python examples/catalog/batch_cron_reliability/builder.py
uv run splunk-studio catalog build batch_cron_reliability --target 9.4.3 --artifact bundle
```

`dashboard.json` is the canonical minimum-target definition. `manifest.json` records its hash,
native validation status, validator evidence grade, provenance, and deferred live-test caveat.
