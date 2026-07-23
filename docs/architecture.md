# Architecture

The project is a versioned Dashboard Studio compiler and validator with hard boundaries between
authoring, evidence, official validation, and deployment.

## Runtime layers

1. `models.py` defines the stable Pydantic dashboard envelope while preserving explicit extension
   boundaries for Splunk-owned option dictionaries.
2. `generation.py` owns deterministic IDs, defaults, tokens, data sources, visualizations, inputs,
   and a 1440-pixel two-column tabbed layout.
3. `contracts.py` defines telemetry, provenance, catalog, artifact, and agent-skill contracts.
4. `catalog.py` compiles ten immutable dashboard specifications into target-aware definitions and
   honest evidence bundles.
5. `validation.py`, `graph.py`, `spl.py`, and `dos.py` own native cross-object and structural
   validation.
6. `codec.py` encodes and decodes the documented `data/ui/views` XML envelope without networking.
7. `cli.py` exposes these surfaces as deterministic JSON or JSONL commands.

Canonical dashboard JSON contains only fields Splunk owns. Telemetry assumptions, provenance,
saved-search proposals, validation state, and evidence grades stay in the artifact manifest so
project metadata cannot make a valid dashboard definition invalid.

## Determinism and mutation policy

- Generated IDs are stable for a fixed call sequence.
- Canonical JSON sorts keys and has stable compact or indented rendering.
- Duplicate IDs, default scopes, and token defaults fail instead of overwriting earlier intent.
- Optimization returns immutable proposals and never silently changes SPL.
- Catalog artifacts are generated from package code and checked for drift.
- Saved-search specifications are advisory. The package can reference a saved search but never
  creates, schedules, edits, or grants access to one.

## Validation authorities

Neither lane is a complete oracle:

- The Python validator owns exact Enterprise target selection, feature introduction boundaries,
  references, layout bounds, and chain graph rules.
- The Splunk NPM validator owns the exact official schema for visualization, input, and data-source
  option surfaces, plus Splunk's Dynamic Options Syntax parser.
- Checked manifests record native success and the selected engine/evidence grade, but deliberately
  report official validation as `not_run`; CI output is the proof of an official-engine run.

A release candidate is acceptable only when native expectations, official-engine expectations,
generated artifacts, typing, and distribution inspection all pass.

## CI-only official engines

The adapter under `.github/ci/npm-validator/` is isolated from the runtime:

- Each engine directory has an exact `package.json` and `package-lock.json`.
- `scripts/check_engine_locks.py` proves profile metadata and resolved lock versions agree.
- GitHub Actions provisions Node, generates an Enterprise preset schema, and streams JSONL cases
  through `DashboardValidator` and the official DOS parser.
- The runner has read-only repository permissions and no package credentials.
- Hatch exclusions plus `scripts/check_distribution.py` prevent Node assets from entering Python
  artifacts.

## Search graph policy

Native graph validation follows documented Dashboard Studio limits: no more than ten direct chain
searches from one parent, no more than one additional chained level, and no child overrides for
`queryParameters`, `refresh`, or `refreshType`. Base/chain optimization is proposed only when
searches share inherited settings and a safe transforming prefix.

See Splunk's
[base and chain search documentation](https://help.splunk.com/en/splunk-enterprise/create-dashboards-and-reports/dashboard-studio/9.4/use-data-sources/chain-searches-together-with-a-base-search-and-chain-searches).

## Agent contract

The v0.2 agent layer is typed policy, not an autonomous runtime. `schema agent` preserves the
original `{target, definition}` contract and adds an `x-observability-skills` extension. `schema
bundle` includes dashboard, artifact, telemetry, and skill schemas in one document. The eight skill
descriptors declare inputs, outputs, heuristics, constraints, and tool names, but do not execute or
grant authority. See [skills](skills.md).

## Offline round-trip boundary

`StudioView`, `encode_view_xml`, `decode_view_xml`, and `compare_roundtrip` implement the documented
`<dashboard version="2">` format. The decoder rejects DTD/entity declarations, normalizes JSON via
`DashboardDefinition`, ignores unknown server-added XML fields, and reports deterministic
JSON-pointer differences.

There is intentionally no HTTP client, SDK dependency, credential handling, publish command, or
live CI fixture in v0.2. A future integration extra may add a disposable publish/readback test, but
it must remain separate from the compiler runtime.
