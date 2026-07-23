# Examples

`basic.py` is the smallest builder walkthrough. The `catalog/` tree contains the ten checked
observability examples shipped for v0.2. Each catalog directory includes:

- `builder.py`, a runnable Python entry point;
- `dashboard.json`, the canonical definition at that dashboard's minimum target;
- `manifest.json`, provenance and compatibility evidence; and
- `README.md`, telemetry assumptions and panel intent.

Regenerate or verify the complete tree with:

```console
uv run python scripts/check_examples.py --write
uv run python scripts/check_examples.py --check
```

The examples use the `portable-observability-v1` logical schema. They contain no data, secrets,
external assets, live Splunk connection code, or automatic publication behavior.
