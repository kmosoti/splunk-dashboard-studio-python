"""Check profile metadata against every isolated CI-only NPM engine lock."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from splunk_dashboard_studio.profiles import available_profiles

ROOT = Path(__file__).resolve().parents[1]
ENGINES = ROOT / ".github" / "ci" / "npm-validator" / "engines"


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected a JSON object in {path}")
    return value


def check_engine_locks() -> list[dict[str, str]]:
    failures: list[dict[str, str]] = []
    expected_engines = {
        profile.engine.engine_id: profile.engine for profile in available_profiles()
    }
    actual_directories = {path.name for path in ENGINES.iterdir() if path.is_dir()}

    for extra in sorted(actual_directories - set(expected_engines)):
        failures.append({"engine": extra, "field": "directory", "message": "unprofiled lock"})
    for missing in sorted(set(expected_engines) - actual_directories):
        failures.append({"engine": missing, "field": "directory", "message": "missing lock"})

    for engine_id, engine in sorted(expected_engines.items()):
        directory = ENGINES / engine_id
        if not directory.is_dir():
            continue
        package = _load(directory / "package.json")
        lock = _load(directory / "package-lock.json")
        expected = {
            "@splunk/dashboard-definition": engine.dashboard_version,
            "@splunk/dashboard-presets": engine.dashboard_version,
            "@splunk/dashboard-validation": engine.dashboard_version,
            "@splunk/visualization-encoding": engine.visualization_encoding_version,
        }
        dependencies = package.get("dependencies")
        lock_packages = lock.get("packages")
        if package.get("private") is not True:
            failures.append({"engine": engine_id, "field": "private", "message": "must be true"})
        if not isinstance(dependencies, dict):
            failures.append(
                {"engine": engine_id, "field": "dependencies", "message": "must be an object"}
            )
            continue
        if not isinstance(lock_packages, dict):
            failures.append(
                {"engine": engine_id, "field": "packages", "message": "must be an object"}
            )
            continue
        root_lock = lock_packages.get("")
        root_dependencies = root_lock.get("dependencies") if isinstance(root_lock, dict) else None
        for dependency, version in expected.items():
            if dependencies.get(dependency) != version:
                failures.append(
                    {
                        "engine": engine_id,
                        "field": f"package.json:{dependency}",
                        "message": f"expected exact version {version!r}",
                    }
                )
            if (
                not isinstance(root_dependencies, dict)
                or root_dependencies.get(dependency) != version
            ):
                failures.append(
                    {
                        "engine": engine_id,
                        "field": f"package-lock.json:root:{dependency}",
                        "message": f"expected exact version {version!r}",
                    }
                )
            locked = lock_packages.get(f"node_modules/{dependency}")
            locked_version = locked.get("version") if isinstance(locked, dict) else None
            if locked_version != version:
                failures.append(
                    {
                        "engine": engine_id,
                        "field": f"package-lock.json:{dependency}",
                        "message": f"expected resolved version {version!r}",
                    }
                )
    return failures


def main() -> int:
    failures = check_engine_locks()
    print(
        json.dumps(
            {
                "checked": len({profile.engine.engine_id for profile in available_profiles()}),
                "failures": failures,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
