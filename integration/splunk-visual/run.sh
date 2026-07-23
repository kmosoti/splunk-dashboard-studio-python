#!/usr/bin/env bash
set -euo pipefail

integration_root="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "${integration_root}/../.." && pwd)"
target="${SPLUNK_TARGET:-10.4.0}"
suite="${SPLUNK_VISUAL_SUITE:-smoke}"
output="${SPLUNK_VISUAL_OUTPUT:-${integration_root}/artifacts/run-${target}}"
manifest="${output}/run-manifest.json"
python_runner=(uv run --frozen --no-dev python)

cd "${repo_root}"
export SPLUNK_IMAGE
SPLUNK_IMAGE="$("${python_runner[@]}" "${integration_root}/scripts/harness.py" image --target "${target}" --field image)"
export SPLUNK_START_ARGS="--accept-license"
requires_general_terms="$("${python_runner[@]}" "${integration_root}/scripts/harness.py" image --target "${target}" --field requires_general_terms)"
if [[ "${requires_general_terms}" == "true" ]]; then
  export SPLUNK_GENERAL_TERMS="--accept-sgt-current-at-splunk-com"
else
  export SPLUNK_GENERAL_TERMS=""
fi
export SPLUNK_PASSWORD="${SPLUNK_PASSWORD:-Visual-QA-Only-1234!}"
export SPLUNK_TARGET_SLUG="${target//./-}"
export SPLUNK_WEB_URL="${SPLUNK_WEB_URL:-http://127.0.0.1:${SPLUNK_WEB_PORT:-8000}}"
export SPLUNK_MGMT_URL="${SPLUNK_MGMT_URL:-https://127.0.0.1:${SPLUNK_MGMT_PORT:-8089}}"
export SPLUNK_VISUAL_MANIFEST="${manifest}"
export SPLUNK_VISUAL_TARGET="${target}"
export SPLUNK_VISUAL_ARTIFACTS="${SPLUNK_VISUAL_ARTIFACTS:-${output}}"

compose=(docker compose --project-directory "${integration_root}" -f "${integration_root}/compose.yaml")

cleanup() {
  local status=$?
  if [[ "${status}" -ne 0 ]]; then
    mkdir -p "${output}"
    "${compose[@]}" logs --no-color >"${output}/splunk-compose.log" 2>&1 || true
    if find "${output}/screenshots" -name '*.png' -print -quit 2>/dev/null | grep -q .; then
      (cd "${integration_root}" && npm run qa:overview) || true
    fi
  fi
  "${python_runner[@]}" "${integration_root}/scripts/harness.py" cleanup --manifest "${manifest}" >/dev/null 2>&1 || true
  if [[ -d "${output}/apps/splunk_health" ]]; then
    "${compose[@]}" exec -T -u 0 splunk \
      chown -R "$(id -u):$(id -g)" /opt/splunk/etc/apps/splunk_health >/dev/null 2>&1 || true
  fi
  "${compose[@]}" down --volumes --remove-orphans >/dev/null 2>&1 || true
  return "${status}"
}
trap cleanup EXIT

"${python_runner[@]}" "${integration_root}/scripts/harness.py" prepare \
  --target "${target}" \
  --suite "${suite}" \
  --include-state-cases \
  --output "${output}"

if [[ -d "${output}/apps/splunk_health" ]]; then
  export SPLUNK_HEALTH_APP_PATH="${output}/apps/splunk_health"
  compose+=( -f "${integration_root}/compose.source-template.yaml" )
fi

"${compose[@]}" up --detach --wait --wait-timeout 900
"${python_runner[@]}" "${integration_root}/scripts/harness.py" wait --startup-timeout 900
"${python_runner[@]}" "${integration_root}/scripts/harness.py" provision-indexes --manifest "${manifest}"
"${python_runner[@]}" "${integration_root}/scripts/harness.py" validate-searches --manifest "${manifest}" --kind source
"${python_runner[@]}" "${integration_root}/scripts/harness.py" publish --manifest "${manifest}"
"${python_runner[@]}" "${integration_root}/scripts/harness.py" validate-searches --manifest "${manifest}" --kind fixture

cd "${integration_root}"
npm test
npm run qa:overview
