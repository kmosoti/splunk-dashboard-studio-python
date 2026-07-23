# Source-derived templates

`rcastley_splunk_health.py` builds the Apache-2.0 Splunk Health template pinned from
`rcastley/splunk-custom-visualizations`. The output requires the matching `splunk_health` custom
visualization app and Splunk Enterprise 10.2 or later.

```console
uv run python examples/source_templates/rcastley_splunk_health.py
```

See [source-derived templates](../../docs/source-templates.md) for provenance, installation
boundaries, and the reproducible import workflow.
