"""Fast native structural checks for Dashboard Studio Dynamic Options Syntax."""

from __future__ import annotations

import re
from collections.abc import Iterator
from dataclasses import dataclass

from pydantic import JsonValue

from splunk_dashboard_studio.issues import IssueOrigin, ValidationIssue

_SOURCE_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_.-]*$")
_STAGE_PATTERN = re.compile(
    r"^[A-Za-z_][A-Za-z0-9_]*(?:\s*\(.*\))?(?:\[[^\]]+\])*$",
    re.DOTALL,
)


class DosSyntaxError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class DosExpression:
    source: str
    stages: tuple[str, ...]


def _split_pipeline(value: str) -> list[str]:
    parts: list[str] = []
    current: list[str] = []
    quote: str | None = None
    escaped = False
    stack: list[str] = []
    pairs = {")": "(", "]": "[", "}": "{"}

    for character in value:
        if escaped:
            current.append(character)
            escaped = False
            continue
        if character == "\\" and quote is not None:
            current.append(character)
            escaped = True
            continue
        if quote is not None:
            current.append(character)
            if character == quote:
                quote = None
            continue
        if character in {'"', "'"}:
            current.append(character)
            quote = character
            continue
        if character in "([{":
            stack.append(character)
            current.append(character)
            continue
        if character in ")]}":
            if not stack or stack.pop() != pairs[character]:
                raise DosSyntaxError(f"Unmatched closing delimiter {character!r}")
            current.append(character)
            continue
        if character == "|" and not stack:
            parts.append("".join(current).strip())
            current = []
            continue
        current.append(character)

    if quote is not None:
        raise DosSyntaxError("Unterminated string literal")
    if stack:
        raise DosSyntaxError(f"Unclosed delimiter {stack[-1]!r}")
    parts.append("".join(current).strip())
    return parts


def parse_dos(value: str) -> DosExpression:
    stripped = value.strip()
    if not stripped.startswith(">"):
        raise DosSyntaxError("Dynamic Options Syntax must start with '>'")
    body = stripped[1:].strip()
    if not body:
        raise DosSyntaxError("Dynamic Options Syntax requires a data source")
    parts = _split_pipeline(body)
    source = parts[0]
    if not _SOURCE_PATTERN.fullmatch(source):
        raise DosSyntaxError(f"Invalid Dynamic Options Syntax data source {source!r}")
    stages = tuple(parts[1:])
    if not stages:
        raise DosSyntaxError("Dynamic Options Syntax requires at least one processing stage")
    for stage in stages:
        if not stage:
            raise DosSyntaxError("Dynamic Options Syntax contains an empty processing stage")
        if not _STAGE_PATTERN.fullmatch(stage):
            raise DosSyntaxError(f"Invalid Dynamic Options Syntax stage {stage!r}")
    return DosExpression(source=source, stages=stages)


def _pointer_escape(value: str) -> str:
    return value.replace("~", "~0").replace("/", "~1")


def iter_dos_values(value: JsonValue, path: str = "$") -> Iterator[tuple[str, str]]:
    if isinstance(value, str):
        if value.lstrip().startswith(">"):
            yield path, value
        return
    if isinstance(value, list):
        for index, child in enumerate(value):
            yield from iter_dos_values(child, f"{path}/{index}")
        return
    if isinstance(value, dict):
        for key, child in value.items():
            yield from iter_dos_values(child, f"{path}/{_pointer_escape(key)}")


def validate_dos_tree(value: JsonValue, path: str = "$") -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    for expression_path, expression in iter_dos_values(value, path):
        try:
            parse_dos(expression)
        except DosSyntaxError as error:
            issues.append(
                ValidationIssue(
                    code="invalid_dos_syntax",
                    path=expression_path,
                    message=str(error),
                    origin=IssueOrigin.DOS,
                    context={"expression": expression},
                )
            )
    return issues
