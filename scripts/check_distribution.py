"""Fail if Python distributions contain Node or NPM assets."""

from __future__ import annotations

import argparse
import json
import tarfile
import zipfile
from pathlib import Path, PurePosixPath

PROHIBITED_NAMES = {"package-lock.json", "package.json"}
PROHIBITED_PARTS = {"node_modules"}
PROHIBITED_SUFFIXES = {".cjs", ".js", ".mjs"}


def artifact_members(path: Path) -> list[str]:
    if path.suffix == ".whl":
        with zipfile.ZipFile(path) as archive:
            return archive.namelist()
    if path.name.endswith((".tar.gz", ".tgz")):
        with tarfile.open(path, "r:gz") as archive:
            return archive.getnames()
    raise ValueError(f"Unsupported distribution artifact: {path}")


def prohibited_members(path: Path) -> list[str]:
    failures: list[str] = []
    for member in artifact_members(path):
        candidate = PurePosixPath(member)
        if (
            candidate.name in PROHIBITED_NAMES
            or PROHIBITED_PARTS.intersection(candidate.parts)
            or candidate.suffix in PROHIBITED_SUFFIXES
        ):
            failures.append(member)
    return sorted(failures)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("directory", nargs="?", default="dist")
    arguments = parser.parse_args()
    directory = Path(arguments.directory)
    artifacts = sorted([*directory.glob("*.whl"), *directory.glob("*.tar.gz")])
    if not artifacts:
        raise SystemExit("No distribution artifacts found")
    results = {str(path): prohibited_members(path) for path in artifacts}
    print(json.dumps(results, indent=2, sort_keys=True))
    return 1 if any(results.values()) else 0


if __name__ == "__main__":
    raise SystemExit(main())
