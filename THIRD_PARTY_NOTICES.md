# Third-party notices

## rcastley/splunk-custom-visualizations

This project includes an adapted Dashboard Studio definition and an integration-only source
snapshot from [rcastley/splunk-custom-visualizations](https://github.com/rcastley/splunk-custom-visualizations),
revision `7424755c461712022367c3fa081fd7e0edc91001`.

- Upstream author: Robert Castley and repository contributors
- Upstream license: Apache License 2.0
- Packaged Python content: the `splunk_health` Dashboard Studio JSON definition, its deterministic
  built-in visualization compatibility port, and provenance metadata
- Integration-only content: the built `splunk_health` app and eight upstream `harness.json`
  visualization contracts

The upstream app, JavaScript, CSS, preview images, and harness contracts are excluded from the
Python wheel and source distribution. The repository's Apache-2.0 `LICENSE` applies to the adapted
source material; upstream origin and exact content hashes are retained in
`integration/splunk-visual/source-lock.json`.
