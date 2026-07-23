# Disposable Splunk visual regression

This integration-only harness starts one pinned Splunk Enterprise standalone in Free mode,
publishes test-only Dashboard Studio views, checks their search results and REST readback, renders
them in Chromium, and creates screenshot and vision-QA artifacts. It does not test authentication,
roles, ACLs, or production publication.

On Splunk 10.2/10.4, the suite also installs a disposable copy of the pinned Apache-2.0 Splunk
Health app from `rcastley/splunk-custom-visualizations`. Its dashboard structure and fixture rows
come from the upstream source definition and eight `harness.json` contracts. The source lock and
vendored snapshot live under this integration tree and never ship in Python artifacts.

Do not start the container until you have read and accepted the applicable
[Splunk General Terms](https://www.splunk.com/en_us/legal/splunk-general-terms.html). The official
image requires explicit license acceptance, and 10.x also requires the current-general-terms flag.
Invoking `run.sh` passes `--accept-license` automatically and adds
`--accept-sgt-current-at-splunk-com` for targets marked as requiring it in `images.json`. There is
no interactive prompt or separate environment-variable gate.

## One-time setup

From this directory:

```console
npm ci
npm exec -- playwright install chromium
```

The repository root must also have its locked Python environment available with
`uv sync --frozen --no-dev`.

## Run and update baselines

Reviewed full-suite baselines for every pinned target are included. Run a normal hard comparison
without setting `SPLUNK_UPDATE_SNAPSHOTS`:

```console
SPLUNK_TARGET=10.4.0 \
SPLUNK_VISUAL_SUITE=smoke \
./integration/splunk-visual/run.sh
```

To intentionally generate candidate screenshots from the exact pinned image:

```console
SPLUNK_TARGET=10.4.0 \
SPLUNK_VISUAL_SUITE=smoke \
SPLUNK_UPDATE_SNAPSHOTS=1 \
./integration/splunk-visual/run.sh
```

Review the images under `baselines/10.4.0/` and the generated `qa-overview.png`, then rerun with
snapshot updates disabled before committing a baseline. Missing or changed baselines fail normal
local and CI runs.

`run.sh` binds ports 8000 and 8089 to `127.0.0.1`, uses a throwaway local password, removes all
test views, stops the container, and deletes its volume on exit. Override ports with
`SPLUNK_WEB_PORT` and `SPLUNK_MGMT_PORT` when they are already occupied. `defaults.yml` enables
Free-mode remote management for these localhost-only REST checks; it is not a production setting.

See [the full workflow documentation](../../docs/visual-regression.md) for fixture semantics, CI
configuration, artifacts, and the advisory vision contract.
