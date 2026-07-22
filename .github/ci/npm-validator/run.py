#!/usr/bin/env python3
"""Run a corpus through one locked Splunk NPM engine and compare expectations."""

from __future__ import annotations

import argparse
import json
import subprocess
import tempfile
from pathlib import Path
from typing import Any


def _run(command: list[str], *, input_text: str | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        input=input_text,
        text=True,
        capture_output=True,
        check=False,
        timeout=180,
    )


def _load_cases(path: Path) -> list[dict[str, Any]]:
    cases = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
    return [case for case in cases if case["expected_npm"] != "skip"]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--engine-dir", type=Path, required=True)
    parser.add_argument("--corpus", type=Path, required=True)
    parser.add_argument(
        "--schema-output",
        type=Path,
        help="Keep the generated official schema at this path instead of a temporary file",
    )
    arguments = parser.parse_args()

    harness = Path(__file__).resolve().parent
    engine = arguments.engine_dir.resolve()
    cases = _load_cases(arguments.corpus)
    temporary_directory: tempfile.TemporaryDirectory[str] | None = None
    if arguments.schema_output is None:
        temporary_directory = tempfile.TemporaryDirectory(prefix="splunk-dashboard-schema-")
        schema = Path(temporary_directory.name) / "schema.json"
    else:
        schema = arguments.schema_output.resolve()
        schema.parent.mkdir(parents=True, exist_ok=True)
    try:
        built = _run(["node", str(harness / "build-schema.cjs"), str(engine), str(schema)])
        if built.returncode:
            print(
                json.dumps(
                    {
                        "status": "error",
                        "phase": "schema",
                        "stdout": built.stdout,
                        "stderr": built.stderr,
                    },
                    indent=2,
                    sort_keys=True,
                )
            )
            return 2

        request = "".join(
            json.dumps(case, sort_keys=True, separators=(",", ":")) + "\n" for case in cases
        )
        completed = _run(
            ["node", str(harness / "validate.cjs"), str(engine), str(schema)],
            input_text=request,
        )
        if completed.returncode not in {0, 1}:
            print(
                json.dumps(
                    {
                        "status": "error",
                        "phase": "validation",
                        "stdout": completed.stdout,
                        "stderr": completed.stderr,
                    },
                    indent=2,
                    sort_keys=True,
                )
            )
            return 2
    finally:
        if temporary_directory is not None:
            temporary_directory.cleanup()

    results = [json.loads(line) for line in completed.stdout.splitlines() if line]
    by_case = {result.get("caseId"): result for result in results}
    failures: list[dict[str, Any]] = []
    for case in cases:
        result = by_case.get(case["case_id"])
        if result is None:
            failures.append({"case_id": case["case_id"], "reason": "missing result"})
        elif result["status"] != case["expected_npm"]:
            failures.append(
                {
                    "case_id": case["case_id"],
                    "expected": case["expected_npm"],
                    "actual": result["status"],
                    "issues": result.get("issues", []),
                }
            )

    summary = {
        "status": "invalid" if failures else "valid",
        "engine": results[0].get("engine") if results else None,
        "checked": len(cases),
        "failures": failures,
        "schema": str(schema) if arguments.schema_output is not None else None,
    }
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
