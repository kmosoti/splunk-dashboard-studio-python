# Splunk Enterprise compatibility

## Supported release lines

| Target | Native profile | Locked NPM engine | Evidence |
|---|---|---|---|
| 9.4.3 and later 9.4 patches | `splunk-enterprise-9.4.3` | Dashboard 27.5.1 | Temporal surrogate |
| 10.0.x | `splunk-enterprise-10.0` | Dashboard 28.6.0 | Temporal surrogate |
| 10.2.x | `splunk-enterprise-10.2` | Dashboard 28.6.0 | Official attribution |
| 10.4.x | `splunk-enterprise-10.4` | Dashboard 29.8.0 | Temporal surrogate |

Targets below 9.4.3, 9.2.x, 9.3.x, unknown release lines, and Splunk Cloud identifiers fail closed.
Public documentation calls these release lines; this project does not label them LTS without a
separate authoritative support contract.

The Python runtime supports CPython 3.12, 3.13, and 3.14. Node is never a runtime requirement.

## Evidence grades

- `official_attribution`: Splunk's Enterprise attribution identifies the relevant Dashboard
  Framework line.
- `verified_installation`: exact package metadata was captured from a matching licensed Enterprise
  installation.
- `temporal_surrogate`: a public package is useful for differential CI, but no exact product bundle
  mapping is claimed.

Product versions and NPM package versions are independent axes. A package published near a Splunk
release is not, by timing alone, proof that the product embeds it.

## 9.4 evidence

The public NPM registry has no `@splunk/dashboard-validation@24.0.0`. Public v24 validation releases
date from 2022, while the
[Enterprise 9.4 release notes](https://help.splunk.com/en/splunk-enterprise/release-notes-and-updates/release-notes/9.4/whats-new/welcome-to-splunk-enterprise-9.4)
date 9.4 GA to December 16, 2024. Dashboard 27.5.1 is the last public release before that date.

The
[9.4 third-party attribution](https://help.splunk.com/en/splunk-enterprise/release-notes-and-updates/release-notes/9.4/third-party-software/credits)
does not establish exact `dashboard-validation`, `dashboard-definition`, and `dashboard-presets`
versions. Therefore 27.5.1 remains a temporal surrogate.

## 10.x evidence

The 10.0 lane reuses Dashboard 28.6.0 as a release-family surrogate pending an authoritative bundle
manifest. The
[10.2 third-party attribution](https://help.splunk.com/en/splunk-enterprise/release-notes-and-updates/release-notes/10.2/third-party-software/credits)
supports the Dashboard Framework 28.6 line, so that profile is graded `official_attribution`.

The public `@splunk/dashboard-validation` registry now includes 29.8.0, and the repository has an
exact lock for it. The public
[10.4 third-party attribution](https://help.splunk.com/en/splunk-enterprise/release-notes-and-updates/release-notes/10.4/third-party-software/credits)
still does not prove that exact product mapping. The 10.4 lane therefore remains
`temporal_surrogate`, despite the lock being real and the expanded corpus passing it.

## Catalog compatibility

Nine catalog dashboards have a minimum target of 9.4.3 and compile across every supported profile.
`microservice_service_map` requires 10.4.0 because it uses the official `splunk.networkGraph`
visualization type. CI generates all eligible dashboard/target combinations transiently; the
repository checks in one canonical definition and evidence manifest per dashboard at its minimum
target.

## Adding or promoting a profile

1. Obtain an official attribution, SBOM, package manifest, or verified licensed installation.
2. Record the Enterprise release line separately from every NPM version.
3. Add feature gates with primary documentation URLs.
4. Add before/at/after native corpus cases and all eligible catalog cases.
5. Pin an isolated exact NPM lock and pass `scripts/check_engine_locks.py`.
6. Pass native, official-engine, determinism, artifact, and distribution gates.
7. Promote the evidence grade only when the source proves the stronger claim.
