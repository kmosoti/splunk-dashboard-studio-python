# Live Splunk visual regression

The integration harness under `integration/splunk-visual/` answers three different questions with
three independent evidence lanes:

| Lane | Question | Gate |
|---|---|---|
| Search-result contract | Did the exact synthetic SPL return the expected rows and values? | Hard |
| Live render regression | Did Splunk ingest, read back, and render every panel without deterministic browser or image regressions? | Hard |
| Vision QA | Does the rendered dashboard show layout or chart-quality defects that deterministic checks missed? | Advisory unless a deterministic failure corroborates it |

Model judgment never replaces search math or screenshot comparison. A vision-only observation is
a warning. A model-reported error can gate only when it cites an existing browser, query, or pixel
diff failure.

## Startup and terms boundary

The harness uses the official `splunk/splunk` image and `SPLUNK_LICENSE_URI=Free`. Free mode avoids
a license secret; it does not remove the software terms. Read the
[Splunk General Terms](https://www.splunk.com/en_us/legal/splunk-general-terms.html) before running
the image. Invoking `run.sh` automatically passes `--accept-license`; targets marked in
`images.json` as requiring the current general terms also receive
`--accept-sgt-current-at-splunk-com`. Local, pull-request, nightly, manual, and release runs all use
this same behavior, with no repository variable or interactive prompt.

Authentication is plumbing only. The disposable container uses an ephemeral admin password so the
REST and browser clients can reach Splunk during initial setup. There are no authentication, role,
ACL, or publication-permission assertions. Free mode disables remote management by default, so
the container-only `defaults.yml` sets `server.conf/[general]/allowRemoteLogin = always`. Both
ports remain bound to `127.0.0.1`, and the setting is destroyed with the disposable volume.

For 10.2 and 10.4, `prepare` also copies the provenance-locked `splunk_health` app into the run
artifact and Compose mounts that disposable copy into the standalone. The vendored source remains
unchanged, the app is absent from 9.4/10.0 runs, and no app asset enters a Python distribution.

## Pinned targets

`images.json` records a tag plus immutable manifest-list digest for every supported target and
declares whether the extra 10.x terms flag is required. The images are Linux amd64 because the
official Splunk Enterprise image currently publishes that architecture for these tags.

| Target | Image manifest digest |
|---|---|
| 9.4.3 | `sha256:27344f73cbe07c3ea003164dbabef38e08e56efb193b39095cf56f8784a42dbe` |
| 10.0.0 | `sha256:10da23a5c78397b38328ed863ca2826390c329c517f9aff7a4978f30e5208e78` |
| 10.2.0 | `sha256:a7a7d800cdf470eeedf5a8eb2a4ea1bb07ade9bef5c95f1c65eabab08e7ac391` |
| 10.4.0 | `sha256:5fef7b0d2c83f6e8b3fe3cda5885e2a01e3a6eb99d8502e6333aaa64e7021f62` |

Updating one digest is a compatibility change: regenerate and review that target's baselines even
when the visible version tag is unchanged.

## What the harness does

For each run, `scripts/harness.py`:

1. Builds eligible dashboards from the production catalog and source-template registry for the
   exact Enterprise target.
2. Copies the definitions and replaces only the test copy's `ds.search` query strings with fixed
   `makeresults` contracts. Production catalog objects and checked examples are unchanged.
3. For the source-derived Splunk Health dashboard, preserves the upstream layout and visualization
   configuration while deriving fixture rows from the eight pinned upstream `harness.json` files.
4. Adds explicit no-data and search-error state dashboards.
5. Starts one standalone Splunk instance in Free mode on localhost, waits for the official
   container health check, and independently retries Splunk Web until its transient unavailable
   page clears before browser work begins.
6. Creates empty event and metric indexes matching the portable telemetry contract.
7. Dispatches the original catalog and source-template SPL and rejects fatal search messages.
   Empty results are valid; this lane checks the real query, not the fixture query.
8. Publishes each generated view through `servicesNS/admin/search/data/ui/views`, reads it back, and
   compares the normalized Dashboard Studio XML envelope.
9. Dispatches every synthetic query and compares projected rows exactly with either `fixtures.json`
   or the pinned upstream harness contract.
10. Renders each view with the locked Playwright/Chromium environment.
11. Deletes the views and removes the container and volume on exit.

The synthetic contracts cover every visualization type currently used by the catalog:

- line charts receive three fixed timestamped points and a target series;
- tables receive three ordered entity/status rows;
- single values receive exactly `99.95`; the API contract checks that raw value while the browser
  contract checks Splunk's default rounded rendering of `100`;
- network graphs receive three explicit source/target/weight edges.

The eight custom Canvas panels receive the exact field names and sample rows declared by their
upstream harnesses. Playwright requires each to expose a visible, non-zero canvas within its panel.
The browser seed fixes particle randomness and suppresses the upstream 50 ms animation interval in
child frames so snapshots represent the initial deterministic render rather than an arbitrary
animation frame.

The browser uses a 1440 by 1100 CSS-pixel viewport, device scale factor 1, UTC, `en-US`, light
theme, one worker, disabled animation and transitions, and a pinned Chromium from Playwright
1.61.1. It asserts dashboard and panel titles, checks table, single-value, and network-node markers
inside their panel bounds, captures an ARIA snapshot, rejects unexpected search/browser/resource
failures, and records full-dashboard and panel screenshots.

## Local commands

Install the integration-only Node dependencies and Chromium once:

```console
uv sync --frozen --no-dev
cd integration/splunk-visual
npm ci
npm exec -- playwright install chromium
cd ../..
```

Generate a candidate baseline:

```console
SPLUNK_TARGET=10.4.0 \
SPLUNK_VISUAL_SUITE=smoke \
SPLUNK_UPDATE_SNAPSHOTS=1 \
./integration/splunk-visual/run.sh
```

Run a normal comparison:

```console
SPLUNK_TARGET=10.4.0 \
SPLUNK_VISUAL_SUITE=smoke \
./integration/splunk-visual/run.sh
```

Use `SPLUNK_VISUAL_SUITE=full` for every target-eligible catalog dashboard. Override
`SPLUNK_VISUAL_OUTPUT`, `SPLUNK_WEB_PORT`, or `SPLUNK_MGMT_PORT` to isolate concurrent local runs.

## Baseline policy

Baselines live under `integration/splunk-visual/baselines/<target>/`. Panel comparisons allow at
most a 0.2 percent differing-pixel ratio; full-dashboard comparisons allow 0.5 percent. The wider
full-page threshold accounts for aggregate antialiasing while panel diffs remain strict.

Normal local and CI runs set Playwright's update policy to `none`. They never rewrite a baseline.
A manual GitHub run with `update_snapshots=true` uploads candidate baseline artifacts but does not
commit them. Review candidates for valid data, title/panel presence, chart selection, clipping,
spacing, and unexpected product chrome before adding them to the repository.

The repository includes reviewed full-suite baselines generated from all four pinned images: 67
screenshots each for 9.4.3, 10.0.0, and 10.2.0, and 73 for 10.4.0. The 9.4/10.0 sets include the
app-free Splunk Health port and its eight built-in panels; the 10.2/10.4 sets include the
source-derived dashboard and its eight custom panels; 10.4 also includes the service-map
dashboard. `baselines/manifest.json` is the machine-readable inventory. A clean comparison with
snapshot updates disabled is required after any regeneration.

## CI tiers

`.github/workflows/visual-regression.yml` provides:

- `visual-smoke`: relevant pull requests and manual smoke runs; Splunk 10.4.0; the business SLO,
  service-map, source-derived Splunk Health, no-data, and error-state dashboards; 25-minute timeout.
- `visual-full`: nightly, manual full, and reusable release runs; 9.4.3, 10.0.0, 10.2.0, and
  10.4.0 matrix; all eligible dashboards plus state fixtures; 35 minutes per target.
- candidate-baseline mode: manual only; updates the working copy and uploads candidate files for
  review without pushing or committing.

The release workflow calls the full matrix before building distributions. The wheel still ships no
Node, browser, integration harness, screenshot, or Splunk artifact. The source distribution includes
only the five curated documentation images, not the integration baselines or harness.

## QA and vision artifacts

Every target artifact contains the generated definitions and XML, run manifest, exact source and
fixture search results, round-trip comparison, Playwright JSON/HTML reports, traces on failure,
ARIA snapshots, full and panel screenshots, and `qa-overview.png` plus `qa-overview.json`.

`qa/vision-prompt.md` and `qa/vision-contract.json` define a provider-neutral inspection handoff.
The allowed categories are blank, loading, search error, overlap, clipping, contrast, wrong chart,
malformed graph, whitespace, and alignment. A vision tool writes
`splunk-vision-qa-report/v1`; `npm run qa:validate-vision -- <report>` checks its structure and
returns failure only for an error that names an ID already present in
`qa-overview.json#/deterministic_failures`. Invented or stale evidence IDs are rejected.

Five reviewed full-dashboard captures are copied into the distributable documentation by
`scripts/sync_dashboard_samples.py`; see the [render gallery](gallery.md). The sample manifest
binds each public image to its target-specific baseline path and SHA-256.

No model provider, credential, or screenshot upload is configured by default. That external-data
decision must be explicit. Codex or another vision-capable reviewer can inspect the generated
overview locally or from a CI artifact and return the same report contract.

## Likely first-run adjustments

Dashboard Studio's internal DOM is not a public compatibility contract. The first authorized run
may reveal a target-specific login redirect, product-tour modal, panel container boundary, or error
wording that needs a narrow selector adjustment. Do not weaken result math or image thresholds to
hide such a mismatch. Capture the trace and screenshot, adjust the smallest affected adapter, and
regenerate only the impacted target baseline.
