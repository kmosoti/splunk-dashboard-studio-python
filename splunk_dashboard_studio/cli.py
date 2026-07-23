"""Dependency-light command line interface."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from pydantic import ValidationError
from pydantic_core import to_jsonable_python

from splunk_dashboard_studio import __version__
from splunk_dashboard_studio.catalog import (
    build_catalog_bundle,
    build_catalog_dashboard,
    catalog_entries,
    portable_telemetry_contract,
)
from splunk_dashboard_studio.corpus import corpus_jsonl
from splunk_dashboard_studio.graph import plan_search_optimizations
from splunk_dashboard_studio.models import DashboardDefinition, unwrap_definition
from splunk_dashboard_studio.profiles import profile_manifest
from splunk_dashboard_studio.schema import (
    agent_contract_schema,
    dashboard_definition_schema,
    schema_bundle,
)
from splunk_dashboard_studio.validation import validate_dashboard


def _read_json(path: str) -> Any:
    if path == "-":
        return json.load(sys.stdin)
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _print_json(value: Any) -> None:
    value = to_jsonable_python(value, by_alias=True)
    print(json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False))


def _write_json(value: Any, output: str) -> None:
    value = to_jsonable_python(value, by_alias=True)
    rendered = json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    if output == "-":
        sys.stdout.write(rendered)
    else:
        Path(output).write_text(rendered, encoding="utf-8")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="splunk-studio",
        description="Generate and validate Splunk Enterprise Dashboard Studio definitions.",
    )
    parser.add_argument("--version", action="version", version=__version__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate = subparsers.add_parser("validate", help="Validate a dashboard JSON definition")
    validate.add_argument("path", nargs="?", default="-", help="JSON path or '-' for stdin")
    validate.add_argument(
        "--target",
        required=True,
        help="Exact Enterprise version, for example 9.4.3",
    )
    validate.add_argument("--strict-warnings", action="store_true")

    schema = subparsers.add_parser("schema", help="Emit an agent-facing JSON Schema")
    schema.add_argument(
        "kind",
        choices=("agent", "bundle", "dashboard", "profiles"),
        default="agent",
        nargs="?",
    )

    corpus = subparsers.add_parser("corpus", help="Generate the deterministic CI corpus as JSONL")
    corpus.add_argument("--target", required=True)
    corpus.add_argument("--output", default="-", help="Output path or '-' for stdout")

    optimize = subparsers.add_parser("optimize", help="Analyze base/chain search opportunities")
    optimize.add_argument("path", nargs="?", default="-", help="JSON path or '-' for stdin")

    catalog = subparsers.add_parser("catalog", help="Inspect or build packaged dashboards")
    catalog_commands = catalog.add_subparsers(dest="catalog_command", required=True)
    catalog_commands.add_parser("list", help="List catalog metadata and telemetry contract")
    catalog_build = catalog_commands.add_parser("build", help="Build a catalog artifact")
    catalog_build.add_argument("example_id")
    catalog_build.add_argument("--target", required=True)
    catalog_build.add_argument(
        "--artifact",
        choices=("definition", "bundle"),
        default="definition",
    )
    catalog_build.add_argument("--output", default="-", help="Output path or '-' for stdout")
    return parser


def main(argv: list[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    try:
        if arguments.command == "validate":
            report = validate_dashboard(
                _read_json(arguments.path),
                target=arguments.target,
                strict_warnings=arguments.strict_warnings,
            )
            _print_json(report)
            return 0 if report.is_valid else 1
        if arguments.command == "schema":
            if arguments.kind == "dashboard":
                _print_json(dashboard_definition_schema())
            elif arguments.kind == "bundle":
                _print_json(schema_bundle())
            elif arguments.kind == "profiles":
                _print_json(profile_manifest())
            else:
                _print_json(agent_contract_schema())
            return 0
        if arguments.command == "corpus":
            output = corpus_jsonl(arguments.target)
            if arguments.output == "-":
                sys.stdout.write(output)
            else:
                Path(arguments.output).write_text(output, encoding="utf-8")
            return 0
        if arguments.command == "optimize":
            payload = unwrap_definition(_read_json(arguments.path))
            definition = DashboardDefinition.model_validate(payload)
            _print_json(plan_search_optimizations(definition.data_sources))
            return 0
        if arguments.command == "catalog":
            if arguments.catalog_command == "list":
                _print_json(
                    {
                        "schema_version": "dashboard-catalog/v1",
                        "telemetry_contract": portable_telemetry_contract(),
                        "entries": catalog_entries(),
                    }
                )
                return 0
            artifact = (
                build_catalog_dashboard(arguments.example_id, arguments.target)
                if arguments.artifact == "definition"
                else build_catalog_bundle(arguments.example_id, arguments.target)
            )
            _write_json(artifact, arguments.output)
            return 0
    except (OSError, ValueError, ValidationError, json.JSONDecodeError) as error:
        _print_json({"status": "error", "message": str(error), "error_type": type(error).__name__})
        return 2
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
