# Changelog

This project follows semantic versioning once a version is published. Entries marked “release
candidate” describe repository state and do not claim a GitHub or PyPI release.

## Unreleased

### 0.2.0 release candidate

Added:

- Python 3.12, 3.13, and 3.14 compatibility policy.
- Typed observability telemetry, provenance, saved-search, catalog, evidence, and agent-skill
  contracts plus a complete schema bundle.
- Builder defaults, token defaults, richer visualization/input fields, and duplicate-write guards.
- Ten packaged observability dashboards, CLI catalog commands, generated minimum-target artifacts,
  and native/official-engine corpus coverage.
- An offline Dashboard Studio REST XML codec with safe CDATA handling and deterministic semantic
  diffs.
- Engine-lock consistency, generated-example drift, release-evidence, checksum, artifact
  attestation, and PyPI trusted-publishing workflows.
- Operational security, skills, architecture, compatibility, and catalog documentation.

Changed:

- Package and runtime version to `0.2.0`.
- Minimum Python version from 3.14 to 3.12.
- The 10.4 network graph type to the official `splunk.networkGraph` spelling.
- Compatibility corpus from eight generic cases per target to include every eligible catalog
  definition.

Deferred:

- Live Splunk publish/readback fixture and HTTP adapter.
- Machine-enforced ACL, sensitive-index, or publication policy.
- Splunk Cloud, 9.2.x, and 9.3.x support.

### 0.1.0 repository baseline

- Deterministic builder, native validator, support profiles, corpus, official-engine CI adapter,
  optimization proposals, schema commands, and distribution guard.
