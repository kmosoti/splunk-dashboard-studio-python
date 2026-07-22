# splunk-dashboard-studio-python

Generate and validate deterministic Splunk Enterprise Dashboard Studio definitions with Python
3.14 and Pydantic 2.

```python
from splunk_dashboard_studio import DashboardBuilder, canonical_json

builder = DashboardBuilder(title="Service health", target="9.4.3")
search = builder.add_search(
    "index=_internal | stats count by sourcetype",
    name="events",
)
builder.add_visualization(
    "splunk.table",
    name="events",
    data_sources={"primary": search},
    options={},
)

dashboard = builder.build()
print(canonical_json(dashboard, indent=2))
```

The package is intentionally Splunk Enterprise-only. It does not claim Splunk Cloud
compatibility, does not connect to a Splunk deployment, and never installs or bundles Node.

## What it validates

- Pydantic 2 dashboard envelopes with stable JSON aliases.
- Explicit Splunk Enterprise targets beginning at 9.4.3.
- Feature availability across the 9.4, 10.0, 10.2, and 10.4 release lines.
- Data-source and visualization references.
- Base/chain parent existence, cycles, depth, fan-out, and inherited options.
- Canvas positions and boundary overflow.
- Structural SPL1 pipelines and Dynamic Options Syntax expressions.
- Deterministic search optimization proposals without silently rewriting SPL.

The native validator is deliberately stricter about cross-object relationships than the official
Dashboard Framework schema. CI adds a second validation lane using pinned Splunk NPM engines.

## Install for development

```console
uv sync --all-groups
uv run pytest -q
```

The project requires Python 3.14 or later. Pydantic's compiled `pydantic-core` performs the hot-path
model parsing and serialization.

## CLI

Validate a dashboard for an exact Enterprise target:

```console
uv run splunk-studio validate dashboard.json --target 9.4.3
```

Read from standard input:

```console
uv run splunk-studio validate - --target 10.2.0 < dashboard.json
```

Emit the complete agent contract, including the Enterprise capability manifest:

```console
uv run splunk-studio schema agent > agent-schema.json
```

Generate the deterministic compatibility corpus used by CI:

```console
uv run splunk-studio corpus --target 10.2.0 --output corpus.jsonl
```

Analyze existing searches for possible base/chain consolidation:

```console
uv run splunk-studio optimize dashboard.json
```

All commands produce machine-readable JSON or JSONL. Exit codes are `0` for success, `1` for a
validly executed check that found an invalid dashboard, and `2` for an invocation or system error.

## Version evidence

Splunk Enterprise versions and public NPM package versions are separate version axes. Each profile
records an evidence grade:

- `official_attribution`: Splunk's Enterprise attribution identifies the Dashboard Framework line.
- `verified_installation`: package metadata was captured from the matching licensed Enterprise
  installation.
- `temporal_surrogate`: the closest applicable public package is used for differential CI, but is
  not presented as an official product mapping.

The 9.4.3 lane uses `@splunk/dashboard-validation@27.5.1` as a temporal surrogate because it is the
last public release before Enterprise 9.4 GA. The repository explicitly rejects the inaccurate
`24.0.0` mapping: that version does not exist for the public validation package. Enterprise 10.2
uses the officially evidenced Dashboard Framework 28.6 line.

See [compatibility.md](docs/compatibility.md) for the complete policy.

## Official NPM validation in CI

Node is development infrastructure, not a runtime dependency. GitHub Actions:

1. Generates a deterministic positive and negative dashboard corpus in Python.
2. Installs an exact, locked NPM engine in an ephemeral runner.
3. Generates the Enterprise Dashboard Studio schema from the matching presets.
4. Runs `DashboardValidator` plus Splunk's DOS parser.
5. Compares actual results with the corpus expectations.
6. Inspects the Python wheel and source distribution to prove that no Node or NPM assets ship.

The CI harness lives under `.github/ci/npm-validator/` and is explicitly excluded from Python build
artifacts. Splunk NPM packages are downloaded during CI and are never redistributed by this project.

## Project status

This is an independent open-source project and is not affiliated with, endorsed by, or supported by
Splunk Inc. “Splunk” and related marks are the property of their respective owners.

## License

Apache-2.0. The license applies to this project's source code, not to separately downloaded Splunk
packages or Splunk software.
