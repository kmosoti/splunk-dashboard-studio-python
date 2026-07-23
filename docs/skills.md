# Observability agent skill contract

The package models an observability platform expert as eight bounded skills. This is a typed,
machine-readable policy layer, not an executable agent router. It cannot run searches, publish a
dashboard, alter ACLs, or create saved searches.

| Skill | Primary inputs | Outputs | Hard boundary |
|---|---|---|---|
| `data_discovery` | Field inventory, samples, semantic conventions | Dataset profile and candidate entities | Never infer stability from one sample |
| `spl_optimization` | SPL, search graph, panel intent | Explicit proposals and shared-base candidates | Never silently rewrite SPL |
| `visualization_selection` | Intent, cardinality, metric type, audience | Visualization and defaults recommendation | Avoid decorative choices |
| `alerting_slo` | SLI, thresholds, burn policy | SLO sections and saved-search specifications | Never create alerts or saved searches |
| `provenance` | Source mapping, schema, definition | Panel provenance and evidence metadata | No unlabeled derived KPI |
| `validation` | Definition, target profile, engine locks | Normalized report and evidence | NPM code never ships in Python artifacts |
| `drift_detection` | Corpus, snapshots, schema deltas | Compatibility diff and regeneration work | Separate product drift from telemetry drift |
| `access_control` | App context, role policy, publish intent | Least-privilege guidance | Advisory only; never publish or mutate ACLs |

## Typed inputs and outputs

`AgentSkill` enumerates the eight stable identifiers. Each `SkillDescriptor` declares:

- `purpose`;
- required conceptual `inputs` and `outputs`;
- decision `heuristics`;
- non-negotiable `constraints`; and
- abstract `tools` that an external orchestrator may map to authorized implementations.

The dashboard-design contract is supported by:

- `TelemetryContract` and `TelemetryField` for signal and field assumptions;
- `CatalogEntry` for dashboard intent and target boundaries;
- `PanelProvenance` for source-to-panel dependencies;
- `SavedSearchSpec` for externally owned performance proposals;
- `DashboardEvidenceManifest` for hashes and validation claims; and
- `DashboardArtifactBundle` for a canonical definition plus its manifest.

## Schema discovery

```console
uv run splunk-studio schema agent
uv run splunk-studio schema bundle
```

The original `DashboardAgentContract(target, definition)` remains source-compatible. Its JSON
Schema now contains `x-observability-skills`. The full schema bundle also includes telemetry,
skill-descriptor, artifact-bundle, dashboard, and Enterprise profile contracts.

## Authority model

An external agent may use these contracts to propose a dashboard, but authority is still explicit:

- discovery does not grant search execution;
- validation does not grant publication;
- a saved-search specification does not grant knowledge-object creation;
- access-control guidance does not grant ACL mutation; and
- an offline codec result does not prove a live Splunk round-trip.

This separation keeps generated artifacts inspectable and prevents “optimization,” “validation,”
or “publishing” from becoming hidden mutation channels.
