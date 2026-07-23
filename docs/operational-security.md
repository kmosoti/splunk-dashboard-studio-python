# Operational security

Dashboard Studio definitions execute searches and expose their results. Treat generated JSON as
workload and access-control configuration, not harmless presentation metadata.

## Package boundary

The core package has no network client, Splunk SDK, credentials, secret store, Node runtime, or
publication command. The offline XML codec serializes the documented `data/ui/views` envelope but
does not authenticate, send, or receive a request. Unknown server-added XML fields are ignored for
semantic comparison; this is not proof of a live round-trip.

## Deployment checklist

Before publishing a generated dashboard:

1. Map every logical index and required field to an approved local data source.
2. Review SPL for index scope, wildcard expansion, cardinality, subsearches, and concurrency cost.
3. Constrain token inputs to allowlisted values; do not turn tokens into unrestricted SPL
   interpolation.
4. Verify dashboard, app, role, and saved-search ACLs under the intended service account.
5. Confirm that panels do not disclose personal data, secrets, security detections, tenant data, or
   internal topology to unauthorized viewers.
6. Keep publication private or app-scoped by default. Published dashboards bypass authentication
   and must contain only explicitly approved non-sensitive content.
7. Review external assets against the Splunk Dashboards Trusted Domains List. The packaged catalog
   uses none.
8. Review refresh and search-concurrency controls. Catalog dashboards deliberately set no
   automatic refresh.
9. Validate with the exact Enterprise profile and official engine, then test in a non-production
   Splunk namespace before promotion.

## Saved searches

Saved searches can reduce repeated work for high-viewer dashboards, but they are separately owned
knowledge objects. Discovery capabilities and ACL behavior may expose more metadata than expected.
The package therefore emits only external `SavedSearchSpec` proposals or explicit references. It
never creates schedules, changes ownership, grants capabilities, or assumes that reference access
implies authorization to inspect all saved searches.

## Sensitive observability signals

Trace IDs, tenant IDs, security detection names, risk events, user-journey events, and infrastructure
topology may be sensitive even when they are not credentials. Use pseudonymous dimensions where
possible, avoid raw user identifiers in top-N panels, and apply retention and role policies to both
source indexes and dashboard read access.

Kernel, network, and eBPF-derived telemetry can materially improve diagnosis but may require
privileged collection. Keep privileged collectors and their raw data outside low-privilege
dashboard roles, and review their host, container, and network exposure separately.

## XML and supply chain

The codec rejects DTD and entity declarations and safely splits `]]>` sequences in CDATA. It still
expects trusted-size input and is not a general XML sanitizer.

Release automation is triggered only by a published GitHub release, verifies tag/version equality,
reruns native and official-engine gates, builds once, inspects artifacts, creates checksums and an
evidence manifest, produces a build-provenance attestation, and uses PyPI trusted publishing. The
repository owner must configure and protect the `pypi` environment before any release.
