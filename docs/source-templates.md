# Source-derived dashboard templates

The source-template catalog is distinct from the project's ten portable observability examples.
Portable examples are authored against the repository's normalized telemetry contract. A
source-derived template instead preserves a named external dashboard, exact repository revision,
content hash, required Splunk app when applicable, license, and documented adaptations.

## Splunk Health by rcastley

`rcastley_splunk_health` imports the eight-panel Dashboard Studio definition from
[`rcastley/splunk-custom-visualizations`](https://github.com/rcastley/splunk-custom-visualizations/tree/7424755c461712022367c3fa081fd7e0edc91001).
The source dashboard covers component status, license consumption, system resources, indexing
queues, forwarders, active searches, scheduler health, and index storage. Its panels use the
upstream `splunk_health` Canvas 2D custom visualization app.

The upstream project declares Splunk Enterprise 10.2+ or Splunk Cloud as its custom-visualization
baseline. This project validates only Splunk Enterprise and therefore rejects this template for
9.4 and 10.0 targets. Building the JSON does not install the required app; operators must install
the matching `splunk_health` app revision separately before publishing the definition.

`rcastley_splunk_health_portable` is a separate compatibility port for Splunk Enterprise 9.4 and
later. It preserves all eight source searches, refresh settings, titles, and the 1920 by 1080
layout. Seven custom Canvas panels become `splunk.table`; the license gauge becomes
`splunk.singlevalue`; custom options and the app dependency are removed. This is an explicit
adaptation, not a claim that the upstream custom-visualization app runs on Splunk 9.

```console
uv run splunk-studio template list
uv run splunk-studio template build rcastley_splunk_health --target 10.2.0
uv run splunk-studio template build rcastley_splunk_health \
  --target 10.4.0 --artifact bundle --output splunk-health.json
uv run splunk-studio template build rcastley_splunk_health_portable \
  --target 9.4.3 --artifact bundle --output splunk-health-portable.json
```

Python callers use `source_template_entries()`, `build_source_template()`, and
`build_source_template_bundle()`. The bundle keeps the definition and provenance contract together.

## What is preserved

- The source-owned panel types, titles, search strings, options, 1920 by 1080 layout, and dark
  dashboard theme.
- The upstream Apache-2.0 license, author attribution, commit SHA, source paths, and normalized
  definition SHA-256.
- The eight upstream `harness.json` contracts, including expected columns, sample rows, formatter
  defaults, default sizes, and no-data messages.
- The built upstream app snapshot used by the disposable integration lane.
- A deterministic built-in visualization transform of the same source definition for the portable
  variant; the transform changes no source SPL.

The Python package contains only the JSON definition, provenance metadata, and attribution notice.
Custom app JavaScript, CSS, images, NPM assets, and browser tooling remain under the integration
tree and are rejected from both wheel and source-distribution artifacts.

## Adopted engineering lessons

The import deliberately applies the most reusable practices from the upstream
[`splunk-viz` skill](https://github.com/rcastley/splunk-custom-visualizations/blob/7424755c461712022367c3fa081fd7e0edc91001/.claude/skills/splunk-viz/SKILL.md):

1. External dashboards are immutable source inputs. Runtime loading verifies the normalized
   definition hash, while the integration lock inventories every copied app and harness file.
2. Render fixtures come from visualization-owned data contracts. The live harness converts the
   upstream sample rows into deterministic `makeresults` SPL instead of inventing panel data.
3. Original SPL and render SPL remain separate. Live Splunk dispatches the original health searches
   for fatal errors, then independently checks exact fixture rows before browser rendering.
4. Canvas QA needs canvas-specific evidence. Playwright requires a visible, non-zero canvas inside
   every custom panel, freezes the upstream 50 ms animation loop, seeds particle randomness, and
   captures panel and full-dashboard screenshots.
5. Custom visualization compatibility has two dimensions: the Enterprise feature boundary and the
   installed app revision. Native validation now treats app-qualified types as a 10.2 feature.
6. A compatibility port must remain visibly distinct from its source. The portable template has a
   separate ID, title, hash, adaptation list, minimum target, and empty required-app contract.

## Reproducible import

Maintainers update the snapshot only from an exact checkout of the pinned revision:

```console
uv run python scripts/sync_source_templates.py \
  --source /path/to/splunk-custom-visualizations --check
```

Use `--write` only for an intentional source update. Changing the revision requires reviewing the
upstream license and diff, updating both package metadata hashes, regenerating 9.4/10.0 portable
and 10.2/10.4 custom visual baselines, and running the complete release evidence suite. The sync
command does not clone the repository or contact GitHub.
