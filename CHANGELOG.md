# Changelog

This project follows semantic versioning once a version is published. Entries marked “release
candidate” describe repository state and do not claim a GitHub or PyPI release.

## Unreleased

### 0.2.1 release candidate

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
- An auto-accepting, integration-only Splunk Free fixture for original-SPL dispatch, exact synthetic
  result math, REST publish/readback, Dashboard Studio browser rendering, and state coverage.
- Locked Playwright screenshot regression, ARIA and trace evidence, QA overview generation, and a
  provider-neutral advisory vision report contract.
- Reviewed full-suite render baselines for pinned Splunk Enterprise 9.4.3, 10.0.0, 10.2.0, and
  10.4.0 images, with a machine-readable provenance inventory.
- A provenance-locked source-template API and CLI for the Apache-2.0 Splunk Health dashboard from
  `rcastley/splunk-custom-visualizations`, including its eight integration-only custom
  visualizations and manifest-driven render contracts.
- A distinct app-free Splunk Health compatibility port using built-in visualizations, validated
  with live Splunk Enterprise 9.4.3 and 10.0.0 render baselines.
- A five-image public gallery synchronized byte-for-byte from reviewed live Splunk baselines.
- Operational security, skills, architecture, compatibility, and catalog documentation.

Changed:

- Package and runtime version to `0.2.1`.
- Minimum Python version from 3.14 to 3.12.
- The 10.4 network graph type to the official `splunk.networkGraph` spelling.
- Native custom-visualization detection to recognize app-qualified visualization types and enforce
  the Splunk Enterprise 10.2 feature boundary.
- Compatibility corpus from eight generic cases per target to include every eligible catalog
  definition and source template; app-free source ports run through official NPM validators while
  app-qualified custom definitions remain live-fixture-only.

Deferred:

- An unattended vision provider or external screenshot-upload credential.
- Machine-enforced ACL, sensitive-index, or publication policy.
- Splunk Cloud, 9.2.x, and 9.3.x support.

### 0.1.0 repository baseline

- Deterministic builder, native validator, support profiles, corpus, official-engine CI adapter,
  optimization proposals, schema commands, and distribution guard.
