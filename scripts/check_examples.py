"""Generate or verify checked catalog examples at each minimum supported target."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from splunk_dashboard_studio.catalog import build_catalog_bundle, catalog_entries
from splunk_dashboard_studio.contracts import CatalogEntry
from splunk_dashboard_studio.generation import canonical_json

ROOT = Path(__file__).resolve().parents[1]
CATALOG_ROOT = ROOT / "examples" / "catalog"


def _json(value: object) -> str:
    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="json", by_alias=True)
    return json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def _builder(example_id: str, target: str) -> str:
    encoded_id = json.dumps(example_id)
    encoded_target = json.dumps(target)
    return f'''"""Build the checked {example_id} catalog dashboard."""

from splunk_dashboard_studio import build_catalog_dashboard, canonical_json

EXAMPLE_ID = {encoded_id}
TARGET = {encoded_target}


def main() -> None:
    print(canonical_json(build_catalog_dashboard(EXAMPLE_ID, TARGET), indent=2))


if __name__ == "__main__":
    main()
'''


def _readme(entry: CatalogEntry) -> str:
    example_id = entry.example_id
    title = entry.title
    target = str(entry.minimum_target)
    frameworks = ", ".join(framework.value for framework in entry.frameworks)
    signals = ", ".join(signal.value for signal in entry.signals)
    indexes = ", ".join(f"`{index}`" for index in entry.logical_indexes)
    panels = "\n".join(f"- `{panel.panel_id}` — {panel.purpose}" for panel in entry.panels)
    return f"""# {title}

- Catalog ID: `{example_id}`
- Priority: `{entry.priority}`
- Checked target: Splunk Enterprise `{target}`
- Telemetry contract: `{entry.telemetry_contract}`

This generated example applies {frameworks} to {signals} telemetry. It assumes the logical
indexes {indexes}; map those names and the required semantic fields to your local Splunk app
before deployment. It does not create saved searches, publish a view, or include sample data.

## Panels

{panels}

## Rebuild

```console
uv run python examples/catalog/{example_id}/builder.py
uv run splunk-studio catalog build {example_id} --target {target} --artifact bundle
```

`dashboard.json` is the canonical minimum-target definition. `manifest.json` records its hash,
native validation status, validator evidence grade, provenance, and deferred live-test caveat.
"""


def expected_files() -> dict[Path, str]:
    expected: dict[Path, str] = {}
    for entry in catalog_entries():
        target = str(entry.minimum_target)
        bundle = build_catalog_bundle(entry.example_id, target)
        directory = CATALOG_ROOT / entry.example_id
        expected[directory / "builder.py"] = _builder(entry.example_id, target)
        expected[directory / "dashboard.json"] = (
            canonical_json(
                bundle.definition,
                indent=2,
            )
            + "\n"
        )
        expected[directory / "manifest.json"] = _json(bundle.manifest)
        expected[directory / "README.md"] = _readme(entry)
    return expected


def check_examples(*, write: bool) -> list[dict[str, str]]:
    failures: list[dict[str, str]] = []
    expected = expected_files()
    for path, content in sorted(expected.items()):
        relative = str(path.relative_to(ROOT))
        if write:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
            continue
        if not path.exists():
            failures.append({"path": relative, "reason": "missing"})
        elif path.read_text(encoding="utf-8") != content:
            failures.append({"path": relative, "reason": "drifted"})

    if CATALOG_ROOT.exists():
        allowed = set(expected)
        for path in sorted(
            candidate
            for candidate in CATALOG_ROOT.rglob("*")
            if candidate.is_file()
            and "__pycache__" not in candidate.parts
            and candidate.suffix != ".pyc"
        ):
            if path not in allowed:
                failures.append(
                    {"path": str(path.relative_to(ROOT)), "reason": "unexpected generated file"}
                )
    return failures


def main() -> int:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true", help="Verify generated examples")
    mode.add_argument("--write", action="store_true", help="Regenerate examples")
    arguments = parser.parse_args()
    failures = check_examples(write=arguments.write)
    print(
        json.dumps(
            {
                "mode": "write" if arguments.write else "check",
                "dashboards": len(catalog_entries()),
                "failures": failures,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
