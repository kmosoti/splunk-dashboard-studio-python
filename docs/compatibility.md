# Splunk Enterprise compatibility

## Supported release lines

| Target | Native profile | NPM engine | Evidence |
|---|---|---|---|
| 9.4.3 and later 9.4 patches | `splunk-enterprise-9.4.3` | Dashboard 27.5.1 | Temporal surrogate |
| 10.0.x | `splunk-enterprise-10.0` | Dashboard 28.6.0 | Release-family surrogate |
| 10.2.x | `splunk-enterprise-10.2` | Dashboard 28.6.0 | Official attribution |
| 10.4.x | `splunk-enterprise-10.4` | Dashboard 29.8.0 | Current public surrogate |

Targets below 9.4.3, unknown Enterprise release lines, and Splunk Cloud identifiers fail closed.

## Why 9.4.3 is not mapped to 24.0.0

The public NPM registry does not contain
`@splunk/dashboard-validation@24.0.0`. Public v24 validation releases date from 2022, while the
[official release notes](https://help.splunk.com/en/splunk-enterprise/release-notes-and-updates/release-notes/9.4/whats-new/welcome-to-splunk-enterprise-9.4)
date Enterprise 9.4 to December 16, 2024. The last public validation release before that GA date
was 27.5.1. The [official 9.4 attribution](https://help.splunk.com/en/splunk-enterprise/release-notes-and-updates/release-notes/9.4/third-party-software/credits)
does not list `dashboard-validation`, `dashboard-definition`, or `dashboard-presets`, so it cannot
establish a package mapping. Timing makes 27.5.1 a useful differential-test surrogate, but it is
not proof of the package embedded in Enterprise.

The 9.4.3 mapping must remain `temporal_surrogate` until package metadata is captured from an
authoritative source or a matching licensed installation. CI and documentation must preserve that
qualification.

## Adding a release profile

1. Obtain an official attribution, SBOM, or package manifest from the Enterprise release.
2. Record the exact product release line separately from every NPM package version.
3. Add feature gates with official documentation URLs.
4. Add before/at/after boundary corpus cases.
5. Pin and lock the CI engine.
6. Pass native, official-engine, artifact, and determinism gates.
7. Promote the evidence grade only when the source justifies it.
